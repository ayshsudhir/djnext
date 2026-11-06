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
    }


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
    pools, _ = service.mood_pools(_lib(), cfg)
    ms = cfg.moods()
    return {"moods": [{"key": k, "label": ms[k].label, "emoji": ms[k].emoji, "name": ms[k].name, "ask": ms[k].ask,
                       "count": len(items), "examples": [t.title for t, _ in items[:4]]}
                      for k, items in pools.items()]}


@app.post("/api/moods/push")
def moods_push():
    from ..export.rekordbox_playlist import RekordboxRunning, write_to_rekordbox

    cfg = service.config()
    pools, _ = service.mood_pools(_lib(), cfg)
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
                               source=body.source or ("soundcloud" if body.mood else None),
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


@app.post("/api/settings")
def settings(body: StyleIn):
    if body.bpm_min >= body.bpm_max:
        raise HTTPException(400, "Lowest BPM must be below highest BPM.")
    service.save_settings({"skill": body.skill if body.skill in ("beginner", "advanced") else "beginner", "style": {
        "bpm_min": body.bpm_min, "bpm_max": body.bpm_max,
        "favourite_artists": [a.strip() for a in body.favourite_artists if a.strip()],
        "exclude_genres": [g.strip().lower() for g in body.exclude_genres if g.strip()],
    }})
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


def run(port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://127.0.0.1:{port}"
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"djnext is running at {url}  (keep this window open; close it to stop)")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
