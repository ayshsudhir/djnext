"""Give every track an energy value on a 0-10 scale.

Priority:
  1. "Energy 7" / "E7" in the rekordbox comment (Mixed In Key writes this; you can also type it yourself)
  2. rekordbox star rating (1 star = 2 ... 5 stars = 10)
  3. rough estimate from BPM (least reliable, so tag your tracks!)
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from .models import Track

_ENERGY_RE = re.compile(r"(?:\benergy\s*[:=\-]?\s*|\bE)(\d{1,2}(?:\.\d+)?)\b", re.IGNORECASE)


def energy_from_comment(comment: str) -> Optional[float]:
    if not comment:
        return None
    m = _ENERGY_RE.search(comment)
    if not m:
        return None
    value = float(m.group(1))
    return value if 0 <= value <= 10 else None


def energy_from_bpm(bpm: float) -> float:
    # 90 BPM -> 1, 140 BPM -> 9 (linear, clamped)
    if bpm <= 0:
        return 5.0
    return max(1.0, min(9.0, 1.0 + (bpm - 90.0) * 8.0 / 50.0))


def assign_energy(track: Track) -> Track:
    if track.energy is not None:
        track.energy_source = track.energy_source or "given"
        return track
    e = energy_from_comment(track.comments)
    if e is not None:
        track.energy, track.energy_source = e, "comment"
    elif track.rating > 0:
        track.energy, track.energy_source = float(track.rating * 2), "rating"
    else:
        track.energy, track.energy_source = energy_from_bpm(track.bpm), "bpm"
    return track


def assign_all(tracks: Iterable[Track]) -> None:
    for t in tracks:
        assign_energy(t)
