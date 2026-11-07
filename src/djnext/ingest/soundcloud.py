"""Your SoundCloud likes and your own playlists (track lists only; no audio is downloaded).

Uses yt-dlp against public pages: soundcloud.com/<user>/likes and soundcloud.com/<user>/sets.
Private playlists aren't visible this way.

Tracks are linked to rekordbox by their exact SoundCloud track id: rekordbox stores streamed
tracks as "soundcloud:tracks:<id>", so no name matching is needed for those.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence, Callable, Dict, List, Optional

from .rekordbox_xml import Library

DEFAULT_CACHE = Path("data/soundcloud.json")
_TRACK_ID_RE = re.compile(r"/tracks/(\d+)")


def _entry_id(entry: dict) -> Optional[str]:
    url = entry.get("url") or ""
    if "/sets/" in url or "/playlists/" in url:
        return None  # a liked playlist, not a track
    m = _TRACK_ID_RE.search(url)
    if m:
        return m.group(1)
    eid = entry.get("id")
    return str(eid) if eid is not None and str(eid).isdigit() else None


def _entry_track(entry: dict) -> Optional[dict]:
    tid = _entry_id(entry)
    if tid is None:
        return None
    return {
        "id": tid,
        "title": entry.get("title") or "",
        "artist": entry.get("uploader") or entry.get("artist") or "",
        "url": entry.get("webpage_url") or entry.get("url") or "",
    }


def label(entry: dict) -> str:
    """'artist - title', falling back to the uploader and slug in the track's URL (flat listings lack names)."""
    url = entry.get("url") or ""
    parts = url.split("soundcloud.com/", 1)[1].split("/") if "soundcloud.com/" in url else []
    artist = entry.get("artist") or (parts[0] if len(parts) >= 2 and parts[0] != "tracks" else "")
    title = entry.get("title") or (parts[1].replace("-", " ") if len(parts) >= 2 else entry.get("id", ""))
    return f"{artist} - {title}" if artist else title


def fetch(user: str, log: Callable[[str], None] = print) -> dict:
    import yt_dlp

    opts = {"extract_flat": "in_playlist", "quiet": True, "no_warnings": True, "skip_download": True}
    data: dict = {"user": user, "synced_at": datetime.now().isoformat(timespec="seconds"), "likes": [], "playlists": {}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        log(f"Fetching likes of {user} ...")
        info = ydl.extract_info(f"https://soundcloud.com/{user}/likes", download=False) or {}
        data["likes"] = [t for t in (_entry_track(e) for e in info.get("entries") or []) if t]
        log(f"  {len(data['likes'])} liked tracks")

        log(f"Fetching playlists of {user} ...")
        sets = ydl.extract_info(f"https://soundcloud.com/{user}/sets", download=False) or {}
        for s in sets.get("entries") or []:
            url = s.get("url") or s.get("webpage_url")
            if not url:
                continue
            pl = ydl.extract_info(url, download=False) or {}
            name = pl.get("title") or s.get("title") or url.rsplit("/", 1)[-1]
            tracks = [t for t in (_entry_track(e) for e in pl.get("entries") or []) if t]
            data["playlists"][name] = tracks
            log(f"  {name}: {len(tracks)} tracks")
    return data


def save(data: dict, cache: Path = DEFAULT_CACHE) -> Path:
    from ..storage import write_json

    return write_json(cache, data)


def load(cache: Path = DEFAULT_CACHE) -> Optional[dict]:
    from ..storage import read_json

    data = read_json(cache)
    return data if isinstance(data, dict) and data.get("user") else None


@dataclass
class AttachResult:
    playlists: Dict[str, int] = field(default_factory=dict)  # "sc:<name>" -> tracks found in rekordbox
    not_analysed: List[dict] = field(default_factory=list)  # in your SoundCloud lists but unknown to rekordbox


def attach(lib: Library, data: dict, skip: Sequence[str] = ()) -> AttachResult:
    """Add 'sc:likes' and 'sc:<playlist>' to lib.playlists, using tracks rekordbox has analysed.
    Lists named in `skip` (switched off in My music) don't count towards not_analysed."""
    by_sc_id = {t.soundcloud_id: t.id for t in lib.tracks.values() if t.soundcloud_id}
    result = AttachResult()
    seen_missing = set()
    lists = {"likes": data.get("likes", [])}
    lists.update(data.get("playlists", {}))
    for name, entries in lists.items():
        ids = []
        for e in entries:
            rid = by_sc_id.get(e["id"])
            if rid:
                ids.append(rid)
            elif e["id"] not in seen_missing and name not in skip:
                seen_missing.add(e["id"])
                result.not_analysed.append({**e, "list": name})
        key = f"sc:{name}"
        lib.playlists[key] = ids
        result.playlists[key] = len(ids)
    return result
