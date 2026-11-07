"""Write a set straight into rekordbox as a playlist (works for streamed SoundCloud tracks too).

Safety:
  * refuses to run while rekordbox is open (pyrekordbox also refuses to commit then)
  * backs up master.db (+ -wal/-shm, masterPlaylists6.xml) to data/backups/<timestamp>/ first
  * only ever ADDS a new playlist inside a "djnext" folder; existing playlists are never changed
"""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence

from ..paths import rekordbox_db_dir

FOLDER_NAME = "djnext"
MOODS_FOLDER = "djnext moods"
DEFAULT_BACKUP_DIR = Path("data/backups")
_FILES = ("master.db", "master.db-wal", "master.db-shm", "masterPlaylists6.xml")


class RekordboxRunning(RuntimeError):
    pass


def rekordbox_running() -> bool:
    from pyrekordbox.utils import get_rekordbox_pid

    return bool(get_rekordbox_pid())


def backup(db_dir: Optional[Path] = None, backup_dir: Path = DEFAULT_BACKUP_DIR) -> Path:
    db_dir = db_dir or rekordbox_db_dir()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest, i = backup_dir / stamp, 2
    while dest.exists():
        dest, i = backup_dir / f"{stamp}-{i}", i + 1
    dest.mkdir(parents=True)
    for name in _FILES:
        if (db_dir / name).exists():
            shutil.copy2(db_dir / name, dest / name)
    prune_backups(backup_dir)
    return dest


KEEP_BACKUPS = 15  # ~10 MB each; older ones are deleted so backups don't fill the disk


def prune_backups(backup_dir: Path = DEFAULT_BACKUP_DIR, keep: int = KEEP_BACKUPS) -> int:
    old = list_backups(backup_dir)[keep:]
    for d in old:
        shutil.rmtree(d, ignore_errors=True)
    return len(old)


def list_backups(backup_dir: Path = DEFAULT_BACKUP_DIR) -> List[Path]:
    if not backup_dir.exists():
        return []
    return sorted((d for d in backup_dir.iterdir() if (d / "master.db").exists()), key=lambda d: d.name, reverse=True)


def restore(backup_path: Path, db_dir: Optional[Path] = None) -> None:
    db_dir = db_dir or rekordbox_db_dir()
    if rekordbox_running():
        raise RekordboxRunning("close rekordbox before restoring a backup")
    if not (backup_path / "master.db").exists():
        raise FileNotFoundError(f"{backup_path} doesn't contain a master.db backup")
    for name in _FILES:
        target = db_dir / name
        if (backup_path / name).exists():
            shutil.copy2(backup_path / name, target)
        elif name.startswith("master.db-") and target.exists():
            target.unlink()  # stale WAL/SHM from after the backup would be replayed otherwise


def _unique_name(existing: Sequence[str], name: str) -> str:
    if name not in existing:
        return name
    i = 2
    while f"{name} ({i})" in existing:
        i += 1
    return f"{name} ({i})"


def write_to_rekordbox(
    content_ids: Optional[List[str]] = None,
    name: str = "",
    cues: Optional[Sequence] = None,
    remove_own_cues: bool = False,
    mood_playlists: Optional[dict] = None,  # {"🔥 Banging": [content ids]} -> "djnext moods" folder
    db_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = DEFAULT_BACKUP_DIR,
    check_running: bool = True,
) -> dict:
    """One safe write: check rekordbox is closed, back up, then (optionally) create a playlist in the
    djnext folder, add mix-point hot cues, or remove all djnext cues. Commits once."""
    from pyrekordbox import Rekordbox6Database

    from .rekordbox_cues import apply_cues, remove_cues

    db_dir = db_dir or rekordbox_db_dir()
    if check_running and rekordbox_running():
        raise RekordboxRunning("rekordbox is open: close it, then run this again")
    if not content_ids and not cues and not remove_own_cues and not mood_playlists:
        raise ValueError("nothing to write")
    backup_path = backup(db_dir, backup_dir) if backup_dir is not None else None

    logging.getLogger("pyrekordbox").setLevel(logging.ERROR)
    db = Rekordbox6Database(path=str(db_dir / "master.db"), db_dir=str(db_dir))
    result: dict = {"backup": backup_path, "folder": FOLDER_NAME}
    try:
        if content_ids:
            folders = [p for p in db.get_playlist().all() if p.Name == FOLDER_NAME and p.Attribute == 1]
            folder = folders[0] if folders else db.create_playlist_folder(FOLDER_NAME)
            siblings = [p.Name for p in db.get_playlist().all() if str(p.ParentID) == str(folder.ID)]
            final_name = _unique_name(siblings, name or "djnext set")
            playlist = db.create_playlist(final_name, parent=folder)
            for cid in content_ids:
                db.add_to_playlist(playlist, int(cid))
            result.update(name=final_name, tracks=len(content_ids))
        if mood_playlists:
            folders = [p for p in db.get_playlist().all() if p.Name == MOODS_FOLDER and p.Attribute == 1]
            mfolder = folders[0] if folders else db.create_playlist_folder(MOODS_FOLDER)
            existing = {p.Name: p for p in db.get_playlist().all()
                        if str(p.ParentID) == str(mfolder.ID) and p.Attribute == 0}
            made = {}
            for pl_name, ids in mood_playlists.items():
                if pl_name in existing:  # our own mood playlist from last time: refresh it
                    db.delete_playlist(existing[pl_name])
                if not ids:
                    continue
                pl = db.create_playlist(pl_name, parent=mfolder)
                for cid in ids:
                    db.add_to_playlist(pl, int(cid))
                made[pl_name] = len(ids)
            result["mood_playlists"] = made
            result["moods_folder"] = MOODS_FOLDER
        if remove_own_cues:
            result["removed_cues"] = remove_cues(db)
        if cues:
            written, skipped = apply_cues(db, cues)
            result.update(cues_written=written, cues_skipped=skipped)
        db.commit()
    finally:
        db.close()
    return result


def write_playlist(content_ids: List[str], name: str, cues: Optional[Sequence] = None, **kw) -> dict:
    if not content_ids:
        raise ValueError("empty set")
    return write_to_rekordbox(content_ids=content_ids, name=name, cues=cues, **kw)
