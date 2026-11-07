"""Discover new tracks on SoundCloud that fit your style (track lists/metadata only; nothing is downloaded).

How it searches:
  1. seeds = your favourite artists' tracks + the best tracks of each mood (from your SoundCloud lists)
  2. SoundCloud's own "related tracks" for every seed, plus a search for each favourite artist
  3. keep 2-9 minute tracks (no DJ sets / podcasts) whose genre/tags fit your genres and that you don't have yet
  4. rank by: how many of your tracks led to it, likes/plays, favourite artists

Liking tracks or creating playlists on your SoundCloud account isn't possible for outside tools, so the result
is a list with links: like the ones you want, then `djnext soundcloud sync` + add them to your rekordbox
collection so rekordbox analyses them.
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from ..config import Config
from ..core.moods import EDIT_RE, VOCAL_RE, _has_word
from .rekordbox_xml import Library
from .soundcloud import _entry_id

DISCOVER_PATH = Path("data/discover.json")
STYLE_WORDS = ["tech house", "techhouse", "house", "techno", "minimal", "deep tech", "groove", "groovy",
               "afro house", "dance", "electronic", "edm", "indie dance", "underground"]
NOT_A_TRACK = re.compile(r"(\bdj set\b|\blive (@|at|from)\b|@|\bpodcast\b|\bb2b\b|\bfull set\b|\bmixtape\b|"
                         r"\bradio show\b|\bepisode\b|\bep\.? ?\d|\bset\b(?!\s*(it|me|you)))", re.IGNORECASE)


@dataclass
class Candidate:
    id: str
    title: str
    uploader: str
    url: str
    duration: float = 0.0
    likes: int = 0
    plays: int = 0
    genre: str = ""
    tags: List[str] = field(default_factory=list)
    seeds: List[str] = field(default_factory=list)  # which of your tracks led here
    via_search: str = ""
    score: float = 0.0
    mood_guess: str = ""
    why: str = ""


class _Silent:
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass  # e.g. "DRM protected" official releases: we just skip their details


JUNK = re.compile(r"\.(m4a|mp3|wav|aiff?|flac)\b|\(\d\)|\b(teaser|snippet|preview|sample pack|unreleased id clip)\b",
                  re.IGNORECASE)


def _ydl(extra: Optional[dict] = None):
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _Silent()}
    opts.update(extra or {})
    return yt_dlp.YoutubeDL(opts)


def _meta(entry: dict) -> dict:
    genres = entry.get("genres") or ([entry["genre"]] if entry.get("genre") else [])
    return dict(
        duration=float(entry.get("duration") or 0), likes=int(entry.get("like_count") or 0),
        plays=int(entry.get("view_count") or 0), genre=", ".join(g for g in genres if g),
        tags=[str(t) for t in (entry.get("tags") or [])][:12],
        url=entry.get("webpage_url") or entry.get("url") or "", title=entry.get("title") or "",
        uploader=entry.get("uploader") or "",
    )


def _fits_style(c: Candidate, cfg: Config) -> bool:
    text = f" {c.genre} {' '.join(c.tags)} ".lower()
    if cfg.style.exclude_genres and _has_word(text, cfg.style.exclude_genres):
        return False
    if not c.genre and not c.tags:
        return bool(c.seeds)  # no genre info: trust SoundCloud's "related to your track"
    squashed = text.replace(" ", "")
    return _has_word(text, STYLE_WORDS) or any(w.replace(" ", "") in squashed for w in STYLE_WORDS)


def _mood_guess(c: Candidate, cfg: Config) -> str:
    text = f" {c.uploader} {c.title} {c.genre} {' '.join(c.tags)} ".lower()
    best, best_s = "", 0.0
    for key, m in cfg.moods().items():
        s = 0.0
        if m.edit_weight and EDIT_RE.search(c.title):
            s += m.edit_weight
        if m.vocal_weight and VOCAL_RE.search(c.title):
            s += m.vocal_weight
        if m.words and _has_word(text, m.words):
            s += m.words_weight
        if m.favourite_weight and _has_word(text, cfg.style.favourite_artists):
            s += m.favourite_weight
        if s > best_s:
            best, best_s = m.label, s
    return best


def discover(lib: Library, cfg: Config, sc_data: dict, seeds_max: int = 15, related_per_seed: int = 15,
             search_per_artist: int = 12, max_lookups: int = 120, results: int = 50,
             log: Callable[[str], None] = print) -> List[Candidate]:
    from ..service import mood_pools

    known = {t.soundcloud_id for t in lib.tracks.values() if t.soundcloud_id}
    lists = [sc_data.get("likes", [])] + list(sc_data.get("playlists", {}).values())
    known |= {e["id"] for lst in lists for e in lst}
    url_by_id = {e["id"]: e["url"] for lst in lists for e in lst if "soundcloud.com/" in (e.get("url") or "")}

    # 1) seeds: spread over moods and artists (max 2 per artist), so results aren't all one artist
    pools, _ = mood_pools(lib, cfg)
    favs = cfg.style.favourite_artists
    queues = [[t for t, _s in items if t.soundcloud_id in url_by_id] for items in pools.values()]
    seeds, per_artist, seen_ids = [], defaultdict(int), set()

    def artist_key(t) -> str:
        return (t.title.split(" - ")[0] if " - " in t.title else t.artist).strip().lower()

    while len(seeds) < seeds_max and any(queues):
        for q in queues:
            while q:
                t = q.pop(0)
                a = artist_key(t)
                if t.soundcloud_id in seen_ids or per_artist[a] >= 2:
                    continue
                seen_ids.add(t.soundcloud_id)
                per_artist[a] += 1
                seeds.append(t)
                break
            if len(seeds) >= seeds_max:
                break
    log(f"Looking for tracks related to {len(seeds)} of your tracks...")

    cands: Dict[str, Candidate] = {}

    def related(seed) -> List[dict]:
        url = url_by_id[seed.soundcloud_id].rstrip("/") + "/recommended"
        try:
            with _ydl({"extract_flat": "in_playlist", "playlistend": related_per_seed}) as y:
                return (y.extract_info(url, download=False) or {}).get("entries") or []
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=6) as pool:
        for seed, entries in zip(seeds, pool.map(related, seeds)):
            for e in entries:
                tid = _entry_id(e)
                if not tid or tid in known:
                    continue
                c = cands.setdefault(tid, Candidate(tid, e.get("title") or "", e.get("uploader") or "",
                                                    e.get("webpage_url") or e.get("url") or ""))
                if seed.title not in c.seeds:
                    c.seeds.append(seed.title)

    # 2) a search per favourite artist (search results come with metadata already)
    for artist in favs:
        log(f"Searching SoundCloud for {artist}...")
        try:
            with _ydl({"extract_flat": "in_playlist"}) as y:
                entries = (y.extract_info(f"scsearch{search_per_artist}:{artist}", download=False) or {}).get("entries") or []
        except Exception:
            entries = []
        for e in entries:
            tid = _entry_id(e)
            if not tid or tid in known:
                continue
            c = cands.setdefault(tid, Candidate(tid, "", "", ""))
            for k, v in _meta(e).items():
                if v and not getattr(c, k):
                    setattr(c, k, v)
            c.via_search = c.via_search or artist

    # 3) fetch metadata for the most promising related tracks that don't have it yet
    todo = sorted((c for c in cands.values() if not c.duration), key=lambda c: -len(c.seeds))[:max_lookups]
    log(f"Checking details of {len(todo)} tracks...")

    def lookup(c: Candidate) -> Optional[dict]:
        try:
            with _ydl() as y:
                return y.extract_info(f"https://api.soundcloud.com/tracks/{c.id}", download=False)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        for c, info in zip(todo, pool.map(lookup, todo)):
            if info:
                for k, v in _meta(info).items():
                    if v:
                        setattr(c, k, v)

    # 4) filter + rank
    good = [c for c in cands.values()
            if c.duration and 120 <= c.duration <= 540 and not NOT_A_TRACK.search(c.title)
            and not JUNK.search(c.title) and _fits_style(c, cfg)]
    if not good:
        return []
    max_seed = max(len(c.seeds) for c in good) or 1
    max_likes = max(math.log1p(c.likes) for c in good) or 1
    for c in good:
        pop = math.log1p(c.likes) / max_likes
        ratio = min(1.0, (c.likes / c.plays) * 20) if c.plays else 0.0  # 5% likes/plays = great
        taste = len(c.seeds) / max_seed
        fav = 1.0 if _has_word(f" {c.uploader} {c.title} ".lower(), favs) else 0.0
        c.score = round(0.35 * taste + 0.35 * pop + 0.15 * ratio + 0.15 * fav, 3)
        reasons = []
        if c.seeds:
            reasons.append(f"related to {len(c.seeds)} of your tracks ({', '.join(c.seeds[:2])}"
                           f"{'…' if len(c.seeds) > 2 else ''})")
        if c.via_search:
            reasons.append(f"found searching {c.via_search}")
        reasons.append(f"{c.likes:,} likes")
        c.why = "; ".join(reasons)
        c.mood_guess = _mood_guess(c, cfg)
    good.sort(key=lambda c: -c.score)
    # variety: at most 3 tracks per uploader and per (favourite) artist name in the title
    picked, count = [], defaultdict(int)
    for c in good:
        keys = [f"u:{c.uploader.lower()}"] + [f"a:{a.lower()}" for a in favs if _has_word(f" {c.title} ".lower(), [a])]
        if any(count[k] >= 3 for k in keys):
            continue
        for k in keys:
            count[k] += 1
        picked.append(c)
        if len(picked) >= results:
            break
    return picked


def save(cands: Sequence[Candidate], path: Path = DISCOVER_PATH) -> Path:
    from ..storage import write_json

    return write_json(path, {"made_at": datetime.now().isoformat(timespec="seconds"),
                             "tracks": [asdict(c) for c in cands]})


def load(path: Path = DISCOVER_PATH) -> Optional[dict]:
    from ..storage import read_json

    data = read_json(path)
    return data if isinstance(data, dict) else None
