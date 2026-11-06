from pathlib import Path

from djnext import feedback as fb
from djnext.config import Config
from djnext.core.models import Track
from djnext.core.report import make_report
from djnext.core.sequencer import build_set
from djnext.export.m3u import read_m3u8, write_m3u8
from djnext.ingest.rekordbox_xml import load_library

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rekordbox.xml"
CFG = Config()


def T(id, bpm, key, energy):
    return Track(id, f"T{id}", artist="A" + id, bpm=bpm, key=key, energy=energy, genre="House")


def test_report_counts():
    tracks = [T("1", 124, "8A", 3), T("2", 124, "9A", 4), T("3", 124, "3B", 5), T("4", 150, "3B", 6)]
    r = make_report(tracks, CFG.curve(), CFG)
    assert r.transitions == 3
    assert r.harmonic == 2  # 8A->9A and 3B->3B
    assert r.clashes == 1  # 9A->3B
    assert r.tempo_out_of_range == 1  # 124->150


def test_optimised_set_beats_random():
    lib = load_library(FIXTURE)
    plan = build_set(lib.playlist_tracks("Friday"), CFG.curve(), CFG, 60, time_budget_s=2)
    r = make_report(plan.tracks, CFG.curve(), CFG, plan.length_s)
    assert r.cost < r.random_cost
    assert r.vs_random_pct > 30
    assert r.curve_correlation is not None and r.curve_correlation > 0.7


def test_m3u8_round_trip(tmp_path):
    tracks = [Track("1", "One", artist="A", path="/music/one.mp3", duration=300), Track("2", "Two", artist="B")]
    entries = read_m3u8(write_m3u8(tracks, tmp_path / "s.m3u8"))
    assert entries == [("/music/one.mp3", "A - One"), ("B - Two", "B - Two")]


def test_feedback_store_and_summary(tmp_path):
    conn = fb.connect(tmp_path / "fb.sqlite")
    tracks = [T("1", 124, "8A", 3), T("2", 125, "9A", 4), T("3", 124, "3B", 5)]
    infos = fb.describe(tracks, CFG)
    assert [i.technique for i in infos] == ["bass_swap", "echo_out"]
    fb.save_transition(conn, "test", infos[0], good=True)
    fb.save_transition(conn, "test", infos[1], good=False, note="vocals clashed")
    fb.save_set(conn, "test", 4)
    s = fb.summary(conn)
    assert s["rated"] == 2 and s["good"] == 1
    assert s["groups"]["technique"]["bass_swap"] == (1, 1)
    assert s["groups"]["key"]["clash (3+ steps)"] == (0, 1)
    assert s["bad"] == [("A2 - T2 -> A3 - T3", "vocals clashed")]
    assert s["sets"][0][1] == 4
