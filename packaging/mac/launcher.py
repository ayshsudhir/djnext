"""Entry point PyInstaller freezes into djnext.app (see build_app.sh).

`djnext.app/Contents/MacOS/djnext --check-listening <model folder> [soundcloud track id]` checks the packaged app can listen
(decodes a generated test sound and runs the music model on it) and exits.
"""
import sys


def check_listening(model_folder: str) -> None:
    import tempfile
    import wave
    from pathlib import Path

    import numpy as np

    from djnext.ingest.listen import Ear

    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "test.wav"
        sr = 44100
        t = np.arange(sr * 12) / sr
        kick = (np.sin(2 * np.pi * 55 * t) * np.exp(-((t * 2.133) % 1) * 12)).astype(np.float32)  # 128 BPM kick
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(sr)
            w.writeframes((kick * 30000).astype("<i2").tobytes())
        ear = Ear(Path(model_folder))
        got = ear.hear(str(f))
        print("listening OK:", len(got["styles"]), "styles,", got["heard_s"], "s heard")
        if len(sys.argv) > 3:  # also stream one SoundCloud track by id
            from djnext.ingest.listen import stream

            sub = Path(d) / "stream"
            sub.mkdir()
            got = ear.hear(stream(sys.argv[3], str(sub)))
            print("streamed OK:", got["heard_s"], "s heard;", ", ".join(list(got["styles"])[:3]))


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--check-listening":
        check_listening(sys.argv[2])
    else:
        from djnext.desktop import main

        main()
