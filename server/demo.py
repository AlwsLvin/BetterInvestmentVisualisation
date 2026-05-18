"""End-to-end pipeline driven by real yfinance data.

Run from the ``server/`` directory:
    python demo.py

Behaviour:
  * Fetches 3y of adjusted-close prices and dividends for the default
    portfolio + ^GSPC benchmark via yfinance (cached under .cache/).
  * Computes ROI / MDD / drawdown duration / recovery / volatility / beta /
    dividend yield.
  * Runs Buckley FAHP + FTOPSIS for both styles to get target allocations.
  * Backtests a 1y monthly DCA plan into each allocation and prints the
    return curve summary.

If you have no internet, the first run will fail; subsequent runs hit the
disk cache (24h TTL).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from app.data.cache import FileCache
from app.data.yfinance_source import YFinanceSource
from app.services.allocation import allocate
from app.services.backtest import Plan, backtest
from app.services.metrics import compute_metrics

DEFAULT_PORTFOLIO = [
    "AAPL.US", "NVDA.US", "IAU.US", "BIL.US", "KO.US", "WMT.US", "HSBC.US",
]
BENCHMARK = "^GSPC"
LOOKBACK_DAYS = 365 * 3
BACKTEST_DAYS = 365


def _print_metrics(metrics: dict) -> None:
    headers = ("ticker", "ROI", "MDD", "DD_dur", "Recov", "Vol", "Beta", "DivYld")
    widths = (10, 8, 8, 8, 8, 8, 8, 8)
    print("  " + "".join(f"{h:>{w}}" for h, w in zip(headers, widths)))
    for ticker, m in metrics.items():
        div = "  n/a  " if m.dividend_yield is None else f"{m.dividend_yield:>7.2%}"
        row = (
            f"{ticker:<10}"
            f"{m.annualized_roi:>8.2%}"
            f"{m.max_drawdown:>8.2%}"
            f"{m.drawdown_duration:>8.0f}"
            f"{m.recovery_time:>8.0f}"
            f"{m.volatility:>8.2%}"
            f"{m.beta:>8.2f}"
            f"{div:>8}"
        )
        print("  " + row)


def _print_allocation(title: str, allocation: dict[str, float]) -> None:
    print(f"\n  {title}")
    width = max(len(k) for k in allocation)
    for k, v in sorted(allocation.items(), key=lambda kv: -kv[1]):
        bar = "#" * int(round(v * 50))
        print(f"    {k:<{width}}  {v:>7.2%}  {bar}")


def _ascii_curve(values: list[float], width: int = 50, height: int = 8) -> list[str]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1
    rows: list[list[str]] = [[" "] * width for _ in range(height)]
    n = len(values)
    for x in range(width):
        idx = int(x * (n - 1) / (width - 1)) if width > 1 else 0
        v = values[idx]
        y = int((v - lo) / (hi - lo) * (height - 1))
        y = (height - 1) - y
        rows[y][x] = "*"
    out = ["".join(r) for r in rows]
    out.append(f"{'lo=' + f'{lo:+.2%}':>{width // 2}}{'hi=' + f'{hi:+.2%}':>{width - width // 2}}")
    return out


def _print_backtest(title: str, result) -> None:
    print(f"\n  {title}")
    print(
        f"    cumulative_return = {result.cumulative_return:+.2%}   "
        f"annualized = {result.annualized_return:+.2%}   "
        f"max_drawdown = {result.max_drawdown:.2%}"
    )
    print(
        f"    total_invested = ${result.total_invested:,.0f}   "
        f"final_nav = ${result.final_nav:,.0f}   "
        f"({len(result.invest_dates)} contributions)"
    )
    for line in _ascii_curve(result.return_pct):
        print("    " + line)


def main() -> None:
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    cache_dir = Path(__file__).parent / ".cache"
    src = YFinanceSource(cache=FileCache(cache_dir))

    print(f"Fetching prices: {start} .. {end}")
    prices = {}
    for ticker in DEFAULT_PORTFOLIO:
        prices[ticker] = src.get_prices(ticker, start, end)
        print(f"  {ticker}: {len(prices[ticker])} bars")
    benchmark = src.get_prices(BENCHMARK, start, end)
    print(f"  {BENCHMARK}: {len(benchmark)} bars")

    print("\nFetching dividends...")
    dividends = {}
    for ticker in DEFAULT_PORTFOLIO:
        d = src.get_dividends(ticker, start, end)
        dividends[ticker] = d
        print(f"  {ticker}: {'none' if d is None else f'{len(d)} payments'}")

    print("\nComputing metrics...")
    metrics = compute_metrics(prices, benchmark, dividends)
    _print_metrics(metrics)

    bt_start = end - timedelta(days=BACKTEST_DAYS)
    plan = Plan(amount=1000.0, frequency="monthly:1")
    print(f"\nBacktest range: {bt_start} .. {end}")
    print(f"Plan: ${plan.amount:.0f} {plan.frequency}")

    for style in ("high_return", "low_volatility"):
        print(f"\n{'=' * 70}\nStyle: {style}\n{'=' * 70}")
        for scheme, kwargs in (
            ("linear", {}),
            ("softmax", {"tau": 0.1}),
        ):
            result = allocate(metrics, style=style, scheme=scheme, **kwargs)  # type: ignore[arg-type]
            label = scheme + (f"(τ={kwargs['tau']})" if scheme == "softmax" else "")
            _print_allocation(label, result.allocation)
            bt = backtest(prices, result.allocation, plan, bt_start, end)
            _print_backtest(f"backtest {label}", bt)


if __name__ == "__main__":
    main()
