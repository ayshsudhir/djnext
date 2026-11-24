"""What the app does, as plain functions: your likes -> the pool -> a playlist -> rekordbox (with hot cues)."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .config import SETTINGS_PATH, Config, load_config
from .core import genres, picker
from .core.models import Track
from .ingest import mixesdb
from .ingest import soundcloud as sc
from .ingest.rekordbox_xml import Library


# ---------- settings made in the app (data/settings.json) ----------

def read_settings() -> dict:
    from .storage import read_json

    data = read_json(SETTINGS_PATH, {})
    return data if isinstance(data, dict) else {}


def save_settings(updates: dict) -> dict:
    from .storage import write_json

    data = read_settings()
    data.update(updates)
    write_json(SETTINGS_PATH, data)
    return data


def config() -> Config:
    return load_config()


def removed() -> List[str]:
    return list(read_settings().get("removed") or [])


def set_removed(track_id: str, out: bool = True) -> List[str]:
    ids = set(removed())
    (ids.add if out else ids.discard)(track_id)
    save_settings({"removed": sorted(ids)})
    return sorted(ids)


# ---------- library ----------

def load_library() -> Library:
    from .ingest.rekordbox_db import load_rekordbox_db

    lib = load_rekordbox_db()
    data = sc.load()
    if data:
        sc.attach(lib, {"likes": data.get("likes", []), "playlists": {}})  # your likes, nothing else
    return lib


def likes(lib: Library) -> List[Track]:
    return [lib.tracks[i] for i in lib.playlists.get("sc:likes", []) if i in lib.tracks]


def with_structure(tracks: List[Track]) -> List[Track]:
    from .ingest.rekordbox_anlz import attach_structures

    todo = [t for t in tracks if t.analysis_path and t.structure is None]
    if todo:
        attach_structures(todo)
    return tracks


def the_pool(lib: Library, include_removed: bool = False) -> Tuple[List[Track], Dict[str, int]]:
    pool, counts = picker.pool(likes(lib), () if include_removed else removed())
    with_structure(pool)
    return pool, counts


# ---------- genre lists ----------

def genre_overrides() -> Dict[str, str]:
    data = read_settings().get("genres") or {}
    return {k: v for k, v in data.items() if v in genres.NAMES}


def set_genre(track_id: str, genre: Optional[str]) -> None:
    """Put a track in another list yourself (None = let djnext decide again)."""
    data = genre_overrides()
    if genre in genres.NAMES:
        data[track_id] = genre
    else:
        data.pop(track_id, None)
    save_settings({"genres": data})


def sort_by_genre(pool: List[Track], store: Optional[mixesdb.Store] = None) -> Dict[str, genres.Verdict]:
    store = store or mixesdb.Store.load()
    cats = {t.id: [store.categories.get(st, []) for st in store.tracks.get(t.id, {}).get("sets", [])] for t in pool}
    return genres.sort_likes(pool, cats, genre_overrides())


def genre_lists(pool: List[Track], verdicts: Dict[str, genres.Verdict]) -> Dict[str, List[Track]]:
    out: Dict[str, List[Track]] = {g: [] for g, _ in genres.GENRES}
    for t in pool:
        out[verdicts[t.id].genre].append(t)
    for tracks in out.values():
        tracks.sort(key=lambda t: t.bpm)
    return out


def send_genre_lists(lists: Dict[str, List[Track]]) -> dict:
    """One rekordbox playlist per genre, in a 'djnext genres' folder (refreshed each time)."""
    from .export.rekordbox_playlist import write_to_rekordbox

    named = {genres.NAMES[g]: [t.id for t in ts] for g, ts in lists.items()}
    return write_to_rekordbox(genre_playlists=named)


def evidence(lib: Library, pool: List[Track]) -> picker.Evidence:
    from .core.popularity import hotness
    from .ingest import sc_stats

    dj = mixesdb.pairs(pool, mixesdb.Store.load())
    blocked = [tuple(p) for p in read_settings().get("blocked_pairs") or []]
    hot, why = hotness(pool, sc_stats.load(), dj.recent_plays)
    return picker.Evidence.build(dj, blocked, hot, why)


# ---------- a different playlist every time ----------

RECENT_KEEP = 3  # remember the last 3 playlists per genre
TRACK_REST = (1.5, 1.0, 0.5)  # a track from the last playlist steps aside a little (hot tracks hardly at all)
PAIR_REST = (2.5, 1.5, 0.8)  # the same transition again is what really makes a set feel the same


def recent_penalties(genre: str, hot: Optional[Dict[str, float]] = None):
    """({track id: penalty}, {(a, b): penalty}) from your last playlists of this genre."""
    hot = hot or {}
    lists = (read_settings().get("recent_playlists") or {}).get(genre) or []
    tracks: Dict[str, float] = {}
    pairs: Dict[Tuple[str, str], float] = {}
    for age, ids in enumerate(lists[:RECENT_KEEP]):
        for tid in ids:
            tracks[tid] = max(tracks.get(tid, 0.0), TRACK_REST[age] * (1.0 - hot.get(tid, 0.0)))
        for a, b in zip(ids, ids[1:]):
            pairs[(a, b)] = max(pairs.get((a, b), 0.0), PAIR_REST[age])
    return tracks, pairs


def remember_playlist(genre: str, track_ids: List[str]) -> None:
    allp = read_settings().get("recent_playlists") or {}
    allp[genre] = [list(track_ids)] + [ids for ids in (allp.get(genre) or []) if ids != list(track_ids)]
    allp[genre] = allp[genre][:RECENT_KEEP]
    save_settings({"recent_playlists": allp})


def block_pair(a_id: str, b_id: str) -> None:
    pairs = [list(p) for p in read_settings().get("blocked_pairs") or []]
    if [a_id, b_id] not in pairs:
        pairs.append([a_id, b_id])
    save_settings({"blocked_pairs": pairs})


# ---------- the playlist ----------

def default_name(shape: str) -> str:
    return f"{picker.SHAPES.get(shape, 'Groovy techno')} {datetime.now():%d %b %H.%M}"


def cue_plan(tracks: List[Track], cfg: Optional[Config] = None):
    from .export.rekordbox_cues import plan_cues

    return plan_cues(tracks, cfg or config())


def send_to_rekordbox(tracks: List[Track], name: str) -> dict:
    """New playlist in rekordbox's 'djnext' folder, with mix-point hot cues on every track."""
    from .export.rekordbox_playlist import write_playlist

    return write_playlist([t.id for t in tracks], name, cues=cue_plan(tracks))
