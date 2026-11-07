from types import SimpleNamespace

from djnext import desktop


class FakeWindow(SimpleNamespace):
    def resize(self, w, h):
        self.width, self.height = w, h

    def move(self, x, y):
        self.x, self.y = x, y

    def load_url(self, url):
        self.url = url


class FakeWebview:
    def __init__(self):
        self.windows = []
        self.screens = [SimpleNamespace(width=1728, height=1117)]

    def create_window(self, title, **kw):
        w = FakeWindow(title=title, url=None, **kw)
        self.windows.append(w)
        return w


def test_one_window_switches_between_live_and_set_builder():
    wv = FakeWebview()
    win = desktop.Windows(wv, "http://127.0.0.1:5000")
    w = win.create(live=True)
    assert w.on_top and w.width == 420 and w.x + w.width <= 1728 and w.html  # splash first
    win.open_main()  # the set-builder button in Live
    assert len(wv.windows) == 1  # no second window
    assert (w.width, w.height) == (900, 760) and not w.on_top and w.url.endswith("/")
    assert win.is_on_top() is False and win.toggle_on_top() is False  # the pin only applies to Live
    win.open_live()  # "Go live"
    assert len(wv.windows) == 1 and w.width == 420 and w.on_top and w.url.endswith("/live")
    assert win.toggle_on_top() is False and w.on_top is False  # pin switched off
    win.open_main()
    win.open_live()
    assert w.on_top is False  # stays unpinned once you switched it off


def test_first_run_setup_window_is_small_and_centred():
    wv = FakeWebview()
    w = desktop.Windows(wv, "http://127.0.0.1:5000").create(live=False, setup=True)
    assert (w.width, w.height) == (540, 800) and not w.on_top and abs(w.x - (1728 - 540) // 2) <= 1


def test_data_folder_is_prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "support"
    desktop.prepare_data_dir(home)
    assert (home / "data").is_dir() and (home / "config.yaml").exists()
    assert desktop._onboarded() is False
    (home / "data" / "settings.json").write_text('{"onboarded": true}')
    assert desktop._onboarded() is True
