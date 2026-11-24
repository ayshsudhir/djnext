"""A small fake library: groovy techno SoundCloud likes with phrase analysis, plus tracks that must never be picked."""
from djnext.core.models import Track
from djnext.core.structure import TrackStructure
from djnext.ingest.rekordbox_xml import Library

# High-mood phrases (start beat, kind): 1 Intro, 2 Build, 3 Breakdown, 5 Drop, 6 Outro
LONG_INTRO = [(1, 1), (129, 5), (257, 3), (321, 5), (449, 6)]  # 32-bar intro
SHORT_INTRO = [(1, 1), (17, 5), (257, 3), (321, 5), (449, 6)]  # 4-bar intro


def structure(bpm, phrases=LONG_INTRO, beats=512):
    spb = 60.0 / bpm
    return TrackStructure.build(bpm, [i * spb for i in range(beats + 1)], 1, phrases, beats + 1)


def sc_track(i, artist, title, bpm, key, genre="Tech House", phrases=LONG_INTRO, duration=360):
    t = Track(str(i), title, artist=artist, bpm=bpm, key=key, genre=genre, duration=duration,
              path=f"soundcloud:tracks:{1000 + i}", source="soundcloud")
    t.structure = structure(bpm, phrases)
    return t


LIKED = [
    sc_track(1, "Solid Grooves Raw", "SGRAW052 Beltran - Smack Yo'", 127, "9B"),
    sc_track(2, "ROB MÂRK", "OMNOM ft. XKYLAR - By Myself (ROB MÂRK Remix)", 128, "9A", genre="Techno"),
    sc_track(3, "Max Styler", "Freaky 1", 129, "9A"),
    sc_track(4, "Fallon", "Diet Coke", 128, "8A"),
    sc_track(5, "Chris Lorenzo", "London's On Fire", 130, "10A"),
    sc_track(6, "Eli Brown", "Nazareth", 131, "10A", genre="Dance"),
    sc_track(7, "Beltran", "The Final Chapter", 127, "8A", phrases=SHORT_INTRO),
    sc_track(8, "Volkoder", "Body", 128, "8B", genre="Electronic"),
    sc_track(9, "Cloonee", "Cloonee - XTC (feat. Jocelyn Enriquez)", 130, "9A"),
    sc_track(10, "Franky Rizardo", "Whatchagonnado", 128, "9A"),
    # never picked:
    sc_track(11, "Indie Band", "Sad Song", 128, "9A", genre="Indie Pop"),  # other style
    sc_track(12, "Someone", "Way Too Fast", 145, "9A", genre="Techno"),  # too fast for groovy techno
    sc_track(13, "Mau P", "Sunrise Set @ Club Space", 130, "9A", duration=7200),  # a DJ set, not a track
    sc_track(14, "Max Styler", "Freaky 1 (Extended Mix)", 129, "9A"),  # second upload of a song
]
NOT_LIKED = sc_track(20, "Max Styler", "Not Liked But Perfect", 128, "9A")


def fake_library() -> Library:
    tracks = {t.id: t for t in LIKED + [NOT_LIKED]}
    for t in tracks.values():
        t.structure = structure(t.bpm, LONG_INTRO if t.id != "7" else SHORT_INTRO)
    lib = Library(tracks=tracks)
    lib.playlists["sc:likes"] = [t.id for t in LIKED]
    return lib


def soundcloud_data() -> dict:
    return {"user": "me", "synced_at": "2026-11-23T10:00:00",
            "likes": [{"id": str(1000 + t_id), "title": "x", "url": ""} for t_id in range(1, 15)], "playlists": {}}
