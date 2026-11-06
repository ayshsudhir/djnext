"""Moods: "what do you want to hear?" -> which tracks fit, and which energy shape the set follows.

Every mood is a set of soft preferences (tempo, intensity, how much of the track is drops, words in the
title/genre, track length ...) plus a few hard rules (BPM range, required words). Each track gets a fit
score 0..1 per mood; tracks above the mood's threshold belong to it. A track can be in several moods.
All moods are defined in config.yaml (`moods:`), with the defaults below as a fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Track

EDIT_RE = re.compile(r"\b(edit|bootleg|mashup|flip|rework|vip|refix)\b|\sx\s", re.IGNORECASE)
VOCAL_RE = re.compile(r"\b(feat\.?|ft\.?|featuring|vocal|vox)\b", re.IGNORECASE)


@dataclass
class Mood:
    key: str
    name: str
    emoji: str = ""
    ask: str = ""  # one-line description shown when choosing
    bpm: Tuple[float, float] = (0, 999)  # hard range (optional; the style's BPM range already applies)
    tempo: Optional[Tuple[float, float]] = None  # preferred place in YOUR tempo range: 0 = slowest, 1 = fastest
    words: List[str] = field(default_factory=list)  # bonus when any appears in title/artist/genre
    words_weight: float = 0.5
    required_words: List[str] = field(default_factory=list)  # hard: at least one must appear
    exclude_words: List[str] = field(default_factory=list)  # hard: none may appear
    intensity: Optional[Tuple[float, float]] = None  # preferred range 0..1 (relative to your library)
    drop_share: Optional[Tuple[float, float]] = None  # preferred share of the track that is drops
    edit_weight: float = 0.0  # prefer edits/bootlegs/mashups of known songs
    vocal_weight: float = 0.0  # prefer tracks with vocals (feat./vocal in title)
    long_weight: float = 0.0  # prefer longer tracks (afters)
    favourite_weight: float = 0.0  # prefer your favourite artists
    threshold: float = 0.6
    curve: str = "classic-1h"

    @property
    def label(self) -> str:
        return f"{self.emoji} {self.name}".strip()


# Defaults are flavours of tech house / groovy techno. Tempo is relative to your style's BPM range,
# so the same moods work for a friend whose range is different.
DEFAULT_MOODS: Dict[str, dict] = {
    "warmup": dict(name="Warm-up groove", emoji="🌅", ask="Deeper, rolling, easy. Early in the night or a chill session.",
                   tempo=[0.0, 0.4], intensity=[0.0, 0.45], drop_share=[0.0, 0.45],
                   words=["deep", "melodic", "afro", "organic", "groove", "minimal", "dub"], words_weight=0.5,
                   curve="chill"),
    "pregame": dict(name="Pregame", emoji="🍻", ask="Groovy, vocal tech house. Getting ready, friends coming over.",
                    tempo=[0.1, 0.6], intensity=[0.25, 0.65], vocal_weight=0.7,
                    words=["house", "disco", "funk", "garage", "groove"], words_weight=0.4, curve="pregame"),
    "drunk": dict(name="Drunk asf", emoji="🥴", ask="Tech house edits of songs everyone knows. Hands up, screaming.",
                  edit_weight=2.0, vocal_weight=0.3, intensity=[0.5, 1.0], drop_share=[0.45, 1.0],
                  words=["remix", "anthem"], words_weight=0.3, threshold=0.62, curve="drunk"),
    "banging": dict(name="Banging", emoji="🔥", ask="Peak-time tech house. No breaks, all killer.",
                    intensity=[0.6, 1.0], drop_share=[0.5, 1.0], favourite_weight=0.6,
                    words=["tech house", "techhouse"], words_weight=0.3, curve="peak-time"),
    "afters": dict(name="Afters", emoji="🌙", ask="Hypnotic, minimal, rolling. 4am, nobody's leaving.",
                   tempo=[0.4, 1.0], drop_share=[0.0, 0.5], intensity=[0.35, 0.8], long_weight=0.5,
                   words=["minimal", "deep tech", "groove", "groovy", "hypnotic", "rominimal", "micro", "dub"],
                   words_weight=0.7, curve="afters"),
    "groovy_techno": dict(name="Groovy techno", emoji="⚡", ask="The techno end of your range: driving and groovy.",
                          tempo=[0.55, 1.0], intensity=[0.45, 1.0],
                          words=["techno", "groove", "groovy", "acid", "hypnotic", "rave"], words_weight=0.8,
                          threshold=0.65, curve="techno"),
}

DEFAULT_MOOD_CURVES: Dict[str, List[List[float]]] = {
    "chill": [[0.0, 2.5], [0.5, 4.5], [1.0, 4.0]],
    "pregame": [[0.0, 3.5], [0.6, 6.0], [1.0, 7.0]],
    "drunk": [[0.0, 6.0], [0.25, 8.5], [0.45, 7.0], [0.7, 9.0], [0.85, 7.5], [1.0, 9.5]],
    "afters": [[0.0, 5.0], [0.3, 6.5], [0.7, 7.0], [1.0, 6.5]],
    "techno": [[0.0, 6.0], [0.5, 8.5], [1.0, 9.5]],
    "peak-time": [[0.0, 6.5], [0.3, 8.5], [0.6, 7.5], [1.0, 9.5]],
}


def load_moods(raw: Optional[Dict[str, dict]]) -> Dict[str, Mood]:
    raw = raw or DEFAULT_MOODS
    moods = {}
    for key, d in raw.items():
        d = dict(d)
        for rng in ("bpm", "tempo", "intensity", "drop_share"):
            if d.get(rng) is not None:
                d[rng] = tuple(float(x) for x in d[rng])
        moods[key] = Mood(key=key, **d)
    return moods


# ---------- features ----------

def _drop_share(t: Track) -> float:
    st = t.structure
    if st is None or not st.phrases or not st.end_s:
        return 0.45
    return sum(p.end_s - p.start_s for p in st.phrases if p.label in ("Drop", "Chorus")) / st.end_s


def _ranks(values: Sequence[float]) -> List[float]:
    """0..1 rank of each value; equal values share the same (average) rank."""
    n = len(values)
    if n < 2:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    r = [0.0] * n
    pos = 0
    while pos < n:
        end = pos
        while end + 1 < n and values[order[end + 1]] == values[order[pos]]:
            end += 1
        avg = (pos + end) / 2 / (n - 1)
        for k in range(pos, end + 1):
            r[order[k]] = avg
        pos = end + 1
    return r


@dataclass
class Features:
    bpm: float
    tempo: float  # 0..1 rank of the BPM within the pool
    intensity: float  # 0..1 relative to the pool (or rating-based when the track has a real energy value)
    drop_share: float
    text: str
    is_edit: bool
    has_vocal: bool
    minutes: float


def features(tracks: Sequence[Track]) -> Dict[str, Features]:
    tracks = list(tracks)
    drops = [_drop_share(t) for t in tracks]
    bpm_r, drop_r = _ranks([t.bpm for t in tracks]), _ranks(drops)
    out = {}
    for t, d, br, dr in zip(tracks, drops, bpm_r, drop_r):
        if t.energy is not None and t.energy_source in ("comment", "rating", "given"):
            inten = max(0.0, min(1.0, t.energy / 10.0))
        else:
            inten = 0.6 * br + 0.4 * dr
        text = f" {t.artist} {t.title} {t.genre} ".lower()
        out[t.id] = Features(t.bpm, br, inten, d, text, bool(EDIT_RE.search(t.title or "")),
                             bool(VOCAL_RE.search(t.title or "")), t.duration / 60.0)
    return out


def _has_word(text: str, words: Sequence[str]) -> bool:
    """True if any of the words/phrases appears as a whole word (so "tere" doesn't match "stereo")."""
    for w in words:
        w = w.strip().lower()
        if w and re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", text):
            return True
    return False


def _range_score(v: float, rng: Tuple[float, float], soft: float) -> float:
    lo, hi = rng
    dist = lo - v if v < lo else v - hi if v > hi else 0.0
    return max(0.0, 1.0 - dist / soft)


def fit(t: Track, f: Features, mood: Mood, favourites: Sequence[str] = ()) -> Optional[float]:
    """0..1 how well a track fits a mood, or None if it breaks a hard rule."""
    lo, hi = mood.bpm
    if not lo <= f.bpm <= hi:
        return None
    if mood.required_words and not _has_word(f.text, mood.required_words):
        return None
    if mood.exclude_words and _has_word(f.text, mood.exclude_words):
        return None
    parts: List[Tuple[float, float]] = []  # (score, weight)
    if mood.tempo:
        parts.append((_range_score(f.tempo, mood.tempo, 0.3), 0.8))
    if mood.intensity:
        parts.append((_range_score(f.intensity, mood.intensity, 0.35), 1.0))
    if mood.drop_share:
        parts.append((_range_score(f.drop_share, mood.drop_share, 0.3), 0.7))
    if mood.words:
        parts.append((1.0 if _has_word(f.text, mood.words) else 0.0, mood.words_weight))
    if mood.edit_weight:
        parts.append((1.0 if f.is_edit else 0.0, mood.edit_weight))
    if mood.vocal_weight:
        parts.append((1.0 if f.has_vocal else 0.0, mood.vocal_weight))
    if mood.long_weight:
        parts.append((min(1.0, max(0.0, (f.minutes - 3.0) / 3.0)), mood.long_weight))
    if mood.favourite_weight and favourites:
        parts.append((1.0 if _has_word(f.text, favourites) else 0.0, mood.favourite_weight))
    if not parts:
        return 1.0
    total_w = sum(w for _, w in parts)
    return sum(s * w for s, w in parts) / total_w


def classify(tracks: Sequence[Track], moods: Dict[str, Mood], favourites: Sequence[str] = (),
             margin: float = 0.04) -> Dict[str, List[Tuple[Track, float]]]:
    """For each mood: the tracks that fit it, best first. Each track goes to its best-fitting mood, and also
    to any other mood it fits almost as well (within `margin`), so the moods stay distinct."""
    feats = features(tracks)
    out: Dict[str, List[Tuple[Track, float]]] = {k: [] for k in moods}
    for t in tracks:
        f = feats[t.id]
        scores = {}
        for key, mood in moods.items():
            score = fit(t, f, mood, favourites)
            if score is not None and score >= mood.threshold:
                scores[key] = score
        if not scores:
            continue
        best = max(scores.values())
        for key, score in scores.items():
            if score >= best - margin:
                out[key].append((t, round(score, 3)))
    for key in out:
        out[key].sort(key=lambda x: -x[1])
    return out


def primary_mood(t: Track, result: Dict[str, List[Tuple[Track, float]]]) -> Optional[str]:
    best, best_s = None, -1.0
    for key, items in result.items():
        for tr, s in items:
            if tr.id == t.id and s > best_s:
                best, best_s = key, s
    return best
