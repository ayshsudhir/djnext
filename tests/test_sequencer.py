from pathlib import Path

import pytest

from djnext.config import Config
from djnext.core.models import Track
from djnext.core.sequencer import _cost, build_set, evaluate, suggest_next
from djnext.export.m3u import write_m3u8
from djnext.ingest.rekordbox_xml import load_library

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rekordbox.xml"
CFG = Config()


@pytest.fixture(scope="module")
def lib():
    return load_library(FIXTURE)


@pytest.fixture(scope="module")
def plan(lib):
    return build_set(lib.playlist_tracks("Friday"), CFG.curve(), CFG, length_min=60, time_budget_s=3)


def test_xml_parsing(lib):
    assert len(lib.tracks) == 32
    assert "Gigs/Friday" in lib.playlists
    t = lib.tracks["1"]
    assert t.key == "12A" and t.bpm == pytest.approx(125.87) and t.energy == 8
    assert t.path == "/Users/demo/Music/Sample Track 01.mp3"  # URL-decoded
    assert len(lib.playlist_tracks("friday")) == 24


def test_no_repeats_and_fills_set(plan):
    ids = [t.id for t in plan.tracks]
    assert len(ids) == len(set(ids))
    last = plan.slots[-1]
    assert last.start_s < 60 * 60 <= last.start_s + 300  # roughly an hour


def test_energy_follows_curve(plan):
    def avg(lo, hi):
        es = [s.track.energy for s in plan.slots if lo <= s.start_s / 60 < hi]
        return sum(es) / len(es)

    peak = max(plan.slots, key=lambda s: s.track.energy)
    assert 20 <= peak.start_s / 60 <= 35 or peak.start_s / 60 >= 50  # a peak slot
    assert avg(0, 10) < avg(20, 35)  # warm-up below first peak
    assert avg(35, 45) < avg(20, 35)  # breather below first peak
    assert avg(35, 45) < avg(50, 61)  # final build back up


def test_start_track_is_respected(lib):
    pool = lib.playlist_tracks("Friday")
    opener = lib.find("Sample Track 03", pool)
    plan = build_set(pool, CFG.curve(), CFG, length_min=30, start=opener, time_budget_s=1)
    assert plan.tracks[0].id == opener.id


def test_beats_hand_made_order(lib, plan):
    """The optimiser should never be worse than simply sorting by energy."""
    naive = sorted(lib.playlist_tracks("Friday"), key=lambda t: t.energy)[: len(plan.slots)]
    assert plan.total_cost <= _cost(naive, CFG.curve(), CFG, 3600)


def test_fast_cost_matches_evaluate(plan):
    assert _cost(plan.tracks, CFG.curve(), CFG, 3600) == pytest.approx(
        evaluate(plan.tracks, CFG.curve(), CFG, 3600).total_cost
    )


def test_suggest_next_prefers_compatible():
    cur = Track("c", "Now", bpm=124, key="8A", energy=6, genre="House")
    good = Track("g", "Good", bpm=125, key="9A", energy=6.5, genre="House")
    bad = Track("b", "Bad", bpm=150, key="3B", energy=2, genre="Trance")
    res = suggest_next(cur, [bad, good, cur], CFG.curve(), CFG, at_fraction=0.3)
    assert [s.track.id for s in res] == ["g", "b"]  # current track excluded


def test_m3u8(tmp_path, plan):
    out = write_m3u8(plan.tracks[:2], tmp_path / "set.m3u8")
    lines = out.read_text().splitlines()
    assert lines[0] == "#EXTM3U"
    assert lines[1].startswith("#EXTINF:")
    assert lines[2].endswith(".mp3")
