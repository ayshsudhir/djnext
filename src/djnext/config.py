"""The few settings the mix points and hot cues need (config.yaml, all optional)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
SETTINGS_PATH = Path("data/settings.json")  # choices made in the app (SoundCloud user, removed tracks ...)


@dataclass
class Config:
    bpm_tolerance: float = 0.06  # the FLX4's default tempo range
    allow_half_double: bool = False  # groovy techno: never mix 65 into 130
    skill: str = "beginner"  # "beginner" = shorter blends (max 16 bars), "advanced" = up to 32 bars
    max_play_seconds: float = 240.0  # play roughly this much of each track before mixing out
    mix_overlap_seconds: float = 30.0


def load_config(path: Optional[Path] = None) -> Config:
    path = path or DEFAULT_CONFIG_PATH
    cfg = Config()
    if not path.exists():
        return cfg
    data = yaml.safe_load(path.read_text()) or {}
    bpm = data.get("bpm") or {}
    cfg.bpm_tolerance = float(bpm.get("tolerance", cfg.bpm_tolerance))
    timing = data.get("timing") or {}
    cfg.max_play_seconds = float(timing.get("max_play_seconds", cfg.max_play_seconds))
    cfg.mix_overlap_seconds = float(timing.get("mix_overlap_seconds", cfg.mix_overlap_seconds))
    if data.get("skill") in ("beginner", "advanced"):
        cfg.skill = data["skill"]
    return cfg
