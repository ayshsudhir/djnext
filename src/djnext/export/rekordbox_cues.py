"""Hot cues for the mix points, so you see them on the waveform and can hit them on the FLX4 pads.

  E  "djnext IN"        on the incoming track: where to cue it
  F  "djnext SWAP"      on the incoming track: its drop, swap the basses here
  G  "djnext NEXT > ..."  on the outgoing track: press play on the next track here

Your own cues are never changed: an occupied slot is skipped (another free pad is used).
All cues made here have a comment starting with "djnext", so they can be replaced or removed.
"""
from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from ..config import Config
from ..core.mix_advice import advise
from ..core.mix_points import plan as plan_points
from ..core.models import Track

TAG = "djnext"
# rekordbox stores hot cue A-H as Kind 1,2,3,5,6,7,8,9 (4 is skipped)
SLOT_KIND = {"A": 1, "B": 2, "C": 3, "D": 5, "E": 6, "F": 7, "G": 8, "H": 9}
KIND_SLOT = {v: k for k, v in SLOT_KIND.items()}
FALLBACK_ORDER = ["E", "F", "G", "H", "D", "C", "B"]  # A is usually the track's first beat


@dataclass
class CuePlan:
    content_id: str
    slot: str
    seconds: float
    comment: str
    track_label: str = ""


def _short(t: Track, n: int = 28) -> str:
    s = t.title or t.label
    return s if len(s) <= n else s[: n - 1] + "…"


def plan_cues(tracks: Sequence[Track], cfg: Config) -> List[CuePlan]:
    cues: List[CuePlan] = []
    for a, b in zip(tracks, tracks[1:]):
        technique = advise(a, b, cfg).technique
        mp = plan_points(a, b, technique, cfg)
        if mp is None:
            continue
        verb = "ECHO OUT, then" if technique == "echo_out" else "start"
        cues.append(CuePlan(a.id, "G", mp.play_b_at_s, f"{TAG} NEXT > {verb} {_short(b)}", a.label))
        cues.append(CuePlan(b.id, "E", mp.cue_b_s, f"{TAG} IN (play on A's {mp.play_b_at_s // 60:.0f}:"
                                                   f"{mp.play_b_at_s % 60:02.0f})", b.label))
        if mp.blend_bars > 0 and mp.swap_at_b_s - mp.cue_b_s > 1:
            what = "swap the bass here" if technique != "wash_out" else "B takes over"
            cues.append(CuePlan(b.id, "F", mp.swap_at_b_s, f"{TAG} SWAP: {what}", b.label))
    return cues


def apply_cues(db, cues: Sequence[CuePlan]) -> Tuple[List[CuePlan], List[CuePlan]]:
    """Inside an open pyrekordbox session (no commit). Returns (written, skipped)."""
    from pyrekordbox.db6 import tables

    content_ids = sorted({c.content_id for c in cues})
    existing: Dict[str, set] = {cid: set() for cid in content_ids}
    for cid in content_ids:
        for cue in db.get_cue(ContentID=cid).all():
            if (cue.Comment or "").startswith(TAG):
                db.delete(cue)  # our own old cues are replaced
            elif cue.Kind in KIND_SLOT:
                existing[cid].add(KIND_SLOT[cue.Kind])

    written, skipped = [], []
    now = datetime.datetime.now()
    for c in cues:
        taken = existing[c.content_id]
        slot = c.slot if c.slot not in taken else next((s for s in FALLBACK_ORDER if s not in taken), None)
        if slot is None:
            skipped.append(c)
            continue
        content = db.get_content(ID=c.content_id)
        if content is None:
            skipped.append(c)
            continue
        ms = int(round(max(0.0, c.seconds) * 1000))
        db.add(tables.DjmdCue(
            ID=str(db.generate_unused_id(tables.DjmdCue)),
            ContentID=str(c.content_id),
            InMsec=ms, InFrame=int(ms * 0.15), InMpegFrame=0, InMpegAbs=0,
            OutMsec=-1, OutFrame=0, OutMpegFrame=0, OutMpegAbs=0,
            Kind=SLOT_KIND[slot], Color=255, ColorTableIndex=0, ActiveLoop=0,
            Comment=c.comment, BeatLoopSize=0, CueMicrosec=0,
            ContentUUID=content.UUID, UUID=str(uuid.uuid4()),
            rb_data_status=0, rb_local_data_status=0, rb_local_deleted=0, rb_local_synced=0,
            created_at=now, updated_at=now,
        ))
        taken.add(slot)
        written.append(CuePlan(c.content_id, slot, c.seconds, c.comment, c.track_label))
    return written, skipped


def remove_cues(db) -> int:
    """Delete every cue this tool created (comment starts with 'djnext'). No commit."""
    from pyrekordbox.db6 import tables

    n = 0
    for cue in db.query(tables.DjmdCue).filter(tables.DjmdCue.Comment.like(f"{TAG}%")).all():
        db.delete(cue)
        n += 1
    return n
