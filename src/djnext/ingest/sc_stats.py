"""How much people listen to each of your liked tracks on SoundCloud (plays, likes, upload date).

Text only, never audio: one small request per track (about 2-3 seconds), cached in data/soundcloud_stats.json
and refreshed once a week in the background.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

from ..core.models import Track

CACHE = Path("data/soundcloud_stats.json")
MAX_AGE_DAYS = 7


def load(path: Path = CACHE) -> Dict[str, dict]:
    from ..storage import read_json

    d = read_json(path, {})
    return d if isinstance(d, dict) else {}


def save(stats: Dict[str, dict], path: Path = CACHE) -> None:
    from ..storage import write_json

    write_json(path, stats)


def stale(tracks: Sequence[Track], stats: Dict[str, dict], now: Optional[datetime] = None) -> list:
    now = now or datetime.now()
    out = []
    for t in tracks:
        sid = t.soundcloud_id
        if not sid:
            continue
        info = stats.get(sid)
        try:
            age = (now - datetime.fromisoformat(info["checked"])).days if info else None
        except (KeyError, ValueError):
            age = None
        if age is None or age >= MAX_AGE_DAYS:
            out.append(t)
    return out


def _fetch_one(sid: str, ydl) -> Optional[dict]:
    info = ydl.extract_info(f"https://api.soundcloud.com/tracks/{sid}", download=False, process=False)
    if not info:
        return None
    return {"plays": int(info.get("view_count") or 0), "likes": int(info.get("like_count") or 0),
            "uploaded": int(info.get("timestamp") or 0)}


def update(tracks: Sequence[Track], progress: Callable[[int, int, Track], None] = lambda *_: None,
           path: Path = CACHE, fetch: Optional[Callable[[str], Optional[dict]]] = None) -> Dict[str, dict]:
    """Fetch stats for tracks that have none or are over a week old. Saves as it goes."""
    stats = load(path)
    todo = stale(tracks, stats)
    if not todo:
        return stats
    ydl = None
    if fetch is None:
        import yt_dlp

        ydl = yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "ignore_no_formats_error": True,
                                "no_warnings": True})
        fetch = lambda sid: _fetch_one(sid, ydl)  # noqa: E731
    for i, t in enumerate(todo):
        progress(i, len(todo), t)
        try:
            got = fetch(t.soundcloud_id)
        except Exception:  # removed track, network hiccup: try again next week
            got = None
        if got is not None:
            stats[t.soundcloud_id] = {**got, "checked": datetime.now().isoformat(timespec="seconds")}
        if i % 10 == 9 or i == len(todo) - 1:
            save(stats, path)
        if fetch is not None and ydl is not None:
            time.sleep(0.5)
    return stats
