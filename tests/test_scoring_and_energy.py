import pytest

from djnext.config import Config
from djnext.core.energy import assign_energy, energy_from_comment
from djnext.core.energy_curve import EnergyCurve
from djnext.core.models import Track
from djnext.core.scoring import bpm_cost, bpm_gap, direction_cost, genre_cost, key_cost

CFG = Config()


def test_bpm_gap_and_half_double():
    assert bpm_gap(125, 125) == 0
    assert bpm_gap(125, 127.5) == pytest.approx(0.02)
    assert bpm_gap(140, 70) == 0  # half time
    assert bpm_gap(70, 140) == 0  # double time
    assert bpm_gap(140, 70, allow_half_double=False) == pytest.approx(0.5)
    assert bpm_gap(0, 120) is None


def test_bpm_cost_tolerance():
    assert bpm_cost(125, 126, CFG) < 0.1  # tiny nudge
    assert bpm_cost(125, 125 * 1.06, CFG) == pytest.approx(1.0)  # edge of +/-6% slider
    assert bpm_cost(100, 140, CFG) == 4.0  # capped


def test_key_and_genre_cost():
    assert key_cost("8A", "8A") == 0
    assert key_cost("8A", "9A") < key_cost("8A", "10A") < key_cost("8A", "3B")
    assert key_cost(None, "8A") == 0.5
    assert genre_cost("House", "house") == 0
    assert genre_cost("Tech House", "House") == 0.3
    assert genre_cost("Techno", "Drum & Bass") == 1.0


def test_direction_cost():
    assert direction_cost(6, 4, slope=10) > 0  # dropping during a build
    assert direction_cost(6, 8, slope=10) == 0
    assert direction_cost(6, 8, slope=-10) > 0  # rising during the breather
    assert direction_cost(6, 4, slope=-10) == 0


def test_energy_from_comment():
    assert energy_from_comment("8A - Energy 7") == 7
    assert energy_from_comment("energy: 4.5") == 4.5
    assert energy_from_comment("E9 banger") == 9
    assert energy_from_comment("great vocal") is None
    assert energy_from_comment("Energy 42") is None


def test_energy_priority():
    assert assign_energy(Track("1", "x", comments="Energy 3", rating=5)).energy == 3
    assert assign_energy(Track("2", "x", rating=4)).energy == 8
    t = assign_energy(Track("3", "x", bpm=128))
    assert t.energy_source == "bpm" and 6 < t.energy < 8


def test_classic_curve_shape():
    curve = Config().curve("classic-1h")
    assert curve.target(0) == pytest.approx(1.5)
    assert curve.target(0.47) == pytest.approx(8.8)
    assert curve.target(0.65) == pytest.approx(5.3)
    assert curve.target(1.0) == pytest.approx(8.8)
    assert curve.slope(0.2) > 0  # building
    assert curve.slope(0.55) < 0  # breather


def test_curve_validation():
    with pytest.raises(ValueError):
        EnergyCurve([[0, 1]])
    with pytest.raises(ValueError):
        EnergyCurve([[0.1, 1], [1, 5]])


def test_style_filter_and_favourites():
    from djnext.config import Style

    st = Style(bpm_min=122, bpm_max=134, exclude_genres=["rock", "hip-hop"], favourite_artists=["Omar+", "Cloonee"])
    assert st.allows(126, "Tech House")
    assert not st.allows(95, "House")  # too slow
    assert not st.allows(126, "Hip-hop & Rap")
    assert st.allows(126, "")  # unknown genre is allowed
    assert st.is_favourite("Defected Records", "Cloonee - Sippin' Yac")  # label upload
    assert st.is_favourite("OMAR+", "Rhythm")
    assert not st.is_favourite("Fisher", "Losing It")


def test_favourite_bonus_lowers_cost():
    from djnext.config import Style
    from djnext.core.scoring import transition

    cfg = Config()
    cfg.style = Style(favourite_artists=["Cloonee"], favourite_bonus=0.5)
    a = Track("a", "x", artist="Someone", bpm=126, key="8A", energy=6)
    fav = Track("b", "y", artist="Cloonee", bpm=126, key="8A", energy=6)
    other = Track("c", "z", artist="Other", bpm=126, key="8A", energy=6)
    assert transition(a, fav, 6, 0, [], cfg).total == transition(a, other, 6, 0, [], cfg).total - 0.5


def test_disliked_pair_is_avoided_and_liked_preferred():
    from djnext.core.scoring import transition

    cfg = Config()
    a = Track("a", "x", artist="A", bpm=124, key="8A", energy=6)
    b = Track("b", "y", artist="B", bpm=124, key="8A", energy=6)
    base = transition(a, b, 6, 0, [], cfg).total
    cfg.pair_feedback = {frozenset(("a", "b")): -1}
    assert transition(a, b, 6, 0, [], cfg).total >= base + 5  # either direction
    assert transition(b, a, 6, 0, [], cfg).total >= base + 5
    cfg.pair_feedback = {frozenset(("a", "b")): 2}
    assert transition(a, b, 6, 0, [], cfg).total < base


def test_spread_guessed_energy():
    from djnext.core.energy import spread_guessed

    tracks = [Track(str(i), "t", bpm=122 + i, energy=6.0 + i * 0.2, energy_source="bpm") for i in range(10)]
    rated = Track("r", "rated", bpm=125, energy=9.0, energy_source="rating")
    assert spread_guessed(tracks + [rated]) == 10
    es = [t.energy for t in tracks]
    assert min(es) == 2.0 and max(es) == 9.0  # now uses the whole range
    assert es == sorted(es)  # slower tracks stay calmer
    assert rated.energy == 9.0 and rated.energy_source == "rating"  # real ratings untouched


def test_same_song_detection():
    from djnext.core.scoring import same_song

    t = lambda title: Track(title, title)
    assert same_song(t("Toxic x Stephanie (Chris Lorenzo Edit)"), t("TOXIC EVIL EDIT"))
    assert same_song(t("Toxic (Chris Lake) x Stephanie"), t("Toxic x Stephanie (Chris Lorenzo Edit)"))
    assert not same_song(t("Deep End (Poolz Bootleg)"), t("How Deep Are Your Dreams"))
    assert not same_song(t("X-Rated"), t("Lights Out (Extended Mix)"))
