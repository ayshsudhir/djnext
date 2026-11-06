"""Write an .m3u8 playlist that rekordbox can import (File > Import > Import Playlist, or drag & drop)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Sequence, Tuple

from ..core.models import Track


def write_m3u8(tracks: Sequence[Track], out: Path) -> Path:
    lines = ["#EXTM3U"]
    for t in tracks:
        lines.append(f"#EXTINF:{int(t.duration)},{t.label}")
        lines.append(t.path or t.label)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def read_m3u8(path: Path) -> List[Tuple[str, str]]:
    """Return (location, label) pairs from an .m3u8 file, in order."""
    entries: List[Tuple[str, str]] = []
    label = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            label = line.split(",", 1)[1] if "," in line else ""
        elif not line.startswith("#"):
            entries.append((line, label))
            label = ""
    return entries
