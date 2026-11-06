"""Whether a run sheet can separate the factors it varies.

This module is new. It is not a port of anything in the JavaScript, and it is
not checked against it; it exists because running the ported ``run_sheet`` over a
full catalogue showed it producing a sheet that was perfectly balanced and
completely useless.

Balance, as ``run_sheet`` measures it, is per factor: every promoter appears
three times, every helper appears three times, spread zero. That is necessary
and it is not sufficient. On a 192-vector catalogue with twelve wells, the greedy
pick returned this:

    CMV   with pHelper-A and 1 copy, three times
    EF1a  with pHelper-B and 2 copies, three times
    CAG   with pHelper-C and 3 copies, three times
    SV40  with pHelper-D and 4 copies, three times

Each factor's marginal counts are flat, so every balance figure the sheet
reports is zero, and nothing in it is estimable: promoter, helper and copy number
move together, so a titre difference between the first three wells and the last
three could be any of the three causes or any combination of them. The term for
this is aliasing, and a sheet that is aliased cannot answer the question it was
built to answer however good its predictions were.

The cost function cannot see this, because it sums each factor's own count and a
sum of marginals is blind to how the levels pair up. Changing that rule would
change what the browser tool produces too, which is a decision for whoever owns
the tool rather than for a port. So this module measures the problem and names
it, which is the part that can be done without changing any answer.
"""

from .jsnum import js_string


def pair_table(sheet, a, b):
    """How often each (level of a, level of b) pair appears in the sheet."""
    counts = {}
    for row in sheet:
        key = (js_string(row["config"][a]), js_string(row["config"][b]))
        counts[key] = counts.get(key, 0) + 1
    return counts


def aliasing(sheet, axes):
    """Report, for every pair of factors, how badly the sheet confounds them.

    Returns one record per pair, worst first. ``determined`` is the plain-language
    verdict: when every level of one factor appears with exactly one level of the
    other, the two cannot be told apart at all. ``cells`` and ``possible`` say how
    much of the pair's grid the sheet visited, which is the gradual version of the
    same thing.
    """
    names = [a["name"] for a in axes]
    levels = {a["name"]: [js_string(v) for v in a["values"]] for a in axes}
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            counts = pair_table(sheet, a, b)
            partners_of_a, partners_of_b = {}, {}
            for (va, vb) in counts:
                partners_of_a.setdefault(va, set()).add(vb)
                partners_of_b.setdefault(vb, set()).add(va)
            a_determines_b = all(len(p) == 1 for p in partners_of_a.values())
            b_determines_a = all(len(p) == 1 for p in partners_of_b.values())
            possible = len(levels[a]) * len(levels[b])
            out.append({
                "factors": (a, b),
                "cells": len(counts),
                "possible": possible,
                "coverage": len(counts) / possible if possible else 0.0,
                "determined": a_determines_b or b_determines_a,
                # The largest and smallest count over the cells the sheet did
                # visit: a pair can cover its grid and still lean on one corner.
                "max_cell": max(counts.values()) if counts else 0,
                "min_cell": min(counts.values()) if counts else 0,
            })
    out.sort(key=lambda r: (not r["determined"], r["coverage"]))
    return out


def worst_case(report):
    """One line a reader can act on, or None when nothing is confounded."""
    if not report:
        return None
    aliased = [r for r in report if r["determined"]]
    if aliased:
        pairs = ", ".join("%s with %s" % r["factors"] for r in aliased)
        return ("This sheet cannot separate %s: each level of one appears with only one "
                "level of the other, so a difference in outcome could be either cause. "
                "Adding wells will not fix it; the combinations have to change."
                % pairs)
    thin = [r for r in report if r["coverage"] < 0.5]
    if thin:
        r = thin[0]
        return ("%s and %s are only seen in %d of their %d combinations, so their joint "
                "effect is mostly unmeasured." % (r["factors"][0], r["factors"][1],
                                                  r["cells"], r["possible"]))
    return None
