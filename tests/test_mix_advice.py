from djnext.config import Config
from djnext.core.mix_advice import advise
from djnext.core.models import Track

CFG = Config()
CFG.skill = "advanced"  # these tests check the detailed (advanced) wording


def T(id, bpm, key, energy, genre="House"):
    return Track(id, f"Track {id}", artist=f"Artist {id}", bpm=bpm, key=key, energy=energy, genre=genre)


def test_bass_swap_for_compatible_tracks():
    adv = advise(T("a", 124, "8A", 6), T("b", 125, "9A", 6.5), CFG)
    assert adv.technique == "bass_swap"
    assert any("LOW" in s for s in adv.steps)
    assert "-0.8%" in adv.steps[0]  # tempo instruction: bring B down to 124


def test_echo_out_on_key_clash():
    adv = advise(T("a", 124, "8A", 6), T("b", 124, "3B", 6), CFG)
    assert adv.technique == "echo_out"
    assert any("clash" in n for n in adv.notes)


def test_echo_out_when_tempo_out_of_range():
    adv = advise(T("a", 124, "8A", 6), T("b", 174, "8A", 6), CFG)
    assert adv.technique == "echo_out"


def test_build_drop_on_energy_jump():
    assert advise(T("a", 124, "8A", 5), T("b", 126, "9A", 8), CFG).technique == "build_drop"


def test_wash_out_into_breather():
    assert advise(T("a", 126, "8A", 9), T("b", 124, "8A", 5), CFG).technique == "wash_out"


def test_filter_fade_for_ok_keys_or_genre_change():
    assert advise(T("a", 124, "8A", 6), T("b", 124, "10A", 6), CFG).technique == "filter_fade"
    assert advise(T("a", 124, "8A", 6, "House"), T("b", 124, "8A", 6, "Techno"), CFG).technique == "filter_fade"


def test_half_time_note():
    adv = advise(T("a", 140, "8A", 6), T("b", 70, "8A", 6), CFG)
    assert "Half/double" in adv.steps[0]


def test_bridge_track_for_clash():
    a, b = T("a", 124, "8A", 6), T("b", 124, "10B", 6)  # 3 steps = clash
    bridge = T("x", 124, "9A", 6)  # 8A -> 9A -> 10B? 9A->10B is 2 steps; still smoother
    perfect = T("y", 124, "9B", 6)  # 8A->9B (2), 9B->10B (1)
    noise = T("z", 150, "2A", 2)
    adv = advise(a, b, CFG, pool=[a, b, bridge, perfect, noise])
    assert adv.technique == "echo_out"
    assert adv.bridge is not None and adv.bridge.id in ("x", "y")


def test_beginner_mode_is_simpler():
    beg = Config()  # beginner is the default
    assert beg.skill == "beginner"
    adv = advise(T("a", 124, "8A", 6), T("b", 125, "9A", 6.5), beg)
    assert adv.technique == "bass_swap" and "easy" in adv.title
    assert "BEAT SYNC" in adv.steps[0] and len(adv.steps) <= 5
    assert "SMART FADER" in adv.alternative
    drop = advise(T("a", 124, "8A", 5), T("b", 126, "9A", 8), beg)
    assert drop.title.startswith("Swap on the drop") and not any("ROLL" in s for s in drop.steps)
    half = advise(T("a", 140, "8A", 6), T("b", 70, "8A", 6), beg)
    assert any("Half/double" in n for n in half.notes)
