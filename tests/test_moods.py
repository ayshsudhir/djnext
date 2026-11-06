from djnext.config import Config
from djnext.core.models import Track
from djnext.core.moods import Mood, classify, features, fit, load_moods


def T(id, title, bpm, artist="Someone", genre="House", energy=None, src="bpm", dur=360):
    return Track(id, title, artist=artist, bpm=bpm, genre=genre, energy=energy, energy_source=src, duration=dur)


def test_default_moods_load_and_have_curves():
    cfg = Config()
    moods = cfg.moods()
    assert set(moods) == {"warmup", "pregame", "drunk", "banging", "afters", "groovy_techno"}
    for m in moods.values():
        assert cfg.curve(m.curve).target(0.5) > 0  # every mood's energy shape exists


def test_whole_word_matching_and_required_words():
    desi = load_moods({"desi": dict(name="Desi", required_words=["bollywood", "tere", "chaiyya"])})["desi"]
    a = T("a", "Chaiyya Chaiyya (Kahani Remix)", 120)
    b = T("b", "In The Streets", 128, artist="STEREOHYPE")  # contains "tere" inside a word
    f = features([a, b])
    assert fit(a, f["a"], desi) is not None
    assert fit(b, f["b"], desi) is None


def test_moods_split_a_tech_house_pool():
    tracks = [
        T("e1", "Toxic x Stephanie (Chris Lorenzo Edit)", 129),
        T("e2", "Deep End (Poolz Bootleg)", 128),
        T("w1", "Fade Away", 122, genre="Deep House"),
        T("w2", "Slow Roller", 123, genre="Melodic House"),
        T("t1", "Hubris", 134, genre="Techno"),
        T("t2", "Acid Groove", 133, genre="Techno"),
        T("x1", "Plain Track", 127),
        T("x2", "Another One", 126),
    ]
    res = classify(tracks, load_moods(None))
    ids = lambda k: {t.id for t, _ in res[k]}
    assert {"e1", "e2"} <= ids("drunk")
    assert {"w1", "w2"} <= ids("warmup") and not ids("warmup") & {"t1", "t2"}
    assert {"t1", "t2"} <= ids("groovy_techno")
    assert all(0 <= s <= 1 for items in res.values() for _, s in items)


def test_rated_energy_is_used_for_intensity():
    calm = T("a", "x", 126, energy=2.0, src="rating")
    f = features([calm, T("b", "y", 126)])
    assert abs(f["a"].intensity - 0.2) < 1e-9


def test_custom_mood_from_config():
    moods = load_moods({"gym": dict(name="Gym", bpm=[128, 135], words=["bounce"], words_weight=1.0, threshold=0.9)})
    m = moods["gym"]
    t = T("g", "Bounce It", 130)
    assert fit(t, features([t])["g"], m) == 1.0
