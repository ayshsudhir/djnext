"""Listen to each liked track once, so djnext knows what it really sounds like.

For every like: the song is streamed from SoundCloud into a temporary file, a music model listens to the whole
song, and the audio is deleted straight away. Only the verdict is kept, in data/listened.json:
  - styles: how much it sounds like each music style (Techno 0.62, Tech House 0.31 ...)
  - sound:  a compact "fingerprint" of its sound, to tell which tracks feel alike (groove, texture)
About 8 seconds per track; new likes are listened to in the background when djnext opens.

The model is Discogs-EffNet by the Music Technology Group (Universitat Pompeu Fabra, Barcelona), trained on
millions of tracks labelled with Discogs' 400 styles. It's downloaded once (18 MB) into data/models.
Licence: CC BY-NC-ND 4.0 (free for non-commercial use). https://essentia.upf.edu/models.html
"""
from __future__ import annotations

import base64
import json
import shutil
import tempfile
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from ..core.models import Track

CACHE = Path("data/listened.json")
MODELS = Path("data/models")
_BASE = "https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bsdynamic-1"
MODEL_FILES = {"discogs-effnet-bsdynamic-1.onnx": _BASE + ".onnx", "discogs-effnet-bsdynamic-1.json": _BASE + ".json"}
VERSION = 1  # bump to listen to everything again (e.g. a better model)
KEEP_STYLES = 25
MAX_TRIES = 3  # a track that can't be streamed (removed, private) is tried again on 3 different days, then left


def load(path: Path = CACHE) -> Dict[str, dict]:
    from ..storage import read_json

    d = read_json(path, {})
    return d if isinstance(d, dict) else {}


def save(data: Dict[str, dict], path: Path = CACHE) -> None:
    from ..storage import write_json

    write_json(path, data, indent=0)


def heard(entry: Optional[dict]) -> bool:
    return bool(entry) and entry.get("v") == VERSION and bool(entry.get("styles"))


def todo(tracks: Sequence[Track], data: Dict[str, dict]) -> List[Track]:
    today = datetime.now().date().isoformat()
    out = []
    for t in tracks:
        e = data.get(t.soundcloud_id or "")
        if not t.soundcloud_id or heard(e):
            continue
        if e and (e.get("failed", 0) >= MAX_TRIES or e.get("last_try") == today):
            continue
        out.append(t)
    return out


def styles_of(entry: Optional[dict]) -> Dict[str, float]:
    """{'Electronic---Techno': 0.62, 'Electronic---Tech House': 0.31, ...} (Discogs 'family---style' names)."""
    if not heard(entry):
        return {}
    return {k: float(v) for k, v in entry["styles"].items()}


def sound_of(entry: Optional[dict]):
    """The sound fingerprint as a unit-length numpy vector, or None."""
    if not heard(entry) or not entry.get("sound"):
        return None
    import numpy as np

    v = np.frombuffer(base64.b64decode(entry["sound"]), dtype=np.float16).astype(np.float32)
    n = float(np.linalg.norm(v))
    return v / n if n else None


def available() -> bool:
    try:
        import essentia  # noqa: F401
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def ensure_model(folder: Path = MODELS, opener: Callable = urllib.request.urlopen) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_FILES.items():
        dest = folder / name
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        req = urllib.request.Request(url, headers={"User-Agent": "djnext"})
        with opener(req, timeout=120) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
        tmp.replace(dest)
    return folder


class Ear:
    """The model, loaded once. hear(audio file) -> verdict."""

    def __init__(self, folder: Path = MODELS):
        import essentia
        import essentia.standard as es
        import onnxruntime as ort

        essentia.log.warningActive = False
        essentia.log.infoActive = False
        self.es = es
        self.session = ort.InferenceSession(str(folder / "discogs-effnet-bsdynamic-1.onnx"),
                                            providers=["CPUExecutionProvider"])
        self.classes = json.loads((folder / "discogs-effnet-bsdynamic-1.json").read_text())["classes"]
        self.mel = es.TensorflowInputMusiCNN()

    def hear(self, audio_file: str) -> dict:
        import numpy as np

        es = self.es
        audio = es.MonoLoader(filename=audio_file, sampleRate=16000, resampleQuality=4)()
        frames = np.array([self.mel(f) for f in es.FrameGenerator(audio, frameSize=512, hopSize=256,
                                                                  startFromZero=True)], dtype=np.float32)
        if len(frames) < 129:
            raise ValueError("too short to judge")
        patches = np.stack([frames[i:i + 128] for i in range(0, len(frames) - 128, 62)])  # ~3 s each, whole song
        act, emb = self.session.run(["activations", "embeddings"], {"melspectrogram": patches})
        act, emb = act.mean(0), emb.mean(0)
        top = sorted(zip(act.tolist(), self.classes), reverse=True)[:KEEP_STYLES]
        return {"v": VERSION, "styles": {c: round(p, 3) for p, c in top},
                "sound": base64.b64encode(emb.astype(np.float16).tobytes()).decode(),
                "heard_s": round(len(audio) / 16000)}


def _tidy() -> None:
    """If djnext was quit in the middle of listening, a temporary folder may be left: delete it."""
    for p in Path(tempfile.gettempdir()).glob("djnext-listen-*"):
        shutil.rmtree(p, ignore_errors=True)


def protected(data: Dict[str, dict]) -> int:
    return sum(1 for e in data.values() if e.get("protected"))


def stream(sid: str, folder: str) -> str:
    """Stream one SoundCloud track into `folder` (a temporary folder that's deleted right after)."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "format": "bestaudio/best",
            "outtmpl": folder + "/a.%(ext)s"}
    with yt_dlp.YoutubeDL(opts) as y:
        y.extract_info(f"https://api.soundcloud.com/tracks/{sid}")
    files = [p for p in Path(folder).iterdir() if p.is_file() and not p.name.endswith(".part")]
    if not files:
        raise RuntimeError("nothing came through")
    return str(files[0])


def update(tracks: Sequence[Track], progress: Callable[[int, int, Track], None] = lambda *_: None,
           path: Path = CACHE, ear: Optional[Ear] = None, fetch: Callable[[str, str], str] = stream) -> Dict[str, dict]:
    """Listen to the tracks not heard yet. Saves as it goes; audio never stays on disk."""
    data = load(path)
    work = todo(tracks, data)
    if not work:
        return data
    _tidy()
    ear = ear or Ear(ensure_model())
    for i, t in enumerate(work):
        progress(i, len(work), t)
        folder = tempfile.mkdtemp(prefix="djnext-listen-")
        try:
            got = ear.hear(fetch(t.soundcloud_id, folder))
            got["checked"] = datetime.now().isoformat(timespec="seconds")
            if t.duration and got["heard_s"] < 0.5 * t.duration:
                got["preview"] = True  # SoundCloud only lets this one be heard in part (Go+)
            data[t.soundcloud_id] = got
        except Exception as e:  # removed / private / network hiccup: try again another day
            old = data.get(t.soundcloud_id) or {}
            msg = str(e)
            protected = "DRM" in msg  # the label copy-protects it: djnext doesn't get around that, so never retry
            data[t.soundcloud_id] = {"failed": MAX_TRIES if protected else old.get("failed", 0) + 1,
                                     "protected": protected or None,
                                     "last_try": datetime.now().date().isoformat(),
                                     "error": f"{type(e).__name__}: {msg[:120]}"}
        finally:
            shutil.rmtree(folder, ignore_errors=True)
        if i % 5 == 4 or i == len(work) - 1:
            save(data, path)
        time.sleep(0.2)
    return data
