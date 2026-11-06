"""Column profiling, ported from engine.js.

Profiling is where a column acquires the identity everything downstream relies
on: numeric, categorical, constant, id, text or empty. ``program.py`` reads
``kind`` in four places and treats a constant column quite differently from a
varying one, so a column that profiles differently here than in the browser
would change the answer rather than the presentation.

Two rules in here are worth reading twice because they are easy to get subtly
wrong in Python:

  * A column is numeric when at least 95% of its *present* values parse as
    numbers - not 95% of its rows. A sheet that is half blank and half numbers
    is numeric.
  * ``\\d`` in the JavaScript source is ASCII-only. The regular expressions here
    spell out ``[0-9]`` so that a column of Devanagari numerals profiles as
    categorical in both implementations.
"""

import functools
import re

from .jsnum import js_compare_strings, js_number, js_object_keys, js_string, js_trim
from .stats import mean, quantile, sd

MISSING = {"", "na", "n/a", "nan", "null", "none", "-", "?", "#n/a", "missing"}

ID_NAME = re.compile(
    r"^(id|row|index|\#|obs|observation|s/?n|serial|run ?order|std ?order|order"
    r"|sample ?id|record ?id|uuid|guid)$|[ _-]id$",
    re.IGNORECASE,
)

# /^-?[\d,]+(\.\d+)?%?$/ with \d pinned to ASCII, as JavaScript defines it.
_NUMERIC_SHAPE = re.compile(r"^-?[0-9,]+(\.[0-9]+)?%?$")

HIGH_CARD = 12
TARGET_PRIOR = 10


def is_missing(value):
    if value is None:
        return True
    return js_trim(str(value)).lower() in MISSING


def to_number(value):
    """``MLEngine.toNumber``: thousands separators and a trailing percent sign
    are stripped, and the percent is *not* divided by 100 - a column of "93%"
    profiles as 93, which is what the rest of the tool expects."""
    if is_missing(value):
        return None
    text = js_trim(str(value))
    if _NUMERIC_SHAPE.match(text):
        text = text.replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    if text == "":
        return None
    v = js_number(text)
    return v if (v == v and abs(v) != float("inf")) else None


def profile_column(name, raw, index):
    n = len(raw)
    missing = 0
    nums = [None] * n
    numeric_ok = 0
    for i in range(n):
        if is_missing(raw[i]):
            missing += 1
            continue
        v = to_number(raw[i])
        nums[i] = v
        if v is not None:
            numeric_ok += 1
    present = n - missing
    col = {"name": name, "index": index, "n": n, "missing": missing, "kind": "categorical"}
    if present == 0:
        col["kind"] = "empty"
        col["values"] = [None] * n
        col["unique"] = 0
        return col

    if numeric_ok / present >= 0.95:
        col["kind"] = "numeric"
        col["values"] = nums
        col["missing"] = sum(1 for v in nums if v is None)
        vals = [v for v in nums if v is not None]
        ordered = sorted(vals)
        levels = list(dict.fromkeys(ordered))   # Set insertion order over the sorted list
        col["unique"] = len(levels)
        col["levels"] = levels if len(levels) <= HIGH_CARD else None
        col["stats"] = {
            "mean": mean(vals), "sd": sd(vals), "min": ordered[0], "max": ordered[-1],
            "median": quantile(ordered, 0.5), "q1": quantile(ordered, 0.25),
            "q3": quantile(ordered, 0.75), "p10": quantile(ordered, 0.1),
            "p90": quantile(ordered, 0.9),
        }
        # A column that counts 1, 2, 3, ... is a row number however it is named.
        sequential = len(vals) > 5
        i = 1
        while i < len(nums) and sequential:
            if nums[i] is None or nums[i] - nums[i - 1] != 1:
                sequential = False
            i += 1
        if col["unique"] <= 1:
            col["kind"] = "constant"
        elif ID_NAME.search(js_trim(name)) or sequential:
            col["kind"] = "id"
    else:
        col["values"] = [None if is_missing(s) else js_trim(str(s)) for s in raw]
        counts = {}
        for v in col["values"]:
            if v is not None:
                counts[v] = counts.get(v, 0) + 1
        # Commonest first, ties by string order. The comparator is the JavaScript
        # one: Array.prototype.sort is stable, and the tie-break returns 1 for
        # equal strings, so it never reorders identical keys.
        keys = js_object_keys(counts)
        levels = sorted(
            keys,
            key=functools.cmp_to_key(
                lambda a, b: (counts[b] - counts[a]) or js_compare_strings(a, b)
            ),
        )
        col["unique"] = len(levels)
        col["counts"] = counts
        col["levels"] = levels
        if col["unique"] <= 1:
            col["kind"] = "constant"
        elif ID_NAME.search(js_trim(name)) or (col["unique"] == present and present > 20):
            col["kind"] = "id"
        elif col["unique"] > 50 and col["unique"] > 0.5 * present:
            col["kind"] = "text"
    return col


def profile(table):
    columns = [
        profile_column(name, [r[j] for r in table["rows"]], j)
        for j, name in enumerate(table["columns"])
    ]
    return {"nRows": len(table["rows"]), "nCols": len(columns), "columns": columns}


def column_value_as_text(col, i):
    """``norm(col.values[i])`` - the string a profiled cell contributes to a
    signature or a dictionary key. Numeric columns hold floats, and an integral
    float must print as "5" and not "5.0" for the two implementations to agree
    on what counts as the same protein."""
    return js_trim(js_string(col["values"][i]))
