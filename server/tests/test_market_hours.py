from datetime import datetime, timezone

from app.data.market_hours import is_open, ref_trading_day


def test_ref_day_uses_market_local_open_clock():
    at = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    assert ref_trading_day("CN", at).isoformat() == "2026-05-11"
    assert ref_trading_day("JP", at).isoformat() == "2026-05-11"


def test_ref_day_waits_until_market_open_after_user_midnight():
    at = datetime(2026, 5, 11, 17, 0, tzinfo=timezone.utc)
    assert ref_trading_day("CN", at).isoformat() == "2026-05-11"
    assert ref_trading_day("JP", at).isoformat() == "2026-05-11"
    assert ref_trading_day("US", at).isoformat() == "2026-05-11"
    assert not is_open("CN", at)
    assert is_open("US", at)


def test_weekend_rolls_back_to_previous_trading_day():
    at = datetime(2026, 5, 11, 2, 0, tzinfo=timezone.utc)
    assert ref_trading_day("US", at).isoformat() == "2026-05-08"
    assert not is_open("US", at)
