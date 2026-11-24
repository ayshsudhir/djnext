from djnext.core.genres import classify, sort_likes
from djnext.core.models import Track


def T(i, title, artist="", bpm=128, genre=""):
    return Track(str(i), title, artist=artist, bpm=bpm, genre=genre)


def test_dj_sets_are_the_strongest_clue():
    t = T(1, "Body", "Volkoder", 128, "Electronic")  # the tag says nothing useful
    v = classify(t, [["Tech House", "Players"], ["Tech House", "House"], ["Tech House"]])
    assert v.genre == "tech-house" and v.sure and "3 DJ sets" in v.why
    techno = classify(T(2, "Nazareth", "Eli Brown", 135, "Dance"), [["Techno"], ["Techno", "Minimal"]])
    assert techno.genre == "groovy-techno"
    fast = classify(T(3, "Rituals", "Bailey Ibbs", 145), [["Techno"]])
    assert fast.genre == "hard-fast"  # techno above ~137 BPM isn't groovy


def test_tags_and_tempo():
    assert classify(T(1, "x", bpm=124, genre="Indie Dance")).genre == "indie-melodic"
    assert classify(T(2, "x", bpm=122, genre="House")).genre == "house"
    assert classify(T(3, "x", bpm=164, genre="Indie Pop")).genre == "other"  # pop is pop, whatever the tempo
    assert classify(T(4, "x", bpm=146, genre="")).genre == "hard-fast"
    guess = classify(T(5, "x", bpm=127))
    assert not guess.sure and "tempo" in guess.why


def test_a_guess_follows_the_artist_and_you_win():
    sure1 = T(1, "Sexy M.F.", "Maccabi House", 124, "Indie Dance")
    sure2 = T(2, "Got Me Crazy", "Maccabi House", 124, "Indie Dance")
    guess = T(3, "First Choice", "Maccabi House", 123)
    v = sort_likes([sure1, sure2, guess], {})
    assert v["3"].genre == "indie-melodic" and "Maccabi House" in v["3"].why
    mine = sort_likes([sure1, sure2, guess], {}, overrides={"3": "house"})
    assert mine["3"].genre == "house" and mine["3"].why == "you put it here"


def test_indie_dance_survives_house_sets():
    """MixesDB almost never tags sets 'Indie Dance': those tracks show up in House / Progressive House sets."""
    house_sets = [["House", "Progressive House", "Tech House"]] * 5
    tagged = T(1, "Sexy M.F.", "Maccabi House", 124, "Indie Dance")
    untagged = T(2, "Kids (Reef Kopel Maccabi Edit)", "Maccabi House", 125, "")
    v = sort_likes([tagged, untagged], {"1": house_sets, "2": house_sets})
    assert v["1"].genre == "indie-melodic" and v["2"].genre == "indie-melodic"
    assert "Maccabi House" in v["2"].why
