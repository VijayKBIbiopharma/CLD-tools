"""The handful of statistics this port needs, matching engine.js.

``quantile`` is the only one with a choice in it, and the choice matters: this
is linear interpolation between order statistics on a list already sorted
ascending (type 7 in the Hyndman-Fan scheme, numpy's default). It is written out
rather than taken from numpy so that the port has one fewer dependency to
qualify, and so that it is visibly the same three lines as the JavaScript.
"""

import math


def mean(values):
    total = 0.0
    for v in values:
        total += v
    return total / len(values) if values else math.nan


def variance(values):
    if len(values) < 2:
        return 0.0
    m = mean(values)
    total = 0.0
    for v in values:
        total += (v - m) * (v - m)
    return total / (len(values) - 1)


def sd(values):
    return math.sqrt(variance(values))


def quantile(sorted_values, q):
    """``MLEngine.quantile``. The argument must already be sorted ascending;
    the JavaScript does not sort it either, and callers that need sorting do it
    themselves."""
    if not sorted_values:
        return math.nan
    pos = (len(sorted_values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)
