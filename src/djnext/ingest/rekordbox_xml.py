"""Read a rekordbox collection export (File > Export Collection in xml format)."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import unquote

from ..core.camelot import to_camelot
from ..core.energy import assign_all
from ..core.models import Track


@dataclass
class Library:
    tracks: Dict[str, Track] = field(default_factory=dict)
    playlists: Dict[str, List[str]] = field(default_factory=dict)  # "Folder/Name" -> track ids

    def playlist_tracks(self, name: str) -> List[Track]:
        if name in self.playlists:
            ids = self.playlists[name]
        else:
            matches = [k for k in self.playlists if k.split("/")[-1].lower() == name.lower()]
            if not matches:
                raise KeyError(f"playlist '{name}' not found")
            if len(matches) > 1:
                raise KeyError(f"playlist name '{name}' is ambiguous: {matches}")
            ids = self.playlists[matches[0]]
        return [self.tracks[i] for i in ids if i in self.tracks]

    def find(self, query: str, pool: Optional[List[Track]] = None) -> Track:
        """Find a track by (part of) 'Artist - Title' or by track id."""
        pool = pool if pool is not None else list(self.tracks.values())
        for t in pool:
            if t.id == query:
                return t
        q = query.lower()
        exact = [t for t in pool if t.label.lower() == q or t.title.lower() == q]
        if len(exact) == 1:
            return exact[0]
        hits = [t for t in pool if q in t.label.lower()]
        if not hits:
            raise KeyError(f"no track matching '{query}'")
        if len(hits) > 1:
            listing = "\n  ".join(t.label for t in hits[:10])
            raise KeyError(f"'{query}' matches {len(hits)} tracks, be more specific:\n  {listing}")
        return hits[0]


def _location_to_path(location: str) -> str:
    if not location:
        return ""
    loc = location
    for prefix in ("file://localhost", "file://"):
        if loc.startswith(prefix):
            loc = loc[len(prefix):]
            break
    return unquote(loc)


def _float(v: Optional[str]) -> float:
    try:
        return float(v) if v else 0.0
    except ValueError:
        return 0.0


def _walk_playlists(node: ET.Element, prefix: str, out: Dict[str, List[str]]) -> None:
    for child in node.findall("NODE"):
        name = child.get("Name", "")
        path = f"{prefix}/{name}" if prefix else name
        if child.get("Type") == "1":  # playlist
            # Key is a TrackID (KeyType 0) or a Location (KeyType 1, resolved in load_library)
            out[path] = [t.get("Key", "") for t in child.findall("TRACK")]
        else:  # folder
            _walk_playlists(child, path, out)


def load_library(path: Path) -> Library:
    root = ET.parse(str(path)).getroot()
    lib = Library()
    collection = root.find("COLLECTION")
    if collection is None:
        raise ValueError(f"{path} does not look like a rekordbox XML export (no COLLECTION)")
    by_location: Dict[str, str] = {}
    for el in collection.findall("TRACK"):
        tid = el.get("TrackID", "")
        if not tid:
            continue
        rating_raw = int(_float(el.get("Rating")))
        t = Track(
            id=tid,
            title=el.get("Name", "") or "",
            artist=el.get("Artist", "") or "",
            bpm=_float(el.get("AverageBpm")),
            key=to_camelot(el.get("Tonality")),
            genre=el.get("Genre", "") or "",
            rating=round(rating_raw / 51) if rating_raw > 5 else rating_raw,
            duration=_float(el.get("TotalTime")),
            path=_location_to_path(el.get("Location", "")),
            comments=el.get("Comments", "") or "",
        )
        lib.tracks[tid] = t
        if el.get("Location"):
            by_location[el.get("Location", "")] = tid
    assign_all(lib.tracks.values())

    playlists_root = root.find("PLAYLISTS")
    if playlists_root is not None:
        top = playlists_root.find("NODE")  # the ROOT folder
        if top is not None:
            _walk_playlists(top, "", lib.playlists)
    # playlists exported with KeyType=1 reference tracks by location instead of id
    for name, ids in lib.playlists.items():
        lib.playlists[name] = [i if i in lib.tracks else by_location.get(i, i) for i in ids]
    return lib
