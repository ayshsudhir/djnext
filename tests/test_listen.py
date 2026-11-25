"""Listening: what's kept, what's retried, and how what it heard sorts and pairs tracks."""
import base64
from pathlib import Path

import numpy as np

from djnext.core import picker
from djnext.core.genres import classify, heard_genres, sort_likes
from djnext.core.models import Track
from djnext.ingest import listen


class FakeEar:
    def hear(self, path):
        assert Path(path).exists()
        v = np.ones(8, dtype=np.float16)
        return {"v": listen.VERSION, "styles": {"Electronic---Techno": 0.7}, "heard_s": 30,
                "sound": base64.b64encode(v.tobytes()).decode()}


def T(i, sid, bpm=130, duration=360, artist="A", title="x"):
    return Track(str(i), title, artist=artist, bpm=bpm, key="9A", duration=duration,
                 path=f"soundcloud:tracks:{sid}", source="soundcloud")


def test_audio_is_deleted_and_only_the_verdict_kept(tmp_path):
    folders = []

    def fetch(sid, folder):
        folders.append(folder)
        if sid == "2":
            raise RuntimeError("track removed")
        f = Path(folder) / "a.mp3"
        f.write_bytes(b"audio")
        return str(f)

    path = tmp_path / "listened.json"
    data = listen.update([T(1, "1"), T(2, "2")], path=path, ear=FakeEar(), fetch=fetch)
    assert all(not Path(f).exists() for f in folders)  # no audio left behind
    assert listen.heard(data["1"]) and data["1"]["preview"] is True  # 30 s of a 6 min track: only a preview
    assert data["2"]["failed"] == 1
    assert listen.todo([T(1, "1"), T(2, "2")], listen.load(path)) == []  # the failed one waits for another day
    assert listen.sound_of(data["1"]) is not None and abs(np.linalg.norm(listen.sound_of(data["1"])) - 1) < 1e-3


def test_what_it_sounds_like_beats_tag_and_tempo():
    t = Track("1", "Freaky", artist="X", bpm=130, genre="Techno")  # uploader says techno, tempo says techno
    v = classify(t, heard={"Electronic---Tech House": 0.6, "Electronic---House": 0.3, "Electronic---Techno": 0.05})
    assert v.genre == "tech-house" and v.sure and "sounds like Tech House" in v.why
    assert heard_genres({"Electronic---Techno": 0.8}, bpm=142) == {"hard-fast": 1.0}  # techno above ~137 BPM


def test_artist_follows_what_their_other_tracks_sound_like():
    a = Track("1", "One", artist="Brunello", bpm=130)
    b = Track("2", "Two", artist="Brunello", bpm=130)
    c = Track("3", "Three", artist="Brunello", bpm=130)  # not heard yet
    techno = {"Electronic---Techno": 0.8}
    v = sort_likes([a, b, c], {}, heard_of={"1": techno, "2": techno})
    assert v["3"].genre == "groovy-techno" and "Brunello" in v["3"].why


def test_sounds_alike_counts_in_the_next_song():
    a, b, c = T(1, "1", bpm=128), T(2, "2", bpm=128), T(3, "3", bpm=128)
    ev = picker.Evidence()
    u = lambda *x: np.array(x, dtype=np.float32) / np.linalg.norm(x)  # noqa: E731
    ev.set_sound({"1": u(1, 0, 0), "2": u(1, 0.1, 0), "3": u(0, 1, 0), "4": u(0.5, 0.5, 0.7)})
    alike, unlike = picker.move(a, b, ev), picker.move(a, c, ev)
    assert alike.parts["sounds_alike"] > 0 > unlike.parts["sounds_alike"]
    assert any("same groove" in r for r in alike.reasons)
