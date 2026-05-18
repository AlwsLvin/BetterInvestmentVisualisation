import pytest

from app.data.lot_size import lot_size
from app.data.symbols import currency_of, market_of, to_yfinance


def test_us_suffix_dropped():
    assert to_yfinance("AAPL.US") == "AAPL"


def test_hk_suffix_preserved():
    assert to_yfinance("0700.HK") == "0700.HK"


def test_sh_translated_to_ss():
    assert to_yfinance("600519.SH") == "600519.SS"


def test_sz_preserved():
    assert to_yfinance("000858.SZ") == "000858.SZ"


def test_index_caret_passthrough():
    assert to_yfinance("^GSPC") == "^GSPC"
    assert to_yfinance("^IXIC") == "^IXIC"


def test_no_dot_passthrough():
    assert to_yfinance("SPY") == "SPY"


def test_unknown_suffix_kept():
    assert to_yfinance("BMW.DE") == "BMW.DE"


def test_korean_suffix_preserved():
    assert to_yfinance("000660.KS") == "000660.KS"


def test_japanese_suffix_preserved():
    assert to_yfinance("7203.T") == "7203.T"


def test_lowercase_suffix_normalized():
    assert to_yfinance("AAPL.us") == "AAPL"


def test_empty_raises():
    with pytest.raises(ValueError):
        to_yfinance("")


def test_currency_mapping():
    assert currency_of("AAPL.US") == "USD"
    assert currency_of("600519.SH") == "CNY"
    assert currency_of("600519.SS") == "CNY"
    assert currency_of("000858.SZ") == "CNY"
    assert currency_of("0700.HK") == "HKD"
    assert currency_of("7203.T") == "JPY"
    assert currency_of("^N225") == "JPY"
    assert currency_of("^HSI") == "HKD"
    assert currency_of("000660.KS") == "KRW"
    assert currency_of("035720.KQ") == "KRW"


def test_market_mapping():
    assert market_of("AAPL.US") == "US"
    assert market_of("600519.SS") == "CN"
    assert market_of("000858.SZ") == "CN"
    assert market_of("0700.HK") == "HK"
    assert market_of("7203.T") == "JP"
    assert market_of("^N225") == "JP"
    assert market_of("^HSI") == "HK"
    assert market_of("000660.KS") == "KR"


def test_lot_size_defaults():
    assert lot_size("AAPL.US") == 1
    assert lot_size("600519.SS") == 100
    assert lot_size("000858.SZ") == 100
    assert lot_size("0700.HK") == 100
    assert lot_size("000660.KS") == 1
