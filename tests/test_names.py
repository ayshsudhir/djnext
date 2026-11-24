import pytest

from djnext.core.names import clean_line, matches, parse


@pytest.mark.parametrize("artist,title,artists,song,version", [
    ("Solid Grooves Raw", "SGRAW052 Beltran - Smack Yo'", ("beltran", "solid grooves raw"), ("smack", "yo"), ()),
    ("Max Styler", "Chris Lake, Green Velvet - Deceiver (Max Styler Remix)",
     ("chris lake", "green velvet", "max styler"), ("deceiver",), ("max", "styler")),
    ("Cloonee", "Cloonee - XTC (feat. Jocelyn Enriquez)", ("cloonee",), ("xtc",), ()),
    ("ROB MÂRK", "OMNOM ft. XKYLAR - By Myself (ROB MÂRK Remix)", ("omnom", "rob mark", "xkylar"), ("by", "myself"),
     ("rob", "mark")),
    ("Volkoder", "Body", ("volkoder",), ("body",), ()),
    ("Experts Only", "Max Styler & Clüb De Combat - On Repeat (Extended Mix)",
     ("max styler", "club de combat", "experts only"), ("on", "repeat"), ()),
])
def test_parse_soundcloud_uploads(artist, title, artists, song, version):
    n = parse(artist, title)
    assert (n.artists, n.title, n.version) == (artists, song, version)


def test_matching_needs_artist_and_title():
    xtc = parse("Cloonee", "Cloonee - XTC (feat. Jocelyn Enriquez)")
    assert matches(xtc, *clean_line("[05] Cloonee - XTC [Hellbent]"))
    assert matches(xtc, *clean_line("0:12:00 - Cloonee feat. Jocelyn Enriquez - XTC (Extended)"))
    assert not matches(xtc, *clean_line("# [23] Dan Molinari - XTC"))  # same title, different song


def test_one_word_titles_and_swapped_uploads():
    body = parse("Volkoder", "Body")
    assert matches(body, *clean_line("[3] Volkoder - Body [Odd Recordings]"))
    assert not matches(body, *clean_line("[3] Loleatta Holloway - Love Sensation (Body Mix)"))
    fake_id = parse("cole ettinger", "Fake ID - Chris Lorenzo (unreleased)")  # uploaded as "Title - Artist"
    assert matches(fake_id, *clean_line("# Chris Lorenzo - Fake ID"))
    assert not matches(fake_id, *clean_line("# Chris Lorenzo - London's On Fire"))


def test_clean_line():
    assert clean_line("# [12] Beltran - Smack Yo' [Solid Grooves Raw]") == ("Beltran", "Smack Yo' [Solid Grooves Raw]")
    assert clean_line("[?] ?") is None and clean_line("no separator") is None
