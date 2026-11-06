"""Store your thumbs up/down on transitions you actually mixed, and summarise them."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import Config
from .core.camelot import key_steps
from .core.mix_advice import advise
from .core.models import Track
from .core.scoring import bpm_gap

DEFAULT_DB = Path("data/feedback.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transitions (
    id INTEGER PRIMARY KEY,
    rated_at TEXT, set_name TEXT, position INTEGER,
    a_id TEXT, a_label TEXT, b_id TEXT, b_label TEXT,
    technique TEXT, key_steps INTEGER, bpm_gap REAL, energy_delta REAL,
    good INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS sets (
    id INTEGER PRIMARY KEY, rated_at TEXT, set_name TEXT, overall INTEGER, note TEXT
);
"""


def connect(db: Optional[Path] = None) -> sqlite3.Connection:
    db = db or DEFAULT_DB  # looked up at call time, so tests/web can point it elsewhere
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db))
    conn.executescript(_SCHEMA)
    return conn


@dataclass
class TransitionInfo:
    position: int
    a: Track
    b: Track
    technique: str
    key_steps: Optional[int]
    bpm_gap: Optional[float]
    energy_delta: float


def describe(tracks: Sequence[Track], cfg: Config) -> List[TransitionInfo]:
    out = []
    for i, (a, b) in enumerate(zip(tracks, tracks[1:]), 2):
        out.append(TransitionInfo(
            position=i, a=a, b=b,
            technique=advise(a, b, cfg).technique,
            key_steps=key_steps(a.key, b.key) if a.key and b.key else None,
            bpm_gap=bpm_gap(a.bpm, b.bpm, cfg.allow_half_double),
            energy_delta=(b.energy or 0) - (a.energy or 0),
        ))
    return out


def save_transition(conn: sqlite3.Connection, set_name: str, t: TransitionInfo, good: bool, note: str = "") -> None:
    conn.execute(
        "INSERT INTO transitions (rated_at, set_name, position, a_id, a_label, b_id, b_label, technique,"
        " key_steps, bpm_gap, energy_delta, good, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), set_name, t.position, t.a.id, t.a.label, t.b.id,
         t.b.label, t.technique, t.key_steps, t.bpm_gap, t.energy_delta, int(good), note),
    )
    conn.commit()


def save_set(conn: sqlite3.Connection, set_name: str, overall: int, note: str = "") -> None:
    conn.execute(
        "INSERT INTO sets (rated_at, set_name, overall, note) VALUES (?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), set_name, overall, note),
    )
    conn.commit()


def _key_bucket(steps: Optional[int]) -> str:
    if steps is None:
        return "unknown key"
    return {0: "same key", 1: "harmonic (1 step)", 2: "ok (2 steps)"}.get(steps, "clash (3+ steps)")


def _bpm_bucket(gap: Optional[float]) -> str:
    if gap is None:
        return "unknown"
    if gap <= 0.01:
        return "<=1%"
    if gap <= 0.03:
        return "1-3%"
    if gap <= 0.06:
        return "3-6%"
    return ">6%"


def summary(conn: sqlite3.Connection) -> Dict[str, object]:
    rows = conn.execute(
        "SELECT technique, key_steps, bpm_gap, good, note, a_label, b_label, set_name FROM transitions"
    ).fetchall()
    groups: Dict[str, Dict[str, List[int]]] = {
        "technique": defaultdict(list), "key": defaultdict(list), "tempo": defaultdict(list),
    }
    bad_notes: List[Tuple[str, str]] = []
    for technique, steps, gap, good, note, a, b, set_name in rows:
        groups["technique"][technique].append(good)
        groups["key"][_key_bucket(steps)].append(good)
        groups["tempo"][_bpm_bucket(gap)].append(good)
        if not good:
            bad_notes.append((f"{a} -> {b}", note or ""))
    sets = conn.execute("SELECT set_name, overall, note, rated_at FROM sets ORDER BY id").fetchall()
    total_good = sum(r[3] for r in rows)
    return {
        "rated": len(rows),
        "good": total_good,
        "groups": {k: {g: (sum(v), len(v)) for g, v in d.items()} for k, d in groups.items()},
        "bad": bad_notes,
        "sets": sets,
    }
