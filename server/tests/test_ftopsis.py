import math

import pytest

from app.core.fuzzy import TFN, make_tfn_from_crisp
from app.services.ftopsis import (
    closeness_to_allocation,
    fuzzy_topsis,
    normalize_decision_matrix,
)


def test_normalize_handles_negative_values_without_zeroing():
    """Original ipynb collapsed negative ROI to (0,0,0). Must not happen here."""
    decision = [
        [make_tfn_from_crisp(0.30)],
        [make_tfn_from_crisp(-0.20)],
        [make_tfn_from_crisp(0.05)],
    ]
    normalized, constants = normalize_decision_matrix(decision, benefit_idx=[0])
    assert constants == []
    assert all(0 <= row[0].l <= 1 for row in normalized)
    assert all(0 <= row[0].u <= 1 for row in normalized)
    assert normalized[0][0].m > normalized[2][0].m > normalized[1][0].m


def test_normalize_constant_column_reports_constant():
    decision = [
        [make_tfn_from_crisp(0.5)],
        [make_tfn_from_crisp(0.5)],
        [make_tfn_from_crisp(0.5)],
    ]
    _, constants = normalize_decision_matrix(decision, benefit_idx=[0])
    assert constants == [0]


def test_normalize_cost_inverts_ranking():
    decision = [
        [make_tfn_from_crisp(0.10)],
        [make_tfn_from_crisp(0.50)],
        [make_tfn_from_crisp(0.90)],
    ]
    normalized, _ = normalize_decision_matrix(decision, benefit_idx=[])
    assert normalized[0][0].m > normalized[2][0].m


def test_fuzzy_topsis_dominant_alternative_has_highest_closeness():
    decision = [
        [TFN(0.9, 1.0, 1.1), TFN(0.05, 0.10, 0.15)],
        [TFN(0.4, 0.5, 0.6), TFN(0.40, 0.50, 0.60)],
        [TFN(0.1, 0.2, 0.3), TFN(0.70, 0.80, 0.90)],
    ]
    weights = [0.5, 0.5]
    result = fuzzy_topsis(decision, weights, benefit_idx=[0])
    cc = result["closeness"]
    assert cc[0] == max(cc)
    assert cc[2] == min(cc)


def test_fuzzy_topsis_weights_length_mismatch():
    decision = [[TFN(1, 1, 1), TFN(1, 1, 1)]]
    with pytest.raises(ValueError):
        fuzzy_topsis(decision, [1.0], benefit_idx=[0])


def test_closeness_to_allocation_linear_normalizes():
    cc = [0.2, 0.5, 0.3]
    a = closeness_to_allocation(cc, scheme="linear")
    assert math.isclose(sum(a), 1.0, rel_tol=1e-9)
    assert a[1] > a[2] > a[0]


def test_closeness_to_allocation_softmax_concentrates_with_low_tau():
    cc = [0.1, 0.5, 0.9]
    soft = closeness_to_allocation(cc, scheme="softmax", tau=0.1)
    assert soft[2] > 0.9


def test_closeness_to_allocation_power_emphasizes_top():
    cc = [0.3, 0.6, 0.9]
    p = closeness_to_allocation(cc, scheme="power", power=4.0)
    lin = closeness_to_allocation(cc, scheme="linear")
    assert p[2] > lin[2]


def test_closeness_to_allocation_floor_respected():
    cc = [0.99, 0.01, 0.01]
    a = closeness_to_allocation(cc, scheme="linear", floor=0.05)
    assert all(ai >= 0.05 - 1e-9 for ai in a)
    assert math.isclose(sum(a), 1.0, rel_tol=1e-9)


def test_closeness_to_allocation_floor_too_large_raises():
    with pytest.raises(ValueError):
        closeness_to_allocation([0.5, 0.5, 0.5], scheme="linear", floor=0.5)


def test_closeness_to_allocation_all_zero_falls_back_to_equal():
    a = closeness_to_allocation([0.0, 0.0, 0.0], scheme="linear")
    assert all(math.isclose(ai, 1 / 3, rel_tol=1e-9) for ai in a)
