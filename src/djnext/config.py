from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from .core.energy_curve import EnergyCurve

DEFAULT_CONFIG_PATH = Path("config.yaml")


@dataclass
class Weights:
    key: float = 3.0
    bpm: float = 1.0
    energy: float = 1.5
    direction: float = 0.7
    genre: float = 0.3
    artist: float = 1.0
    disliked_pair: float = 5.0  # you rated this pair 👎: practically never pair them again
    liked_pair: float = 0.5  # you rated this pair 👍: small preference
    mood_fit: float = 1.0  # prefer tracks that fit the chosen mood best


@dataclass
class Style:
    bpm_min: float = 0.0
    bpm_max: float = 999.0
    exclude_genres: List[str] = field(default_factory=list)
    favourite_artists: List[str] = field(default_factory=list)
    favourite_bonus: float = 0.5

    def allows(self, bpm: float, genre: str) -> bool:
        if bpm and not (self.bpm_min <= bpm <= self.bpm_max):
            return False
        g = (genre or "").lower()
        return not any(x.lower() in g for x in self.exclude_genres)

    def is_favourite(self, artist: str, title: str) -> bool:
        text = f"{artist} - {title}".lower()
        return any(a.lower() in text for a in self.favourite_artists)


@dataclass
class Config:
    weights: Weights = field(default_factory=Weights)
    style: Style = field(default_factory=Style)
    moods_raw: Optional[Dict[str, dict]] = None  # from config.yaml `moods:` (None = built-in defaults)
    pair_feedback: Dict[frozenset, int] = field(default_factory=dict)  # {a_id, b_id} -> +n liked / -n disliked
    bpm_tolerance: float = 0.06
    allow_half_double: bool = True
    artist_gap: int = 3
    skill: str = "beginner"  # "beginner" = simpler mixes and steps, "advanced" = longer blends, rolls, more knobs
    max_play_seconds: float = 240.0
    mix_overlap_seconds: float = 30.0
    default_curve: str = "classic-1h"
    curves: Dict[str, List[List[float]]] = field(
        default_factory=lambda: {
            "classic-1h": [
                [0.00, 1.5], [0.17, 4.0], [0.33, 6.5], [0.47, 8.8],
                [0.65, 5.3], [0.83, 6.6], [1.00, 8.8],
            ]
        }
    )

    def moods(self):
        from .core.moods import load_moods

        return load_moods(self.moods_raw)

    def curve(self, name: Optional[str] = None) -> EnergyCurve:
        from .core.moods import DEFAULT_MOOD_CURVES

        name = name or self.default_curve
        if name not in self.curves and name in DEFAULT_MOOD_CURVES:
            return EnergyCurve(DEFAULT_MOOD_CURVES[name], name=name)
        if name not in self.curves:
            raise KeyError(f"unknown curve '{name}'. Available: {', '.join(self.curves)}")
        return EnergyCurve(self.curves[name], name=name)


SETTINGS_PATH = Path("data/settings.json")  # style changes made in the web app


def _apply_settings_overrides(cfg: "Config") -> None:
    import json

    if not SETTINGS_PATH.exists():
        return
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8")) or {}
    if settings.get("skill") in ("beginner", "advanced"):
        cfg.skill = settings["skill"]
    st = settings.get("style") or {}
    for key in ("bpm_min", "bpm_max", "favourite_bonus"):
        if key in st:
            setattr(cfg.style, key, float(st[key]))
    for key in ("exclude_genres", "favourite_artists"):
        if key in st:
            setattr(cfg.style, key, list(st[key]))


FEEDBACK_DB = Path("data/feedback.sqlite")


def _load_pair_feedback(cfg: "Config") -> None:
    if not FEEDBACK_DB.exists():
        return
    import sqlite3

    try:
        rows = sqlite3.connect(str(FEEDBACK_DB)).execute("SELECT a_id, b_id, good FROM transitions").fetchall()
    except sqlite3.Error:
        return
    for a, b, good in rows:
        key = frozenset((str(a), str(b)))
        cfg.pair_feedback[key] = cfg.pair_feedback.get(key, 0) + (1 if good else -1)


def load_config(path: Optional[Path] = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    cfg = Config()
    _load_pair_feedback(cfg)
    if not path.exists():
        _apply_settings_overrides(cfg)
        return cfg
    data = yaml.safe_load(path.read_text()) or {}
    w = data.get("weights") or {}
    cfg.weights = Weights(**{k: float(v) for k, v in w.items() if hasattr(Weights, k)})
    bpm = data.get("bpm") or {}
    cfg.bpm_tolerance = float(bpm.get("tolerance", cfg.bpm_tolerance))
    cfg.allow_half_double = bool(bpm.get("allow_half_double", cfg.allow_half_double))
    timing = data.get("timing") or {}
    cfg.max_play_seconds = float(timing.get("max_play_seconds", cfg.max_play_seconds))
    cfg.mix_overlap_seconds = float(timing.get("mix_overlap_seconds", cfg.mix_overlap_seconds))
    cfg.artist_gap = int(data.get("artist_gap", cfg.artist_gap))
    cfg.skill = str(data.get("skill", cfg.skill))
    st = data.get("style") or {}
    cfg.style = Style(
        bpm_min=float(st.get("bpm_min", 0.0)),
        bpm_max=float(st.get("bpm_max", 999.0)),
        exclude_genres=list(st.get("exclude_genres") or []),
        favourite_artists=list(st.get("favourite_artists") or []),
        favourite_bonus=float(st.get("favourite_bonus", 0.5)),
    )
    _apply_settings_overrides(cfg)
    if data.get("curves"):
        cfg.curves = data["curves"]
    cfg.default_curve = data.get("default_curve", cfg.default_curve)
    if data.get("moods"):
        cfg.moods_raw = data["moods"]
    return cfg
