import io
import json
import re
from pathlib import Path

from djnext import __version__, updater


def test_version_matches_pyproject():
    py = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert re.search(r'^version = "(.+)"', py, re.M).group(1) == __version__


def test_is_newer():
    assert updater.is_newer("0.3.1", "0.3.0") and updater.is_newer("v1.0.0", "0.9.9")
    assert not updater.is_newer("0.3.0", "0.3.0") and not updater.is_newer("0.2.9", "0.3.0")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_check_reads_the_latest_release():
    rel = {"tag_name": "v9.0.0", "body": "New stuff", "html_url": "https://github.com/x",
           "assets": [{"name": "djnext.dmg", "browser_download_url": "https://dl/djnext.dmg"}]}
    out = updater.check(opener=lambda req, timeout=0: FakeResponse(json.dumps(rel).encode()))
    assert out["newer"] and out["latest"] == "9.0.0" and out["url"] == "https://dl/djnext.dmg"
    assert out["notes"] == "New stuff"


def test_check_offline_is_not_an_error():
    def boom(*a, **k):
        raise OSError("no internet")
    out = updater.check(opener=boom)
    assert out["newer"] is False and "Couldn't reach GitHub" in out["error"]


def test_running_from_code_is_not_the_app():
    assert updater.app_bundle() is None and updater.how() in ("source", "manual")


def test_source_update_pulls_then_reinstalls():
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    def run(cmd, **kw):
        calls.append(cmd)
        return R()
    assert updater.update_source(run=run) == "restart"
    assert calls[0][-2:] == ["pull", "--ff-only"] and "install" in calls[1]
