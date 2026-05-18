from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.core.fuzzy import TFN, make_tfn_from_crisp
from app.services.fahp import (
    Style,
    benefit_indices,
    compute_global_weights,
)
from app.services.ftopsis import Scheme, closeness_to_allocation, fuzzy_topsis
from app.services.metrics import AssetMetrics


@dataclass
class AllocationResult:
    tickers: list[str]
    indicators: list[str]
    style: Style
    scheme: Scheme
    has_dividend: bool
    global_weights: dict[str, float]
    closeness: dict[str, float]
    allocation: dict[str, float]
    constant_criteria: list[str]
    debug: dict


def _build_decision_matrix(
    metrics: Mapping[str, AssetMetrics],
    indicators: Sequence[str],
    spread_pct: float,
    sigma: Mapping[str, Mapping[str, float]] | None,
) -> tuple[list[str], list[list[TFN]]]:
    tickers = list(metrics.keys())
    rows: list[list[TFN]] = []
    for ticker in tickers:
        m = metrics[ticker]
        row: list[TFN] = []
        for name in indicators:
            value = getattr(m, name)
            if value is None:
                raise ValueError(
                    f"{ticker} missing indicator {name}; reduce indicator set "
                    f"(e.g. has_dividend=False) before building the matrix"
                )
            sig = None
            if sigma is not None:
                sig = sigma.get(ticker, {}).get(name)
            row.append(make_tfn_from_crisp(float(value), sigma=sig, spread_pct=spread_pct))
        rows.append(row)
    return tickers, rows


def allocate(
    metrics: Mapping[str, AssetMetrics],
    style: Style = "high_return",
    scheme: Scheme = "softmax",
    tau: float = 1.0,
    power: float = 2.0,
    floor: float = 0.0,
    spread_pct: float = 0.1,
    sigma: Mapping[str, Mapping[str, float]] | None = None,
) -> AllocationResult:
    """End-to-end FAHP + FTOPSIS allocation.

    Steps:
      1. Decide whether dividend yield is usable (every asset must have it).
      2. Compute global indicator weights from the chosen style via Buckley FAHP.
      3. Fuzzify the crisp decision matrix.
      4. Run FTOPSIS to get per-asset closeness coefficients.
      5. Convert closeness into allocation proportions via the chosen scheme.
    """
    if not metrics:
        raise ValueError("metrics is empty")

    has_dividend = all(m.dividend_yield is not None for m in metrics.values())
    weights, indicators = compute_global_weights(style, has_dividend=has_dividend)

    tickers, decision_matrix = _build_decision_matrix(
        metrics, indicators, spread_pct=spread_pct, sigma=sigma
    )
    benefit_idx = benefit_indices(indicators)

    topsis = fuzzy_topsis(decision_matrix, weights, benefit_idx)
    allocation = closeness_to_allocation(
        topsis["closeness"], scheme=scheme, tau=tau, power=power, floor=floor
    )

    return AllocationResult(
        tickers=tickers,
        indicators=indicators,
        style=style,
        scheme=scheme,
        has_dividend=has_dividend,
        global_weights=dict(zip(indicators, weights)),
        closeness=dict(zip(tickers, topsis["closeness"])),
        allocation=dict(zip(tickers, allocation)),
        constant_criteria=[indicators[i] for i in topsis["constant_criteria"]],
        debug={
            "d_plus": dict(zip(tickers, topsis["d_plus"])),
            "d_minus": dict(zip(tickers, topsis["d_minus"])),
            "decision_matrix": [
                [t.as_tuple() for t in row] for row in decision_matrix
            ],
            "normalized": [
                [t.as_tuple() for t in row] for row in topsis["normalized"]
            ],
        },
    )
