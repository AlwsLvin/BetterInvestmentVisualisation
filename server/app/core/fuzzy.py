from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Union

Number = Union[int, float]


@dataclass(frozen=True)
class TFN:
    """Triangular Fuzzy Number (l, m, u) with l <= m <= u.

    Construction auto-sorts so users may pass values in any order without
    silently violating the ordering invariant.
    """

    l: float
    m: float
    u: float

    def __post_init__(self) -> None:
        vals = sorted((float(self.l), float(self.m), float(self.u)))
        object.__setattr__(self, "l", vals[0])
        object.__setattr__(self, "m", vals[1])
        object.__setattr__(self, "u", vals[2])

    def __add__(self, other: "TFN") -> "TFN":
        return TFN(self.l + other.l, self.m + other.m, self.u + other.u)

    def __mul__(self, other: Union["TFN", Number]) -> "TFN":
        if isinstance(other, TFN):
            return TFN(self.l * other.l, self.m * other.m, self.u * other.u)
        s = float(other)
        if s >= 0:
            return TFN(self.l * s, self.m * s, self.u * s)
        return TFN(self.u * s, self.m * s, self.l * s)

    def __rmul__(self, other: Number) -> "TFN":
        return self.__mul__(other)

    def __sub__(self, other: "TFN") -> "TFN":
        return TFN(self.l - other.u, self.m - other.m, self.u - other.l)

    def power(self, p: float) -> "TFN":
        if self.l <= 0:
            raise ValueError("TFN.power requires strictly positive support")
        return TFN(self.l ** p, self.m ** p, self.u ** p)

    def inverse(self) -> "TFN":
        if self.l == 0 or self.m == 0 or self.u == 0:
            raise ValueError("Cannot invert a TFN containing zero")
        return TFN(1.0 / self.u, 1.0 / self.m, 1.0 / self.l)

    def centroid(self) -> float:
        return (self.l + self.m + self.u) / 3.0

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.l, self.m, self.u)

    def __iter__(self):
        yield self.l
        yield self.m
        yield self.u

    def __str__(self) -> str:
        return f"({self.l:.4f}, {self.m:.4f}, {self.u:.4f})"


def tfn_distance(a: TFN, b: TFN) -> float:
    """Vertex distance between two TFNs (Chen 2000)."""
    return math.sqrt(((a.l - b.l) ** 2 + (a.m - b.m) ** 2 + (a.u - b.u) ** 2) / 3.0)


def tfn_geomean(items: Sequence[TFN]) -> TFN:
    """Geometric mean of a sequence of TFNs (component-wise).

    Used by Buckley's FAHP. Requires strictly positive supports.
    """
    n = len(items)
    if n == 0:
        raise ValueError("Cannot take geometric mean of empty sequence")
    log_l = sum(math.log(t.l) for t in items) / n
    log_m = sum(math.log(t.m) for t in items) / n
    log_u = sum(math.log(t.u) for t in items) / n
    return TFN(math.exp(log_l), math.exp(log_m), math.exp(log_u))


def tfn_sum(items: Iterable[TFN]) -> TFN:
    total = TFN(0.0, 0.0, 0.0)
    for t in items:
        total = total + t
    return total


def make_tfn_from_crisp(x: float, sigma: float | None = None, k: float = 1.0,
                         spread_pct: float = 0.1) -> TFN:
    """Fuzzify a crisp value into a TFN.

    Two modes:
      - sigma given: l = x - k*sigma, m = x, u = x + k*sigma  (preferred when
        a real uncertainty estimate is available, e.g. rolling std).
      - else: symmetric percentage spread around x; for negative x the
        ordering still holds because TFN auto-sorts.

    Symmetric spread avoids the bug in the original ipynb where
    ``max(0, x*0.9)`` clipped negatives to zero and broke the l<=m<=u
    invariant.
    """
    if sigma is not None:
        return TFN(x - k * sigma, x, x + k * sigma)
    spread = abs(x) * spread_pct if x != 0 else spread_pct
    return TFN(x - spread, x, x + spread)
