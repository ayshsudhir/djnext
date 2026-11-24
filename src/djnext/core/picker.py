"""The one job: from your SoundCloud likes (one genre list at a time), pick what plays next, so the floor never stops.

For every possible 'A then B' djnext checks, in this order:
  1. Can it be mixed at all?  Tempo within 6% (no half/double-time tricks) and a compatible key
     (same, one step on the Camelot wheel, or the relative major/minor). Anything else is never picked.
  2. Has it been tested?  Real DJs played B straight after A (MixesDB tracklists of professional DJ sets).
     (Your own past sets are deliberately NOT used: only what pro DJs do and the music itself count.)
  3. Same groove?  The two tracks turn up in the same DJ sets, or DJs who play A also play B's artist.
  4. Will the blend be clean?  B has a long intro to lay over A's outro (rekordbox phrase analysis).
  5. Does it keep the flow?  Small tempo steps, energy building the way the playlist should,
     no artist twice within 3 tracks, and a mix of well-known tunes and deeper cuts.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import names
from .camelot import key_steps
from .models import Track
from .structure import PEAK_LABELS

MIN_S, MAX_S = 120, 15 * 60  # shorter = a preview clip, longer = a recorded DJ set

MAX_TEMPO_GAP = 0.05  # beyond ~5% pitched vocals and synths start to sound wrong (the FLX4 allows 6%)
COMFY_TEMPO_GAP = 0.02  # up to 2% nobody on the floor notices
KNOWN_SETS = 5  # found in at least this many DJ sets = a tune people know


@dataclass
class Evidence:
    """Everything djnext knows about which tracks go together."""
    dj_direct: Dict[Tuple[str, str], int] = field(default_factory=dict)  # (a, b): DJs played a then b
    dj_near: Dict[frozenset, int] = field(default_factory=dict)
    dj_same_set: Dict[frozenset, int] = field(default_factory=dict)
    artist_affinity: Dict[Tuple[str, str], float] = field(default_factory=dict)
    dj_plays: Dict[str, int] = field(default_factory=dict)  # track id -> DJ sets it was found in
    blocked: Set[Tuple[str, str]] = field(default_factory=set)  # transitions you said don't work

    @classmethod
    def build(cls, dj=None, blocked: Iterable[Tuple[str, str]] = ()):
        ev = cls(blocked=set(map(tuple, blocked)))
        if dj is not None:
            ev.dj_direct, ev.dj_near, ev.dj_same_set = dict(dj.direct), dict(dj.near), dict(dj.same_set)
            ev.artist_affinity, ev.dj_plays = dict(dj.artist_affinity), dict(dj.plays)
        return ev


# ---------- the pool ----------

def pool(likes: Sequence[Track], removed: Iterable[str] = ()) -> Tuple[List[Track], Dict[str, int]]:
    """Your liked tracks that djnext can use: analysed in rekordbox, a real track (not a clip or a DJ set),
    not removed by you, and only one upload of each song. (Which genre list each one is in: core/genres.py.)"""
    removed = set(removed)
    counts = {"likes": len(likes), "not_analysed": 0, "not_a_track": 0, "removed": 0, "duplicate": 0}
    out: List[Track] = []
    seen: Set[Tuple[str, ...]] = set()

    def song(t: Track) -> Tuple[str, ...]:
        n = names.of(t)
        return n.title + n.version

    removed_songs = {song(t) for t in likes if t.id in removed} - {()}
    for t in likes:
        if t.id in removed or song(t) in removed_songs:  # "don't use" covers every upload of that song
            counts["removed"] += 1
        elif t.bpm <= 0 or not t.key:
            counts["not_analysed"] += 1
        elif t.duration and not MIN_S <= t.duration <= MAX_S:
            counts["not_a_track"] += 1
        else:
            s = song(t)
            if s and s in seen:
                counts["duplicate"] += 1
                continue
            seen.add(s)
            out.append(t)
    return out, counts


# ---------- one track after another ----------

def tempo_gap(a: Track, b: Track) -> float:
    return abs(b.bpm - a.bpm) / a.bpm if a.bpm > 0 and b.bpm > 0 else 1.0


def intro_bars(t: Track) -> Optional[int]:
    """Bars before the first drop: how much room there is to blend this track in."""
    st = t.structure
    if st is None or not st.phrases:
        return None
    bar = 4 * 60.0 / (st.bpm or t.bpm or 125.0)
    peak = next((p for p in st.phrases[1:] if p.label in PEAK_LABELS), None)
    end = peak.start_s if peak else st.phrases[min(1, len(st.phrases) - 1)].end_s
    return int(round((end - st.phrases[0].start_s) / bar))


def outro_bars(t: Track) -> Optional[int]:
    st = t.structure
    if st is None or not st.phrases:
        return None
    bar = 4 * 60.0 / (st.bpm or t.bpm or 125.0)
    peaks = [p for p in st.phrases if p.label in PEAK_LABELS]
    if not peaks:
        return None
    return int(round((st.phrases[-1].end_s - peaks[-1].end_s) / bar))


def _credits(t: Track) -> Set[str]:
    n = names.of(t)
    return set(n.artists) | ({" ".join(n.version)} if n.version else set())


def same_artist(a: Track, b: Track) -> bool:
    """Shares an artist or remixer (Max Styler's remix of Deceiver and Max Styler's own track count as the same)."""
    return bool(_credits(a) & _credits(b))


def mixable(a: Track, b: Track, max_key_steps: int = 1) -> bool:
    if a.id == b.id or tempo_gap(a, b) > MAX_TEMPO_GAP:
        return False
    if a.key and b.key and key_steps(a.key, b.key) > max_key_steps:
        return False
    return True


@dataclass
class Move:
    """Playing `b` after `a`: how good it is and why."""
    track: Track
    score: float
    reasons: List[str]
    parts: Dict[str, float] = field(default_factory=dict)

    @property
    def why(self) -> str:
        return " · ".join(self.reasons)


def _times(n: int) -> str:
    return "once" if n == 1 else "twice" if n == 2 else f"{n}×"


def move(a: Track, b: Track, ev: Evidence) -> Move:
    """How good is b straight after a? (only call for mixable pairs)"""
    parts: Dict[str, float] = {}
    tested: List[Tuple[float, str]] = []  # (strength, reason): the best one or two are shown

    gap = tempo_gap(a, b)
    parts["tempo"] = -3.0 * max(0.0, gap - COMFY_TEMPO_GAP / 2) ** 2 / (MAX_TEMPO_GAP - COMFY_TEMPO_GAP / 2) ** 2
    steps = key_steps(a.key, b.key) if a.key and b.key else None
    parts["key"] = {0: 0.6, 1: 0.2}.get(steps, -0.5) if steps is not None else -0.3

    n = ev.dj_direct.get((a.id, b.id), 0)
    if n:
        parts["dj_pair"] = 3.0 * math.log2(1 + n)
        tested.append((parts["dj_pair"], f"real DJs played it straight after this {_times(n)}"))
    back = ev.dj_direct.get((b.id, a.id), 0)
    if back and not n:
        parts["dj_pair_reversed"] = 1.5 * math.log2(1 + back)
        tested.append((parts["dj_pair_reversed"], f"DJs mix these two together ({_times(back)}, other way round)"))
    pair = frozenset((a.id, b.id))
    near, same = ev.dj_near.get(pair, 0), ev.dj_same_set.get(pair, 0)
    if near and not (n or back):
        parts["dj_near"] = 1.2 * math.log2(1 + near)
        tested.append((parts["dj_near"], f"DJs played these close together in {near} set{'s' if near > 1 else ''}"))
    elif same and not (n or back):
        parts["dj_same_set"] = 0.6 * math.log2(1 + same)
        tested.append((parts["dj_same_set"], f"in the same DJ set{'s' if same > 1 else ''} ({same})"))
    aff = (ev.artist_affinity.get((a.id, b.id), 0.0) + ev.artist_affinity.get((b.id, a.id), 0.0)) / 2
    if aff > 0:
        parts["same_scene"] = 1.5 * aff
        if not (n or back or near or same):
            artist = (names.of(b).artists or ("",))[0].title()
            tested.append((parts["same_scene"], f"DJs who play this also play {artist}"))
    if (a.id, b.id) in ev.blocked:
        parts["you_said_no"] = -20.0

    ib, oa = intro_bars(b), outro_bars(a)
    blend: Optional[str] = None
    if ib is not None:
        if ib >= 16:
            parts["intro"] = 0.6
            blend = f"{ib}-bar intro, easy to blend"
        elif ib < 8:
            parts["intro"] = -0.8
            blend = f"short intro ({ib} bars): bring it in on a phrase change"
    if oa is not None and oa < 8:
        parts["outro"] = -0.3

    shown = [r for _, r in sorted(tested, reverse=True)[:2]]
    sign = "+" if b.bpm >= a.bpm else "−"
    key_txt = (f"{a.key}→{b.key}" + (" same key" if steps == 0 else " in key")) if steps is not None else "key unknown"
    basics = f"{a.bpm:.0f}→{b.bpm:.0f} BPM ({sign}{gap * 100:.1f}%), {key_txt}"
    reasons = shown + [basics] + ([blend] if blend else [])
    return Move(b, sum(parts.values()), reasons, parts)


# ---------- energy and the playlist shape ----------

def energy_levels(tracks: Sequence[Track]) -> Dict[str, float]:
    """0 (deepest) .. 1 (hardest) within these tracks: from tempo and how much of each track is drops."""
    if not tracks:
        return {}

    def drop_share(t: Track) -> float:
        st = t.structure
        if st is None or not st.phrases or not st.end_s:
            return 0.45
        return sum(p.end_s - p.start_s for p in st.phrases if p.label in PEAK_LABELS) / st.end_s

    def ranks(xs: List[float]) -> List[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        for pos, i in enumerate(order):
            r[i] = pos / max(1, len(xs) - 1)
        return r

    br, dr = ranks([t.bpm for t in tracks]), ranks([drop_share(t) for t in tracks])
    return {t.id: 0.6 * b + 0.4 * d for t, b, d in zip(tracks, br, dr)}


SHAPES = {
    "build": "Warm up, then build",  # start deep, climb to the hardest tracks by ~70%, stay up there
    "peak": "Peak time",  # stay high, small waves
}


def target_energy(i: int, n: int, shape: str) -> float:
    x = i / max(1, n - 1)
    if shape == "peak":
        return 0.75 + 0.1 * math.sin(x * math.pi * 3)
    return 0.15 + 0.75 * min(1.0, x / 0.7)


# ---------- the playlist ----------

@dataclass
class Step:
    track: Track
    why: str  # why it follows the track before
    score: float = 0.0
    known: bool = False  # a tune DJs play a lot


@dataclass
class Playlist:
    steps: List[Step]
    shape: str

    @property
    def tracks(self) -> List[Track]:
        return [s.track for s in self.steps]


def _flow_penalty(seq: Sequence[Track], b: Track, energy: Dict[str, float], i: int, n: int, shape: str,
                  ev: Evidence) -> float:
    p = -2.0 * (energy.get(b.id, 0.5) - target_energy(i, n, shape)) ** 2
    a = seq[-1]
    if b.bpm < a.bpm:  # the tempo should climb (build) or hold (peak), not saw up and down
        drop_pct = (a.bpm - b.bpm) / a.bpm * 100
        p -= (0.6 if shape == "build" else 0.3) * drop_pct
    for prev in seq[-3:-1]:  # (straight after is ruled out in build)
        if same_artist(prev, b):
            p -= 4.0
    if len(seq) >= 2:  # 3 crowd-pleasers in a row gets predictable, 3 unknowns in a row loses people
        known = [ev.dj_plays.get(t.id, 0) >= KNOWN_SETS for t in seq[-2:]]
        b_known = ev.dj_plays.get(b.id, 0) >= KNOWN_SETS
        if known[0] == known[1] == b_known:
            p -= 0.7
    return p


def build(tracks: Sequence[Track], ev: Evidence, length: int = 12, start: Optional[Track] = None,
          shape: str = "build", beam: int = 16, avoid: Iterable[str] = ()) -> Playlist:
    """The best chain of `length` tracks (looking ahead, so one good pair doesn't lead into a dead end)."""
    avoid = set(avoid)
    tracks = [t for t in tracks if t.id not in avoid or (start is not None and t.id == start.id)]
    if not tracks:
        raise ValueError("No tracks to pick from.")
    length = max(2, min(length, len(tracks)))
    energy = energy_levels(tracks)
    moves: Dict[Tuple[str, str], Move] = {}

    def mv(a: Track, b: Track) -> Optional[Move]:
        k = (a.id, b.id)
        if k not in moves:
            moves[k] = move(a, b, ev) if mixable(a, b) else None
        return moves[k]

    if start is not None:
        beams = [([start], 0.0)]
    else:
        def opener(t: Track) -> float:
            links = sorted((m.score for b in tracks if (m := mv(t, b)) is not None), reverse=True)[:3]
            return (-2.0 * (energy.get(t.id, 0.5) - target_energy(0, length, shape)) ** 2
                    + 0.3 * sum(links) / 3 if links else -5.0)
        beams = [([t], opener(t)) for t in sorted(tracks, key=opener, reverse=True)[:beam]]

    for i in range(1, length):
        grown = []
        for seq, total in beams:
            used = {t.id for t in seq}
            a = seq[-1]
            options = [(b, m) for b in tracks if b.id not in used and (m := mv(a, b)) is not None]
            varied = [(b, m) for b, m in options if not same_artist(a, b)]  # never the same artist twice in a row
            options = varied or options
            if not options:  # nothing in key: allow two steps on the wheel rather than stopping
                options = [(b, move(a, b, ev)) for b in tracks if b.id not in used and mixable(a, b, 2)]
            for b, m in options:
                grown.append((seq + [b], total + m.score + _flow_penalty(seq, b, energy, i, length, shape, ev)))
        if not grown:
            break
        grown.sort(key=lambda x: x[1], reverse=True)
        beams = grown[:beam]

    best = beams[0][0]
    steps = [Step(best[0], "opener", known=ev.dj_plays.get(best[0].id, 0) >= KNOWN_SETS)]
    for a, b in zip(best, best[1:]):
        m = mv(a, b) or move(a, b, ev)
        steps.append(Step(b, m.why, m.score, ev.dj_plays.get(b.id, 0) >= KNOWN_SETS))
    return Playlist(steps, shape)


def alternatives(prev: Track, nxt: Optional[Track], tracks: Sequence[Track], ev: Evidence, used: Iterable[str],
                 top: int = 5) -> List[Move]:
    """Other tracks that could go in this slot: mix well after `prev` (and into `nxt`, if there is one)."""
    used = set(used)
    out = []
    for b in tracks:
        if b.id in used or not mixable(prev, b) or same_artist(prev, b) or (nxt is not None and same_artist(b, nxt)):
            continue
        m = move(prev, b, ev)
        if nxt is not None:
            if not mixable(b, nxt, 2):
                continue
            m.score += 0.5 * move(b, nxt, ev).score
        out.append(m)
    return sorted(out, key=lambda m: m.score, reverse=True)[:top]
