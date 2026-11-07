from types import SimpleNamespace

from djnext import desktop


class FakeWebview:
    def __init__(self):
        self.windows = []
        self.screens = [SimpleNamespace(width=1728, height=1117)]

    def create_window(self, title, **kw):
        w = SimpleNamespace(title=title, restore=lambda: None, show=lambda: None, **kw)
        self.windows.append(w)
        return w


def test_live_window_sits_on_top_at_the_right_edge():
    wv = FakeWebview()
    win = desktop.Windows(wv, "http://127.0.0.1:5000")
    live = win._make_live()
    assert live.title == "djnext Live" and live.on_top and live.width == 420
    assert live.x + live.width <= 1728 and live.html  # splash first, then the page loads
    assert win.is_on_top() is True and win.toggle_on_top() is False and win.is_on_top() is False
    win.open_main()  # second window goes straight to the page
    assert wv.windows[1].url == "http://127.0.0.1:5000" and wv.windows[1].html is None
    win.open_live()  # already open: no duplicate
    assert len(wv.windows) == 2


def test_data_folder_is_prepared(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    home = tmp_path / "support"
    desktop.prepare_data_dir(home)
    assert (home / "data").is_dir() and (home / "config.yaml").exists()
    assert desktop._onboarded() is False
    (home / "data" / "settings.json").write_text('{"onboarded": true}')
    assert desktop._onboarded() is True
