from pathlib import Path

from djnext.config import Config, Style
from djnext.core.models import Track
from djnext.ingest import discover as dc
from djnext.ingest.rekordbox_xml import Library


def test_filters():
    assert dc.NOT_A_TRACK.search("TECH HOUSE 2026 SET - Discip, Beltran")
    assert dc.NOT_A_TRACK.search("Live @ Experts Only Miami")
    assert not dc.NOT_A_TRACK.search("Lights Out (Extended Mix)")
    assert not dc.NOT_A_TRACK.search("Set It Off")
    assert dc.JUNK.search("Beltran - RUSATISFIED v6 (1).m4a")
    assert dc.JUNK.search("No Hesitating (Max Dean Remix) teaser")
    assert not dc.JUNK.search("Tchami - Adieu (Westend Edit)")


def test_fits_style_and_mood_guess():
    cfg = Config()
    cfg.style = Style(exclude_genres=["hip-hop", "rock"], favourite_artists=["Beltran"])
    th = dc.Candidate("1", "Track", "X", "u", genre="Tech House")
    rap = dc.Candidate("2", "Track", "X", "u", genre="Hip-hop & Rap")
    unknown_related = dc.Candidate("3", "Track", "X", "u", seeds=["Your Track"])
    unknown = dc.Candidate("4", "Track", "X", "u")
    assert dc._fits_style(th, cfg) and not dc._fits_style(rap, cfg)
    assert dc._fits_style(unknown_related, cfg) and not dc._fits_style(unknown, cfg)
    edit = dc.Candidate("5", "Adieu (Westend Edit)", "Westend", "u", genre="House")
    assert "Drunk" in dc._mood_guess(edit, cfg)


class FakeYDL:
    """Pretends to be SoundCloud: related tracks, search results and track details."""
    def __init__(self, opts): self.opts = opts
    def __enter__(self): return self
    def __exit__(self, *a): return False

    def extract_info(self, url, download=False):
        if url.endswith("/recommended"):
            return {"entries": [{"id": "900", "title": "Great New One", "url": "https://api.soundcloud.com/tracks/900"},
                                {"id": "111", "title": "Already Mine", "url": "https://api.soundcloud.com/tracks/111"},
                                {"id": "901", "title": "My DJ Set", "url": "https://api.soundcloud.com/tracks/901"}]}
        if url.startswith("scsearch"):
            return {"entries": [{"id": "902", "title": "Beltran - New Banger", "uploader": "Beltran", "duration": 300,
                                 "like_count": 5000, "view_count": 90000, "genres": ["Tech House"],
                                 "webpage_url": "https://soundcloud.com/beltran/new-banger"},
                                {"id": "903", "title": "Some Rap Song", "duration": 200, "like_count": 99999,
                                 "genres": ["Hip-hop & Rap"], "webpage_url": "https://soundcloud.com/x/rap"}]}
        tid = url.rsplit("/", 1)[-1]
        if tid == "900":
            return {"title": "Great New One", "uploader": "Someone", "duration": 330, "like_count": 1200,
                    "view_count": 20000, "genre": "House", "webpage_url": "https://soundcloud.com/someone/great"}
        if tid == "901":
            return {"title": "My DJ Set", "duration": 3600, "like_count": 10, "genre": "House", "webpage_url": "x"}
        return None


def test_discover_end_to_end(monkeypatch, tmp_path):
    lib = Library(tracks={"a": Track("a", "Seed Track", artist="Beltran", bpm=128, key="8A", genre="Tech House",
                                     duration=300, path="soundcloud:tracks:111", source="soundcloud", energy=7)})
    sc_data = {"likes": [{"id": "111", "url": "https://soundcloud.com/beltran/seed-track", "title": "Seed Track"}],
               "playlists": {}}
    cfg = Config()
    cfg.style = Style(bpm_min=120, bpm_max=134, exclude_genres=["hip-hop"], favourite_artists=["Beltran"])
    monkeypatch.setattr(dc, "_ydl", lambda extra=None: FakeYDL(extra))
    import djnext.service as service
    monkeypatch.setattr(service, "mood_pools", lambda lib, cfg, *a, **k: ({"banging": [(lib.tracks["a"], 0.9)]}, []))
    cands = dc.discover(lib, cfg, sc_data, log=lambda m: None)
    ids = [c.id for c in cands]
    assert set(ids) == {"900", "902"}  # not: already mine (111), a DJ set (901), rap (903)
    great = next(c for c in cands if c.id == "900")
    assert great.seeds == ["Seed Track"] and "related to 1 of your tracks" in great.why
    out = dc.save(cands, tmp_path / "d.json")
    assert len(dc.load(out)["tracks"]) == 2
