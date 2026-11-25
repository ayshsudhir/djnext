"""Sort your likes into genre lists.

Clues, strongest first, added up:
  1. how it sounds: a music model listened to the whole track (see ingest/listen.py)
  2. the artist: what their other tracks in your likes sound like / where you put them
  3. the genres of the DJ sets the track was played in (MixesDB tags its sets: Tech House, Techno, Deep House ...)
  4. the genre tag in rekordbox / SoundCloud (often messy or empty: uploaders tag almost anything "Techno")
  5. the tempo, only to split techno from hard & fast (above ~137 BPM) and as a last tie-breaker
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

# what the model hears (Discogs styles, "Electronic---Techno") -> (genre, weight); "techno" splits by tempo
HEARD_ELECTRONIC: Dict[str, Tuple[str, float]] = {
    "Techno": ("techno", 1.0), "Minimal Techno": ("techno", 1.0), "Deep Techno": ("techno", 1.0),
    "Dub Techno": ("techno", 0.8), "Tech Trance": ("techno", 0.5), "Acid": ("techno", 0.6), "Tribal": ("techno", 0.5),
    "Industrial": ("techno", 0.4), "EBM": ("techno", 0.4), "Electro": ("tech-house", 0.4),
    "Hard Techno": ("hard-fast", 1.0), "Schranz": ("hard-fast", 1.0), "Gabber": ("hard-fast", 1.0),
    "Hardcore": ("hard-fast", 1.0), "Hardstyle": ("hard-fast", 1.0), "Happy Hardcore": ("hard-fast", 1.0),
    "Speedcore": ("hard-fast", 1.0), "Jumpstyle": ("hard-fast", 1.0), "Hard Trance": ("hard-fast", 1.0),
    "Hard House": ("hard-fast", 0.6), "Psy-Trance": ("hard-fast", 0.8), "Goa Trance": ("hard-fast", 0.8),
    "Trance": ("hard-fast", 0.4), "Drum n Bass": ("hard-fast", 1.0), "Jungle": ("hard-fast", 1.0),
    "Dubstep": ("hard-fast", 1.0), "Halftime": ("hard-fast", 0.8), "Breakcore": ("hard-fast", 1.0),
    "Breakbeat": ("hard-fast", 0.4), "Breaks": ("hard-fast", 0.4), "Hands Up": ("hard-fast", 0.8),
    "Makina": ("hard-fast", 1.0), "Donk": ("hard-fast", 0.8),
    "Tech House": ("tech-house", 1.0), "Minimal": ("tech-house", 0.7), "Bassline": ("tech-house", 0.9),
    "Ghetto House": ("tech-house", 0.8), "Ghetto": ("tech-house", 0.6), "Speed Garage": ("tech-house", 0.7),
    "Tribal House": ("tech-house", 0.7), "Electro House": ("tech-house", 0.8), "Juke": ("tech-house", 0.3),
    "House": ("house-ish", 1.0), "Deep House": ("house", 1.0), "Garage House": ("house", 0.9), "Disco": ("house", 0.9),
    "Nu-Disco": ("house", 0.8), "Italo House": ("house", 0.8), "Acid House": ("house", 0.6),
    "UK Garage": ("house", 0.8), "Hip-House": ("house", 0.6), "Euro House": ("house", 0.5), "Latin": ("house", 0.3),
    "Progressive House": ("indie-melodic", 0.9), "Progressive Trance": ("indie-melodic", 0.6),
    "Downtempo": ("indie-melodic", 1.0), "Synth-pop": ("indie-melodic", 0.6), "Darkwave": ("indie-melodic", 0.8),
    "New Wave": ("indie-melodic", 0.6), "Electroclash": ("indie-melodic", 0.7), "Leftfield": ("indie-melodic", 0.6),
    "Synthwave": ("indie-melodic", 0.6), "Chillwave": ("indie-melodic", 0.7), "Ambient": ("indie-melodic", 0.5),
    "Trip Hop": ("indie-melodic", 0.5), "IDM": ("indie-melodic", 0.4), "Balearic": ("indie-melodic", 0.8),
    "Dance-pop": ("other", 1.0), "Eurodance": ("other", 0.8), "Hip Hop": ("other", 1.0), "Euro-Disco": ("other", 0.5),
    "Big Beat": ("other", 0.3), "Vaporwave": ("other", 0.8), "Chiptune": ("other", 0.8),
}
# styles that only mean "hard & fast" when the track IS fast; at club-house tempos it's a trance-y lead or a
# wobbly bass in a tech house / techno track, so it leans techno there, weakly
ONLY_WHEN_FAST = {"Trance", "Psy-Trance", "Goa Trance", "Hard Trance", "Dubstep", "Halftime", "Breakbeat", "Breaks",
                  "Hands Up", "Drum n Bass", "Jungle"}
HEARD_OTHER_FAMILY = 0.6  # pop, hip hop, rock ...: weaker, the model hears a bit of these in lots of vocal dance tracks
HEARD_FAMILY: Dict[str, Tuple[str, float]] = {"Funk / Soul---Disco": ("house", 0.6), "Funk / Soul---Boogie": ("house", 0.4)}


def heard_genres(styles: Dict[str, float], bpm: float = 0.0) -> Dict[str, float]:
    """What the model heard, as shares of our genre lists (adding up to 1). {} = not heard."""
    votes: Dict[str, float] = {}
    for name, p in styles.items():
        family, _, style = name.partition("---")
        if name in HEARD_FAMILY:
            g, w = HEARD_FAMILY[name]
        elif family == "Electronic":
            g, w = HEARD_ELECTRONIC.get(style, (None, 0.0))
            if style in ONLY_WHEN_FAST and 0 < bpm <= 137:
                g, w = "techno", 0.25
        else:
            g, w = "other", HEARD_OTHER_FAMILY
        if g:
            g = _techno_split(bpm) if g == "techno" else g
            votes[g] = votes.get(g, 0.0) + p * w
    # Discogs calls most of today's tech house plain "House": the tempo and the track's other styles decide
    hi = votes.pop("house-ish", 0.0)
    if hi:
        lean = votes.get("tech-house", 0.0) - votes.get("house", 0.0)
        to_tech = 0.6 if bpm >= 126 else 0.25 if bpm >= 123 else 0.1
        to_tech = min(0.9, max(0.1, to_tech + 0.5 * lean))
        votes["tech-house"] = votes.get("tech-house", 0.0) + hi * to_tech
        votes["house"] = votes.get("house", 0.0) + hi * (1 - to_tech)
    total = sum(votes.values())
    return {g: v / total for g, v in votes.items()} if total else {}


def top_styles(styles: Dict[str, float], n: int = 2) -> str:
    best = sorted(styles.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return ", ".join(k.partition("---")[2] or k for k, _ in best)


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
             artist_name: str = "", heard: Optional[Dict[str, float]] = None) -> Verdict:
    """heard: the model's styles for this track (see ingest/listen.py), if it has listened to it."""
    score: Dict[str, float] = {g: 0.0 for g, _ in GENRES}
    clues: List[str] = []

    hv = heard_genres(heard or {}, t.bpm)
    if hv:
        for g, v in hv.items():
            score[g] += 5.0 * v  # the strongest clue: what it actually sounds like
        clues.append(f"sounds like {top_styles(heard)}")

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
            score[g] += 2.0 * v / total  # up to 2 points, shared by the genres of the sets it was played in
        top = max(votes, key=votes.get)
        clues.append(f"played in {len(set_categories)} DJ set{'s' if len(set_categories) != 1 else ''}, mostly {NAMES[top].lower()}")

    tg = tag_genre(t)
    if tg:
        # a specific tag ("Indie Dance", "Tech House", "Techno", "Pop") beats MixesDB's catch-all "House" sets
        score[tg] += (0.8 if tg in ("house", "groovy-techno") else 1.5) if hv else (1.5 if tg == "house" else 2.5)
        clues.append(f"tagged “{t.genre}”")

    if artist_votes:
        n = sum(artist_votes.values())
        for g, v in artist_votes.items():
            score[g] += 2.5 * v / n
        clues.append(f"like {artist_name}'s other tracks")

    bpm = t.bpm
    if bpm > 137:
        score["hard-fast"] += 2.0
    elif 0 < bpm < 118:
        score["other"] += 1.5
    elif bpm <= 124:
        score["house"] += 0.5
        score["indie-melodic"] += 0.4
    else:
        score["tech-house"] += 0.1  # 125-136 with no other clue: only a tie-breaker, never the reason

    ranked = sorted(score.items(), key=lambda kv: kv[1], reverse=True)
    best, second = ranked[0], ranked[1]
    sure = bool(clues) and best[1] - second[1] >= 0.75 and (bool(hv) or bool(tg) or total >= 3 or bool(artist_votes))
    why = " · ".join(clues) if clues else f"not heard yet, guessed from the tempo ({bpm:.0f} BPM)"
    return Verdict(best[0], sure, why, tg)


def sort_likes(tracks: Sequence[Track], categories_of: Dict[str, List[List[str]]],
               overrides: Optional[Dict[str, str]] = None,
               heard_of: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Verdict]:
    """track id -> Verdict. `categories_of`: track id -> the category lists of the DJ sets it was found in.
    `heard_of`: track id -> the styles the model heard.

    A track also follows its artist / label: what their OTHER tracks in your likes sound like (or where you put
    them, which counts double). If your other Maccabi House tracks are indie dance, a new Maccabi House edit leans
    that way too."""
    from . import names

    overrides = overrides or {}
    heard_of = heard_of or {}
    credits = {t.id: list(names.of(t).artists) for t in tracks}
    tags = {t.id: tag_genre(t) for t in tracks}
    # each track's own evidence about its artists: your choice (x2), else what it sounds like, else its tag
    own: Dict[str, Dict[str, float]] = {}
    for t in tracks:
        if overrides.get(t.id) in NAMES:
            own[t.id] = {overrides[t.id]: 2.0}
        elif heard_of.get(t.id):
            own[t.id] = heard_genres(heard_of[t.id], t.bpm)
        elif tags[t.id] and tags[t.id] != "other":
            own[t.id] = {tags[t.id]: 0.7}
    who: Dict[str, Dict[str, float]] = {}
    for t in tracks:
        for a in credits[t.id]:
            for g, w in own.get(t.id, {}).items():
                who.setdefault(a, {})
                who[a][g] = who[a].get(g, 0.0) + w
    out: Dict[str, Verdict] = {}
    for t in tracks:
        if overrides.get(t.id) in NAMES:
            out[t.id] = Verdict(overrides[t.id], True, "you put it here", tags[t.id])
            continue
        votes: Dict[str, float] = {}
        name = ""
        for a in credits[t.id]:
            others = dict(who.get(a, {}))
            for g, w in own.get(t.id, {}).items():  # not the track itself
                others[g] = others.get(g, 0.0) - w
            for g, n in others.items():
                if n > 1e-6:
                    votes[g] = votes.get(g, 0.0) + n
                    name = name or a.title()
        out[t.id] = classify(t, categories_of.get(t.id, []), votes or None, name, heard_of.get(t.id))
    return out
