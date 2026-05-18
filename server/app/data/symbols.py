"""Translate the project's own symbol convention to data-source-specific ones.

Project convention:
    {ticker}.{market}     where market in {US, HK, SH, SZ, T, KS, KQ}
    plus pass-through for index/ETF symbols that already start with '^' or
    have no dot at all.

yfinance convention:
    US:    AAPL              (no suffix)
    HK:    0700.HK
    SH:    600519.SS         (yfinance uses .SS for Shanghai)
    SZ:    000858.SZ
    JP:    7203.T
    KS:    000660.KS
    KQ:    035720.KQ
"""
from __future__ import annotations

_YF_SUFFIX = {
    "US": "",
    "HK": ".HK",
    "SH": ".SS",
    "SS": ".SS",
    "SZ": ".SZ",
    "T": ".T",
    "KS": ".KS",
    "KQ": ".KQ",
}

_KNOWN_INDEX_MARKETS = {
    "^GSPC": "US",
    "^IXIC": "US",
    "^DJI": "US",
    "^N225": "JP",
    "^HSI": "HK",
    "^HSCE": "HK",
    "^KS11": "KR",
    "^KQ11": "KR",
    "^SSEC": "CN",
    "000001.SS": "CN",
    "000016.SS": "CN",
    "000300.SS": "CN",
    "000905.SS": "CN",
    "399001.SZ": "CN",
    "399006.SZ": "CN",
}

_MARKET_CURRENCY = {
    "US": "USD",
    "CN": "CNY",
    "HK": "HKD",
    "JP": "JPY",
    "KR": "KRW",
}


def _normalized(symbol: str) -> str:
    return symbol.strip().upper()


def to_yfinance(symbol: str) -> str:
    if not symbol:
        raise ValueError("Empty symbol")
    if symbol.startswith("^") or "." not in symbol:
        return symbol
    code, suffix = symbol.rsplit(".", 1)
    suffix_upper = suffix.upper()
    yf_suffix = _YF_SUFFIX.get(suffix_upper, f".{suffix_upper}")
    return code + yf_suffix


def market_suffix(symbol: str) -> str:
    if not symbol or symbol.startswith("^") or "." not in symbol:
        return "US"
    return symbol.rsplit(".", 1)[1].upper()


def market_of(symbol: str) -> str:
    known = _KNOWN_INDEX_MARKETS.get(_normalized(symbol))
    if known:
        return known
    suffix = market_suffix(symbol)
    if suffix in {"SH", "SS", "SZ"}:
        return "CN"
    if suffix == "HK":
        return "HK"
    if suffix == "T":
        return "JP"
    if suffix in {"KS", "KQ"}:
        return "KR"
    return "US"


def currency_of(symbol: str) -> str:
    known_market = _KNOWN_INDEX_MARKETS.get(_normalized(symbol))
    if known_market:
        return _MARKET_CURRENCY[known_market]
    suffix = market_suffix(symbol)
    if suffix in {"SH", "SS", "SZ"}:
        return "CNY"
    if suffix == "HK":
        return "HKD"
    if suffix == "T":
        return "JPY"
    if suffix in {"KS", "KQ"}:
        return "KRW"
    return "USD"
