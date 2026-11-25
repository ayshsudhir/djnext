"""Load phrase analysis + beat grid from rekordbox's analysis files (read-only)."""
from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..core.models import Track
from ..core.structure import TrackStructure
from ..paths import rekordbox_share_dir



def _read_tags(path: Path, wanted: Iterable[str]) -> Dict[str, object]:
    """Parse only the wanted tags of an ANLZ file (skipping the big waveform tags = ~50x faster)."""
    from construct import Int16ub
    from pyrekordbox.anlz.file import TAGS, XOR_MASK

    data = path.read_bytes()
    # every block starts with: 4-byte type, u32 header length, u32 total length (big-endian)
    magic, file_header_len, file_len = struct.unpack(">4sII", data[:12])
    if magic != b"PMAI":
        return {}
    wanted = set(wanted)
    found: Dict[str, object] = {}
    i = file_header_len
    while i + 12 <= min(file_len, len(data)) and wanted - set(found):
        raw_type, _, len_tag = struct.unpack(">4sII", data[i:i + 12])
        tag_type = raw_type.decode("ascii", "replace")
        if len_tag <= 0:
            break
        if tag_type in wanted:
            tag_data = data[i:i + len_tag]
            if tag_type == "PSSI" and not 1 <= Int16ub.parse(tag_data[18:20]) <= 3:
                # masked PSSI (same unmasking as pyrekordbox's AnlzFile)
                len_entries = Int16ub.parse(tag_data[16:18])
                buf = bytearray(tag_data)
                for x in range(len(buf) - 18):
                    buf[18 + x] ^= (XOR_MASK[x % len(XOR_MASK)] + len_entries) % 256
                tag_data = bytes(buf)
            found[tag_type] = TAGS[tag_type](tag_data)
        i += len_tag
    return found


def _bands(two_ex: Path) -> list:
    """rekordbox's 3-band waveform preview (PWV6, in the .2EX file): 1200 columns of (low, mid, high)."""
    if not two_ex.exists():
        return []
    tag = _read_tags(two_ex, ["PWV6"]).get("PWV6")
    if tag is None:
        return []
    raw = bytes(tag.content.entries)
    return [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw) - 2, 3)]


def load_structure(analysis_path: str, share_dir: Optional[Path] = None,
                   duration_s: float = 0.0) -> Optional[TrackStructure]:
    if not analysis_path:
        return None
    share_dir = share_dir or rekordbox_share_dir()
    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)
    base = share_dir / analysis_path.lstrip("/")
    dat, ext = base.with_suffix(".DAT"), base.with_suffix(".EXT")
    if not dat.exists() or not ext.exists():
        return None
    try:
        beats_tag = _read_tags(dat, ["PQTZ"]).get("PQTZ")
        pssi_tag = _read_tags(ext, ["PSSI"]).get("PSSI")
        if beats_tag is None or pssi_tag is None:
            return None
        _, bpms, times = beats_tag.get()
        pssi = pssi_tag.content
    except Exception:  # damaged / unexpected analysis file: just skip structure for this track
        return None
    if len(times) == 0:
        return None
    bpm = float(bpms[0]) if len(bpms) else 120.0
    entries = [(e.beat, e.kind) for e in pssi.entries]
    st = TrackStructure.build(bpm, [float(t) for t in times], int(pssi.mood), entries, int(pssi.end_beat))
    try:
        st.set_energy(_bands(base.with_suffix(".2EX")), duration_s)
    except Exception:  # no 3-band waveform: cues fall back to rekordbox's phrase names
        pass
    return st


def attach_structures(tracks: Iterable[Track], share_dir: Optional[Path] = None) -> Dict[str, int]:
    """Fill track.structure where rekordbox has phrase analysis. Returns counts for reporting."""
    counts = {"with": 0, "without": 0}
    for t in tracks:
        if t.structure is None and t.analysis_path:
            t.structure = load_structure(t.analysis_path, share_dir, float(t.duration or 0))
        counts["with" if t.structure else "without"] += 1
    return counts
