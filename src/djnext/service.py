"""The steps behind every command, as plain functions (used by the web app; the CLI shares filter_pool)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .config import SETTINGS_PATH, Config, Style, load_config
from .core.energy import spread_guessed
from .core.mix_advice import MixAdvice, advise
from .core.models import Track
from .core.report import make_report, report_lines
from .core.sequencer import SetPlan, build_set
from .core.structure import fmt
from .export.m3u import read_m3u8, write_m3u8
from .ingest import soundcloud as sc
from .ingest.rekordbox_xml import Library

MAX_TRACK_SECONDS = 15 * 60  # longer = a recorded DJ set, not a track
MIN_TRACK_SECONDS = 120  # shorter = a clip/preview


# ---------- settings made in the web app (data/settings.json, layered over config.yaml) ----------

def read_settings() -> dict:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {}


def save_settings(updates: dict) -> dict:
    data = read_settings()
    data.update(updates)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return data


def config() -> Config:
    return load_config()


# ---------- library ----------

def load_library() -> Tuple[Library, Optional[sc.AttachResult]]:
    from .ingest.rekordbox_db import load_rekordbox_db

    lib = load_rekordbox_db()
    data = sc.load()
    return lib, (sc.attach(lib, data) if data else None)


def filter_pool(pool: List[Track], source: Optional[str], style: Optional[Style]) -> Tuple[List[Track], List[str]]:
    """Apply source / BPM-known / style / length filters. Returns (tracks, human-readable notes)."""
    notes: List[str] = []
    out = pool if not source else [t for t in pool if t.source == source or (source == "local" and not t.is_stream)]
    seen, uniq = set(), []
    for t in out:  # the same track can be in rekordbox twice (e.g. a SoundCloud track added two times)
        key = t.path or t.label.lower()
        if key not in seen:
            seen.add(key)
            uniq.append(t)
    if len(uniq) < len(out):
        notes.append(f"Ignoring {len(out) - len(uniq)} duplicate entries of the same track.")
    out = uniq
    no_bpm = [t for t in out if t.bpm <= 0]
    if no_bpm:
        notes.append(f"Skipping {len(no_bpm)} tracks with no BPM (not analysed in rekordbox).")
        out = [t for t in out if t.bpm > 0]
    if style is not None:
        off = [t for t in out if not style.allows(t.bpm, t.genre)]
        if off:
            notes.append(f"Style filter ({style.bpm_min:.0f}-{style.bpm_max:.0f} BPM, no "
                         f"{'/'.join(style.exclude_genres[:3])}...): left out {len(off)} tracks.")
            out = [t for t in out if style.allows(t.bpm, t.genre)]
    clips = [t for t in out if 0 < t.duration < MIN_TRACK_SECONDS]
    if clips:
        notes.append(f"Skipping {len(clips)} clips shorter than 2 min, e.g. {clips[0].label}.")
        out = [t for t in out if not 0 < t.duration < MIN_TRACK_SECONDS]
    long_ones = [t for t in out if t.duration > MAX_TRACK_SECONDS]
    if long_ones:
        notes.append(f"Skipping {len(long_ones)} recordings longer than {MAX_TRACK_SECONDS // 60} min "
                     f"(DJ sets/mixes, not tracks), e.g. {long_ones[0].label}.")
        out = [t for t in out if t.duration <= MAX_TRACK_SECONDS]
    return out, notes


def pool_from(lib: Library, lists: Optional[Sequence[str]], source: Optional[str],
              style: Optional[Style]) -> Tuple[List[Track], List[str]]:
    if lists:
        uniq: Dict[str, Track] = {}
        for name in lists:
            for t in lib.playlist_tracks(name):
                uniq.setdefault(t.id, t)
        tracks = list(uniq.values())
    else:
        tracks = list(lib.tracks.values())
    return filter_pool(tracks, source, style)


def with_structure(tracks: List[Track]) -> List[Track]:
    from .ingest.rekordbox_anlz import attach_structures

    todo = [t for t in tracks if t.analysis_path and t.structure is None]
    if todo:
        attach_structures(todo)
    return tracks


# ---------- making a set ----------

@dataclass
class SetResult:
    plan: SetPlan
    advice: List[Optional[MixAdvice]]
    notes: List[str] = field(default_factory=list)
    set_file: Path = Path("set.m3u8")


def exclude_only(style: Style) -> Style:
    """Moods bring their own tempo rules; only keep the genres you never want."""
    return Style(exclude_genres=list(style.exclude_genres), favourite_artists=list(style.favourite_artists))


def mood_pools(lib: Library, cfg: Config, lists: Optional[Sequence[str]] = None,
               source: Optional[str] = "soundcloud") -> Tuple[Dict[str, list], List[str]]:
    from .core.moods import classify

    pool, notes = pool_from(lib, lists, source, cfg.style)  # stick to your genres / BPM range
    with_structure(pool)
    return classify(pool, cfg.moods(), cfg.style.favourite_artists), notes


def make_set(lib: Library, cfg: Config, lists: Optional[Sequence[str]] = None, source: Optional[str] = None,
             length_min: float = 60, curve: Optional[str] = None, use_style: bool = True,
             set_file: Path = Path("set.m3u8"), mood: Optional[str] = None) -> SetResult:
    for t in lib.tracks.values():
        t.mood_fit = 0.0  # don't let a previous mood's scores leak into this set
    if mood:
        moods = cfg.moods()
        if mood not in moods:
            raise ValueError(f"Unknown mood '{mood}'. Choose one of: {', '.join(moods)}")
        pools, notes = mood_pools(lib, cfg, lists, source)
        pool = []
        for t, score in pools[mood]:
            t.mood_fit = score
            pool.append(t)
        notes.append(f"{moods[mood].label}: {len(pool)} of your tracks fit this mood.")
        curve = curve or moods[mood].curve
        if len(pool) < 8:
            raise ValueError(f"Only {len(pool)} tracks fit {moods[mood].label}. Try another mood, or analyse more "
                             "tracks in rekordbox.")
    else:
        pool, notes = pool_from(lib, lists, source, cfg.style if use_style else None)
    if not pool:
        raise ValueError("No tracks to pick from with these settings.")
    with_structure(pool)
    if spread_guessed(pool):
        notes.append("No energy ratings, so energy was estimated from tempo + how much of each track is drops, "
                     "ranked within these tracks. Star-rate tracks in rekordbox for better results.")
    plan = build_set(pool, cfg.curve(curve), cfg, length_min=length_min)
    advice: List[Optional[MixAdvice]] = [None] + [
        advise(a.track, b.track, cfg, plan.unused) for a, b in zip(plan.slots, plan.slots[1:])
    ]
    write_m3u8(plan.tracks, set_file)
    write_notes(plan, advice, set_file.with_name(set_file.stem + "_notes.txt"))
    return SetResult(plan, advice, notes, set_file)


def write_notes(plan: SetPlan, advice: List[Optional[MixAdvice]], out: Path) -> Path:
    lines = [f"DJ set notes: {plan.curve.name}, {plan.length_s / 60:.0f} min", ""]
    for i, (slot, adv) in enumerate(zip(plan.slots, advice), 1):
        t = slot.track
        lines.append(f"{i:2d}. [{fmt(slot.start_s)}] {t.label}  ({t.bpm:.1f} BPM, {t.key or '?'}, energy {t.energy or 0:.0f})")
        if adv is not None:
            lines.append("    " + adv.text().replace("\n", "\n    "))
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def set_to_json(res: SetResult, cfg: Config) -> dict:
    plan = res.plan
    rep = make_report(plan.tracks, plan.curve, cfg, plan.length_s)
    rows = []
    for i, (slot, adv) in enumerate(zip(plan.slots, res.advice), 1):
        t = slot.track
        rows.append({
            "n": i, "time": fmt(slot.start_s), "start_min": slot.start_s / 60, "id": t.id,
            "title": t.title, "artist": t.artist, "label": t.label, "bpm": round(t.bpm, 1), "key": t.key or "?",
            "energy": t.energy, "energy_source": t.energy_source, "target": round(slot.target, 1),
            "transition": slot.reason if i > 1 else "opener",
            "technique": adv.title if adv else None, "technique_id": adv.technique if adv else None,
            "timing": adv.timing if adv else [], "steps": adv.steps if adv else [],
            "advice_notes": adv.notes if adv else [], "alternative": adv.alternative if adv else None,
            "bridge": adv.bridge.label if adv and adv.bridge else None,
        })
    xs = [i / 100 for i in range(101)]
    return {
        "curve": plan.curve.name, "length_min": plan.length_s / 60, "tracks": rows, "notes": res.notes,
        "report": report_lines(rep), "vs_random_pct": round(rep.vs_random_pct),
        "curve_points": [{"x": x * plan.length_s / 60, "y": round(plan.curve.target(x), 2)} for x in xs],
        "unused": len(plan.unused),
        "bpm_guessed": sum(1 for t in plan.tracks if t.energy_source in ("bpm", "spread")),
    }


def tracks_from_set(lib: Library, set_file: Path) -> List[Track]:
    by_path = {t.path: t for t in lib.tracks.values() if t.path}
    by_label = {t.label.lower(): t for t in lib.tracks.values()}
    out = []
    for location, label in read_m3u8(set_file):
        t = by_path.get(location) or by_label.get(label.lower())
        if t is not None:
            out.append(t)
    return with_structure(out)


def default_set_name(curve: str) -> str:
    return f"{datetime.now():%b %d %H.%M} {curve}"
