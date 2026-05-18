from __future__ import annotations

from typing import Literal, Sequence

from app.core.fuzzy import TFN, tfn_geomean, tfn_sum

PairwiseMatrix = Sequence[Sequence[tuple[float, float, float]]]
Style = Literal["high_return", "low_volatility", "balanced"]

CRITERIA = ("roi", "mdd", "volatility")
BENEFIT_INDICATORS = ("annualized_roi", "dividend_yield")
COST_INDICATORS = (
    "max_drawdown",
    "drawdown_duration",
    "recovery_time",
    "volatility",
    "beta",
)
ALL_INDICATORS = BENEFIT_INDICATORS + COST_INDICATORS


_CRITERIA_HIGH_RETURN: PairwiseMatrix = [
    [(1, 1, 1), (3, 5, 7), (3, 5, 7)],
    [(1 / 7, 1 / 5, 1 / 3), (1, 1, 1), (3, 5, 7)],
    [(1 / 7, 1 / 5, 1 / 3), (1 / 7, 1 / 5, 1 / 3), (1, 1, 1)],
]

_CRITERIA_BALANCED: PairwiseMatrix = [
    [(1, 1, 1), (1 / 9, 1 / 7, 1 / 5), (1 / 7, 1 / 5, 1 / 3)],
    [(5, 7, 9), (1, 1, 1), (1, 3, 5)],
    [(3, 5, 7), (1 / 5, 1 / 3, 1), (1, 1, 1)],
]

_CRITERIA_LOW_VOLATILITY: PairwiseMatrix = [
    [(1, 1, 1), (1 / 9, 1 / 7, 1 / 5), (1 / 11, 1 / 9, 1 / 7)],
    [(5, 7, 9), (1, 1, 1), (1 / 3, 1, 1)],
    [(7, 9, 11), (1, 1, 3), (1, 1, 1)],
]

STYLE_PRESETS: dict[Style, PairwiseMatrix] = {
    "high_return": _CRITERIA_HIGH_RETURN,
    "balanced": _CRITERIA_BALANCED,
    "low_volatility": _CRITERIA_LOW_VOLATILITY,
}

_ROI_FACTOR: PairwiseMatrix = [
    [(1, 1, 1), (1, 3, 5)],
    [(1 / 5, 1 / 3, 1), (1, 1, 1)],
]

_MDD_FACTOR: PairwiseMatrix = [
    [(1, 1, 1), (1 / 7, 1 / 5, 1 / 3), (1 / 7, 1 / 5, 1 / 3)],
    [(3, 5, 7), (1, 1, 1), (1 / 5, 1 / 3, 1)],
    [(3, 5, 7), (1, 3, 5), (1, 1, 1)],
]

_VOLATILITY_FACTOR: PairwiseMatrix = [
    [(1, 1, 1), (1, 3, 5)],
    [(1 / 5, 1 / 3, 1), (1, 1, 1)],
]


def _to_tfn_matrix(matrix: PairwiseMatrix) -> list[list[TFN]]:
    return [[TFN(*cell) for cell in row] for row in matrix]


def _validate_pairwise(matrix: list[list[TFN]]) -> None:
    n = len(matrix)
    if n == 0:
        raise ValueError("Pairwise matrix is empty")
    for row in matrix:
        if len(row) != n:
            raise ValueError("Pairwise matrix must be square")
    for i in range(n):
        d = matrix[i][i]
        if not (d.l == d.m == d.u == 1):
            raise ValueError("Diagonal entries must be (1,1,1)")


def buckley_weights(matrix: PairwiseMatrix) -> list[float]:
    """Compute crisp criterion weights using Buckley's geometric-mean FAHP.

    Why Buckley over Chang's extent analysis: Chang's V(P_i >= P_j) can yield
    zero weights even for criteria the decision-maker considers important
    (Wang/Luo/Hua 2008). Buckley's geometric mean never collapses to zero
    unless the input itself is degenerate.

    Steps:
      1. r_i = (a_i1 * a_i2 * ... * a_in)^(1/n)        (TFN geomean of row)
      2. R = r_1 + r_2 + ... + r_n
      3. w_i_fuzzy = r_i * R^{-1}                       (still a TFN)
      4. Defuzzify by centroid, then normalize to sum to 1.
    """
    tfn_matrix = _to_tfn_matrix(matrix)
    _validate_pairwise(tfn_matrix)

    row_geomeans = [tfn_geomean(row) for row in tfn_matrix]
    total = tfn_sum(row_geomeans)
    inv_total = total.inverse()
    fuzzy_weights = [r * inv_total for r in row_geomeans]
    crisp = [w.centroid() for w in fuzzy_weights]
    s = sum(crisp)
    if s == 0:
        n = len(crisp)
        return [1.0 / n] * n
    return [c / s for c in crisp]


def style_to_criteria_weights(style: Style) -> list[float]:
    if style not in STYLE_PRESETS:
        raise ValueError(f"Unknown style: {style}")
    return buckley_weights(STYLE_PRESETS[style])


def compute_global_weights(
    style: Style,
    has_dividend: bool = True,
) -> tuple[list[float], list[str]]:
    """Compute the global weight vector across all leaf indicators.

    Returns (weights, indicator_names) with equal length. When
    ``has_dividend`` is False the dividend_yield leaf is dropped and the
    full weight of the ROI criterion goes to annualized_roi.

    The resulting indicator order is:
        annualized_roi, [dividend_yield], max_drawdown, drawdown_duration,
        recovery_time, volatility, beta
    """
    criteria_w = style_to_criteria_weights(style)
    mdd_w = buckley_weights(_MDD_FACTOR)
    vol_w = buckley_weights(_VOLATILITY_FACTOR)

    if has_dividend:
        roi_w = buckley_weights(_ROI_FACTOR)
        weights = [
            criteria_w[0] * roi_w[0],
            criteria_w[0] * roi_w[1],
            criteria_w[1] * mdd_w[0],
            criteria_w[1] * mdd_w[1],
            criteria_w[1] * mdd_w[2],
            criteria_w[2] * vol_w[0],
            criteria_w[2] * vol_w[1],
        ]
        names = list(ALL_INDICATORS)
    else:
        weights = [
            criteria_w[0],
            criteria_w[1] * mdd_w[0],
            criteria_w[1] * mdd_w[1],
            criteria_w[1] * mdd_w[2],
            criteria_w[2] * vol_w[0],
            criteria_w[2] * vol_w[1],
        ]
        names = ["annualized_roi"] + list(COST_INDICATORS)

    s = sum(weights)
    return [w / s for w in weights], names


def benefit_indices(indicator_names: Sequence[str]) -> list[int]:
    return [i for i, n in enumerate(indicator_names) if n in BENEFIT_INDICATORS]
