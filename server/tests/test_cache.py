import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from app.data.cache import FileCache


def test_cache_miss_returns_none(tmp_path):
    cache = FileCache(tmp_path)
    assert cache.get("nonexistent") is None


def test_cache_round_trip_series(tmp_path):
    cache = FileCache(tmp_path)
    s = pd.Series([1.0, 2.0, 3.0],
                  index=pd.date_range("2024-01-01", periods=3))
    cache.set("k", s)
    out = cache.get("k")
    assert out is not None
    pd.testing.assert_series_equal(out, s)


def test_cache_ttl_expiry(tmp_path):
    cache = FileCache(tmp_path, ttl_seconds=1)
    s = pd.Series([1.0])
    cache.set("k", s)
    path = next(tmp_path.glob("*.pkl"))
    old = time.time() - 10
    os.utime(path, (old, old))
    assert cache.get("k") is None


def test_cache_can_store_none_sentinel(tmp_path):
    cache = FileCache(tmp_path)
    cache.set("k", "__BV_NO_DIVIDEND__")
    assert cache.get("k") == "__BV_NO_DIVIDEND__"


def test_cache_clear(tmp_path):
    cache = FileCache(tmp_path)
    cache.set("k1", pd.Series([1.0]))
    cache.set("k2", pd.Series([2.0]))
    cache.clear()
    assert cache.get("k1") is None
    assert cache.get("k2") is None


def test_corrupt_cache_file_falls_back_to_miss(tmp_path):
    cache = FileCache(tmp_path)
    cache.set("k", pd.Series([1.0]))
    path = next(tmp_path.glob("*.pkl"))
    path.write_bytes(b"not a pickle")
    assert cache.get("k") is None
    assert not path.exists()


def test_cache_read_os_error_falls_back_to_miss(tmp_path, monkeypatch):
    cache = FileCache(tmp_path)
    cache.set("k", pd.Series([1.0]))
    path = next(tmp_path.glob("*.pkl"))
    original_open = Path.open

    def fail_for_cache_file(self, *args, **kwargs):
        if self == path:
            raise OSError(24, "Too many open files")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_for_cache_file)

    assert cache.get("k") is None


def test_cache_write_os_error_is_ignored(tmp_path, monkeypatch):
    cache = FileCache(tmp_path)

    def fail_named_tempfile(*args, **kwargs):
        raise OSError(24, "Too many open files")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", fail_named_tempfile)

    cache.set("k", pd.Series([1.0]))

    assert cache.get("k") is None


def test_cache_concurrent_reads_and_writes_do_not_leave_partial_files(tmp_path):
    cache = FileCache(tmp_path)

    def write_and_read(i: int):
        expected = pd.Series([float(i)], name="value")
        cache.set("shared", expected)
        return cache.get("shared")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write_and_read, range(32)))

    assert any(result is not None for result in results)
    final = cache.get("shared")
    assert final is not None
    assert isinstance(final, pd.Series)
    assert list(tmp_path.glob("*.tmp")) == []
