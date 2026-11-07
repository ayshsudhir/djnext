from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from djnext import feedback as fb  # noqa: E402
from djnext import service  # noqa: E402
from djnext.ingest.rekordbox_xml import load_library  # noqa: E402
from djnext.web import app as webapp  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rekordbox.xml"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # set.m3u8 / notes / settings land in a temp folder
    monkeypatch.setattr(service, "load_library", lambda: (load_library(FIXTURE), None))
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: None)
    monkeypatch.setattr(fb, "DEFAULT_DB", tmp_path / "fb.sqlite")
    monkeypatch.setattr(webapp, "_running", lambda: True)
    webapp.STATE.update(lib=None, attach=None, set=None)
    return TestClient(webapp.app)


def test_page_and_status(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    s = client.get("/api/status").json()
    assert s["library"]["total"] == 32 and s["soundcloud"] is None
    assert any(l["key"] == "Gigs/Friday" for l in s["rekordbox_lists"])


def test_make_set_rate_and_feedback(client, tmp_path):
    r = client.post("/api/set", json={"lists": ["Gigs/Friday"], "source": None, "length": 30, "use_style": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["tracks"]) >= 5 and d["tracks"][1]["technique"]
    assert (tmp_path / "set.m3u8").exists() and (tmp_path / "set_notes.txt").exists()
    r = client.post("/api/rate", json={"ratings": [{"position": 2, "good": True}, {"position": 3, "good": False, "note": "meh"}],
                                       "overall": 4})
    assert r.json() == {"saved": 2}
    f = client.get("/api/feedback").json()
    assert f["rated"] == 2 and f["good"] == 1


def test_push_refuses_while_rekordbox_open(client, monkeypatch):
    import djnext.export.rekordbox_playlist as rp

    monkeypatch.setattr(rp, "rekordbox_running", lambda: True)
    client.post("/api/set", json={"lists": ["Gigs/Friday"], "source": None, "length": 30, "use_style": False})
    r = client.post("/api/push", json={"cues": True})
    assert r.status_code == 409


def test_settings_saved_and_validated(client, tmp_path):
    assert client.post("/api/settings", json={"bpm_min": 130, "bpm_max": 120}).status_code == 400
    s = client.post("/api/settings", json={"bpm_min": 120, "bpm_max": 128, "favourite_artists": ["Cloonee", " "]}).json()
    assert s["style"]["bpm_max"] == 128 and s["style"]["favourite_artists"] == ["Cloonee"]
    assert (tmp_path / "data" / "settings.json").exists()


def test_moods_and_mood_set(client):
    moods = client.get("/api/moods").json()["moods"]
    assert {m["key"] for m in moods} >= {"warmup", "drunk", "banging", "afters"}
    best = max(moods, key=lambda m: m["count"])
    if best["count"] >= 8:
        r = client.post("/api/set", json={"mood": best["key"], "length": 30})
        assert r.status_code == 200, r.text
        assert any("fit this mood" in n for n in r.json()["notes"])
    thin = [m for m in moods if m["count"] < 8]
    if thin:
        assert client.post("/api/set", json={"mood": thin[0]["key"], "length": 30}).status_code == 400


def test_undo_restores_latest_backup(client, tmp_path, monkeypatch):
    import djnext.export.rekordbox_playlist as rp

    assert client.post("/api/undo", json={}).status_code == 400  # no backups yet
    db_dir = tmp_path / "rb"
    db_dir.mkdir()
    (db_dir / "master.db").write_text("NEW")
    old = tmp_path / "data" / "backups" / "20260101-000000"
    old.mkdir(parents=True)
    (old / "master.db").write_text("OLD")
    monkeypatch.setattr(rp, "rekordbox_db_dir", lambda: db_dir)
    monkeypatch.setattr(rp, "rekordbox_running", lambda: True)
    assert client.post("/api/undo", json={}).status_code == 409  # refuses while rekordbox is open
    monkeypatch.setattr(rp, "rekordbox_running", lambda: False)
    assert client.post("/api/undo", json={}).json() == {"restored": "20260101-000000"}
    assert (db_dir / "master.db").read_text() == "OLD"


def test_first_run_setup_and_rekordbox_poll(client):
    assert client.get("/api/status").json()["onboarded"] is False  # no SoundCloud, no setup yet: show the wizard
    assert client.get("/api/rekordbox").json() == {"running": True}
    s = client.post("/api/settings", json={"bpm_min": 165, "bpm_max": 178, "favourite_artists": [],
                                           "exclude_genres": [], "onboarded": True}).json()
    assert s["onboarded"] is True and s["style"]["bpm_min"] == 165
    s = client.post("/api/settings", json={"bpm_min": 120, "bpm_max": 130}).json()  # later saves keep the flag
    assert s["onboarded"] is True


def test_unexpected_errors_explain_themselves(client, monkeypatch):
    from fastapi.testclient import TestClient

    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'x'")

    monkeypatch.setattr(webapp, "_running", lambda: False)
    client.post("/api/set", json={"length": 30, "source": None})
    import djnext.export.rekordbox_playlist as rp
    monkeypatch.setattr(rp, "write_to_rekordbox", boom)
    r = TestClient(webapp.app, raise_server_exceptions=False).post("/api/push", json={})
    assert r.status_code == 500 and "was not changed" in r.json()["detail"] and "No module" in r.json()["detail"]
