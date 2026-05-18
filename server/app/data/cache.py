"""Simple file-based pickle cache for market data Series.

yfinance hits a remote API and is rate-limited; the same daily price range
yields identical results until the next session close, so caching to disk
turns a 7-second portfolio fetch into 200 ms on subsequent runs.
"""
from __future__ import annotations

import hashlib
import pickle
import tempfile
import time
from threading import RLock
from pathlib import Path
from typing import Any


class FileCache:
    def __init__(self, cache_dir: Path | str, ttl_seconds: int = 24 * 3600):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds
        self._lock = RLock()

    def _path(self, key: str) -> Path:
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
        return self.cache_dir / f"{h}.pkl"

    def get(self, key: str) -> Any | None:
        path = self._path(key)
        with self._lock:
            try:
                if not path.exists():
                    return None
                if time.time() - path.stat().st_mtime > self.ttl_seconds:
                    return None
                with path.open("rb") as f:
                    return pickle.load(f)
            except (pickle.PickleError, EOFError):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
            except OSError:
                return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        tmp_name: str | None = None
        with self._lock:
            try:
                with tempfile.NamedTemporaryFile(
                    "wb",
                    delete=False,
                    dir=self.cache_dir,
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                ) as f:
                    tmp_name = f.name
                    pickle.dump(value, f)
                Path(tmp_name).replace(path)
                tmp_name = None
            except OSError:
                pass
            finally:
                if tmp_name is not None:
                    try:
                        Path(tmp_name).unlink(missing_ok=True)
                    except OSError:
                        pass

    def clear(self) -> None:
        with self._lock:
            try:
                paths = list(self.cache_dir.glob("*.pkl"))
            except OSError:
                return None
            for p in paths:
                try:
                    p.unlink(missing_ok=True)
                except OSError:
                    pass
            return None
