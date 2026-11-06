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

    def natural_mix_out(self, max_play_s: float) -> float:
        """Where this track would normally hand over: its outro, or for very long tracks the last
        phrase boundary before roughly max_play_s (e.g. after the second drop)."""
        if not self.phrases:
            return 0.0
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
