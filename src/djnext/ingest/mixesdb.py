"""Pairs real DJs have played: tracklists from MixesDB (www.mixesdb.com, an open wiki with a public API).

Only YOUR liked tracks are looked up, and only to learn which of them DJs play together. Nothing from
MixesDB is ever added to a playlist. Everything is cached in data/mixesdb.json, so each track is looked up
once (about 10-20 seconds per track the first time; we wait 1 second between requests to be polite).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from ..core import names
from ..core.models import Track

API = "https://www.mixesdb.com/w/api.php"
USER_AGENT = "djnext/0.3 (personal DJ tool; https://github.com/ayshsudhir/djnext)"
CACHE = Path("data/mixesdb.json")
SETS_PER_TRACK = 20
PAUSE_S = 1.0


def _get(params: dict, opener=urllib.request.urlopen) -> Optional[dict]:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(3):
        try:
            with opener(req, timeout=30) as r:
                return json.load(r)
        except Exception:
            time.sleep(3 * (attempt + 1))
    return None


def _tracklist(wikitext: str) -> List[Tuple[str, str]]:
    out = []
    for line in wikitext.splitlines():
        s = line.lstrip()
        if not s.startswith(("#", "[", "*")) and not s[:1].isdigit():
            continue
        parsed = names.clean_line(s)
        if parsed:
            out.append(parsed)
    return out


@dataclass
class Store:
    tracks: Dict[str, dict] = field(default_factory=dict)  # track id -> {"checked": iso, "sets": [set titles]}
    sets: Dict[str, List[Tuple[str, str]]] = field(default_factory=dict)  # set title -> [(artist, title), ...]
    categories: Dict[str, List[str]] = field(default_factory=dict)  # set title -> MixesDB categories ("Tech House" ...)

    @classmethod
    def load(cls, path: Path = CACHE) -> "Store":
        from ..storage import read_json

        d = read_json(path, {})
        if not isinstance(d, dict):
            return cls()
        return cls(d.get("tracks", {}), {k: [tuple(x) for x in v] for k, v in d.get("sets", {}).items()},
                   d.get("categories", {}))

    def save(self, path: Path = CACHE) -> None:
        from ..storage import write_json

        write_json(path, {"tracks": self.tracks, "sets": self.sets, "categories": self.categories})

    def todo(self, tracks: Iterable[Track]) -> List[Track]:
        return [t for t in tracks if t.id not in self.tracks]


def lookup(track: Track, store: Store, get: Optional[Callable[[dict], Optional[dict]]] = None) -> int:
    """Find the sets this track was played in. Returns how many."""
    get = get or _get
    name = names.of(track)
    found: List[str] = []
    if name.title:
        queries = []
        if name.main_artist:
            queries.append(f'"{name.title_text}" "{name.main_artist}"')
        queries.append(f'"{name.title_text}"')
        titles: List[str] = []
        for q in queries:
            d = get({"action": "query", "list": "search", "srsearch": q, "srlimit": SETS_PER_TRACK, "srwhat": "text"})
            time.sleep(PAUSE_S)
            titles = [r["title"] for r in (d or {}).get("query", {}).get("search", [])]
            if titles:
                break
        for st in titles:
            if st not in store.sets:
                p = get({"action": "parse", "page": st, "prop": "wikitext"})
                time.sleep(PAUSE_S)
                if not p or "parse" not in p:
                    continue
                store.sets[st] = _tracklist(p["parse"]["wikitext"]["*"])
            if any(names.matches(name, a, t) for a, t in store.sets[st]):
                found.append(st)
    store.tracks[track.id] = {"checked": datetime.now().isoformat(timespec="seconds"), "sets": found}
    return len(found)


def fill_categories(store: Store, get: Optional[Callable[[dict], Optional[dict]]] = None) -> int:
    """Genre tags of the sets your tracks were found in, 50 sets per request. Returns how many sets were filled."""
    get = get or _get
    wanted = sorted({st for info in store.tracks.values() for st in info["sets"]} - set(store.categories))
    for i in range(0, len(wanted), 50):
        batch = wanted[i:i + 50]
        d = get({"action": "query", "prop": "categories", "titles": "|".join(batch), "cllimit": "max"})
        time.sleep(PAUSE_S)
        if not d or "query" not in d:
            continue
        renamed = {n["to"]: n["from"] for n in d["query"].get("normalized", [])}
        for page in d["query"].get("pages", {}).values():
            title = renamed.get(page.get("title", ""), page.get("title", ""))
            store.categories[title] = [c["title"].split(":", 1)[-1] for c in page.get("categories", [])]
        for st in batch:
            store.categories.setdefault(st, [])  # asked once; a set without tags isn't asked again
    return len(wanted)


def update(tracks: Sequence[Track], progress: Callable[[int, int, Track], None] = lambda *_: None,
           path: Path = CACHE) -> Store:
    """Look up every track not checked yet; saves after each one so stopping half-way loses nothing.
    Then fetch the genre tags of any new sets."""
    store = Store.load(path)
    todo = store.todo(tracks)
    for i, t in enumerate(todo):
        progress(i, len(todo), t)
        lookup(t, store)
        store.save(path)
    if fill_categories(store):
        store.save(path)
    return store


# ---------- what the tracklists say about your tracks ----------

@dataclass
class DJPairs:
    """For tracks in your pool: how often real DJs played them back to back / close together / in the same set,
    and how 'known' each track is (in how many sets it was found)."""
    direct: Dict[Tuple[str, str], int] = field(default_factory=lambda: defaultdict(int))  # (a, b): a straight into b
    near: Dict[frozenset, int] = field(default_factory=lambda: defaultdict(int))  # within 3 tracks
    same_set: Dict[frozenset, int] = field(default_factory=lambda: defaultdict(int))
    artist_affinity: Dict[Tuple[str, str], float] = field(default_factory=dict)  # (a, b): share of a's sets with b's artist
    plays: Dict[str, int] = field(default_factory=dict)  # track id -> sets found
    recent_plays: Dict[str, int] = field(default_factory=dict)  # track id -> sets from the last 12 months
    checked: int = 0


def set_date(title: str) -> Optional[datetime]:
    """'2025-08-29 - Adam Ten @ ...' -> 29 Aug 2025; '2024 - ...' -> mid 2024; no date -> None."""
    import re

    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", title)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2) or 6), int(m.group(3) or 15)
    try:
        return datetime(y, min(max(mo, 1), 12), min(max(d, 1), 28))
    except ValueError:
        return None


def pairs(pool: Sequence[Track], store: Store, now: Optional[datetime] = None) -> DJPairs:
    now = now or datetime.now()
    out = DJPairs()
    parsed = {t.id: names.of(t) for t in pool}
    by_set: Dict[str, List[str]] = defaultdict(list)
    for t in pool:
        info = store.tracks.get(t.id)
        if info is None:
            continue
        out.checked += 1
        out.plays[t.id] = len(info["sets"])
        out.recent_plays[t.id] = sum(1 for st in info["sets"] if (d := set_date(st)) and (now - d).days <= 365)
        for st in info["sets"]:
            by_set[st].append(t.id)
    for st, ids in by_set.items():
        lines = store.sets.get(st, [])
        pos: Dict[str, List[int]] = {}
        for tid in set(ids):
            pos[tid] = [i for i, (a, ti) in enumerate(lines) if names.matches(parsed[tid], a, ti)]
        tids = [t for t in pos if pos[t]]
        for a in tids:
            for b in tids:
                if a >= b:
                    continue
                key = frozenset((a, b))
                out.same_set[key] += 1
                gaps = [pb - pa for pa in pos[a] for pb in pos[b]]
                if any(abs(g) <= 3 for g in gaps):
                    out.near[key] += 1
                if 1 in gaps:
                    out.direct[(a, b)] += 1
                if -1 in gaps:
                    out.direct[(b, a)] += 1
    # groove neighbourhood: do DJs who play A also play B's artist in the same set?
    artist_sets: Dict[str, List[str]] = {}
    for t in pool:
        info = store.tracks.get(t.id)
        if info and info["sets"]:
            artist_sets[t.id] = info["sets"]
    set_artists: Dict[str, str] = {}  # set title -> " | artist one | artist two | " (for whole-name lookups)
    for sets_a in artist_sets.values():
        for st in sets_a:
            if st not in set_artists:
                set_artists[st] = " | " + " | ".join(" ".join(names.words(la)) for la, _ in store.sets.get(st, [])) + " | "
    for a, sets_a in artist_sets.items():
        for b in pool:
            if b.id == a or not parsed[b.id].artists:
                continue
            artist = parsed[b.id].artists[0]
            if len(artist) < 3:
                continue
            hits = sum(1 for st in sets_a if f" {artist} " in set_artists[st])
            if hits:
                out.artist_affinity[(a, b.id)] = hits / len(sets_a)
    return out
