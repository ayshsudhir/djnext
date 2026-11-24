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


def _fake_app(path, files=3):
    (path / "Contents" / "MacOS").mkdir(parents=True)
    exe = path / "Contents" / "MacOS" / "djnext"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)
    for i in range(files):
        (path / "Contents" / f"f{i}").write_text(str(i))
    return path


def _run_swap(tmp_path, new, old, monkeypatch):
    import subprocess

    script = tmp_path / "swap.sh"
    # no real Bin, codesign, hdiutil or open in the test: stub them
    body = updater.SWAP_SCRIPT.replace('$HOME/.Trash', str(tmp_path / "trash")).replace("command -v codesign", "false")
    body = body.replace('hdiutil detach', 'true').replace('open "$OLD"', 'true')
    (tmp_path / "trash").mkdir()
    script.write_text(body)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    (tmp_path / "Library" / "Logs").mkdir(parents=True)
    subprocess.run(["/bin/bash", str(script), "999999", str(new), str(old), "/nonexistent"], env=env, check=True)
    return (tmp_path / "Library" / "Logs" / "djnext.log").read_text()


def test_swap_replaces_the_app_in_one_step(tmp_path, monkeypatch):
    new = _fake_app(tmp_path / "mnt" / "djnext.app", files=5)
    old = _fake_app(tmp_path / "Applications" / "djnext.app", files=1)
    log = _run_swap(tmp_path, new, old, monkeypatch)
    assert (old / "Contents" / "f4").exists() and "updated" in log
    assert not (tmp_path / "Applications" / ".djnext-update.app").exists()
    assert len(list((tmp_path / "trash").iterdir())) == 1  # the old version went to the Bin


def test_swap_keeps_the_old_app_when_the_copy_fails(tmp_path, monkeypatch):
    new = tmp_path / "mnt" / "djnext.app"  # missing: the download/mount went wrong
    old = _fake_app(tmp_path / "Applications" / "djnext.app", files=1)
    log = _run_swap(tmp_path, new, old, monkeypatch)
    assert (old / "Contents" / "MacOS" / "djnext").exists() and (old / "Contents" / "f0").exists()
    assert "kept the old version" in log and not list((tmp_path / "trash").iterdir())
