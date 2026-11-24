"""Small tempo/key/genre helpers used by the mix advice (how to mix A into B)."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from ..config import Config
from .camelot import key_steps
from .models import Track

_KEY_COST = {0: 0.0, 1: 0.1, 2: 0.5}

_STOP = set("""remix edit extended original mix version feat featuring with the and you your for from that this what
when into over just like dont cant love deep night dance house techno music time feel back down girl party body
baby free download premiere bootleg rework mashup vocal dub club radio intro outro part main official video live
2023 2024 2025 2026 records track tracks sample song""".split())


@lru_cache(maxsize=4096)
def _song_words(title: str) -> frozenset:
    """Distinctive words of a title ('Toxic x Stephanie (Chris Lorenzo Edit)' -> {'toxic', 'stephanie', ...})."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return frozenset(w for w in words if len(w) >= 4 and w not in _STOP)


def same_song(a: Track, b: Track) -> bool:
    """Two different uploads/edits of the same song (e.g. three 'Toxic' edits)."""
    wa, wb = _song_words(a.title), _song_words(b.title)
    shared = wa & wb
    # one shared distinctive word is enough for short titles; long titles need two
    need = 1 if min(len(wa), len(wb)) <= 3 else 2
    return len(shared) >= need


def key_cost(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.5  # unknown key: neutral-ish
    return _KEY_COST.get(key_steps(a, b), 1.0)


def bpm_gap(a: float, b: float, allow_half_double: bool = True) -> Optional[float]:
    """Relative tempo change needed to beatmatch b to a (0.02 = 2%)."""
    if a <= 0 or b <= 0:
        return None
    options = [b, b * 2, b / 2] if allow_half_double else [b]
    return min(abs(o - a) / a for o in options)


def bpm_cost(a: float, b: float, cfg: Config) -> float:
    gap = bpm_gap(a, b, cfg.allow_half_double)
    if gap is None:
        return 0.5
    return min((gap / cfg.bpm_tolerance) ** 2, 4.0)


def genre_cost(a: str, b: str) -> float:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return 0.25
    if a == b:
        return 0.0
    if set(a.replace("/", " ").split()) & set(b.replace("/", " ").split()):
        return 0.3  # e.g. "tech house" vs "house"
    return 1.0
