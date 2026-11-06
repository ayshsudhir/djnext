from djnext.config import Config
from djnext.core.mix_advice import advise
from djnext.core.mix_points import plan
from djnext.core.models import Track
from djnext.core.sequencer import play_seconds
from djnext.core.structure import TrackStructure, phrase_label

CFG = Config()


def make(bpm, phrases, total_beats):
    """phrases: (start_beat, kind) with mood High: 1 Intro, 2 Build, 3 Breakdown, 5 Drop, 6 Outro."""
    spb = 60.0 / bpm
    beats = [i * spb for i in range(total_beats + 1)]
    return TrackStructure.build(bpm, beats, 1, phrases, total_beats + 1)


def T(id, bpm, key, energy, st):
    t = Track(id, f"T{id}", artist=f"A{id}", bpm=bpm, key=key, energy=energy, genre="Tech House")
    t.structure = st
    return t


# 128 BPM: one bar = 1.875 s. Intro 16 bars, Drop 32, Breakdown 16, Drop 32, Outro 16 = 112 bars
STD = [(1, 1), (65, 5), (193, 3), (257, 5), (385, 6)]


def test_phrase_labels_and_times():
    assert phrase_label(1, 5) == "Drop" and phrase_label(1, 2) == "Build" and phrase_label(2, 9) == "Chorus"
    st = make(128, STD, 448)
    assert [p.label for p in st.phrases] == ["Intro", "Drop", "Breakdown", "Drop", "Outro"]
    assert st.intro.bars == 16 and st.outro.bars == 16
    assert abs(st.outro.start_s - 384 * 60 / 128) < 1e-6  # beat 385 -> 180 s
    assert st.first_peak().label == "Drop"


def test_bass_swap_lines_up_drop_with_outro():
    a = T("a", 128, "8A", 6, make(128, STD, 448))
    b = T("b", 128, "9A", 6, make(128, STD, 448))
    mp = plan(a, b, "bass_swap", CFG)
    assert mp.cue_b_s == 0  # B from its intro
    assert abs(mp.play_b_at_s - a.structure.outro.start_s) < 1e-6  # on A's outro
    assert mp.blend_bars == 16
    assert abs(mp.swap_at_a_s - a.structure.end_s) < 1e-6  # B's drop lands as A's outro ends
    assert abs(mp.swap_at_b_s - b.structure.first_peak().start_s) < 1e-6


def test_long_run_up_starts_b_earlier_in_a():
    short_outro = make(128, [(1, 1), (65, 5), (193, 6)], 224)  # outro only 8 bars
    a = T("a", 128, "8A", 6, short_outro)
    b = T("b", 128, "8A", 6, make(128, STD, 448))  # 16-bar run-up
    mp = plan(a, b, "bass_swap", CFG)
    assert mp.play_b_at_s + 16 * 1.875 <= a.structure.end_s + 0.05  # blend fits before A ends
    assert mp.play_b_at_s < a.structure.outro.start_s


def test_build_drop_cues_b_before_its_drop():
    b_st = make(128, [(1, 1), (33, 2), (97, 5), (225, 6)], 288)  # intro 8, build 16, drop 32
    a = T("a", 128, "8A", 5, make(128, STD, 448))
    b = T("b", 128, "9A", 8, b_st)
    adv = advise(a, b, CFG)
    assert adv.technique == "build_drop"
    mp = plan(a, b, "build_drop", CFG)
    assert mp.blend_bars <= 16
    assert abs(mp.swap_at_b_s - b_st.first_peak().start_s) < 1e-6
    assert any("Loop or roll" in line for line in adv.timing)


def test_echo_out_timing_and_no_structure():
    a = T("a", 124, "8A", 6, make(124, STD, 448))
    b = T("b", 124, "3B", 6, make(124, STD, 448))
    mp = plan(a, b, "echo_out", CFG)
    assert abs(mp.play_b_at_s - a.structure.outro.start_s) < 1e-6 and mp.blend_bars == 0
    plain = Track("p", "plain", bpm=124, key="8A", energy=6)
    assert plan(a, plain, "bass_swap", CFG) is None  # no analysis -> no timing, advice still works
    assert advise(a, plain, CFG).timing == []


def test_play_seconds_uses_outro():
    t = T("a", 128, "8A", 6, make(128, STD, 448))
    assert abs(play_seconds(t, CFG) - t.structure.outro.start_s) < 1e-6


def test_cue_plan_for_a_set():
    from djnext.export.rekordbox_cues import SLOT_KIND, plan_cues

    a = T("a", 128, "8A", 6, make(128, STD, 448))
    b = T("b", 128, "9A", 6, make(128, STD, 448))
    c = T("c", 128, "9A", 6, make(128, STD, 448))
    cues = plan_cues([a, b, c], CFG)
    by = {(q.content_id, q.slot): q for q in cues}
    assert set(by) == {("a", "G"), ("b", "E"), ("b", "F"), ("b", "G"), ("c", "E"), ("c", "F")}
    assert abs(by[("a", "G")].seconds - a.structure.outro.start_s) < 1e-6  # start B on A's outro
    assert by[("b", "F")].seconds == b.structure.first_peak().start_s  # B's drop
    assert all(q.comment.startswith("djnext") for q in cues)
    assert SLOT_KIND["D"] == 5  # rekordbox skips kind 4


def test_beginner_blends_are_short():
    beg = Config()
    a = T("a", 128, "8A", 6, make(128, STD, 448))
    b = T("b", 128, "9A", 6, make(128, [(1, 1), (129, 5), (257, 3), (321, 6)], 384))  # 32-bar intro
    assert plan(a, b, "bass_swap", beg).blend_bars <= 16
    adv_cfg = Config(); adv_cfg.skill = "advanced"
    assert plan(a, b, "bass_swap", adv_cfg).blend_bars == 32
