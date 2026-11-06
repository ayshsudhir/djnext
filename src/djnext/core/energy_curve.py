"""Target energy over the course of a set (piecewise-linear through control points)."""
from __future__ import annotations

from bisect import bisect_right
from typing import List, Sequence, Tuple


class EnergyCurve:
    def __init__(self, points: Sequence[Sequence[float]], name: str = "custom"):
        pts: List[Tuple[float, float]] = sorted((float(t), float(e)) for t, e in points)
        if len(pts) < 2:
            raise ValueError("an energy curve needs at least 2 points")
        if pts[0][0] != 0.0 or pts[-1][0] != 1.0:
            raise ValueError("energy curve must start at t=0 and end at t=1")
        self.name = name
        self.points = pts
        self._ts = [t for t, _ in pts]

    def _segment(self, t: float) -> int:
        t = min(max(t, 0.0), 1.0)
        i = bisect_right(self._ts, t) - 1
        return min(max(i, 0), len(self.points) - 2)

    def target(self, t: float) -> float:
        t = min(max(t, 0.0), 1.0)
        i = self._segment(t)
        (t0, e0), (t1, e1) = self.points[i], self.points[i + 1]
        return e0 + (e1 - e0) * (t - t0) / (t1 - t0)

    def slope(self, t: float) -> float:
        """Energy change per whole set (units: energy / set fraction). >0 building, <0 cooling."""
        i = self._segment(t)
        (t0, e0), (t1, e1) = self.points[i], self.points[i + 1]
        return (e1 - e0) / (t1 - t0)
