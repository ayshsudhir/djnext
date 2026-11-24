"""djnext's one screen: runs only on your own computer."""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import service
from ..core import genres, names, picker
from ..core.structure import fmt
from ..ingest import mixesdb
from ..ingest import soundcloud as sc

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="djnext")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

STATE: dict = {"lib": None, "pool": None, "counts": None, "ev": None, "verdicts": None, "playlist": None,
               "genre": None}
LOOKUP: dict = {"running": False, "done": 0, "total": 0, "current": "", "error": ""}
_lock = threading.Lock()


@app.exception_handler(Exception)
async def _unexpected(request, exc):
    import logging
    import traceback

    from fastapi.responses import JSONResponse

    traceback.print_exc()
    logging.getLogger("djnext").error("Error in %s: %r", request.url.path, exc)
    msg = (f"djnext hit an error: {type(exc).__name__}: {exc}. "
           + ("Your rekordbox library was not changed. " if request.url.path in ("/api/send", "/api/send_genres") else "")
           + "Details are in ~/Library/Logs/djnext.log (Mac app).")
    return JSONResponse({"detail": msg}, status_code=500)


def _load(reload: bool = False):
    with _lock:
        if STATE["lib"] is None or reload:
            try:
                STATE["lib"] = service.load_library()
            except FileNotFoundError as e:
                raise HTTPException(404, f"Couldn't find your rekordbox library ({e}). Is rekordbox installed?")
            STATE["pool"] = None
        if STATE["pool"] is None:
            STATE["pool"], STATE["counts"] = service.the_pool(STATE["lib"])
            STATE["ev"] = service.evidence(STATE["lib"], STATE["pool"])
            STATE["verdicts"] = service.sort_by_genre(STATE["pool"])
    return STATE["lib"], STATE["pool"], STATE["ev"]


def _refresh_evidence() -> None:
    STATE["pool"] = None
    _load()


def _genre_pool(genre: str):
    """The tracks in one genre list."""
    _, pool, _ = _load()
    v = STATE["verdicts"]
    return [t for t in pool if v[t.id].genre == genre]


def _running() -> bool:
    from ..export.rekordbox_playlist import rekordbox_running

    try:
        return rekordbox_running()
    except Exception:
        return False


def _track(t, ev: picker.Evidence) -> dict:
    v = (STATE.get("verdicts") or {}).get(t.id)
    artist, title = names.display(t)
    return {"genre": v.genre if v else "", "genre_sure": bool(v and v.sure), "genre_why": v.why if v else "",
            "id": t.id, "label": t.label, "artist": artist, "title": title,
            "bpm": round(t.bpm, 1), "key": t.key or "?", "known": ev.dj_plays.get(t.id, 0) >= picker.KNOWN_SETS,
            "dj_sets": ev.dj_plays.get(t.id, 0), "intro_bars": picker.intro_bars(t)}


def _playlist_json() -> dict:
    pl: Optional[picker.Playlist] = STATE["playlist"]
    if pl is None:
        return {"steps": []}
    ev = STATE["ev"]
    cues = {}
    try:
        for c in service.cue_plan(pl.tracks):
            cues.setdefault(c.content_id, []).append({"slot": c.slot, "at": fmt(c.seconds),
                                                      "what": c.comment.replace("djnext ", "")})
    except Exception:  # a track without phrase analysis: show the list anyway
        pass
    steps = []
    for s in pl.steps:
        steps.append({**_track(s.track, ev), "why": s.why, "cues": sorted(cues.get(s.track.id, []), key=lambda c: c["slot"])})
    genre = STATE.get("genre") or ""
    return {"steps": steps, "shape": pl.shape, "shape_name": picker.SHAPES.get(pl.shape, pl.shape),
            "genre": genre, "name": f"{genres.NAMES.get(genre, 'djnext')} {datetime.now():%d %b %H.%M}"}


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"))


@app.get("/api/status")
def status():
    data = sc.load()
    out = {"soundcloud": {"user": data["user"], "synced_at": data.get("synced_at", ""),
                          "likes": len(data.get("likes", []))} if data else None,
           "rekordbox_running": _running(), "lookup": dict(LOOKUP)}
    if not data:
        return out
    lib, pool, ev = _load()
    start_auto_refresh()
    c = STATE["counts"]
    store = mixesdb.Store.load()
    v = STATE["verdicts"]
    out.update({
        "genres": [{"id": g, "name": name, "count": sum(1 for t in pool if v[t.id].genre == g),
                    "guessed": sum(1 for t in pool if v[t.id].genre == g and not v[t.id].sure)}
                   for g, name in genres.GENRES],
        "pool": len(pool),
        "counts": {**c, "in_rekordbox": c["likes"], "not_in_rekordbox": max(0, len(data.get("likes", [])) - c["likes"])},
        "dj_checked": sum(1 for t in pool if t.id in store.tracks),
        "dj_found": sum(1 for t in pool if store.tracks.get(t.id, {}).get("sets")),
        "tracks": sorted((_track(t, ev) for t in pool), key=lambda d: d["label"].lower()),
    })
    return out


@app.get("/api/rekordbox")
def rekordbox_state():
    """Cheap check the page polls, so Send can say whether rekordbox is open."""
    return {"running": _running()}


class SyncIn(BaseModel):
    user: str = ""


@app.post("/api/soundcloud/sync")
def soundcloud_sync(body: SyncIn):
    current = sc.load()
    raw = body.user.strip() or (current or {}).get("user", "")
    user = raw.rstrip("/").split("soundcloud.com/")[-1].split("/")[0].split("?")[0]
    if not user or " " in user:
        raise HTTPException(400, "Paste your SoundCloud profile link, for example https://soundcloud.com/your-name.")
    try:
        data = sc.fetch(user, log=lambda *_: None)
    except Exception as e:
        raise HTTPException(400, f"Couldn't read SoundCloud likes for '{user}': {e}")
    data["playlists"] = {}  # only your likes are used
    sc.save(data)
    _load(reload=True)
    return status()


@app.get("/api/missing")
def missing():
    """Likes rekordbox doesn't know yet (never loaded or added to its Collection), so djnext can't use them."""
    data = sc.load()
    if not data:
        return {"tracks": []}
    lib, _, _ = _load()
    res = sc.attach(lib, {"likes": data.get("likes", []), "playlists": {}})
    return {"tracks": [{"label": sc.label(e), "url": e.get("url", "")} for e in res.not_analysed]}


@app.post("/api/reload")
def reload():
    _load(reload=True)
    return status()


def _lookup_worker(tracks) -> None:
    try:
        def progress(i, n, t):
            LOOKUP.update(done=i, total=n, current=t.label)
        mixesdb.update(tracks, progress=progress)
    except Exception as e:  # no internet etc.: keep what we have
        LOOKUP["error"] = f"Stopped: {e}"
    finally:
        LOOKUP.update(running=False, current="")
        _refresh_evidence()


AUTO: dict = {"started": False}
LIKES_MAX_AGE_H = 24


def _auto_refresh() -> None:
    """When djnext opens: fetch your likes again if they're over a day old, then look up new tracks in DJ
    tracklists. All in the background, so nothing needs a button press."""
    try:
        data = sc.load()
        if data and data.get("user"):
            try:
                age_h = (datetime.now() - datetime.fromisoformat(data.get("synced_at", ""))).total_seconds() / 3600
            except ValueError:
                age_h = LIKES_MAX_AGE_H + 1
            if age_h > LIKES_MAX_AGE_H:
                LOOKUP.update(current="Updating your likes from SoundCloud…")
                fresh = sc.fetch(data["user"], log=lambda *_: None)
                fresh["playlists"] = {}
                if fresh.get("likes"):  # a failed or empty read never wipes your list
                    sc.save(fresh)
                    _load(reload=True)
                LOOKUP.update(current="")
    except Exception as e:  # offline etc.: carry on with what we have
        LOOKUP.update(current="", error=f"Couldn't update your likes: {type(e).__name__}")
    _, pool, _ = _load()
    todo = mixesdb.Store.load().todo(pool)
    if todo and not LOOKUP["running"]:
        LOOKUP.update(running=True, done=0, total=len(todo), error="")
        _lookup_worker(todo)


def start_auto_refresh() -> None:
    if AUTO["started"] or not sc.load():
        return
    AUTO["started"] = True
    threading.Thread(target=_auto_refresh, daemon=True).start()


@app.post("/api/djsets")
def djsets():
    """Look your tracks up in DJ tracklists (MixesDB), in the background."""
    _, pool, _ = _load()
    if LOOKUP["running"]:
        return status()
    todo = mixesdb.Store.load().todo(pool)
    if not todo:
        return status()
    LOOKUP.update(running=True, done=0, total=len(todo), current="", error="")
    threading.Thread(target=_lookup_worker, args=(todo,), daemon=True).start()
    return status()


class MakeIn(BaseModel):
    genre: str = "tech-house"
    length: int = 12
    shape: str = "build"
    start_id: Optional[str] = None


@app.post("/api/playlist")
def make_playlist(body: MakeIn):
    _, _, ev = _load()
    if body.genre not in genres.NAMES:
        raise HTTPException(400, "Pick a genre first.")
    pool = _genre_pool(body.genre)
    if len(pool) < 3:
        raise HTTPException(400, f"Only {len(pool)} tracks in {genres.NAMES[body.genre]}. Pick another genre, or move "
                                 "tracks into this list under “Your genre lists”.")
    STATE["genre"] = body.genre
    start = next((t for t in pool if t.id == body.start_id), None) if body.start_id else None
    import random

    STATE["playlist"] = picker.build(pool, ev, length=body.length, start=start,
                                     shape=body.shape if body.shape in picker.SHAPES else "build",
                                     recent=service.recent_penalties(body.genre), rng=random.Random())
    service.remember_playlist(body.genre, [t.id for t in STATE["playlist"].tracks])
    return _playlist_json()


@app.get("/api/playlist")
def get_playlist():
    return _playlist_json()


class SlotIn(BaseModel):
    position: int  # 0-based


@app.post("/api/playlist/options")
def options(body: SlotIn):
    """Other tracks that could go in this slot (from the same genre list)."""
    _, _, ev = _load()
    pool = _genre_pool(STATE.get("genre") or "tech-house")
    pl: Optional[picker.Playlist] = STATE["playlist"]
    if pl is None or not 0 < body.position < len(pl.steps):
        raise HTTPException(400, "Pick a track after the first one.")
    prev = pl.steps[body.position - 1].track
    nxt = pl.steps[body.position + 1].track if body.position + 1 < len(pl.steps) else None
    used = {s.track.id for s in pl.steps}
    alts = picker.alternatives(prev, nxt, pool, ev, used)
    return {"options": [{**_track(m.track, ev), "why": m.why} for m in alts]}


class ReplaceIn(BaseModel):
    position: int
    track_id: str


@app.post("/api/playlist/replace")
def replace(body: ReplaceIn):
    _, pool, ev = _load()
    pl: Optional[picker.Playlist] = STATE["playlist"]
    t = next((x for x in pool if x.id == body.track_id), None)  # any of your tracks (Other options picks from the list)
    if pl is None or t is None or not 0 <= body.position < len(pl.steps):
        raise HTTPException(400, "That track can't go there.")
    tracks = pl.tracks
    tracks[body.position] = t
    STATE["playlist"] = _restep(tracks, pl.shape, ev)
    return _playlist_json()


def _restep(tracks, shape: str, ev: picker.Evidence) -> picker.Playlist:
    steps = [picker.Step(tracks[0], "opener", known=ev.dj_plays.get(tracks[0].id, 0) >= picker.KNOWN_SETS)]
    for a, b in zip(tracks, tracks[1:]):
        m = picker.move(a, b, ev)
        why = m.why if picker.mixable(a, b) else "⚠ hard mix: " + m.why
        steps.append(picker.Step(b, why, m.score, ev.dj_plays.get(b.id, 0) >= picker.KNOWN_SETS))
    return picker.Playlist(steps, shape)


@app.post("/api/playlist/rebuild_from")
def rebuild_from(body: SlotIn):
    """Keep the tracks before this slot, drop this one and pick the rest again."""
    _, all_tracks, ev = _load()
    pool = _genre_pool(STATE.get("genre") or "tech-house")
    pl: Optional[picker.Playlist] = STATE["playlist"]
    if pl is None or not 0 < body.position < len(pl.steps):
        raise HTTPException(400, "Pick a track after the first one.")
    keep = pl.tracks[:body.position]
    dropped = pl.steps[body.position].track
    service.block_pair(keep[-1].id, dropped.id)
    STATE["ev"] = ev = service.evidence(STATE["lib"], all_tracks)
    import random

    genre = STATE.get("genre") or "tech-house"
    rest = picker.build(pool, ev, length=len(pl.steps) - len(keep) + 1, start=keep[-1], shape=pl.shape,
                        avoid={t.id for t in keep[:-1]}, recent=service.recent_penalties(genre), rng=random.Random())
    STATE["playlist"] = _restep(keep + rest.tracks[1:], pl.shape, ev)
    return _playlist_json()


class TrackIn(BaseModel):
    track_id: str
    out: bool = True


@app.post("/api/remove")
def remove(body: TrackIn):
    """Never use this track (or, with out=False, use it again)."""
    service.set_removed(body.track_id, body.out)
    pl: Optional[picker.Playlist] = STATE["playlist"]
    _refresh_evidence()
    if pl is not None and body.out and body.track_id in {t.id for t in pl.tracks}:
        tracks = [t for t in pl.tracks if t.id != body.track_id]
        STATE["playlist"] = _restep(tracks, pl.shape, STATE["ev"]) if tracks else None
    return {"status": status(), "playlist": _playlist_json()}


class GenreIn(BaseModel):
    track_id: str
    genre: Optional[str] = None  # None = let djnext decide again


@app.post("/api/genre")
def move_genre(body: GenreIn):
    """Put a track in another genre list."""
    if body.genre is not None and body.genre not in genres.NAMES:
        raise HTTPException(400, "Unknown genre.")
    service.set_genre(body.track_id, body.genre)
    _load()
    STATE["verdicts"] = service.sort_by_genre(STATE["pool"])
    return status()


@app.post("/api/send_genres")
def send_genres():
    """Each genre list as a rekordbox playlist in a 'djnext genres' folder."""
    from ..export.rekordbox_playlist import RekordboxRunning

    _, pool, _ = _load()
    lists = service.genre_lists(pool, STATE["verdicts"])
    try:
        out = service.send_genre_lists(lists)
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit rekordbox (Cmd+Q), then press the button again.")
    return {"folder": out["genres_folder"], "playlists": out["genre_playlists"], "backup": str(out["backup"])}


@app.get("/api/removed")
def removed_tracks():
    lib, _, ev = _load()
    return {"tracks": [_track(lib.tracks[i], ev) for i in service.removed() if i in lib.tracks]}


class SendIn(BaseModel):
    name: str = ""


@app.post("/api/send")
def send(body: SendIn):
    from ..export.rekordbox_playlist import RekordboxRunning

    pl: Optional[picker.Playlist] = STATE["playlist"]
    if pl is None or not pl.steps:
        raise HTTPException(400, "Make a playlist first.")
    try:
        out = service.send_to_rekordbox(pl.tracks, body.name.strip() or service.default_name(pl.shape))
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit rekordbox (Cmd+Q), then press Send again.")
    return {"name": out["name"], "folder": out["folder"], "tracks": out["tracks"],
            "cues": len(out.get("cues_written") or []), "cues_skipped": len(out.get("cues_skipped") or []),
            "backup": str(out["backup"])}


@app.post("/api/undo")
def undo():
    """Put back rekordbox's library from just before the last Send."""
    from ..export.rekordbox_playlist import RekordboxRunning, list_backups, restore

    backups = list_backups()
    if not backups:
        raise HTTPException(400, "Nothing to undo.")
    try:
        restore(backups[0])
    except RekordboxRunning:
        raise HTTPException(409, "rekordbox is open. Quit rekordbox (Cmd+Q), then press Undo again.")
    return {"restored": backups[0].name}


@app.get("/api/update")
def update_check():
    """Is there a newer djnext? (asks GitHub; offline = no)"""
    from .. import updater

    return updater.check()


@app.post("/api/update")
def update_install():
    """Install the newest version. The Mac app quits and reopens itself; from the code, restart djnext after."""
    import os

    from .. import updater

    info = updater.check()
    if not info["newer"]:
        raise HTTPException(400, "You already have the newest djnext." if info["latest"] else
                            info.get("error") or "Couldn't check for updates.")
    how = updater.how()
    try:
        if how == "app":
            updater.install_app(info["url"], quit_app=lambda: threading.Timer(1.0, lambda: os._exit(0)).start())
            return {"done": "restarting", "version": info["latest"]}
        if how == "source":
            updater.update_source()
            return {"done": "restart", "version": info["latest"]}
    except Exception as e:
        raise HTTPException(400, f"The update didn't work: {e}. Your djnext wasn't changed.")
    return {"done": "manual", "version": info["latest"], "page": info.get("page", "")}


def serve(port: int = 8765, open_browser: bool = True) -> None:
    import webbrowser

    import uvicorn

    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
