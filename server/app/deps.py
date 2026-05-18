"""Singleton dependencies wired into FastAPI routes.

Keeping these in a separate module makes them trivially overridable in
tests via ``app.dependency_overrides``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.data.cache import FileCache
from app.data.yfinance_source import YFinanceSource
from app.schemas import SettingsModel


@lru_cache(maxsize=1)
def get_cache() -> FileCache:
    return FileCache(Path(__file__).resolve().parent.parent / ".cache")


@lru_cache(maxsize=1)
def get_intraday_cache() -> FileCache:
    return FileCache(
        Path(__file__).resolve().parent.parent / ".cache" / "intraday",
        ttl_seconds=60,
    )


@lru_cache(maxsize=1)
def get_data_source() -> YFinanceSource:
    return YFinanceSource(cache=get_cache(), intraday_cache=get_intraday_cache())


_SETTINGS = SettingsModel()


def get_settings() -> SettingsModel:
    return _SETTINGS


def update_settings(new: SettingsModel) -> SettingsModel:
    global _SETTINGS
    _SETTINGS = new
    return _SETTINGS
