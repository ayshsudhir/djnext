import pytest

from djnext.core.camelot import key_steps, to_camelot

ALL_24 = {
    # minor (A)
    "Am": "8A", "Em": "9A", "Bm": "10A", "F#m": "11A", "C#m": "12A", "G#m": "1A",
    "D#m": "2A", "A#m": "3A", "Fm": "4A", "Cm": "5A", "Gm": "6A", "Dm": "7A",
    # major (B)
    "C": "8B", "G": "9B", "D": "10B", "A": "11B", "E": "12B", "B": "1B",
    "F#": "2B", "Db": "3B", "Ab": "4B", "Eb": "5B", "Bb": "6B", "F": "7B",
}


@pytest.mark.parametrize("musical,camelot", ALL_24.items())
def test_all_24_keys(musical, camelot):
    assert to_camelot(musical) == camelot


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("8A", "8A"), ("12b", "12B"), ("Bbm", "3A"), ("Ebm", "2A"), ("Cmaj", "8B"),
        ("Amin", "8A"), ("1m", "8A"), ("1d", "8B"), ("6d", "1B"), ("12d", "7B"),
        ("", None), (None, None), ("H", None), ("13A", None),
    ],
)
def test_other_notations(raw, expected):
    assert to_camelot(raw) == expected


def test_key_steps():
    assert key_steps("8A", "8A") == 0
    assert key_steps("8A", "9A") == 1
    assert key_steps("8A", "7A") == 1
    assert key_steps("8A", "8B") == 1
    assert key_steps("12A", "1A") == 1  # wheel wraps around
    assert key_steps("8A", "9B") == 2
    assert key_steps("8A", "3B") >= 5  # far away = clash
