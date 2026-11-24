"""How 'hot' each track is right now: what people listen to and what DJs play this year.

Three signals, each ranked within your own likes (0 = least, 1 = most):
  - SoundCloud plays (people listen to it a lot)
  - plays per day since it came out (it's taking off now, not a slow-burning classic)
  - professional DJ sets from the last 12 months that played it (MixesDB)
A track's hotness is the average of the signals it has; with no data at all it counts as average-ish (0.3).
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from .models import Track

UNKNOWN = 0.3
HOT = 0.75  # from here on a track is shown as "hot right now"


def _ranks(values: Dict[str, float]) -> Dict[str, float]:
    """0..1 by rank, ties share the same value."""
    if not values:
        return {}
    order = sorted(set(values.values()))
    if len(order) == 1:
        return {k: 0.5 for k in values}
    pos = {v: i / (len(order) - 1) for i, v in enumerate(order)}
    return {k: pos[v] for k, v in values.items()}


def _short(n: int) -> str:
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}K" if n >= 1e3 else str(n)


def hotness(tracks: Sequence[Track], sc_stats: Dict[str, dict], recent_dj: Dict[str, int],
            now: Optional[datetime] = None) -> Tuple[Dict[str, float], Dict[str, str]]:
    """({track id: 0..1}, {track id: short reason})"""
    now = now or datetime.now()
    plays, per_day, dj = {}, {}, {}
    for t in tracks:
        st = sc_stats.get(t.soundcloud_id or "")
        if st and st.get("plays"):
            plays[t.id] = math.log10(1 + st["plays"])
            if st.get("uploaded"):
                days = max(30.0, (now - datetime.fromtimestamp(st["uploaded"])).days)
                per_day[t.id] = st["plays"] / days
        if t.id in recent_dj:
            dj[t.id] = float(recent_dj[t.id])
    rp, rd, rj = _ranks(plays), _ranks(per_day), _ranks(dj)
    score: Dict[str, float] = {}
    why: Dict[str, str] = {}
    for t in tracks:
        parts = [r[t.id] for r in (rp, rd, rj) if t.id in r]
        score[t.id] = sum(parts) / len(parts) if parts else UNKNOWN
        bits: List[str] = []
        st = sc_stats.get(t.soundcloud_id or "")
        if st and st.get("plays"):
            bits.append(f"{_short(st['plays'])} plays on SoundCloud")
        if recent_dj.get(t.id):
            n = recent_dj[t.id]
            bits.append(f"{n} DJ set{'s' if n > 1 else ''} this year")
        why[t.id] = " · ".join(bits)
    return score, why
