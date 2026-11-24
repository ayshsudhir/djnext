"""Update djnext from inside the app: no Terminal needed.

The Mac app asks GitHub for the newest release. If it's newer, "Update now" downloads djnext.dmg, opens it
(invisibly), and a small helper waits for djnext to quit, swaps the new djnext.app in place of the old one
(the old one goes to the Bin) and opens it again. Your data in ~/Library/Application Support/djnext is untouched.

Run from the code instead (the "Start djnext" script)? Then updating means `git pull` and reinstalling, which the
app does for you too.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Tuple

from . import __version__

REPO = "ayshsudhir/djnext"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET = "djnext.dmg"


def _ver(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return _ver(latest) > _ver(current)


def app_bundle() -> Optional[Path]:
    """The running djnext.app, when djnext runs as the Mac app."""
    if not getattr(sys, "frozen", False):
        return None
    p = Path(sys.executable).resolve()
    for parent in p.parents:
        if parent.suffix == ".app":
            return parent
    return None


def source_folder() -> Optional[Path]:
    """The git checkout, when djnext runs from the code."""
    root = Path(__file__).resolve().parents[2]
    return root if (root / ".git").exists() and (root / "pyproject.toml").exists() else None


def check(opener: Callable = urllib.request.urlopen) -> dict:
    """What's the newest version? Never raises: offline just means 'no update found'."""
    out = {"current": __version__, "latest": None, "newer": False, "notes": "", "url": "", "how": how()}
    try:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "djnext"})
        with opener(req, timeout=10) as r:
            rel = json.load(r)
    except Exception as e:
        out["error"] = f"Couldn't reach GitHub ({type(e).__name__})."
        return out
    latest = (rel.get("tag_name") or "").lstrip("v")
    asset = next((a for a in rel.get("assets", []) if a.get("name") == ASSET), None)
    out.update(latest=latest, newer=bool(latest) and is_newer(latest), notes=(rel.get("body") or "").strip()[:1500],
               url=asset.get("browser_download_url", "") if asset else "", page=rel.get("html_url", ""))
    return out


def how() -> str:
    """'app' (swap the Mac app), 'source' (git pull), or 'manual' (download it yourself)."""
    if app_bundle() is not None:
        return "app"
    if source_folder() is not None and shutil.which("git"):
        return "source"
    return "manual"


def _download(url: str, dest: Path, opener: Callable = urllib.request.urlopen) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "djnext"})
    with opener(req, timeout=120) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


SWAP_SCRIPT = r'''#!/bin/bash
# djnext updater: wait for the old djnext to quit, swap in the new app, open it.
PID="$1"; NEW="$2"; OLD="$3"; MNT="$4"; LOG="$HOME/Library/Logs/djnext.log"
for i in $(seq 1 60); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
{
  echo "--- updating djnext: $NEW -> $OLD"
  TRASH="$HOME/.Trash/djnext $(date +%Y%m%d-%H%M%S).app"
  if mv "$OLD" "$TRASH" && ditto "$NEW" "$OLD"; then
    xattr -dr com.apple.quarantine "$OLD" 2>/dev/null
    echo "updated; old version is in the Bin"
  else
    echo "update failed; putting the old version back"
    [ -d "$OLD" ] || mv "$TRASH" "$OLD"
  fi
  hdiutil detach "$MNT" -quiet 2>/dev/null
} >> "$LOG" 2>&1
open "$OLD"
'''


def install_app(url: str, quit_app: Callable[[], None], opener: Callable = urllib.request.urlopen) -> str:
    """Mac app: download the new version and hand over to the swap helper, then quit."""
    bundle = app_bundle()
    if bundle is None:
        raise RuntimeError("Not running as the Mac app.")
    if not url:
        raise RuntimeError("That release has no djnext.dmg to download.")
    work = Path(tempfile.mkdtemp(prefix="djnext-update-"))
    dmg = _download(url, work / ASSET, opener)
    mnt = work / "mnt"
    mnt.mkdir()
    subprocess.run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", str(mnt), str(dmg)],
                   check=True, capture_output=True)
    new_app = mnt / "djnext.app"
    if not new_app.exists():
        subprocess.run(["hdiutil", "detach", str(mnt), "-quiet"])
        raise RuntimeError("The download doesn't contain djnext.app.")
    script = work / "swap.sh"
    script.write_text(SWAP_SCRIPT)
    script.chmod(0o755)
    subprocess.Popen(["/bin/bash", str(script), str(os.getpid()), str(new_app), str(bundle), str(mnt)],
                     start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    quit_app()
    return "restarting"


def update_source(run: Callable = subprocess.run) -> str:
    """Running from the code: pull the newest code and reinstall. You then restart djnext."""
    root = source_folder()
    if root is None:
        raise RuntimeError("Not running from a git checkout.")
    pull = run(["git", "-C", str(root), "pull", "--ff-only"], capture_output=True, text=True)
    if pull.returncode != 0:
        raise RuntimeError("Couldn't update the code: " + (pull.stderr or pull.stdout).strip()[:300])
    run([sys.executable, "-m", "pip", "install", "-q", "-e", str(root)], capture_output=True, text=True)
    return "restart"
