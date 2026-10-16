"""Summary statistics: percentile bootstrap confidence intervals, median, p95."""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from typing import Any

BOOTSTRAP_SAMPLES = 2000
BOOTSTRAP_SEED = 20261013


def mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("mean of an empty sequence")
    return sum(values) / len(values)


def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (numpy's default method), q in [0, 100]."""
    if not values:
        raise ValueError("percentile of an empty sequence")
    if not 0 <= q <= 100:
        raise ValueError("q must be within [0, 100]")
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def bootstrap_ci[T](
    values: Sequence[T],
    *,
    stat: Callable[[Sequence[T]], float] = mean,  # type: ignore[assignment]
    samples: int = BOOTSTRAP_SAMPLES,
    level: float = 0.95,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    """Percentile bootstrap interval of `stat` over documents (resampling documents with replacement)."""
    if not values:
        raise ValueError("bootstrap of an empty sequence")
    if len(values) == 1:
        v = stat(values)
        return v, v
    rng = random.Random(seed)
    n = len(values)
    boots = [stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(samples)]
    alpha = (1 - level) / 2 * 100
    return percentile(boots, alpha), percentile(boots, 100 - alpha)


def paired_diff_ci(a: Sequence[float], b: Sequence[float], **kw: Any) -> tuple[float, tuple[float, float]]:
    """Mean of a[i] - b[i] over the same documents, with its bootstrap interval."""
    if len(a) != len(b):
        raise ValueError("paired samples differ in length")
    diffs = [x - y for x, y in zip(a, b, strict=True)]
    return mean(diffs), bootstrap_ci(diffs, **kw)


def intervals_overlap(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]
