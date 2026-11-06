"""Where things live, on Mac and Windows.

rekordbox's library is found with pyrekordbox's own lookup (works for rekordbox 6 and 7 on both systems).
djnext's own files (config.yaml, data/) live in the folder you run it from, which is the project folder
when started with the "Start djnext" scripts.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path("config.yaml")
DATA_DIR = Path("data")


@lru_cache(maxsize=1)
def rekordbox_db_dir() -> Path:
    """Folder that holds rekordbox's master.db (e.g. ~/Library/Pioneer/rekordbox on a Mac,
    %APPDATA%\\Pioneer\\rekordbox on Windows)."""
    try:
        from pyrekordbox.config import get_config

        for version in ("rekordbox7", "rekordbox6"):
            try:
                db_dir = get_config(version).get("db_dir")
            except Exception:
                db_dir = None
            if db_dir and (Path(db_dir) / "master.db").exists():
                return Path(db_dir)
    except ImportError:
        pass
    return Path.home() / "Library" / "Pioneer" / "rekordbox"


def rekordbox_share_dir() -> Path:
    """Folder with rekordbox's analysis files (phrases, beat grids)."""
    return rekordbox_db_dir() / "share"
