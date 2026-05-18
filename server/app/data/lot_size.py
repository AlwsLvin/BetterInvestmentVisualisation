from __future__ import annotations

from app.data.symbols import market_suffix


def lot_size(symbol: str) -> int:
    suffix = market_suffix(symbol)
    if suffix in {"SH", "SS", "SZ", "HK"}:
        return 100
    return 1
