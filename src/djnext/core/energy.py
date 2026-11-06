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


def spread_guessed(tracks: Iterable[Track], low: float = 2.0, high: float = 9.0) -> int:
    """Tracks whose energy was only guessed from BPM all end up around 6-8 when a set uses a narrow BPM
    range. Re-rank them *within this pool* by tempo and by how much of the track is drops (from rekordbox's
    phrase analysis), and spread them from `low` to `high` so a set can actually build and breathe.
    Tracks with a real energy value (comment or star rating) are left alone. Returns how many changed."""
    guessed = [t for t in tracks if t.energy_source in ("bpm", "spread")]
    if len(guessed) < 3:
        return 0

    def drop_share(t: Track) -> float:
        st = t.structure
        if st is None or not st.phrases or not st.end_s:
            return 0.45  # typical value
        return sum(p.end_s - p.start_s for p in st.phrases if p.label in ("Drop", "Chorus")) / st.end_s

    from .moods import _ranks as ranks  # tie-aware ranking

    bpm_rank = ranks([t.bpm for t in guessed])
    drop_rank = ranks([drop_share(t) for t in guessed])
    score = [0.6 * b + 0.4 * d for b, d in zip(bpm_rank, drop_rank)]
    final = ranks(score)
    for t, r in zip(guessed, final):
        t.energy = round(low + (high - low) * r, 1)
        t.energy_source = "spread"
    return len(guessed)
