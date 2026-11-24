"""Closing, crashing and reopening djnext must never leave it erroring on the next start."""
from djnext.storage import read_json, write_json

def test_damaged_file_is_set_aside_not_fatal(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text('{"skill": "beginn')  # half-written: the app was closed mid-save
    assert read_json(p, {}) == {}
    assert not p.exists() and list(tmp_path.glob("settings.json.damaged-*"))  # kept for inspection
    write_json(p, {"skill": "advanced"})
    assert read_json(p) == {"skill": "advanced"} and not list(tmp_path.glob(".settings.json.*.tmp"))


def test_backups_are_trimmed(tmp_path):
    from djnext.export.rekordbox_playlist import backup, list_backups

    db = tmp_path / "rb"
    db.mkdir()
    (db / "master.db").write_bytes(b"x")
    for _ in range(18):
        backup(db, tmp_path / "backups")
    assert len(list_backups(tmp_path / "backups")) == 15
