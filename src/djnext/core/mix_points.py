"""Exact mix points from rekordbox's phrase analysis: when to start B, where to cue it, when to swap.

Times for A are on A's own clock (A is the master deck). B is synced to A, so B positions are
given as phrase names plus B's track time, which is what you see when you cue B.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..config import Config
from .models import Track
from .structure import PEAK_LABELS, Phrase, TrackStructure, fmt

MAX_BLEND_BARS = 32
MIN_BLEND_BARS = 8


@dataclass
class MixPoints:
    cue_b_s: float  # where to cue B (B's time)
    play_b_at_s: float  # A's time when you press play on B (on the 1)
    blend_bars: int
    swap_at_a_s: float  # A's time for the bass swap / the drop
    swap_at_b_s: float  # B's time for the same moment
    a_gone_by_s: float  # A's time by which A should be out
    lines: List[str] = field(default_factory=list)


def _bar(bpm: float) -> float:
    return 4 * 60.0 / (bpm or 120.0)


def _label_at(st: TrackStructure, t: float) -> str:
    p = st.phrase_at(t + 0.05)
    return p.label if p else "end"


def _b_target(sb: TrackStructure) -> Phrase:
    """B's 'arrival' moment (where the bass swap / drop happens).
    1. its first drop/chorus, if that comes 4-40 bars in
    2. otherwise a phrase change about 16 bars in (8-32)
    3. otherwise its first drop, wherever it is (the cue is then placed shortly before it)"""
    bar = _bar(sb.bpm)
    b0 = sb.phrases[0].start_s

    def bars_in(p: Phrase) -> float:
        return (p.start_s - b0) / bar

    peaks = [p for p in sb.phrases[1:] if p.label in PEAK_LABELS and 4 <= bars_in(p) <= 40]
    if peaks:
        return peaks[0]
    others = [p for p in sb.phrases[1:] if 8 <= bars_in(p) <= 32]
    if others:
        return min(others, key=lambda p: abs(bars_in(p) - 16))
    peak = sb.first_peak()
    if peak is not None and peak is not sb.phrases[0]:
        return peak
    return sb.phrases[1] if len(sb.phrases) > 1 else sb.phrases[0]


def _b_cue(sb: TrackStructure, target_s: float, max_bars: int) -> float:
    """Latest phrase start (or the very beginning) at most max_bars before the target."""
    limit = target_s - max_bars * _bar(sb.bpm) - 0.05
    candidates = [p.start_s for p in sb.phrases if limit <= p.start_s < target_s - 0.05]
    if candidates:
        return min(candidates)  # longest allowed run-up that starts on a phrase
    return max(sb.phrases[0].start_s, target_s - max_bars * _bar(sb.bpm))


_LANDING_RANK = {"Outro": 3, "end": 3, "Breakdown": 2, "Build": 1, "Verse": 1, "Bridge": 1}


def _a_handover(sa: TrackStructure, blend_s: float, cfg: Config) -> float:
    """A's time to press play on B. B's arrival (play time + blend) should land on a phrase change in A,
    ideally A's outro/end or a breakdown, and B should start on a phrase change too."""
    nat = sa.natural_mix_out(cfg.max_play_seconds)
    end = sa.end_s
    beat = 60.0 / (sa.bpm or 120.0)
    bounds = sa.boundaries()
    best, best_key = None, None
    for landing in bounds + [end]:
        if not (nat - 0.05 <= landing <= min(end, nat + blend_s) + 0.05):
            continue
        play_at = landing - blend_s
        if play_at < 30:
            continue
        aligned = any(abs(play_at - b) < beat / 2 for b in bounds)
        label = "end" if abs(landing - end) < 0.05 else _label_at(sa, landing)
        key = (aligned, _LANDING_RANK.get(label, 0), landing)
        if best_key is None or key > best_key:
            best, best_key = play_at, key
    if best is not None:
        return best
    if nat + blend_s <= end + 0.05:
        return nat
    fits = [b for b in bounds if b + blend_s <= end + 0.05 and b >= 30]
    return fits[-1] if fits else max(0.0, end - blend_s)


def plan(a: Track, b: Track, technique: str, cfg: Config) -> Optional[MixPoints]:
    sa, sb = a.structure, b.structure
    if sa is None or sb is None or not sa.phrases or not sb.phrases:
        return None
    bar_a, bar_b = _bar(a.bpm or sa.bpm), _bar(b.bpm or sb.bpm)

    if technique == "echo_out":
        out = sa.natural_mix_out(cfg.max_play_seconds)
        prev = sa.phrase_at(out - 0.5)
        b_start = sb.phrases[0].start_s
        peak = sb.first_peak()
        lines = [
            f"Let A play to {fmt(out)} (end of its {prev.label if prev else 'phrase'}, where its "
            f"{_label_at(sa, out)} starts). Hit the ECHO on the last beat before {fmt(out)} and pull A down on the 1.",
            f"Start B from {fmt(b_start)} ({sb.phrases[0].label}) on that same 1"
            + (f", or from {fmt(peak.start_s)} (its {peak.label}) for a hard switch." if peak else "."),
        ]
        return MixPoints(b_start, out, 0, out, b_start, out, lines)

    max_run = 16 if technique == "build_drop" or cfg.skill == "beginner" else MAX_BLEND_BARS
    target = _b_target(sb)
    cue = _b_cue(sb, target.start_s, max_run)
    blend_bars = max(1, round((target.start_s - cue) / bar_b))
    if technique in ("filter_fade", "wash_out") or cfg.skill == "beginner":
        blend_bars = min(blend_bars, 16 if technique == "bass_swap" else (8 if cfg.skill == "beginner" else 16))
        cue = max(cue, target.start_s - blend_bars * bar_b)
    blend_s_a = blend_bars * bar_a  # B runs at A's tempo
    play_at = _a_handover(sa, blend_s_a, cfg)
    swap_a = play_at + blend_s_a
    a_gone = min(sa.end_s, swap_a + 8 * bar_a)
    cue_label = _label_at(sb, cue)
    a_label = _label_at(sa, play_at)

    lines = [
        f"Cue B at {fmt(cue)} (start of its {cue_label}, {blend_bars} bars before its {target.label}).",
        f"Press PLAY on B on the 1 when A reaches {fmt(play_at)} (start of A's {a_label}).",
    ]
    if technique == "build_drop":
        lines.append(f"Loop or roll A's last 4 bars before {fmt(swap_a)}. B's {target.label} hits at A {fmt(swap_a)} "
                     f"= B {fmt(target.start_s)}: swap the basses right on that 1.")
    elif technique == "wash_out":
        lines.append(f"Wash A out with reverb by A {fmt(swap_a)}. B's {target.label} starts at B {fmt(target.start_s)}.")
    else:
        lines.append(f"Swap the basses at A {fmt(swap_a)} = B {fmt(target.start_s)}, where B's {target.label} starts "
                     f"({blend_bars}-bar blend).")
    if technique != "wash_out":
        if a_gone >= sa.end_s - 1:
            lines.append(f"A's music ends at {fmt(sa.end_s)}, so pull A's fader down as B takes over.")
        else:
            lines.append(f"Have A fully out by {fmt(a_gone)} (A's music ends at {fmt(sa.end_s)}).")
    if blend_bars < MIN_BLEND_BARS and technique == "bass_swap":
        lines.append(f"B's run-up is only {blend_bars} bars: a quick swap works better than a long blend here.")
    return MixPoints(cue, play_at, blend_bars, swap_a, target.start_s, a_gone, lines)
