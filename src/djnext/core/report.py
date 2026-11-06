"""Scorecard for a set: is it technically clean, and is it better than a random shuffle?"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..config import Config
from .camelot import key_steps
from .energy_curve import EnergyCurve
from .models import Track
from .scoring import bpm_gap
from .sequencer import _cost, evaluate, play_seconds


@dataclass
class Report:
    transitions: int
    harmonic: int  # key steps <= 1
    ok_keys: int  # key steps == 2
    clashes: int  # key steps >= 3
    unknown_keys: int
    tempo_out_of_range: int
    energy_deviation: float  # average |energy - target|
    curve_correlation: Optional[float]  # -1..1, how well the energy *shape* follows the curve
    cost: float
    random_cost: float  # average over random shuffles of the same tracks
    bpm_sorted_cost: float

    @property
    def vs_random_pct(self) -> float:
        return (1 - self.cost / self.random_cost) * 100 if self.random_cost > 0 else 0.0


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    if sx == 0 or sy == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sx * sy)


def set_length_s(tracks: Sequence[Track], cfg: Config) -> float:
    return sum(play_seconds(t, cfg) for t in tracks)


def make_report(
    tracks: Sequence[Track],
    curve: EnergyCurve,
    cfg: Config,
    length_s: Optional[float] = None,
    shuffles: int = 50,
    seed: int = 0,
) -> Report:
    tracks = list(tracks)
    length_s = length_s or set_length_s(tracks, cfg)
    plan = evaluate(tracks, curve, cfg, length_s)

    harmonic = ok = clash = unknown = tempo_out = 0
    for a, b in zip(tracks, tracks[1:]):
        if a.key and b.key:
            s = key_steps(a.key, b.key)
            harmonic += s <= 1
            ok += s == 2
            clash += s >= 3
        else:
            unknown += 1
        g = bpm_gap(a.bpm, b.bpm, cfg.allow_half_double)
        tempo_out += g is not None and g > cfg.bpm_tolerance

    energies = [s.track.energy or 0.0 for s in plan.slots]
    targets = [s.target for s in plan.slots]
    deviation = sum(abs(e - t) for e, t in zip(energies, targets)) / max(len(energies), 1)

    rng = random.Random(seed)
    random_costs = []
    for _ in range(shuffles):
        shuffled = list(tracks)
        rng.shuffle(shuffled)
        random_costs.append(_cost(shuffled, curve, cfg, length_s))
    bpm_sorted = sorted(tracks, key=lambda t: t.bpm)

    return Report(
        transitions=max(len(tracks) - 1, 0),
        harmonic=harmonic,
        ok_keys=ok,
        clashes=clash,
        unknown_keys=unknown,
        tempo_out_of_range=tempo_out,
        energy_deviation=deviation,
        curve_correlation=_pearson(energies, targets),
        cost=plan.total_cost,
        random_cost=sum(random_costs) / len(random_costs) if random_costs else 0.0,
        bpm_sorted_cost=_cost(bpm_sorted, curve, cfg, length_s),
    )


def report_lines(r: Report) -> List[str]:
    n = max(r.transitions, 1)
    corr = f"{r.curve_correlation:.2f}" if r.curve_correlation is not None else "n/a"
    return [
        f"Harmonic transitions (key steps <= 1):  {r.harmonic}/{r.transitions} ({r.harmonic / n:.0%})",
        f"'Ok' keys (2 steps, use a filter):       {r.ok_keys}/{r.transitions}",
        f"Key clashes (3+ steps, echo out):        {r.clashes}/{r.transitions}"
        + (f"   (+{r.unknown_keys} with unknown key)" if r.unknown_keys else ""),
        f"Tempo jumps beyond +/-6% slider:         {r.tempo_out_of_range}/{r.transitions}",
        f"Energy vs target curve:                  {r.energy_deviation:.1f} points off on average, "
        f"shape match {corr} (1.0 = perfect)",
        f"Total cost {r.cost:.1f}  vs  random shuffle {r.random_cost:.1f}  vs  sorted by BPM {r.bpm_sorted_cost:.1f}"
        f"  ->  {r.vs_random_pct:.0f}% better than random",
    ]
