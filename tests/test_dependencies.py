"""Every pyrekordbox name djnext imports must exist (a library update once renamed one and broke Send to rekordbox)."""
import importlib

import pytest

NEEDED = [
    ("pyrekordbox", "Rekordbox6Database"),
    ("pyrekordbox.db6", "tables"),
    ("pyrekordbox.utils", "get_rekordbox_pid"),
    ("pyrekordbox.config", "get_config"),
    ("pyrekordbox.anlz.file", "TAGS"),
    ("pyrekordbox.anlz.file", "XOR_MASK"),
]


@pytest.mark.parametrize("module,name", NEEDED)
def test_pyrekordbox_has_what_djnext_uses(module, name):
    assert hasattr(importlib.import_module(module), name)


def test_cue_tables_used_by_send_to_rekordbox():
    from pyrekordbox.db6 import tables

    assert hasattr(tables, "DjmdCue") and hasattr(tables, "DjmdContent")
