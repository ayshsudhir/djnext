from djnext.core.models import Track
from djnext.ingest import soundcloud as sc
from djnext.ingest.rekordbox_xml import Library


def test_entry_parsing_and_label():
    e = sc._entry_track({"url": "https://soundcloud.com/waxmotif/age-of-love-remix", "id": 123})
    assert e["id"] == "123"
    assert sc.label(e) == "waxmotif - age of love remix"
    assert sc._entry_track({"url": "https://api.soundcloud.com/tracks/456"})["id"] == "456"
    assert sc._entry_track({"url": "https://soundcloud.com/u/sets/my-list", "id": 9}) is None  # liked playlist


def test_attach_links_by_soundcloud_id():
    lib = Library(tracks={
        "a": Track("a", "One", path="soundcloud:tracks:111", source="soundcloud", bpm=124),
        "b": Track("b", "Two", path="/music/two.mp3", source="local", bpm=124),
    })
    data = {"likes": [{"id": "111"}, {"id": "222", "title": "Unknown"}], "playlists": {"Set": [{"id": "111"}]}}
    res = sc.attach(lib, data)
    assert lib.playlists["sc:likes"] == ["a"] and lib.playlists["sc:Set"] == ["a"]
    assert [e["id"] for e in res.not_analysed] == ["222"]
