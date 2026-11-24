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
    sure: bool  # False = a guess (few clues, or a close call): worth checking
    why: str
    tag_genre: Optional[str] = None  # the genre the track's own tag points to, if any


def _techno_split(bpm: float) -> str:
    return "hard-fast" if bpm > 137 else "groovy-techno"


def tag_genre(t: Track) -> Optional[str]:
    tag = (t.genre or "").lower().strip()
    for words, g in TAG_WORDS:
        if tag and any(w in tag for w in words):
            return _techno_split(t.bpm) if g == "techno" else g
    return None


def classify(t: Track, set_categories: Sequence[Sequence[str]] = (), artist_votes: Optional[Dict[str, float]] = None,
             artist_name: str = "") -> Verdict:
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
            score[g] += 3.0 * v / total  # up to 3 points, shared by the genres of the sets it was played in
        top = max(votes, key=votes.get)
        clues.append(f"played in {len(set_categories)} DJ set{'s' if len(set_categories) != 1 else ''}, mostly {NAMES[top].lower()}")

    tg = tag_genre(t)
    if tg:
        # a specific tag ("Indie Dance", "Tech House", "Techno", "Pop") beats MixesDB's catch-all "House" sets
        score[tg] += 1.5 if tg == "house" else 2.5
        clues.append(f"tagged “{t.genre}”")

    if artist_votes:
        n = sum(artist_votes.values())
        for g, v in artist_votes.items():
            score[g] += 2.5 * v / n
        clues.append(f"like your other {artist_name} tracks")

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
    sure = bool(clues) and best[1] - second[1] >= 0.75 and (bool(tg) or total >= 3 or bool(artist_votes))
    why = " · ".join(clues) if clues else f"guessed from the tempo ({bpm:.0f} BPM)"
    return Verdict(best[0], sure, why, tg)


def sort_likes(tracks: Sequence[Track], categories_of: Dict[str, List[List[str]]],
               overrides: Optional[Dict[str, str]] = None) -> Dict[str, Verdict]:
    """track id -> Verdict. `categories_of`: track id -> the category lists of the DJ sets it was found in.

    Tracks without a useful tag of their own follow their artist / label: if your other Maccabi House tracks are
    tagged indie dance (or you put them there), an untagged Maccabi House edit goes there too."""
    from . import names

    overrides = overrides or {}
    credits = {t.id: list(names.of(t).artists) for t in tracks}
    tags = {t.id: tag_genre(t) for t in tracks}
    # what each artist / label is, from tracks with real evidence: your own choices count double, tags once
    who: Dict[str, Dict[str, float]] = {}
    for t in tracks:
        g, w = (overrides[t.id], 2.0) if overrides.get(t.id) in NAMES else (tags[t.id], 1.0)
        if g and g != "other":
            for a in credits[t.id]:
                who.setdefault(a, {})
                who[a][g] = who[a].get(g, 0.0) + w
    out: Dict[str, Verdict] = {}
    for t in tracks:
        if overrides.get(t.id) in NAMES:
            out[t.id] = Verdict(overrides[t.id], True, "you put it here", tags[t.id])
            continue
        votes: Dict[str, float] = {}
        name = ""
        if not tags[t.id]:
            for a in credits[t.id]:
                for g, n in who.get(a, {}).items():
                    votes[g] = votes.get(g, 0.0) + n
                    name = name or a.title()
        out[t.id] = classify(t, categories_of.get(t.id, []), votes or None, name)
    return out
