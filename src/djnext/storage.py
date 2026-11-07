"""Saving djnext's own files safely.

- write_json: writes to a temporary file first and then swaps it in, so quitting (or a crash, or the Mac sleeping)
  in the middle of a save can never leave a half-written file behind.
- read_json: if a file is damaged anyway, it's renamed to "<name>.damaged-<time>" (kept, not deleted) and
  djnext carries on as if it wasn't there, instead of failing on every start.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_lock = threading.Lock()  # one save at a time (the web server handles requests in parallel threads)


def write_json(path: Path, data: Any, indent: int = 2) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=indent, ensure_ascii=False)
    with _lock:
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)  # atomic: the file is either the old version or the new one, never half
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return path


def read_json(path: Path, default: Any = None) -> Any:
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError, OSError) as e:
        aside = path.with_name(f"{path.name}.damaged-{datetime.now():%Y%m%d-%H%M%S}")
        try:
            path.rename(aside)
        except OSError:
            pass
        logging.getLogger("djnext").warning("%s was damaged (%s); set aside as %s", path, e, aside.name)
        print(f"djnext: {path} was damaged ({e}); set aside as {aside.name} and starting without it.")
        return default
