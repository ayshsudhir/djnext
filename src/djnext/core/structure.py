"""Song structure from rekordbox's phrase analysis: intro, build, drop, breakdown, outro ... with times."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

# rekordbox phrase kinds per "mood" (see Deep Symmetry's rekordbox analysis docs)
_HIGH = {1: "Intro", 2: "Build", 3: "Breakdown", 4: "Breakdown", 5: "Drop", 6: "Outro"}
_MID = {1: "Intro", 2: "Verse", 3: "Verse", 4: "Verse", 5: "Verse", 6: "Verse", 7: "Verse",
        8: "Bridge", 9: "Chorus", 10: "Outro"}
_LOW = {1: "Intro", 2: "Verse", 3: "Verse", 4: "Verse", 5: "Verse", 6: "Verse", 7: "Verse",
        8: "Bridge", 9: "Chorus", 10: "Outro"}
_MOODS = {1: _HIGH, 2: _MID, 3: _LOW}

PEAK_LABELS = ("Drop", "Chorus")
LOUD = 0.75  # a phrase at 75% of the track's full sound is one of its big parts
GOING = 0.65  # still in full swing (not yet the outro)
RISE = 0.2  # this much louder than the phrase before = the bass / the drop comes in


def phrase_label(mood: int, kind: int) -> str:
    return _MOODS.get(mood, _HIGH).get(kind, "Phrase")


@dataclass
class Phrase:
    label: str
    start_beat: int  # 1-based beat number
    end_beat: int  # exclusive
    start_s: float
    end_s: float

    @property
    def bars(self) -> int:
        return max(0, (self.end_beat - self.start_beat) // 4)


@dataclass
class TrackStructure:
    bpm: float
    beat_times: List[float]  # seconds, index 0 = beat 1
    phrases: List[Phrase] = field(default_factory=list)
    # how full each phrase sounds, 0..1 (bass counts most), from rekordbox's 3-band waveform; empty = unknown
    energy: List[float] = field(default_factory=list)

    @classmethod
    def build(
        cls, bpm: float, beat_times: Sequence[float], mood: int, entries: Sequence[tuple], end_beat: int
    ) -> "TrackStructure":
        """entries: (start_beat, kind) pairs from rekordbox's PSSI tag, in order."""
        st = cls(bpm=bpm, beat_times=list(beat_times))
        starts = [(int(b), int(k)) for b, k in entries]
        for i, (beat, kind) in enumerate(starts):
            nxt = starts[i + 1][0] if i + 1 < len(starts) else int(end_beat)
            if nxt <= beat:
                continue
            st.phrases.append(Phrase(phrase_label(mood, kind), beat, nxt, st.time_at_beat(beat), st.time_at_beat(nxt)))
        return st

    def time_at_beat(self, beat: int) -> float:
        i = beat - 1
        if 0 <= i < len(self.beat_times):
            return self.beat_times[i]
        last_i = len(self.beat_times) - 1
        base = self.beat_times[-1] if self.beat_times else 0.0
        return base + (i - last_i) * 60.0 / (self.bpm or 120.0)

    @property
    def intro(self) -> Optional[Phrase]:
        return self.phrases[0] if self.phrases and self.phrases[0].label == "Intro" else None

    @property
    def outro(self) -> Optional[Phrase]:
        return self.phrases[-1] if self.phrases and self.phrases[-1].label == "Outro" else None

    @property
    def end_s(self) -> float:
        return self.phrases[-1].end_s if self.phrases else 0.0

    def first_peak(self) -> Optional[Phrase]:
        return next((p for p in self.phrases if p.label in PEAK_LABELS), None)

    def phrase_at(self, t: float) -> Optional[Phrase]:
        return next((p for p in self.phrases if p.start_s <= t < p.end_s), None)

    def boundaries(self) -> List[float]:
        return [p.start_s for p in self.phrases]

    def set_energy(self, columns: Sequence[Sequence[float]], duration_s: float) -> None:
        """columns: rekordbox's 3-band waveform preview, (low, mid, high) per column across the whole file."""
        if not columns or duration_s <= 0 or not self.phrases:
            return
        n = len(columns)
        level = [0.6 * lo + 0.2 * mid + 0.2 * hi for lo, mid, hi in columns]
        ref = sorted(level)[int(0.9 * (n - 1))] or 1.0
        out = []
        for p in self.phrases:
            a = min(n - 1, int(p.start_s / duration_s * n))
            b = max(a + 1, min(n, int(p.end_s / duration_s * n)))
            out.append(min(1.0, sum(level[a:b]) / (b - a) / ref))
        self.energy = out

    def loud(self, i: int) -> bool:
        return bool(self.energy) and self.energy[i] >= LOUD

    def arrival(self, min_bars: float = 4, max_bars: float = 48) -> Optional[Phrase]:
        """Where the groove really kicks in: the first phrase that gets loud after a quieter one (the bass comes in,
        the drop lands), judged by how the track sounds rather than by rekordbox's phrase names."""
        if not self.energy:
            return None
        bar = 4 * 60.0 / (self.bpm or 120.0)
        b0 = self.phrases[0].start_s
        for i in range(1, len(self.phrases)):
            bars_in = (self.phrases[i].start_s - b0) / bar
            if bars_in > max_bars:
                break
            if bars_in >= min_bars and self.energy[i] >= 0.6 and self.energy[i] - self.energy[i - 1] >= RISE:
                return self.phrases[i]
        return None

    def natural_mix_out(self, max_play_s: float) -> float:
        """Where this track would normally hand over: once its last loud part is over (its outro).
        Only very long tracks hand over earlier: right after a loud part ends, from about max_play_s on.
        Never before the track's main part has played."""
        if not self.phrases:
            return 0.0
        if self.energy:
            ph, e = self.phrases, self.energy
            loud = [i for i in range(len(ph)) if e[i] >= GOING]
            if loud:
                last = loud[-1]
                out = ph[last + 1].start_s if last + 1 < len(ph) else (self.outro.start_s if self.outro else ph[-1].start_s)
                if out <= max_play_s + 180:
                    return out
                calm = [ph[i].start_s for i in range(1, len(ph))
                        if e[i] < GOING - 0.1 and e[i - 1] >= LOUD and ph[i].start_s >= max_play_s]
                return calm[0] if calm else out
        target = self.outro.start_s if self.outro else self.phrases[-1].start_s
        if target <= max_play_s + 90:
            return target
        # prefer handing over where a drop has just finished (breakdown/build/outro), not as one starts
        calm = [p.start_s for p in self.phrases if 90 <= p.start_s <= max_play_s + 30 and p.label not in PEAK_LABELS]
        if calm:
            return calm[-1]
        earlier = [b for b in self.boundaries() if 90 <= b <= max_play_s + 30]
        return earlier[-1] if earlier else target

    def summary(self) -> str:
        return " > ".join(f"{p.label} {fmt(p.start_s)} ({p.bars} bars)" for p in self.phrases)


def fmt(seconds: float) -> str:
    seconds = max(0.0, seconds)
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"
