"""Sort your likes into genre lists, without listening to them.

Three clues, added up:
  1. the genres of the DJ sets the track was played in (MixesDB tags its sets: Tech House, Techno, Deep House ...)
  2. the genre tag in rekordbox / SoundCloud (often messy or empty, so it only counts as one clue)
  3. the tempo (above ~137 BPM it's not groovy anything; below ~118 it's not a club track)
You can always move a track to another list yourself; that choice wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Track

GENRES: List[Tuple[str, str]] = [
    ("groovy-techno", "Groovy techno"),
    ("tech-house", "Tech house"),
    ("house", "House"),
    ("indie-melodic", "Indie dance & melodic"),
    ("hard-fast", "Hard & fast"),
    ("other", "Other"),
]
NAMES = dict(GENRES)

# MixesDB set categories -> (genre, weight). Progressive House is tagged on lots of radio shows, so it counts less.
SET_TAGS: Dict[str, Tuple[str, float]] = {
    "Techno": ("techno", 1.0), "Minimal": ("techno", 0.8), "Hard Techno": ("hard-fast", 1.0),
    "Acid Techno": ("techno", 0.8), "Detroit Techno": ("techno", 1.0), "Industrial Techno": ("hard-fast", 1.0),
    "Tech House": ("tech-house", 1.0),
    "House": ("house", 0.6), "Deep House": ("house", 1.0), "Disco": ("house", 0.8), "Nu Disco": ("house", 0.8),
    "Euro House": ("other", 0.6), "Funky House": ("house", 1.0), "Soulful House": ("house", 1.0),
    "Garage": ("house", 0.8), "UK Garage": ("house", 0.8), "Bassline": ("house", 0.6), "Jacked": ("tech-house", 0.6),
    "Progressive House": ("indie-melodic", 0.4), "Progressive": ("indie-melodic", 0.4),
    "Melodic Techno": ("indie-melodic", 1.0), "Indie Dance": ("indie-melodic", 1.0), "Organic House": ("indie-melodic", 1.0),
    "Afro House": ("indie-melodic", 1.0), "Downtempo": ("indie-melodic", 0.8), "Balearic": ("indie-melodic", 0.8),
    "Electronica": ("indie-melodic", 0.6),
    "Trance": ("hard-fast", 0.8), "Psytrance": ("hard-fast", 1.0), "Hard Dance": ("hard-fast", 1.0),
    "Drum & Bass": ("hard-fast", 1.0), "Dubstep": ("hard-fast", 1.0), "Hardstyle": ("hard-fast", 1.0),
    "Breaks": ("hard-fast", 0.6),
    "EDM": ("other", 1.0), "Big Room": ("other", 1.0), "Electro House": ("other", 0.8), "Pop": ("other", 1.0),
    "Hip Hop": ("other", 1.0), "Commercial": ("other", 1.0),
}

# words in the rekordbox/SoundCloud genre tag -> genre (checked in this order, first hit wins)
TAG_WORDS: List[Tuple[Tuple[str, ...], str]] = [
    (("pop", "hip hop", "hip-hop", "rap", "r&b", "edm", "reggaeton", "rock", "country", "soundtrack",
      "ambient", "classical", "jazz", "funk carioca"), "other"),
    (("tech house", "techhouse", "tech-house", "deep tech", "minimal", "jackin"), "tech-house"),
    (("melodic", "indie", "afro", "organic", "progressive", "downtempo", "electronica"), "indie-melodic"),
    (("hard", "trance", "drum", "d&b", "dnb", "dubstep", "psy", "bass music", "breaks"), "hard-fast"),
    (("techno",), "techno"),
    (("deep house", "house", "disco", "garage", "funk", "soul"), "house"),
]


@dataclass
class Verdict:
    genre: str
    sure: bool  # False = a guess from tempo alone (or a close call): worth checking
    why: str


def _techno_split(bpm: float) -> str:
    return "hard-fast" if bpm > 137 else "groovy-techno"


def classify(t: Track, set_categories: Sequence[Sequence[str]] = ()) -> Verdict:
    score: Dict[str, float] = {g: 0.0 for g, _ in GENRES}
    clues: List[str] = []

    votes: Dict[str, float] = {}
    for cats in set_categories:
        for c in cats:
            if c in SET_TAGS:
                g, w = SET_TAGS[c]
                g = _techno_split(t.bpm) if g == "techno" else g
                votes[g] = votes.get(g, 0.0) + w
    total = sum(votes.values())
    if total:
        for g, v in votes.items():
            score[g] += 3.0 * v / total  # DJ sets are the strongest clue, worth 3 points in all
        top = max(votes, key=votes.get)
        clues.append(f"played in {len(set_categories)} DJ set{'s' if len(set_categories) != 1 else ''}, mostly {NAMES[top].lower()}")

    tag = (t.genre or "").lower().strip()
    if tag:
        for words, g in TAG_WORDS:
            if any(w in tag for w in words):
                g = _techno_split(t.bpm) if g == "techno" else g
                score[g] += 2.5 if g == "other" else 1.5  # "Indie Pop" at 164 BPM is still pop
                clues.append(f"tagged “{t.genre}”")
                break

    bpm = t.bpm
    if bpm > 137:
        score["hard-fast"] += 2.0
    elif 0 < bpm < 118:
        score["other"] += 1.5
    elif bpm <= 124:
        score["house"] += 0.5
        score["indie-melodic"] += 0.4
    else:
        score["tech-house"] += 0.3  # 125-136 with no other clue: the middle of your style
        score["groovy-techno"] += 0.4 if bpm >= 129 else 0.0
        score["tech-house"] += 0.3 if bpm <= 128 else 0.0

    ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    best, second = ranked[0], ranked[1]
    sure = bool(clues) and best[1] - second[1] >= 0.75
    why = " · ".join(clues) if clues else f"guessed from the tempo ({bpm:.0f} BPM)"
    return Verdict(best[0], sure, why)


def sort_likes(tracks: Sequence[Track], categories_of: Dict[str, List[List[str]]],
               overrides: Optional[Dict[str, str]] = None) -> Dict[str, Verdict]:
    """track id -> Verdict. `categories_of`: track id -> the category lists of the DJ sets it was found in."""
    from . import names

    overrides = overrides or {}
    out: Dict[str, Verdict] = {}
    for t in tracks:
        if overrides.get(t.id) in NAMES:
            out[t.id] = Verdict(overrides[t.id], True, "you put it here")
        else:
            out[t.id] = classify(t, categories_of.get(t.id, []))
    # a guess follows the artist / label: if their other tracks are clearly in one list, so is this one
    who: Dict[str, Dict[str, int]] = {}
    credits = {t.id: set(names.of(t).artists) for t in tracks}
    for t in tracks:
        if out[t.id].sure:
            for a in credits[t.id]:
                who.setdefault(a, {}).setdefault(out[t.id].genre, 0)
                who[a][out[t.id].genre] += 1
    for t in tracks:
        if out[t.id].sure:
            continue
        votes: Dict[str, int] = {}
        for a in credits[t.id]:
            for g, n in who.get(a, {}).items():
                votes[g] = votes.get(g, 0) + n
        if votes:
            g = max(votes, key=votes.get)
            if votes[g] >= 2 * (sum(votes.values()) - votes[g]) and (g != "hard-fast" or t.bpm > 132):
                artist = next(a for a in credits[t.id] if g in who.get(a, {}))
                out[t.id] = Verdict(g, False, f"like your other {artist.title()} tracks")
    return out
