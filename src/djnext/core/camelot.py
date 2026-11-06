"""Musical key -> Camelot wheel conversion and harmonic distance."""
from __future__ import annotations

import re
from typing import Optional, Tuple

_MAJOR = {
    "C": 8, "G": 9, "D": 10, "A": 11, "E": 12, "B": 1, "CB": 1,
    "F#": 2, "GB": 2, "C#": 3, "DB": 3, "G#": 4, "AB": 4,
    "D#": 5, "EB": 5, "A#": 6, "BB": 6, "F": 7, "E#": 7,
}
_MINOR = {
    "A": 8, "E": 9, "B": 10, "F#": 11, "GB": 11, "C#": 12, "DB": 12,
    "G#": 1, "AB": 1, "D#": 2, "EB": 2, "A#": 3, "BB": 3,
    "F": 4, "E#": 4, "C": 5, "B#": 5, "G": 6, "D": 7,
}

_CAMELOT_RE = re.compile(r"^(\d{1,2})\s*([AaBb])$")
_OPENKEY_RE = re.compile(r"^(\d{1,2})\s*([mMdD])$")
_MUSICAL_RE = re.compile(r"^([A-Ga-g])([#b]?)\s*(m|min|minor|maj|major|M)?$")


def to_camelot(raw: Optional[str]) -> Optional[str]:
    """Convert 'Am', 'F#m', 'Bb', 'Cmaj', '8A', or Open Key '1m' to Camelot ('8A')."""
    if not raw:
        return None
    s = raw.strip().replace("♯", "#").replace("♭", "b")
    if not s:
        return None

    m = _CAMELOT_RE.match(s)
    if m:
        n = int(m.group(1))
        return f"{n}{m.group(2).upper()}" if 1 <= n <= 12 else None

    m = _OPENKEY_RE.match(s)
    if m:
        n = int(m.group(1))
        if not 1 <= n <= 12:
            return None
        letter = "A" if m.group(2).lower() == "m" else "B"
        return f"{((n + 6) % 12) + 1}{letter}"

    m = _MUSICAL_RE.match(s)
    if m:
        note = (m.group(1) + m.group(2)).upper()
        mode = m.group(3) or ""
        minor = mode in ("m", "min", "minor")
        table = _MINOR if minor else _MAJOR
        n = table.get(note)
        if n is None:
            return None
        return f"{n}{'A' if minor else 'B'}"
    return None


def parse(camelot: str) -> Tuple[int, str]:
    return int(camelot[:-1]), camelot[-1]


def key_steps(a: str, b: str) -> int:
    """Harmonic distance in wheel steps: 0 same key, 1 neighbour/relative, higher = clash."""
    na, la = parse(a)
    nb, lb = parse(b)
    d = abs(na - nb) % 12
    d = min(d, 12 - d)
    return d + (0 if la == lb else 1)
