"""Closing, crashing and reopening djnext must never leave it erroring on the next start."""
from pathlib import Path

import pytest

from djnext.ingest.rekordbox_xml import load_library
from djnext.storage import read_json, write_json

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rekordbox.xml"


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


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from djnext import service
    from djnext.web import app as webapp

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service, "load_library", lambda: (load_library(FIXTURE), None))
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: None)
    monkeypatch.setattr(webapp, "_running", lambda: False)

    def fresh_start():  # like quitting djnext and opening it again
        webapp.STATE.update(lib=None, attach=None, set=None, live=None)
        return TestClient(webapp.app)

    return fresh_start


def _play(c, n=2, crowd=4):
    ids = [t["id"] for t in c.get("/api/live/search", params={"q": "sample"}).json()["tracks"][:n]]
    for i in ids:
        c.post("/api/live/now", json={"track_id": i})
    c.post("/api/live/crowd", json={"level": crowd})
    return ids


def test_reopening_mid_set_carries_on(app_client):
    c = app_client()
    ids = _play(c)
    c = app_client()  # closed and reopened
    s = c.get("/api/live/state").json()
    assert s["current"]["id"] == ids[-1] and s["crowd"] == 4 and s["played"] == 1 and s["session"]
    assert c.get("/api/live/suggest").json()["picks"]


def test_an_ended_set_is_not_resumed(app_client):
    c = app_client()
    _play(c)
    c.post("/api/live/end")
    c = app_client()
    s = c.get("/api/live/state").json()
    assert s["current"] is None and s["session"] is None
    assert c.get("/api/live/review").json()["tracks"]  # the ended set can still be reviewed


def test_reload_library_mid_set_keeps_your_place(app_client):
    c = app_client()
    ids = _play(c)
    c.post("/api/reload", json={})
    s = c.get("/api/live/state").json()
    assert s["current"]["id"] == ids[-1] and s["crowd"] == 4


def test_damaged_files_dont_stop_the_app(app_client, tmp_path):
    c = app_client()
    _play(c)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "settings.json").write_text("{oops")
    live = tmp_path / "data" / "live"
    (live / "2026-01-01T00-00-00.json").write_text("not json")
    c = app_client()
    assert c.get("/api/status").status_code == 200
    assert c.get("/api/live/state").status_code == 200
    assert c.get("/api/live/learned").status_code == 200
    assert c.get("/api/live/review").status_code == 200
