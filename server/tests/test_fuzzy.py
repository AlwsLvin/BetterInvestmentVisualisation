import math

import pytest

from app.core.fuzzy import (
    TFN,
    make_tfn_from_crisp,
    tfn_distance,
    tfn_geomean,
    tfn_sum,
)


def test_tfn_auto_sorts():
    t = TFN(3, 1, 2)
    assert (t.l, t.m, t.u) == (1.0, 2.0, 3.0)


def test_tfn_negative_values_keep_ordering():
    t = TFN(-0.18, -0.20, -0.22)
    assert t.l <= t.m <= t.u


def test_addition_and_scalar_multiplication():
    a = TFN(1, 2, 3)
    b = TFN(0.5, 1, 1.5)
    s = a + b
    assert s.as_tuple() == (1.5, 3.0, 4.5)
    p = a * 2
    assert p.as_tuple() == (2.0, 4.0, 6.0)


def test_negative_scalar_multiplication_preserves_order():
    a = TFN(1, 2, 3)
    p = a * -1
    assert p.l <= p.m <= p.u


def test_inverse_rejects_zero():
    with pytest.raises(ValueError):
        TFN(0, 1, 2).inverse()


def test_geomean_of_identity_is_identity():
    items = [TFN(1, 1, 1)] * 5
    g = tfn_geomean(items)
    assert math.isclose(g.l, 1.0)
    assert math.isclose(g.m, 1.0)
    assert math.isclose(g.u, 1.0)


def test_geomean_known_value():
    items = [TFN(2, 4, 8), TFN(2, 4, 8)]
    g = tfn_geomean(items)
    assert math.isclose(g.l, 2.0, rel_tol=1e-9)
    assert math.isclose(g.m, 4.0, rel_tol=1e-9)
    assert math.isclose(g.u, 8.0, rel_tol=1e-9)


def test_distance_between_equal_tfns_is_zero():
    a = TFN(0.1, 0.2, 0.3)
    assert tfn_distance(a, a) == 0.0


def test_make_tfn_from_negative_crisp_keeps_invariant():
    t = make_tfn_from_crisp(-0.2, spread_pct=0.1)
    assert t.l <= t.m <= t.u
    assert math.isclose(t.m, -0.2)


def test_make_tfn_from_zero_uses_default_spread():
    t = make_tfn_from_crisp(0.0, spread_pct=0.1)
    assert t.u > t.l


def test_tfn_sum_empty_is_zero():
    z = tfn_sum([])
    assert z.as_tuple() == (0.0, 0.0, 0.0)
