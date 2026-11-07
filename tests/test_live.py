from datetime import datetime, timedelta
from pathlib import Path

import pytest

from djnext.config import Config
from djnext.core.live import CROWD, Session, review, suggest
from djnext.ingest.rekordbox_xml import load_library

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rekordbox.xml"


def _pool():
    lib = load_library(FIXTURE)
    return [t for t in lib.tracks.values() if t.bpm > 0]


def test_crowd_steers_energy():
    pool = _pool()
    cur = sorted(pool, key=lambda t: t.energy or 5)[len(pool) // 2]
    cfg = Config()
    dead = suggest(cur, pool, 1, cfg, top=5)
    wild = suggest(cur, pool, 5, cfg, top=5)
    assert dead and wild and cur.id not in {p.track.id for p in dead + wild}
    avg = lambda ps: sum(p.energy_delta for p in ps) / len(ps)  # noqa: E731
    assert avg(dead) > avg(wild)  # a dead room gets a bigger lift than a room that's already going off
    assert all(c.need for c in CROWD.values())


def test_pleasers_get_priority_when_the_room_is_dead():
    pool = _pool()
    cur = pool[0]
    cfg = Config()
    plain = suggest(cur, pool, 1, cfg, top=len(pool))
    last = plain[-1].track.id
    boosted = suggest(cur, pool, 1, cfg, pleasers={last: 1.0}, top=len(pool))
    assert [p.track.id for p in boosted].index(last) < len(pool) - 2
    assert all(t.mood_fit == 0 for t in pool)  # scores don't leak into the library


def test_review_finds_tracks_that_lifted_the_room():
    pool = _pool()
    s = Session(started="2026-11-07T22:00:00")
    t0 = datetime.fromisoformat(s.started)
    from djnext.core.live import Event
    ev = lambda m, kind, t=None, c=0: Event((t0 + timedelta(minutes=m)).isoformat(), kind,  # noqa: E731
                                            t.id if t else "", t.label if t else "", c)
    s.events = [ev(0, "track", pool[0]), ev(1, "crowd", c=2), ev(4, "track", pool[1]), ev(6, "crowd", c=4),
                ev(8, "track", pool[2]), ev(9, "crowd", c=3)]
    r = review(s, now=t0 + timedelta(minutes=12))
    assert r["length_min"] == 12 and [p["crowd"] for p in r["timeline"]] == [2, 4, 3]
    assert r["lifted"][0]["id"] == pool[1].id and r["dipped"][0]["id"] == pool[2].id


fastapi = pytest.importorskip("fastapi")


def test_live_endpoints(client_live):
    c = client_live
    assert c.get("/live").status_code == 200
    hits = c.get("/api/live/search", params={"q": "sample track"}).json()["tracks"]
    assert hits
    assert c.get("/api/live/suggest").json()["picks"] == []  # nothing playing yet
    c.post("/api/live/now", json={"track_id": hits[0]["id"]})
    c.post("/api/live/crowd", json={"level": 5})
    s = c.get("/api/live/suggest").json()
    assert s["name"] == "Going off" and s["picks"] and s["picks"][0]["technique"]
    c.post("/api/live/now", json={"track_id": s["picks"][0]["id"]})
    r = c.post("/api/live/end").json()
    assert len(r["tracks"]) == 2 and r["timeline"][0]["crowd"] == 5
    assert c.get("/api/live/sessions").json()["sessions"]
    learned = c.get("/api/live/learned").json()
    assert learned["sets"] == 1 and learned["tracks"] >= 1
    assert "learned" in c.get("/api/live/suggest").json()["picks"][0] if c.get("/api/live/state").json()["current"] else True


@pytest.fixture()
def client_live(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from djnext import service
    from djnext.web import app as webapp

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(service, "load_library", lambda: (load_library(FIXTURE), None))
    monkeypatch.setattr(webapp.sc, "load", lambda *a, **k: None)
    webapp.STATE.update(lib=None, attach=None, set=None, live=None)
    return TestClient(webapp.app)


def _set(start, plan):
    """plan: list of (minute, 'track', Track) or (minute, 'crowd', level)."""
    from djnext.core.live import Event
    s = Session(started=start)
    t0 = datetime.fromisoformat(start)
    for m, kind, x in plan:
        at = (t0 + timedelta(minutes=m)).isoformat()
        s.events.append(Event(at, "track", x.id, x.label) if kind == "track" else Event(at, "crowd", crowd=x))
    return s


def test_learns_from_reviews_and_moves_lifters_up():
    from djnext.core.live import learn

    pool = _pool()
    cur = pool[0]
    cfg = Config()
    before = [p.track.id for p in suggest(cur, pool, 3, cfg, top=len(pool))]
    lifter, dud = before[-1], before[0]  # worst-ranked track turns out to lift the room; the top pick flops
    lib = {t.id: t for t in pool}
    sets = [_set(f"2026-11-0{d}T22:00:00", [(0, "track", cur), (1, "crowd", 2), (3, "track", lib[lifter]), (5, "crowd", 5),
                                           (8, "track", lib[dud]), (9, "crowd", 2)]) for d in (1, 2, 3)]
    mem = learn(sets)
    assert mem.sets == 3 and mem.track[lifter] == [3.0, 3.0, 3.0] and mem.track[dud] == [-3.0, -3.0, -3.0]
    after = [p.track.id for p in suggest(cur, pool, 3, cfg, top=len(pool), memory=mem)]
    assert after.index(lifter) < before.index(lifter) and after.index(dud) > before.index(dud)
    assert mem.note(cur.id, lifter) == "worked after this track before"
    assert "dipped" in mem.note("someone-else", dud)
    assert mem.bonus(cur.id, lifter, 1) > mem.bonus(cur.id, lifter, 4)  # rescue tracks count extra when the room is dead


def test_holding_a_hot_room_counts_without_touching_the_knob():
    from djnext.core.live import learn

    pool = _pool()
    mem = learn([_set("2026-11-01T22:00:00", [(0, "track", pool[0]), (1, "crowd", 5), (3, "track", pool[1]),
                                              (7, "track", pool[2]), (8, "crowd", 1), (9, "track", pool[3])])])
    assert mem.track[pool[1].id] == [0.5]  # stayed at going-off
    assert mem.track[pool[3].id] == [-0.25]  # left a dead room dead
