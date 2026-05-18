from __future__ import annotations

import math
from typing import Literal, Sequence

from app.core.fuzzy import TFN, tfn_distance

Scheme = Literal["linear", "softmax", "power"]
EPS = 1e-12


def normalize_decision_matrix(
    decision_matrix: Sequence[Sequence[TFN]],
    benefit_idx: Sequence[int],
) -> tuple[list[list[TFN]], list[int]]:
    """Min-max normalize a fuzzy decision matrix into [0, 1].

    Why min-max instead of Chen's r_ij = x_ij/c_j (benefit) or
    r_ij = a_j/x_ij (cost):
      * The original ipynb collapsed negative ROI rows to (0,0,0) because of
        ``max(0, x*0.9)`` and division by ``max_u`` could blow up when the
        column max was zero or negative. Min-max with column min subtracted
        handles negatives natively without information loss.
      * Cost-side ``1 - u/max_u`` degenerated to (0,0,0) for the worst
        alternative; min-max-inverted preserves separation.

    A column with zero range (all alternatives equal on this criterion) gets
    normalized to (0.5, 0.5, 0.5) and its index is reported back so callers
    can warn or ignore the criterion.
    """
    n_alt = len(decision_matrix)
    if n_alt == 0:
        return [], []
    n_crit = len(decision_matrix[0])
    benefit_set = set(benefit_idx)

    normalized: list[list[TFN]] = [[TFN(0, 0, 0)] * n_crit for _ in range(n_alt)]
    constant_criteria: list[int] = []

    for j in range(n_crit):
        col = [decision_matrix[i][j] for i in range(n_alt)]
        lo = min(t.l for t in col)
        hi = max(t.u for t in col)
        rng = hi - lo
        m_vals = [t.m for t in col]
        m_spread = max(m_vals) - min(m_vals)
        if rng < EPS or m_spread < EPS:
            constant_criteria.append(j)
            for i in range(n_alt):
                normalized[i][j] = TFN(0.5, 0.5, 0.5)
            continue
        if j in benefit_set:
            for i in range(n_alt):
                t = col[i]
                normalized[i][j] = TFN(
                    (t.l - lo) / rng,
                    (t.m - lo) / rng,
                    (t.u - lo) / rng,
                )
        else:
            for i in range(n_alt):
                t = col[i]
                normalized[i][j] = TFN(
                    (hi - t.u) / rng,
                    (hi - t.m) / rng,
                    (hi - t.l) / rng,
                )

    return normalized, constant_criteria


def fuzzy_topsis(
    decision_matrix: Sequence[Sequence[TFN]],
    weights: Sequence[float],
    benefit_idx: Sequence[int],
) -> dict:
    """Run FTOPSIS and return per-alternative closeness coefficients.

    Returns a dict with keys: closeness, d_plus, d_minus, normalized,
    weighted, constant_criteria.
    """
    n_alt = len(decision_matrix)
    n_crit = len(decision_matrix[0]) if n_alt else 0
    if len(weights) != n_crit:
        raise ValueError(
            f"weights length {len(weights)} != criteria count {n_crit}"
        )

    normalized, constants = normalize_decision_matrix(decision_matrix, benefit_idx)
    weighted = [
        [normalized[i][j] * weights[j] for j in range(n_crit)]
        for i in range(n_alt)
    ]

    a_pos = [TFN(1, 1, 1) * weights[j] for j in range(n_crit)]
    a_neg = [TFN(0, 0, 0) for _ in range(n_crit)]

    d_plus = [
        sum(tfn_distance(weighted[i][j], a_pos[j]) for j in range(n_crit))
        for i in range(n_alt)
    ]
    d_minus = [
        sum(tfn_distance(weighted[i][j], a_neg[j]) for j in range(n_crit))
        for i in range(n_alt)
    ]

    closeness = []
    for dp, dn in zip(d_plus, d_minus):
        denom = dp + dn
        closeness.append(dn / denom if denom > EPS else 0.0)

    return {
        "closeness": closeness,
        "d_plus": d_plus,
        "d_minus": d_minus,
        "normalized": normalized,
        "weighted": weighted,
        "constant_criteria": constants,
    }


def closeness_to_allocation(
    closeness: Sequence[float],
    scheme: Scheme = "softmax",
    tau: float = 1.0,
    power: float = 2.0,
    floor: float = 0.0,
) -> list[float]:
    """Convert closeness coefficients into investment proportions.

    Schemes:
      * linear  - w_i = CC_i / sum(CC).  Faithful to user expectation of
                  "归一化".  Spreads weight; underperformers still get share.
      * softmax - w_i = exp(CC_i / tau) / sum(...).  Concentrates on top
                  performers; smaller tau -> sharper.
      * power   - w_i = CC_i^p / sum(CC^p).  Polynomial sharpening.

    ``floor`` sets a per-asset minimum (e.g. 0.02 for 2%); residual is
    redistributed proportionally on top.
    """
    if not closeness:
        return []
    n = len(closeness)

    if scheme == "linear":
        raw = list(closeness)
    elif scheme == "softmax":
        if tau <= 0:
            raise ValueError("softmax tau must be > 0")
        m = max(closeness)
        raw = [math.exp((c - m) / tau) for c in closeness]
    elif scheme == "power":
        if power <= 0:
            raise ValueError("power must be > 0")
        raw = [max(c, 0.0) ** power for c in closeness]
    else:
        raise ValueError(f"Unknown scheme: {scheme}")

    s = sum(raw)
    if s <= EPS:
        return [1.0 / n] * n
    weights = [r / s for r in raw]

    if floor > 0:
        if floor * n > 1:
            raise ValueError("floor * n must not exceed 1")
        residual = 1.0 - floor * n
        weights = [floor + residual * w for w in weights]

    return weights
