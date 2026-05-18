import math

import pytest

from app.services.fahp import (
    ALL_INDICATORS,
    COST_INDICATORS,
    STYLE_PRESETS,
    benefit_indices,
    buckley_weights,
    compute_global_weights,
)


def test_buckley_weights_sum_to_one():
    matrix = STYLE_PRESETS["high_return"]
    w = buckley_weights(matrix)
    assert math.isclose(sum(w), 1.0, rel_tol=1e-9)
    assert all(wi > 0 for wi in w)


def test_buckley_no_zero_weight_for_dominated_criterion():
    """Chang's extent analysis would have produced 0 here; Buckley must not."""
    matrix = [
        [(1, 1, 1), (1 / 9, 1 / 7, 1 / 5), (1 / 11, 1 / 9, 1 / 7)],
        [(5, 7, 9), (1, 1, 1), (1 / 3, 1, 1)],
        [(7, 9, 11), (1, 1, 3), (1, 1, 1)],
    ]
    w = buckley_weights(matrix)
    assert all(wi > 0 for wi in w)


def test_identity_pairwise_yields_equal_weights():
    n = 4
    matrix = [[(1, 1, 1)] * n for _ in range(n)]
    w = buckley_weights(matrix)
    for wi in w:
        assert math.isclose(wi, 1 / n, rel_tol=1e-9)


def test_dominant_criterion_gets_largest_weight():
    matrix = [
        [(1, 1, 1), (3, 5, 7), (3, 5, 7)],
        [(1 / 7, 1 / 5, 1 / 3), (1, 1, 1), (1, 1, 1)],
        [(1 / 7, 1 / 5, 1 / 3), (1, 1, 1), (1, 1, 1)],
    ]
    w = buckley_weights(matrix)
    assert w[0] == max(w)


def test_high_return_style_emphasizes_roi_over_volatility():
    w = buckley_weights(STYLE_PRESETS["high_return"])
    assert w[0] > w[2]


def test_low_volatility_style_emphasizes_volatility_over_roi():
    w = buckley_weights(STYLE_PRESETS["low_volatility"])
    assert w[2] > w[0]


def test_compute_global_weights_with_dividend_returns_seven_indicators():
    weights, names = compute_global_weights("high_return", has_dividend=True)
    assert len(weights) == 7
    assert names == list(ALL_INDICATORS)
    assert math.isclose(sum(weights), 1.0, rel_tol=1e-9)


def test_compute_global_weights_without_dividend_returns_six_indicators():
    weights, names = compute_global_weights("high_return", has_dividend=False)
    assert len(weights) == 6
    assert names == ["annualized_roi"] + list(COST_INDICATORS)
    assert math.isclose(sum(weights), 1.0, rel_tol=1e-9)


def test_validate_pairwise_rejects_non_unit_diagonal():
    with pytest.raises(ValueError):
        buckley_weights([[(2, 2, 2), (1, 1, 1)], [(1, 1, 1), (1, 1, 1)]])


def test_validate_pairwise_rejects_non_square():
    with pytest.raises(ValueError):
        buckley_weights([[(1, 1, 1), (1, 1, 1)]])


def test_benefit_indices_with_dividend():
    _, names = compute_global_weights("high_return", has_dividend=True)
    assert benefit_indices(names) == [0, 1]


def test_benefit_indices_without_dividend():
    _, names = compute_global_weights("high_return", has_dividend=False)
    assert benefit_indices(names) == [0]
