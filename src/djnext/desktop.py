"""djnext as a Mac app: its own window, a Dock icon, and data where Mac apps keep theirs.

This is what djnext.app runs. It
  - keeps your settings, SoundCloud lists, ratings and backups in ~/Library/Application Support/djnext
    (the app itself stays read-only in /Applications, so an update never touches your data),
  - writes a log to ~/Library/Logs/djnext.log (handy when something goes wrong),
  - starts the local web server on a free port, only reachable from this Mac,
  - shows the page in a native window (WebKit, like Safari). Closing the window or Cmd+Q quits djnext.

Run it from source with:  python -m djnext.desktop   (needs `pip install pywebview`)
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
from pathlib import Path

APP_NAME = "djnext"
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
LOG_FILE = Path.home() / "Library" / "Logs" / f"{APP_NAME}.log"


def _bundled(name: str) -> Path:
    """A file shipped inside the app (PyInstaller unpacks them to sys._MEIPASS), or from the source checkout."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / name


def prepare_data_dir(support_dir: Path = SUPPORT_DIR) -> Path:
    """Create the data folder on first start, copy in the default config, and make it the working folder
    (djnext reads config.yaml and data/ relative to where it runs)."""
    (support_dir / "data").mkdir(parents=True, exist_ok=True)
    cfg = support_dir / "config.yaml"
    if not cfg.exists():
        default = _bundled("config.yaml")
        if default.exists():
            shutil.copyfile(default, cfg)
    os.chdir(support_dir)
    return support_dir


def _log_to_file() -> None:
    """A Mac app has no Terminal window, so send output to ~/Library/Logs/djnext.log (Console.app can show it)."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log = open(LOG_FILE, "a", buffering=1, encoding="utf-8")
    log.write(f"\n--- djnext started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = sys.stderr = log


SPLASH = """<!DOCTYPE html><html><body style="margin:0;height:100vh;display:grid;place-items:center;background:#0c0b12;
color:#a09cb0;font:15px -apple-system,sans-serif"><div style="text-align:center">
<div style="width:90px;height:90px;margin:0 auto 18px;border-radius:50%;animation:s 1.6s linear infinite;
background:radial-gradient(circle,#ff3d8b 0 14px,#111 15px 100%),repeating-radial-gradient(circle,#111 0 2px,#1c1c1c 2px 4px)"></div>
Starting djnext…</div><style>@keyframes s{to{transform:rotate(360deg)}}</style></body></html>"""


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve(port: int) -> None:
    import uvicorn

    from .web.app import app

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)


def _wait_until_up(url: str, timeout: float = 30.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(url + "/api/rekordbox", timeout=1)
            return True
        except Exception:
            time.sleep(0.15)
    return False


def _onboarded() -> bool:
    import json

    p = Path("data/settings.json")
    try:
        if json.loads(p.read_text(encoding="utf-8")).get("onboarded"):
            return True
    except Exception:
        pass
    return Path("data/soundcloud.json").exists()


class Windows:
    """The two windows, and the functions their pages can call (window.pywebview.api.*)."""

    def __init__(self, webview, url: str):
        self._wv, self._url = webview, url
        self._main = self._live = None

    def _alive(self, w) -> bool:
        return w is not None and w in self._wv.windows

    # called from the pages (return plain values only)
    def open_main(self) -> None:
        self._make_main()

    def open_live(self) -> None:
        self._make_live()

    def _make_main(self):
        if self._alive(self._main):
            self._main.restore(); self._main.show()
            return self._main
        self._main = self._wv.create_window(
            APP_NAME, html=SPLASH if self._main is None and self._live is None else None,
            url=None if self._main is None and self._live is None else self._url,
            width=1280, height=880, min_size=(420, 600), background_color="#0c0b12", text_select=True, js_api=self)
        return self._main

    def _make_live(self):
        """A narrow window at the right edge of the screen, kept on top so it stays visible over rekordbox."""
        if self._alive(self._live):
            self._live.restore(); self._live.show()
            return self._live
        first = self._main is None and self._live is None
        width, height, x, y = 420, 900, None, None
        try:
            screen = self._wv.screens[0]
            height = min(940, screen.height - 60)
            x, y = screen.width - width - 12, 30
        except Exception:
            pass
        self._live = self._wv.create_window(
            f"{APP_NAME} Live", html=SPLASH if first else None, url=None if first else self._url + "/live",
            width=width, height=height, x=x, y=y, min_size=(360, 520), on_top=True,
            background_color="#0c0b12", js_api=self)
        return self._live

    def toggle_on_top(self) -> bool:
        if self._alive(self._live):
            self._live.on_top = not self._live.on_top
            return self._live.on_top
        return False

    def is_on_top(self) -> bool:
        return bool(self._alive(self._live) and self._live.on_top)


def main() -> None:
    if getattr(sys, "frozen", False):
        _log_to_file()
    prepare_data_dir()
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(target=_serve, args=(port,), daemon=True).start()

    try:
        import webview
    except ImportError:  # running from source without pywebview: fall back to the browser
        import webbrowser

        _wait_until_up(url)
        webbrowser.open(url)
        print(f"djnext is running at {url} (Ctrl+C to stop)")
        threading.Event().wait()
        return

    windows = Windows(webview, url)
    first_run = not _onboarded()
    # The app opens as the small Live window next to rekordbox; the very first start shows the setup instead.
    first = windows._make_main() if first_run else windows._make_live()

    def _load_when_ready():
        if not _wait_until_up(url):
            first.load_html("<body style='background:#0c0b12;color:#eee;font:16px -apple-system;padding:40px'>"
                            f"djnext couldn't start. Details are in {LOG_FILE}.</body>")
            return
        first.load_url(url + ("/" if first_run else "/live"))

    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True  # SoundCloud links open in your browser
    webview.start(_load_when_ready)  # returns when the last window is closed
    os._exit(0)  # stop the server thread too


if __name__ == "__main__":
    main()
