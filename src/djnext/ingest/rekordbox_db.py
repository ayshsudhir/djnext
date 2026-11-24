"""Read rekordbox 6/7's own library database (master.db) with pyrekordbox.

Safety: the database is COPIED to a temporary folder first and only the copy is opened,
so your real rekordbox library is never touched (and it works while rekordbox is running).
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from ..core.camelot import to_camelot
from ..core.energy import assign_all
from ..core.models import Track
from ..paths import rekordbox_db_dir
from .rekordbox_xml import Library

_COPY = ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml")


def source_of(path: str) -> str:
    if ":" in path and not path.startswith("/"):
        return path.split(":", 1)[0]  # "soundcloud", "apple-music", "beatport" ...
    return "local"


def load_rekordbox_db(db_dir: Optional[Path] = None) -> Library:
    try:
        from pyrekordbox import Rekordbox6Database
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Reading the rekordbox database needs pyrekordbox: pip install pyrekordbox") from e

    db_dir = db_dir or rekordbox_db_dir()
    if not (db_dir / "master.db").exists():
        raise FileNotFoundError(f"no rekordbox database at {db_dir / 'master.db'}")

    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)  # "Rekordbox is running" is fine: we use a copy
    tmp = Path(tempfile.mkdtemp(prefix="djnext-rb-"))
    try:
        for name in _COPY:
            if (db_dir / name).exists():
                shutil.copy2(db_dir / name, tmp / name)
        db = Rekordbox6Database(path=str(tmp / "master.db"), db_dir=str(tmp))
        lib = Library()
        for c in db.get_content().all():
            path = c.FolderPath or ""
            if (c.Length or 0) < 30:  # sampler one-shots, sound effects
                continue
            t = Track(
                id=str(c.ID),
                title=c.Title or "",
                artist=c.ArtistName or "",
                bpm=(c.BPM or 0) / 100.0,
                key=to_camelot(c.KeyName),
                genre=c.GenreName or "",
                rating=int(c.Rating or 0),
                duration=float(c.Length or 0),
                path=path,
                comments=c.Commnt or "",
                source=source_of(path),
                analysis_path=c.AnalysisDataPath or "",
            )
            lib.tracks[t.id] = t
        for pl in db.get_playlist().all():
            if pl.Attribute != 0:  # 1 = folder, 4 = smart playlist
                continue
            songs = sorted(pl.Songs, key=lambda s: s.TrackNo or 0)
            ids = [str(s.ContentID) for s in songs if str(s.ContentID) in lib.tracks]
            if ids:
                lib.playlists[pl.Name] = ids
        db.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    assign_all(lib.tracks.values())
    return lib
