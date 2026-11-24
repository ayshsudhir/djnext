from datetime import datetime

from conftest import LIKED

from djnext.core import picker
from djnext.core.popularity import hotness
from djnext.ingest import sc_stats

NOW = datetime(2026, 11, 24)


def test_hot_tracks_rank_highest():
    a, b, c = LIKED[0], LIKED[1], LIKED[2]
    stats = {a.soundcloud_id: {"plays": 2_000_000, "uploaded": int(datetime(2026, 6, 1).timestamp())},
             b.soundcloud_id: {"plays": 5_000, "uploaded": int(datetime(2020, 1, 1).timestamp())}}
    hot, why = hotness([a, b, c], stats, {a.id: 9, b.id: 0}, now=NOW)
    assert hot[a.id] == 1.0 and hot[b.id] == 0.0 and hot[c.id] == 0.3  # c: no data, counts as average-ish
    assert why[a.id] == "2.0M plays on SoundCloud · 9 DJ sets this year"


def test_hot_bonus_and_reason():
    a, b = LIKED[0], LIKED[1]
    ev = picker.Evidence.build(hot={b.id: 1.0}, hot_why={b.id: "2.0M plays on SoundCloud"})
    m = picker.move(a, b, ev)
    assert m.parts["hot"] == picker.HOT_WEIGHT and "🔥 hot right now (2.0M plays on SoundCloud)" in m.why
    cold = picker.move(a, b, picker.Evidence.build(hot={b.id: 0.0}))
    assert m.score - cold.score == picker.HOT_WEIGHT


def test_stats_are_cached_and_refreshed_weekly(tmp_path):
    path = tmp_path / "stats.json"
    calls = []

    def fetch(sid):
        calls.append(sid)
        return {"plays": 10, "likes": 1, "uploaded": 0}
    sc_stats.update(LIKED[:3], path=path, fetch=fetch)
    sc_stats.update(LIKED[:3], path=path, fetch=fetch)  # fresh: not asked again
    assert len(calls) == 3 and len(sc_stats.load(path)) == 3
    old = sc_stats.load(path)
    for v in old.values():
        v["checked"] = "2020-01-01T00:00:00"
    assert len(sc_stats.stale(LIKED[:3], old)) == 3  # a week later: refresh
