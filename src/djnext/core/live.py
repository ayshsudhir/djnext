"""Live mode: read the crowd, get the next track.

While you play, you set a knob for how the crowd is reacting (1 = dead ... 5 = going off). djnext turns that into
what the room needs next (a target energy and direction) and ranks tracks that also mix well with what's playing
now (key, tempo). Every crowd reading is logged with the track that was playing, so after the set you get a review:
which tracks lifted the room and where it dipped.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..config import Config
from .models import Track
from .scoring import explain, transition


@dataclass(frozen=True)
class Crowd:
    level: int
    emoji: str
    name: str
    need: str  # what the room needs, shown as the headline
    tip: str  # how to play it
    energy_step: float  # target = current energy + this
    slope: float  # wanted direction (+ build, 0 hold, - cool down)
    pleaser: float  # 0..1 how much to favour crowd-pleasers (well-known edits)
    key_weight: float  # 1 = normal; lower = allow a bigger key jump to change things up
    genre_weight: float


CROWD = {
    1: Crowd(1, "💤", "Dead", "Change it up: something they know",
             "Don't blend this one. Echo out and drop a crowd-pleaser with a big, recognisable hook.",
             2.5, 1.0, 1.0, 0.35, 0.0),
    2: Crowd(2, "😐", "Meh", "Lift the energy",
             "Pick something with more drive or a vocal hook. A build-and-drop swap gets attention.",
             1.8, 0.8, 0.6, 0.7, 0.3),
    3: Crowd(3, "🙂", "Vibing", "Build it up gently",
             "They're with you. Step the energy up a little and keep the mixes smooth.",
             1.0, 0.5, 0.15, 1.0, 1.0),
    4: Crowd(4, "🙌", "Into it", "Push it: take them higher",
             "Go for a stronger track in key. Long bass-swap blends keep the momentum.",
             1.2, 0.6, 0.1, 1.0, 1.0),
    5: Crowd(5, "🔥", "Going off", "Ride it, don't break it",
             "Keep the energy right here. Stay in key, stay on tempo and mix long. Save the breather for later.",
             0.2, 0.0, 0.0, 1.2, 1.0),
}


@dataclass
class Pick:
    track: Track
    cost: float
    why: str
    energy_delta: float


def suggest(current: Track, pool: Sequence[Track], crowd: int, cfg: Config, played: Sequence[Track] = (),
            pleasers: Optional[Dict[str, float]] = None, top: int = 6,
            memory: Optional["Memory"] = None) -> List[Pick]:
    """Best next tracks for this crowd reading. `pleasers` = {track id: 0..1 crowd-pleaser score}.
    `memory` = what your past live sets taught (tracks and transitions that lifted or dropped the room)."""
    c = CROWD[max(1, min(5, int(crowd)))]
    cfg = copy.copy(cfg)
    cfg.weights = copy.copy(cfg.weights)
    cfg.weights.key *= c.key_weight
    cfg.weights.genre *= c.genre_weight
    cur_e = current.energy if current.energy is not None else 5.0
    target = max(0.0, min(10.0, cur_e + c.energy_step))
    recent = list(played) + [current]
    exclude = {t.id for t in recent}
    out = []
    for cand in pool:
        if cand.id in exclude:
            continue
        saved = cand.mood_fit
        cand.mood_fit = c.pleaser * (pleasers or {}).get(cand.id, 0.0) * 2.0
        try:
            cost = transition(current, cand, target, c.slope, recent, cfg).total
        finally:
            cand.mood_fit = saved
        if memory is not None:
            cost -= memory.bonus(current.id, cand.id, crowd)
        e = cand.energy if cand.energy is not None else 5.0
        out.append(Pick(cand, cost, explain(current, cand, target, cfg), e - cur_e))
    out.sort(key=lambda p: p.cost)
    return out[:top]


# ---------- the session log (for the review) ----------

@dataclass
class Event:
    at: str  # ISO time
    kind: str  # "track", "crowd", or "end" (you pressed End set)
    track_id: str = ""
    label: str = ""
    crowd: int = 0


@dataclass
class Session:
    started: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    events: List[Event] = field(default_factory=list)

    def log(self, kind: str, track: Optional[Track] = None, crowd: int = 0) -> None:
        self.events.append(Event(datetime.now().isoformat(timespec="seconds"), kind,
                                 track.id if track else "", track.label if track else "", crowd))

    def save(self, folder: Path) -> Path:
        from ..storage import write_json

        return write_json(folder / f"{self.started.replace(':', '-')}.json",
                          {"started": self.started, "events": [asdict(e) for e in self.events]}, indent=1)

    @classmethod
    def load(cls, path: Path) -> "Session":
        """Raises ValueError for a damaged file (callers skip it)."""
        from ..storage import read_json

        d = read_json(path)
        if not isinstance(d, dict) or "started" not in d:
            raise ValueError(f"{path.name} isn't a djnext set")
        return cls(d["started"], [Event(**e) for e in d.get("events", [])])


def review(session: Session, now: Optional[datetime] = None) -> dict:
    """How the set went: a crowd timeline, and per track the average reading and whether the room rose or fell."""
    t0 = datetime.fromisoformat(session.started)
    end = now or datetime.now()
    mins = lambda iso: (datetime.fromisoformat(iso) - t0).total_seconds() / 60  # noqa: E731
    timeline, tracks = [], []
    crowd = 0
    for e in session.events:
        if e.kind == "crowd":
            crowd = e.crowd
            timeline.append({"min": round(mins(e.at), 2), "crowd": e.crowd})
            if tracks:
                tracks[-1]["readings"].append(e.crowd)
        elif e.kind == "track":
            tracks.append({"label": e.label, "id": e.track_id, "min": round(mins(e.at), 2),
                           "prev_id": tracks[-1]["id"] if tracks else "", "start_crowd": crowd, "readings": []})
    for i, t in enumerate(tracks):
        r = t.pop("readings")
        t["n_readings"] = len(r)
        t["avg"] = round(sum(r) / len(r), 2) if r else (t["start_crowd"] or None)
        t["end_crowd"] = r[-1] if r else t["start_crowd"]
        t["lift"] = (t["end_crowd"] - t["start_crowd"]) if t["start_crowd"] and t["end_crowd"] else 0
    readings = [p["crowd"] for p in timeline]
    lifted = sorted([t for t in tracks if t["lift"] > 0], key=lambda t: -t["lift"])[:5]
    dipped = sorted([t for t in tracks if t["lift"] < 0], key=lambda t: t["lift"])[:5]
    return {
        "started": session.started, "length_min": round((end - t0).total_seconds() / 60, 1),
        "timeline": timeline, "tracks": tracks,
        "avg_crowd": round(sum(readings) / len(readings), 2) if readings else None,
        "peak_share": round(sum(1 for r in readings if r >= 4) / len(readings) * 100) if readings else 0,
        "lifted": lifted, "dipped": dipped,
    }


# ---------- learning from your reviews ----------

@dataclass
class Memory:
    """What past live sets say. Lifts are in crowd-knob steps (e.g. +2 = from meh to into it while it played)."""
    track: Dict[str, List[float]] = field(default_factory=dict)  # track id -> lifts
    rescue: Dict[str, List[float]] = field(default_factory=dict)  # lifts when the room was dead/meh
    pair: Dict[tuple, List[float]] = field(default_factory=dict)  # (previous id, track id) -> lifts
    sets: int = 0

    TRACK_WEIGHT = 0.6  # cost points per crowd step of average lift (same scale as the transition weights)
    PAIR_WEIGHT = 0.5
    RESCUE_WEIGHT = 0.8

    @staticmethod
    def _shrunk(lifts: List[float]) -> float:
        """Average lift, pulled towards 0 when there's little evidence (1 play counts half, 3 plays count 3/4)."""
        return sum(lifts) / (len(lifts) + 1) if lifts else 0.0

    def bonus(self, prev_id: str, track_id: str, crowd: int) -> float:
        b = self.TRACK_WEIGHT * self._shrunk(self.track.get(track_id, []))
        b += self.PAIR_WEIGHT * self._shrunk(self.pair.get((prev_id, track_id), []))
        if crowd <= 2:
            b += self.RESCUE_WEIGHT * self._shrunk(self.rescue.get(track_id, []))
        return max(-2.5, min(2.5, b))

    def note(self, prev_id: str, track_id: str) -> str:
        """Short reason shown on a pick, e.g. 'lifted the room 2× before'."""
        pair = self.pair.get((prev_id, track_id), [])
        if pair and self._shrunk(pair) > 0:
            return "worked after this track before"
        lifts = self.track.get(track_id, [])
        up, down = sum(1 for x in lifts if x > 0), sum(1 for x in lifts if x < 0)
        if up > down:
            return f"lifted the room {up}× before"
        if down > up:
            return f"the room dipped {down}× with this one"
        return ""


def learn(sessions: Sequence[Session]) -> Memory:
    """Turn saved live sets into a Memory: how the crowd moved while each track played."""
    mem = Memory()
    for sess in sessions:
        r = review(sess, now=datetime.fromisoformat(sess.events[-1].at) if sess.events else None)
        counted = False
        for t in r["tracks"]:
            if not t["start_crowd"]:
                continue  # no reading yet when it started: nothing to compare with
            lift = float(t["lift"])
            if lift == 0:  # you didn't move the knob: keeping a hot room hot counts, leaving a dead room dead doesn't
                held = t["end_crowd"]
                lift = 0.5 if held >= 4 else -0.25 if held <= 2 else 0.0
            counted = True
            mem.track.setdefault(t["id"], []).append(lift)
            if t["start_crowd"] <= 2:
                mem.rescue.setdefault(t["id"], []).append(lift)
            if t["prev_id"]:
                mem.pair.setdefault((t["prev_id"], t["id"]), []).append(lift)
        mem.sets += counted
    return mem
