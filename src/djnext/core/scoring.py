"""Cost of playing track B after track A at a given point in the set. Lower = better."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from functools import lru_cache
from typing import Dict, Optional, Sequence

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


def energy_cost(energy: float, target: float) -> float:
    return ((energy - target) / 2.0) ** 2  # 2 points off target = cost 1


def direction_cost(prev_energy: float, energy: float, slope: float) -> float:
    """Penalise moving against the curve: dropping while building, rising during a breather."""
    delta = energy - prev_energy
    if slope > 1.0 and delta < 0:
        return -delta / 2.0
    if slope < -1.0 and delta > 0:
        return delta / 2.0
    return 0.0


@dataclass
class Transition:
    total: float
    parts: Dict[str, float] = field(default_factory=dict)


def transition(
    prev: Optional[Track],
    nxt: Track,
    target: float,
    slope: float,
    recent: Sequence[Track],
    cfg: Config,
) -> Transition:
    w = cfg.weights
    e = nxt.energy if nxt.energy is not None else 5.0
    parts = {"energy": w.energy * energy_cost(e, target)}
    if prev is not None:
        pe = prev.energy if prev.energy is not None else 5.0
        parts["key"] = w.key * key_cost(prev.key, nxt.key)
        parts["bpm"] = w.bpm * bpm_cost(prev.bpm, nxt.bpm, cfg)
        parts["genre"] = w.genre * genre_cost(prev.genre, nxt.genre)
        parts["direction"] = w.direction * direction_cost(pe, e, slope)
    if prev is not None and cfg.pair_feedback:
        verdict = cfg.pair_feedback.get(frozenset((prev.id, nxt.id)), 0)
        if verdict < 0:
            parts["your_rating"] = w.disliked_pair
        elif verdict > 0:
            parts["your_rating"] = -w.liked_pair
    if nxt.mood_fit:
        parts["mood"] = -w.mood_fit * nxt.mood_fit
    if cfg.style.favourite_artists and cfg.style.is_favourite(nxt.artist, nxt.title):
        parts["favourite"] = -cfg.style.favourite_bonus
    if any(same_song(r, nxt) for r in recent):
        parts["same_song"] = 25.0  # another edit of a song that's already in the set: never worth it
    if nxt.artist:
        window = list(recent)[-cfg.artist_gap:] if cfg.artist_gap > 0 else []
        if any(r.artist.lower() == nxt.artist.lower() for r in window):
            parts["artist"] = w.artist
    return Transition(total=sum(parts.values()), parts=parts)


def explain(prev: Optional[Track], nxt: Track, target: float, cfg: Config) -> str:
    bits = []
    if prev is not None:
        if prev.key and nxt.key:
            steps = key_steps(prev.key, nxt.key)
            tag = "perfect" if steps == 0 else "harmonic" if steps == 1 else "ok" if steps == 2 else "clash"
            bits.append(f"{prev.key}->{nxt.key} {tag}")
        gap = bpm_gap(prev.bpm, nxt.bpm, cfg.allow_half_double)
        if gap is not None:
            sign = "+" if nxt.bpm >= prev.bpm else "-"
            warn = "" if gap <= cfg.bpm_tolerance else " (beyond pitch range!)"
            bits.append(f"{prev.bpm:.0f}->{nxt.bpm:.0f} BPM {sign}{gap * 100:.1f}%{warn}")
    e = nxt.energy if nxt.energy is not None else 5.0
    bits.append(f"energy {e:.0f} (target {target:.1f})")
    return " | ".join(bits)
