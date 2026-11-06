"""How to mix track A into track B on a DDJ-FLX4, chosen from key, BPM, genre and energy.

Techniques:
  bass_swap    long blend, swap the LOW knobs on the phrase   (compatible key + tempo + vibe)
  filter_fade  HPF out / LPF in with the CFX filter knob      (keys only "ok", or a genre change)
  build_drop   loop roll on A's build, slam B in on the drop   (big energy jump up, compatible)
  wash_out     reverb/echo tail on A into B's soft intro       (big energy drop, i.e. the breather)
  echo_out     echo on A's last phrase, cut, B starts clean    (key clash or tempo out of range)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ..config import Config
from .camelot import key_steps
from .models import Track
from .mix_points import plan
from .scoring import bpm_cost, bpm_gap, genre_cost, key_cost


@dataclass
class MixAdvice:
    technique: str  # short id
    title: str
    steps: List[str]
    notes: List[str] = field(default_factory=list)
    alternative: Optional[str] = None
    bridge: Optional[Track] = None  # a track that would sit nicely between A and B
    timing: List[str] = field(default_factory=list)  # exact mix points from phrase analysis

    def short(self) -> str:
        return self.title

    def text(self) -> str:
        lines = [f"{self.title}"]
        if self.timing:
            lines.append("  When:")
            lines += [f"    - {t}" for t in self.timing]
            lines.append("  How:")
        lines += [f"  {i}. {s}" for i, s in enumerate(self.steps, 1)]
        lines += [f"  * {n}" for n in self.notes]
        if self.alternative:
            lines.append(f"  Alternative: {self.alternative}")
        if self.bridge is not None:
            lines.append(f"  Smoother route: play '{self.bridge.label}' in between")
        return "\n".join(lines)


def _tempo_step(a: Track, b: Track, cfg: Config) -> Optional[str]:
    if a.bpm <= 0 or b.bpm <= 0:
        return None
    raw = abs(b.bpm - a.bpm) / b.bpm
    gap = bpm_gap(a.bpm, b.bpm, cfg.allow_half_double)
    if gap is not None and raw > cfg.bpm_tolerance and gap <= cfg.bpm_tolerance:
        return (f"Half/double time: {b.bpm:.0f} vs {a.bpm:.0f} BPM. The beats only line up every other beat, "
                "so keep the overlap short.")
    if raw < 0.003:
        return f"Tempos already match ({a.bpm:.1f} vs {b.bpm:.1f} BPM). Just cue B on the 1."
    pct = (a.bpm - b.bpm) / b.bpm * 100
    return f"Set B's TEMPO slider to {pct:+.1f}% (to {a.bpm:.1f} BPM) or press BEAT SYNC, then cue B on the 1."


def _bridge(a: Track, b: Track, pool: Sequence[Track], cfg: Config) -> Optional[Track]:
    """A track that turns one rough transition into two smooth ones (keys <= 2 steps, tempo in range)."""
    if not (a.key and b.key):
        return None
    best, best_cost = None, float("inf")
    ea = a.energy if a.energy is not None else 5.0
    eb = b.energy if b.energy is not None else 5.0
    for x in pool:
        if x.id in (a.id, b.id) or not x.key:
            continue
        if key_steps(a.key, x.key) > 2 or key_steps(x.key, b.key) > 2:
            continue
        g1 = bpm_gap(a.bpm, x.bpm, cfg.allow_half_double)
        g2 = bpm_gap(x.bpm, b.bpm, cfg.allow_half_double)
        if g1 is None or g2 is None or g1 > cfg.bpm_tolerance or g2 > cfg.bpm_tolerance:
            continue
        ex = x.energy if x.energy is not None else 5.0
        c = (key_cost(a.key, x.key) + key_cost(x.key, b.key)
             + bpm_cost(a.bpm, x.bpm, cfg) + bpm_cost(x.bpm, b.bpm, cfg)
             + 0.2 * abs(ex - (ea + eb) / 2))  # energy should sit between A and B
        if c < best_cost:
            best, best_cost = x, c
    return best


SYNC = "Press BEAT SYNC on deck B (and leave it on), so the beats stay locked for you."
SMART_FADER = ("Easiest of all: turn on the FLX4's SMART FADER in rekordbox and just move the crossfader slowly; "
               "it handles the volume and bass for you.")

_BEGINNER = {
    "bass_swap": ("Bass swap (easy version)", [
        SYNC,
        "Turn B's LOW knob all the way left. Start B at its IN point (pad E if you added cues) when A reaches the "
        "time under When (pad G on A).",
        "Slowly push B's channel fader all the way up over about 8 bars.",
        "At the swap point (pad F, see When): on the 1, turn A's LOW all the way left and B's LOW back to the middle, both at once.",
        "Pull A's fader down over the next 4-8 bars.",
    ]),
    "filter_fade": ("Filter fade (easy version)", [
        SYNC,
        "Turn B's CFX knob to the left (it sounds muffled), push its fader up, and start B at its IN point (pad E).",
        "Over 8 bars: slowly turn B's CFX back to the middle, and A's CFX to the right (A goes thin).",
        "At the swap point (pad F, see When): pull A's fader down and set A's CFX back to the middle.",
    ]),
    "echo_out": ("Echo out (easy version)", [
        "No need to match anything: the echo hides the change.",
        "Beat FX: choose ECHO, 1 beat, on A's channel.",
        "At the time under When (pad G on A): press the BEAT FX ON button and pull A's fader down straight away.",
        "Right away, press PLAY on B from its IN point (pad E) with its fader up. Done.",
    ]),
    "build_drop": ("Swap on the drop (easy version)", [
        SYNC,
        "Turn B's LOW all the way left and push its fader up. Start B at its IN point (pad E) at the time under When.",
        "When B's drop hits (pad F, see When): turn A's LOW all the way left and B's LOW back to the middle, then pull A's "
        "fader down.",
    ]),
    "wash_out": ("Reverb fade-out (easy version)", [
        SYNC,
        "Start B at its IN point (pad E) with its fader low.",
        "Beat FX: choose REVERB on A's channel. At the time under When (pad G on A), turn it on, then over 4 bars pull "
        "A's fader down while pushing B's up.",
    ]),
}


def _make_beginner(adv: "MixAdvice") -> None:
    title, steps = _BEGINNER.get(adv.technique, (adv.title, adv.steps))
    adv.title, adv.steps = title, list(steps)
    if adv.technique != "echo_out":
        adv.alternative = SMART_FADER
    else:
        adv.alternative = "If the echo feels hard to time, a filter fade over 8 bars also works."


def advise(a: Track, b: Track, cfg: Config, pool: Sequence[Track] = ()) -> MixAdvice:
    steps_key = key_steps(a.key, b.key) if a.key and b.key else None
    gap = bpm_gap(a.bpm, b.bpm, cfg.allow_half_double)
    ea = a.energy if a.energy is not None else 5.0
    eb = b.energy if b.energy is not None else 5.0
    de = eb - ea
    same_vibe = genre_cost(a.genre, b.genre) <= 0.3
    tempo_ok = gap is not None and gap <= cfg.bpm_tolerance
    key_good = steps_key is not None and steps_key <= 1
    key_ok = steps_key is not None and steps_key <= 2
    clash = steps_key is not None and steps_key >= 3

    notes: List[str] = []
    tempo = _tempo_step(a, b, cfg)

    if not tempo_ok or clash:
        why = "the tempos are too far apart to beatmatch" if not tempo_ok else f"the keys clash ({a.key} vs {b.key})"
        adv = MixAdvice(
            "echo_out", "Echo out",
            [
                "Let A play into its last phrase (count 16 or 32 bars from a drop or breakdown).",
                "Beat FX: choose ECHO, 1/2 or 1 beat, on A's channel, and turn LEVEL/DEPTH to about 70%.",
                "On the last bar of the phrase, press the Beat FX ON button, then pull A's fader (or the crossfader) down on the 1.",
                "Start B from its first beat or a hot cue while the echo tail fades out. B is now on its own.",
            ],
            alternative="Filter fade: sweep A's CFX knob fully right (high-pass) over 8 bars and cut on the phrase. "
                        "Also hides a clash.",
        )
        notes.append(f"Why: {why}, so long overlaps will sound messy. Keep A and B apart.")
        if tempo_ok and tempo:
            notes.append(tempo + " (only needed if you overlap at all)")
        if pool:
            adv.bridge = _bridge(a, b, pool, cfg)
    elif de <= -2:
        adv = MixAdvice(
            "wash_out", "Reverb wash-out into a breather",
            [
                tempo or "Beatmatch B to A.",
                "Start B on an intro or breakdown section, with its fader low and LOW at 9 o'clock.",
                "Beat FX: REVERB (or ECHO 1 beat) on A. At the end of A's phrase, turn the effect on and pull A out.",
                "Bring B's fader up and its LOW back to 12 o'clock over 8 bars, so the room 'breathes'.",
            ],
            alternative="Filter fade with A's CFX knob going low-pass (left), which feels like the room is going underwater.",
        )
        notes.append(f"Energy drops {ea:.0f} -> {eb:.0f}. Let it breathe and don't rush back up.")
    elif de >= 2 and eb >= 6 and key_ok:  # jump INTO a high-energy section
        adv = MixAdvice(
            "build_drop", "Build and drop swap",
            [
                tempo or "Beatmatch B to A.",
                "Cue B a few bars before its drop. Cut B's LOW fully (fully left), with its fader at about 3/4.",
                "On A's build, use Beat FX ROLL (1 beat, then 1/2, then 1/4) or a 4-beat loop on A, then halve it.",
                "On the drop, swap the basses together on the 1: A's LOW and fader go down, B's LOW goes to 12 o'clock.",
            ],
            alternative="Bass swap over 16 bars if you'd rather lift the energy gradually.",
        )
        notes.append(f"Energy jumps {ea:.0f} -> {eb:.0f}. Make the drop the moment.")
    elif key_good and same_vibe and gap is not None and gap <= 0.03:
        adv = MixAdvice(
            "bass_swap", "Long blend with a bass swap",
            [
                tempo or "Beatmatch B to A.",
                "Start B with its LOW fully cut (fully left) and its fader up (usually as A's outro begins).",
                "During the blend (16 to 32 bars), ease B's HI and MID in and take A's HI down a little.",
                "On a phrase change (the 1 of a 16-bar phrase), swap the basses: A's LOW goes fully left and B's LOW goes to 12 o'clock, in one move.",
                "Fade A out over the next 8 bars.",
            ],
            alternative="Filter fade (A's CFX knob going high-pass) if the blend gets crowded.",
        )
        notes.append(f"Keys {a.key} -> {b.key} are harmonic, so you can let both tracks play together for a long time."
                     if cfg.skill != "beginner" else f"Keys {a.key} -> {b.key} match, so the overlap will sound clean.")
    else:
        adv = MixAdvice(
            "filter_fade", "Filter fade",
            [
                tempo or "Beatmatch B to A.",
                "Bring B in with its CFX knob turned left (low-pass) and its LOW cut.",
                "Over 8 to 16 bars, turn A's CFX knob right (high-pass) while you open B's filter back to 12 o'clock.",
                "Swap the LOW knobs on the phrase change, then fade A out.",
            ],
            alternative="Echo out (Beat FX ECHO 1/2 beat on A) for a quicker, cleaner change.",
        )
        reason = []
        if steps_key == 2:
            reason.append(f"keys {a.key} -> {b.key} are only 'ok'")
        if not same_vibe:
            reason.append(f"genre change ({a.genre or '?'} -> {b.genre or '?'})")
        if gap is not None and gap > 0.03:
            reason.append(f"a {gap * 100:.1f}% tempo change")
        if steps_key is None:
            reason.append("a key is unknown")
        if reason:
            notes.append("Filters hide the mids because of " + ", ".join(reason) + ". Keep the overlap short.")
    adv.notes = notes + adv.notes
    if cfg.skill == "beginner":
        _make_beginner(adv)
        if tempo and tempo.startswith("Half/double"):
            adv.notes.append(tempo)  # still worth knowing, even with SYNC
    points = plan(a, b, adv.technique, cfg)
    if points is not None:
        adv.timing = points.lines
    return adv
