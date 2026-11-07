"""djnext in the browser: runs only on your own computer (http://127.0.0.1:8765)."""
from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import feedback as fb
from .. import service
from ..ingest import soundcloud as sc

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="djnext")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

STATE: dict = {"lib": None, "attach": None, "set": None}


def _lib(reload: bool = False):
    if STATE["lib"] is None or reload:
        try:
            STATE["lib"], STATE["attach"] = service.load_library()
        except FileNotFoundError as e:
            raise HTTPException(404, f"Couldn't find your rekordbox library ({e}). Is rekordbox installed?")
    return STATE["lib"]


def _running() -> bool:
    from ..export.rekordbox_playlist import rekordbox_running

    try:
        return rekordbox_running()
    except Exception:
        return False


def _mood_source():
    """Moods pick from your SoundCloud tracks once SoundCloud is synced, otherwise from the whole collection."""
    return "soundcloud" if sc.load() else None


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.get("/api/status")
def status():
    from collections import Counter

    lib = _lib()
    cfg = service.config()
    data = sc.load()
    lists = []
    if data:
        res = sc.attach(lib, data)
        names = {"likes": data.get("likes", []), **data.get("playlists", {})}
        lists = [{"key": f"sc:{n}", "name": n, "total": len(e), "ready": res.playlists.get(f"sc:{n}", 0)}
                 for n, e in names.items()]
    rb_lists = [{"key": k, "name": k, "total": len(v), "ready": len(v)}
                for k, v in lib.playlists.items() if not k.startswith("sc:") and v]
    return {
        "library": {"total": len(lib.tracks), "by_source": Counter(t.source or "local" for t in lib.tracks.values())},
        "rekordbox_running": _running(),
        "soundcloud": {"user": data["user"], "synced_at": data["synced_at"]} if data else None,
        "soundcloud_lists": lists, "rekordbox_lists": rb_lists,
        "not_analysed": len(sc.attach(lib, data).not_analysed) if data else 0,
        "curves": list(cfg.curves), "default_curve": cfg.default_curve,
        "style": cfg.style.__dict__, "skill": cfg.skill,
        "has_set": STATE["set"] is not None,
        "onboarded": bool(service.read_settings().get("onboarded") or data),
    }


@app.get("/api/rekordbox")
def rekordbox_state():
    """Cheap check the page polls, so it can say whether rekordbox is open."""
    return {"running": _running()}


class SyncIn(BaseModel):
    user: str


@app.post("/api/soundcloud/sync")
def soundcloud_sync(body: SyncIn):
    user = body.user.strip().rstrip("/").split("soundcloud.com/")[-1].split("/")[0]
    if not user:
        raise HTTPException(400, "Enter your SoundCloud username or profile link.")
    try:
        data = sc.fetch(user, log=lambda *_: None)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read SoundCloud for '{user}': {e}")
    sc.save(data)
    _lib(reload=True)
    return status()


@app.get("/api/soundcloud/missing")
def soundcloud_missing():
    data = sc.load()
    if not data:
        return {"tracks": []}
    res = sc.attach(_lib(), data)
    return {"tracks": [{"label": sc.label(e), "url": e.get("url", "")} for e in res.not_analysed]}


@app.post("/api/reload")
def reload():
    _lib(reload=True)
    return status()


@app.get("/api/moods")
def moods():
    cfg = service.config()
    pools, _ = service.mood_pools(_lib(), cfg, source=_mood_source())
    ms = cfg.moods()
    return {"moods": [{"key": k, "label": ms[k].label, "emoji": ms[k].emoji, "name": ms[k].name, "ask": ms[k].ask,
                       "count": len(items), "examples": [t.title for t, _ in items[:4]]}
                      for k, items in pools.items()]}


@app.post("/api/moods/push")
def moods_push():
    from ..export.rekordbox_playlist import RekordboxRunning, write_to_rekordbox

    cfg = service.config()
    pools, _ = service.mood_pools(_lib(), cfg, source=_mood_source())
    ms = cfg.moods()
    try:
        out = write_to_rekordbox(mood_playlists={ms[k].label: [t.id for t, _ in v] for k, v in pools.items()})
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit rekordbox first, then press the button again.")
    return {"folder": out["moods_folder"], "playlists": out["mood_playlists"], "backup": str(out["backup"])}


@app.get("/api/discover")
def discover_saved():
    from ..ingest import discover as dc

    return dc.load() or {"tracks": []}


@app.post("/api/discover")
def discover_run():
    from ..ingest import discover as dc

    data = sc.load()
    if not data:
        raise HTTPException(400, "Sync your SoundCloud first (My music tab).")
    cands = dc.discover(_lib(), service.config(), data, log=lambda *_: None)
    dc.save(cands)
    return dc.load()


class SetIn(BaseModel):
    mood: Optional[str] = None
    lists: List[str] = []
    source: Optional[str] = "soundcloud"
    length: float = 60
    curve: Optional[str] = None
    use_style: bool = True


@app.post("/api/set")
def make_set(body: SetIn):
    lib = _lib()
    cfg = service.config()
    try:
        res = service.make_set(lib, cfg, lists=(body.lists or None) if not body.mood else None,
                               source=_mood_source() if body.mood else body.source,
                               length_min=body.length, curve=None if body.mood else body.curve,
                               use_style=body.use_style, mood=body.mood)
    except (ValueError, KeyError) as e:
        raise HTTPException(400, str(e.args[0] if e.args else e))
    STATE["set"] = res
    STATE["set_label"] = cfg.moods()[body.mood].label if body.mood else None
    return service.set_to_json(res, cfg)


class PushIn(BaseModel):
    name: Optional[str] = None
    cues: bool = True


@app.post("/api/push")
def push(body: PushIn):
    from ..export.rekordbox_cues import plan_cues
    from ..export.rekordbox_playlist import RekordboxRunning, write_to_rekordbox

    res = STATE["set"]
    if res is None:
        raise HTTPException(400, "Make a set first.")
    cfg = service.config()
    tracks = res.plan.tracks
    try:
        out = write_to_rekordbox(content_ids=[t.id for t in tracks],
                                 name=body.name or service.default_set_name(STATE.get("set_label") or res.plan.curve.name),
                                 cues=plan_cues(tracks, cfg) if body.cues else None,
                                 remove_own_cues=body.cues)  # old djnext cues from earlier sets go first
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit rekordbox (Cmd+Q on Mac, or close it on Windows), then press the button again.")
    return {"name": out["name"], "folder": out["folder"], "tracks": out["tracks"],
            "cues": len(out.get("cues_written") or []), "cues_skipped": len(out.get("cues_skipped") or []),
            "backup": str(out["backup"])}


class Rating(BaseModel):
    position: int  # 2 = transition from track 1 into track 2
    good: bool
    note: str = ""


class RateIn(BaseModel):
    ratings: List[Rating]
    overall: int = 0
    overall_note: str = ""


@app.post("/api/rate")
def rate(body: RateIn):
    res = STATE["set"]
    if res is None:
        raise HTTPException(400, "Make (and mix) a set first.")
    cfg = service.config()
    infos = {t.position: t for t in fb.describe(res.plan.tracks, cfg)}
    conn = fb.connect()
    name = f"{res.set_file.name} (web {service.default_set_name(res.plan.curve.name)})"
    saved = 0
    for r in body.ratings:
        if r.position in infos:
            fb.save_transition(conn, name, infos[r.position], good=r.good, note=r.note.strip())
            saved += 1
    if 1 <= body.overall <= 5:
        fb.save_set(conn, name, body.overall, body.overall_note.strip())
    return {"saved": saved}


@app.get("/api/feedback")
def feedback():
    if not fb.DEFAULT_DB.exists():
        return {"rated": 0}
    s = fb.summary(fb.connect())
    return {"rated": s["rated"], "good": s["good"], "groups": s["groups"], "bad": s["bad"][-15:],
            "sets": [list(x) for x in s["sets"]]}


class StyleIn(BaseModel):
    skill: str = "beginner"
    bpm_min: float
    bpm_max: float
    favourite_artists: List[str] = []
    exclude_genres: List[str] = []
    onboarded: Optional[bool] = None


@app.post("/api/settings")
def settings(body: StyleIn):
    if body.bpm_min >= body.bpm_max:
        raise HTTPException(400, "Lowest BPM must be below highest BPM.")
    service.save_settings({"skill": body.skill if body.skill in ("beginner", "advanced") else "beginner", "style": {
        "bpm_min": body.bpm_min, "bpm_max": body.bpm_max,
        "favourite_artists": [a.strip() for a in body.favourite_artists if a.strip()],
        "exclude_genres": [g.strip().lower() for g in body.exclude_genres if g.strip()],
    }, **({"onboarded": body.onboarded} if body.onboarded is not None else {})})
    return status()


@app.get("/api/backups")
def backups():
    from ..export.rekordbox_playlist import list_backups

    return {"backups": [b.name for b in list_backups()[:10]]}


@app.post("/api/undo")
def undo():
    from ..export.rekordbox_playlist import RekordboxRunning, list_backups, restore

    bs = list_backups()
    if not bs:
        raise HTTPException(400, "Nothing to undo: djnext hasn't changed your rekordbox library yet.")
    try:
        restore(bs[0])
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit it first, then press Undo again.")
    _lib(reload=True)
    return {"restored": bs[0].name}


@app.post("/api/cues/remove")
def remove_cues():
    from ..export.rekordbox_playlist import RekordboxRunning, write_to_rekordbox

    try:
        out = write_to_rekordbox(remove_own_cues=True)
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit it first.")
    return {"removed": out["removed_cues"], "backup": str(out["backup"])}


# ---------- live mode ----------

LIVE_DIR = Path("data/live")


@app.get("/live")
def live_page():
    return FileResponse(str(STATIC / "live.html"))


def _live() -> dict:
    """Tracks to pick from while playing (your style; SoundCloud tracks once synced) + crowd-pleaser scores."""
    from ..core.energy import spread_guessed

    lv = STATE.get("live")
    if lv is None or lv.get("lib") is not _lib():
        cfg = service.config()
        lib = _lib()
        pool, _ = service.pool_from(lib, None, _mood_source(), cfg.style)
        service.with_structure(pool)
        spread_guessed(pool)
        pools, _ = service.mood_pools(lib, cfg, source=_mood_source())
        pleasers = {t.id: score for t, score in pools.get("drunk", [])}
        lv = STATE["live"] = {"lib": lib, "pool": pool, "pleasers": pleasers, "current": None, "played": [],
                              "crowd": 3, "session": None}
    return lv


def _track_json(t) -> dict:
    return {"id": t.id, "title": t.title, "artist": t.artist, "bpm": round(t.bpm, 1), "key": t.key or "?",
            "energy": round(t.energy if t.energy is not None else 5.0, 1), "genre": t.genre}


def _session(lv: dict):
    from ..core.live import Session

    if lv["session"] is None:
        lv["session"] = Session()
    return lv["session"]


def _memory():
    """What all your saved live sets taught (re-read each time, so the set you're playing counts too)."""
    from ..core.live import Session, learn

    sessions = []
    for path in sorted(LIVE_DIR.glob("*.json")) if LIVE_DIR.exists() else []:
        try:
            sessions.append(Session.load(path))
        except Exception:
            continue  # a damaged file shouldn't stop the app
    return learn(sessions)


@app.get("/api/live/learned")
def live_learned():
    mem = _memory()
    lib = _lib()
    name = lambda i: lib.tracks[i].label if i in lib.tracks else i  # noqa: E731
    ranked = sorted(((mem._shrunk(v), k) for k, v in mem.track.items()), reverse=True)
    rescue = sorted(((mem._shrunk(v), k) for k, v in mem.rescue.items() if mem._shrunk(v) > 0), reverse=True)
    return {"sets": mem.sets, "tracks": len(mem.track), "transitions": len(mem.pair),
            "best": [name(k) for s, k in ranked if s > 0][:5],
            "worst": [name(k) for s, k in reversed(ranked) if s < 0][:5],
            "rescue": [name(k) for _, k in rescue][:5]}


@app.get("/api/live/state")
def live_state():
    lv = _live()
    return {"current": _track_json(lv["current"]) if lv["current"] else None, "crowd": lv["crowd"],
            "played": len(lv["played"]), "session": lv["session"].started if lv["session"] else None,
            "tracks": len(lv["pool"])}


@app.get("/api/live/search")
def live_search(q: str = ""):
    words = q.lower().split()
    if not words:
        return {"tracks": []}
    hits = [t for t in _live()["pool"] if all(w in t.label.lower() for w in words)]
    return {"tracks": [_track_json(t) for t in hits[:8]]}


class NowIn(BaseModel):
    track_id: str


@app.post("/api/live/now")
def live_now(body: NowIn):
    lv = _live()
    t = next((x for x in lv["pool"] if x.id == body.track_id), None) or _lib().tracks.get(body.track_id)
    if t is None:
        raise HTTPException(404, "That track isn't in your library any more. Try Reload library.")
    service.with_structure([t])
    if lv["current"] is not None and lv["current"].id != t.id:
        lv["played"].append(lv["current"])
    lv["current"] = t
    sess = _session(lv)
    sess.log("track", t)
    sess.save(LIVE_DIR)
    return live_state()


class CrowdIn(BaseModel):
    level: int


@app.post("/api/live/crowd")
def live_crowd(body: CrowdIn):
    lv = _live()
    lv["crowd"] = max(1, min(5, body.level))
    sess = _session(lv)
    sess.log("crowd", crowd=lv["crowd"])
    sess.save(LIVE_DIR)
    return live_state()


@app.get("/api/live/suggest")
def live_suggest():
    from ..core.live import CROWD, suggest
    from ..core.mix_advice import advise

    lv = _live()
    c = CROWD[lv["crowd"]]
    head = {"crowd": lv["crowd"], "emoji": c.emoji, "name": c.name, "need": c.need, "tip": c.tip}
    if lv["current"] is None:
        return {**head, "picks": []}
    cfg = service.config()
    memory = _memory()
    picks = suggest(lv["current"], lv["pool"], lv["crowd"], cfg, lv["played"], lv["pleasers"], memory=memory)
    service.with_structure([p.track for p in picks])
    out = []
    for p in picks:
        adv = advise(lv["current"], p.track, cfg, lv["pool"])
        out.append({**_track_json(p.track), "why": p.why, "delta": round(p.energy_delta, 1),
                    "pleaser": lv["pleasers"].get(p.track.id, 0) >= 0.5,
                    "learned": memory.note(lv["current"].id, p.track.id),
                    "technique": adv.title, "technique_id": adv.technique, "steps": adv.steps,
                    "timing": adv.timing})
    return {**head, "picks": out}


@app.get("/api/live/review")
def live_review(session: Optional[str] = None):
    from ..core.live import Session, review

    if session:
        path = LIVE_DIR / f"{session.replace(':', '-')}.json"
        if not path.exists():
            raise HTTPException(404, "No such session.")
        sess = Session.load(path)
    else:
        sess = _live()["session"]
        if sess is None:
            past = sorted(LIVE_DIR.glob("*.json")) if LIVE_DIR.exists() else []
            if not past:
                raise HTTPException(400, "No live set yet. Pick what's playing and set the crowd knob to start one.")
            sess = Session.load(past[-1])
    return review(sess)


@app.get("/api/live/sessions")
def live_sessions():
    past = sorted(LIVE_DIR.glob("*.json"), reverse=True) if LIVE_DIR.exists() else []
    return {"sessions": [p.stem for p in past[:30]]}


@app.post("/api/live/end")
def live_end():
    lv = _live()
    sess = lv["session"]
    lv.update(current=None, played=[], crowd=3, session=None)
    if sess is None or not sess.events:
        raise HTTPException(400, "Nothing to review yet.")
    from ..core.live import review

    return review(sess)


def run(port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    import socket

    url = f"http://127.0.0.1:{port}"
    with socket.socket() as probe:  # already running (double-clicked twice)? just open the page again
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            print(f"djnext is already running at {url}, opening it in your browser.")
            if open_browser:
                webbrowser.open(url)
            return
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"djnext is running at {url}  (keep this window open; close it to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
