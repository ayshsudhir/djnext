import pytest
from conftest import fake_library, soundcloud_data

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from djnext import service  # noqa: E402
from djnext.ingest import mixesdb  # noqa: E402
from djnext.web import app as webapp  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # settings, cache and backups land in a temp folder
    monkeypatch.setattr(service, "load_library", fake_library)
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: soundcloud_data())
    monkeypatch.setattr(service, "with_structure", lambda tracks: tracks)
    monkeypatch.setattr(webapp, "_running", lambda: False)
    webapp.STATE.update(lib=None, pool=None, counts=None, ev=None, verdicts=None, playlist=None, genre=None)
    webapp.LOOKUP.update(running=False, done=0, total=0, current="", error="")
    webapp.AUTO["started"] = True  # no real SoundCloud / MixesDB calls from the tests
    return TestClient(webapp.app)


def test_first_run_asks_for_soundcloud(client, monkeypatch):
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: None)
    assert client.get("/").status_code == 200
    s = client.get("/api/status").json()
    assert s["soundcloud"] is None and "pool" not in s
    assert client.post("/api/soundcloud/sync", json={"user": "has space"}).status_code == 400


def test_status_shows_your_likes_in_genre_lists(client):
    s = client.get("/api/status").json()
    assert s["pool"] == 12 and len(s["tracks"]) == 12
    assert all(t["id"] != "20" for t in s["tracks"])  # not liked
    genre = {t["id"]: t["genre"] for t in s["tracks"]}
    assert genre["1"] == "tech-house" and genre["11"] == "other" and genre["12"] == "hard-fast"
    assert {g["id"]: g["count"] for g in s["genres"]}["tech-house"] >= 6
    assert s["dj_checked"] == 0 and "history_sessions" not in s


def test_move_a_track_to_another_genre(client):
    s = client.post("/api/genre", json={"track_id": "1", "genre": "house"}).json()
    t = next(t for t in s["tracks"] if t["id"] == "1")
    assert t["genre"] == "house" and t["genre_why"] == "you put it here"
    s = client.post("/api/genre", json={"track_id": "1", "genre": None}).json()  # let djnext decide again
    assert next(t for t in s["tracks"] if t["id"] == "1")["genre"] == "tech-house"
    assert client.post("/api/genre", json={"track_id": "1", "genre": "polka"}).status_code == 400


def test_make_playlist_with_hot_cues(client):
    p = client.post("/api/playlist", json={"genre": "tech-house", "length": 6, "shape": "build"}).json()
    assert len(p["steps"]) == 6 and p["steps"][0]["why"] == "opener"
    assert all(s["id"] != "20" for s in p["steps"])
    assert all(s["genre"] == "tech-house" for s in p["steps"])  # only from the chosen list
    assert p["name"].startswith("Tech house")
    assert p["steps"][1]["cues"] and {c["slot"] for c in p["steps"][1]["cues"]} >= {"E"}  # cue-in on every incoming track
    start = client.post("/api/playlist", json={"genre": "tech-house", "length": 4, "start_id": "5"}).json()
    assert start["steps"][0]["id"] == "5"
    small = client.post("/api/playlist", json={"genre": "hard-fast", "length": 4})
    assert small.status_code == 400 and "Only 1 tracks" in small.json()["detail"]


def test_swap_and_doesnt_work_here(client):
    p = client.post("/api/playlist", json={"length": 6}).json()
    opts = client.post("/api/playlist/options", json={"position": 2}).json()["options"]
    used = {s["id"] for s in p["steps"]}
    assert opts and all(o["id"] not in used for o in opts)
    p2 = client.post("/api/playlist/replace", json={"position": 2, "track_id": opts[0]["id"]}).json()
    assert p2["steps"][2]["id"] == opts[0]["id"] and len(p2["steps"]) == 6
    before, dropped = p2["steps"][2]["id"], p2["steps"][3]["id"]
    p3 = client.post("/api/playlist/rebuild_from", json={"position": 3}).json()
    assert p3["steps"][2]["id"] == before and p3["steps"][3]["id"] != dropped
    assert [before, dropped] in service.read_settings()["blocked_pairs"]
    assert client.post("/api/playlist/options", json={"position": 0}).status_code == 400


def test_dont_use_a_track(client):
    p = client.post("/api/playlist", json={"length": 5}).json()
    gone = p["steps"][1]["id"]
    d = client.post("/api/remove", json={"track_id": gone}).json()
    assert d["status"]["pool"] == 11 and gone not in {s["id"] for s in d["playlist"]["steps"]}
    assert [t["id"] for t in client.get("/api/removed").json()["tracks"]] == [gone]
    d = client.post("/api/remove", json={"track_id": gone, "out": False}).json()
    assert d["status"]["pool"] == 12


def test_send_needs_rekordbox_closed_and_writes_cues(client, monkeypatch):
    import djnext.export.rekordbox_playlist as rp

    assert client.post("/api/send", json={}).status_code == 400  # nothing made yet
    client.post("/api/playlist", json={"length": 4})

    def running(*a, **k):
        raise rp.RekordboxRunning("open")
    monkeypatch.setattr(rp, "write_playlist", running)
    assert client.post("/api/send", json={}).status_code == 409

    seen = {}

    def write(ids, name, cues=None, **kw):
        seen.update(ids=ids, name=name, cues=cues)
        return {"name": name, "folder": "djnext", "tracks": len(ids), "cues_written": cues, "backup": "b"}
    monkeypatch.setattr(rp, "write_playlist", write)
    d = client.post("/api/send", json={"name": "Friday"}).json()
    assert d["name"] == "Friday" and d["tracks"] == 4 and len(seen["ids"]) == 4 and d["cues"] >= 3


def test_find_dj_pairs_runs_in_background(client, monkeypatch):
    done = []
    monkeypatch.setattr(mixesdb, "update", lambda tracks, progress=None: done.append(len(tracks)))
    client.post("/api/djsets", json={})
    import time
    for _ in range(50):
        if not webapp.LOOKUP["running"]:
            break
        time.sleep(0.02)
    assert done == [12] and webapp.LOOKUP["running"] is False


def test_send_genre_lists(client, monkeypatch):
    import djnext.export.rekordbox_playlist as rp

    seen = {}

    def write(**kw):
        seen.update(kw)
        return {"genres_folder": "djnext genres", "backup": "b",
                "genre_playlists": {k: len(v) for k, v in kw["genre_playlists"].items() if v}}
    monkeypatch.setattr(rp, "write_to_rekordbox", write)
    d = client.post("/api/send_genres", json={}).json()
    assert d["folder"] == "djnext genres" and d["playlists"]["Tech house"] >= 6
    assert set(seen["genre_playlists"]) == {"Groovy techno", "Tech house", "House", "Indie dance & melodic",
                                            "Hard & fast", "Other"}  # empty lists are cleared too


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
    assert client.post("/api/undo", json={}).status_code == 409
    monkeypatch.setattr(rp, "rekordbox_running", lambda: False)
    assert client.post("/api/undo", json={}).json() == {"restored": "20260101-000000"}
    assert (db_dir / "master.db").read_text() == "OLD"


def test_unexpected_errors_explain_themselves(client, monkeypatch):
    import djnext.export.rekordbox_playlist as rp

    client.post("/api/playlist", json={"length": 4})

    def boom(*a, **k):
        raise ModuleNotFoundError("No module named 'x'")
    monkeypatch.setattr(rp, "write_playlist", boom)
    r = TestClient(webapp.app, raise_server_exceptions=False).post("/api/send", json={})
    assert r.status_code == 500 and "was not changed" in r.json()["detail"]


def test_auto_refresh_updates_old_likes_then_looks_up(client, monkeypatch):
    data = soundcloud_data()
    data["synced_at"] = "2020-01-01T00:00:00"
    saved, looked = [], []
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: data)
    monkeypatch.setattr(webapp.sc, "fetch", lambda user, log=None: {**soundcloud_data(), "user": user})
    monkeypatch.setattr(webapp.sc, "save", lambda d: saved.append(d))
    monkeypatch.setattr(mixesdb, "update", lambda tracks, progress=None: looked.append(len(tracks)))
    webapp._auto_refresh()
    assert saved and saved[0]["user"] == "me" and saved[0]["playlists"] == {}
    assert looked == [12] and webapp.LOOKUP["running"] is False


def test_update_endpoints(client, monkeypatch):
    from djnext import updater

    monkeypatch.setattr(updater, "check", lambda: {"current": "0.3.0", "latest": "0.3.0", "newer": False,
                                                   "notes": "", "url": "", "how": "source"})
    assert client.get("/api/update").json()["newer"] is False
    assert client.post("/api/update", json={}).status_code == 400  # nothing newer
    monkeypatch.setattr(updater, "check", lambda: {"current": "0.3.0", "latest": "0.3.1", "newer": True,
                                                   "notes": "", "url": "u", "how": "source"})
    monkeypatch.setattr(updater, "how", lambda: "source")
    monkeypatch.setattr(updater, "update_source", lambda: "restart")
    assert client.post("/api/update", json={}).json() == {"done": "restart", "version": "0.3.1"}


def test_likes_missing_from_rekordbox(client, monkeypatch):
    data = soundcloud_data()
    data["likes"].append({"id": "999", "title": "Brand new like", "url": "https://soundcloud.com/x/new"})
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: data)
    assert client.get("/api/status").json()["counts"]["not_in_rekordbox"] == 1
    assert [t["url"] for t in client.get("/api/missing").json()["tracks"]] == ["https://soundcloud.com/x/new"]


def test_hidden_always_hides(client):
    """Bars styled with display:flex must still disappear when hidden (they did not in 0.3.2)."""
    html = client.get("/").text
    assert "[hidden] { display: none !important; }" in html


def test_make_another_gives_a_new_playlist(client):
    seen = []
    for _ in range(3):
        p = client.post("/api/playlist", json={"genre": "tech-house", "length": 4}).json()
        seen.append(tuple(s["id"] for s in p["steps"]))
    assert len(set(seen)) >= 2  # not the same playlist over and over
    recent = service.read_settings()["recent_playlists"]["tech-house"]
    assert [tuple(x) for x in recent] == seen[::-1]  # newest first, last 3 kept
    assert service.recent_penalties("tech-house")[seen[-1][0]] == 3.0
