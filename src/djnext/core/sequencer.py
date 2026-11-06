"""Turn a pool of tracks into an ordered set that follows the energy curve.

1. Greedy: walk through the set's time, always picking the cheapest next track.
2. Local search: reverse segments (2-opt), swap two tracks, or swap a track in from the
   unused pool, keeping any change that lowers the total cost of the set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..config import Config
from .energy_curve import EnergyCurve
from .models import Track
from .scoring import Transition, explain, same_song, transition


@dataclass
class Slot:
    track: Track
    start_s: float
    t_mid: float  # position in the set as a fraction 0..1 (middle of the track)
    target: float
    cost: Transition
    reason: str


@dataclass
class SetPlan:
    slots: List[Slot]
    total_cost: float
    length_s: float
    curve: EnergyCurve
    unused: List[Track] = field(default_factory=list)

    @property
    def tracks(self) -> List[Track]:
        return [s.track for s in self.slots]


def play_seconds(track: Track, cfg: Config) -> float:
    """How long a track is 'the main track' in the set before the next one takes over."""
    if track.structure is not None and track.structure.phrases:
        out = track.structure.natural_mix_out(cfg.max_play_seconds)  # e.g. start of its outro
        start = track.structure.intro.start_s if track.structure.intro else 0.0
        if out - start >= 60:
            return out - start
    full = track.duration if track.duration > 0 else cfg.max_play_seconds
    return max(60.0, min(full, cfg.max_play_seconds) - cfg.mix_overlap_seconds)


def evaluate(order: Sequence[Track], curve: EnergyCurve, cfg: Config, length_s: float) -> SetPlan:
    slots: List[Slot] = []
    elapsed, total = 0.0, 0.0
    prev: Optional[Track] = None
    for tr in order:
        p = play_seconds(tr, cfg)
        t_mid = min((elapsed + p / 2) / length_s, 1.0)
        target = curve.target(t_mid)
        cost = transition(prev, tr, target, curve.slope(t_mid), [s.track for s in slots], cfg)
        slots.append(Slot(tr, elapsed, t_mid, target, cost, explain(prev, tr, target, cfg)))
        total += cost.total
        elapsed += p
        prev = tr
    return SetPlan(slots, total, length_s, curve)


def _cost(order: Sequence[Track], curve: EnergyCurve, cfg: Config, length_s: float) -> float:
    """Same total as evaluate(), without building explanation strings (hot path)."""
    elapsed, total = 0.0, 0.0
    prev: Optional[Track] = None
    for i, tr in enumerate(order):
        p = play_seconds(tr, cfg)
        t_mid = min((elapsed + p / 2) / length_s, 1.0)
        total += transition(prev, tr, curve.target(t_mid), curve.slope(t_mid), order[:i], cfg).total
        elapsed += p
        prev = tr
    return total


def _greedy(
    pool: List[Track], curve: EnergyCurve, cfg: Config, length_s: float, start: Optional[Track]
) -> List[Track]:
    remaining = list(pool)
    order: List[Track] = []
    elapsed = 0.0
    if start is not None:
        order.append(start)
        remaining = [t for t in remaining if t.id != start.id]
        elapsed += play_seconds(start, cfg)
    while remaining and elapsed < length_s:
        prev = order[-1] if order else None
        best, best_cost = None, float("inf")
        options = [c for c in remaining if not any(same_song(c, o) for o in order)]
        if not options:
            break  # only other edits of songs already in the set are left: a shorter set beats a repeat
        for cand in options:
            p = play_seconds(cand, cfg)
            t_mid = min((elapsed + p / 2) / length_s, 1.0)
            c = transition(prev, cand, curve.target(t_mid), curve.slope(t_mid), order, cfg).total
            if c < best_cost:
                best, best_cost = cand, c
        assert best is not None
        order.append(best)
        remaining = [t for t in remaining if t.id != best.id]
        elapsed += play_seconds(best, cfg)
    return order


def _improve(
    order: List[Track],
    pool: List[Track],
    curve: EnergyCurve,
    cfg: Config,
    length_s: float,
    fixed_start: bool,
    time_budget_s: float,
) -> List[Track]:
    deadline = time.monotonic() + time_budget_s
    best = list(order)
    best_cost = _cost(best, curve, cfg, length_s)
    lo = 1 if fixed_start else 0
    improved = True
    while improved and time.monotonic() < deadline:
        improved = False
        n = len(best)
        candidates: List[List[Track]] = []
        for i in range(lo, n - 1):
            for j in range(i + 1, n):
                candidates.append(best[:i] + best[i:j + 1][::-1] + best[j + 1:])  # 2-opt
                swapped = list(best)
                swapped[i], swapped[j] = swapped[j], swapped[i]
                candidates.append(swapped)
        used = {t.id for t in best}
        unused = [t for t in pool if t.id not in used]
        for k in range(lo, n):
            for u in unused:
                replaced = list(best)
                replaced[k] = u
                candidates.append(replaced)
        for cand in candidates:
            if time.monotonic() >= deadline:
                break
            c = _cost(cand, curve, cfg, length_s)
            if c < best_cost - 1e-9:
                best, best_cost, improved = cand, c, True
                break
    return best


def build_set(
    pool: Sequence[Track],
    curve: EnergyCurve,
    cfg: Config,
    length_min: float = 60.0,
    start: Optional[Track] = None,
    time_budget_s: float = 5.0,
) -> SetPlan:
    if not pool:
        raise ValueError("no tracks to order")
    # de-duplicate by id while keeping order
    uniq: Dict[str, Track] = {}
    for t in pool:
        uniq.setdefault(t.id, t)
    tracks = list(uniq.values())
    length_s = length_min * 60.0
    order = _greedy(tracks, curve, cfg, length_s, start)
    order = _improve(order, tracks, curve, cfg, length_s, start is not None, time_budget_s)
    plan = evaluate(order, curve, cfg, length_s)
    used = {t.id for t in order}
    plan.unused = [t for t in tracks if t.id not in used]
    return plan


@dataclass
class Suggestion:
    track: Track
    cost: float
    reason: str


def suggest_next(
    current: Track,
    pool: Sequence[Track],
    curve: EnergyCurve,
    cfg: Config,
    at_fraction: float,
    played: Sequence[Track] = (),
    top: int = 5,
) -> List[Suggestion]:
    """Best tracks to play after `current`, at position `at_fraction` (0..1) of the set."""
    exclude = {current.id} | {t.id for t in played}
    target = curve.target(at_fraction)
    slope = curve.slope(at_fraction)
    recent = list(played) + [current]
    out = []
    for cand in pool:
        if cand.id in exclude:
            continue
        c = transition(current, cand, target, slope, recent, cfg)
        out.append(Suggestion(cand, c.total, explain(current, cand, target, cfg)))
    out.sort(key=lambda s: s.cost)
    return out[:top]
