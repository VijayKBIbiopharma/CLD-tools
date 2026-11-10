"""JavaScript value semantics, implemented exactly.

This module exists for one reason: the Python port is checked against the
JavaScript original by running both over the same inputs and asserting the
answers are identical (``tests/test_oracle.py``). That check is only worth
having if the two implementations agree on the primitive operations too, and
JavaScript and Python disagree on several that this code depends on:

  * ``String(5.0)`` is ``"5"`` in JavaScript and ``"5.0"`` in Python. The port
    builds dictionary keys and identity signatures out of stringified numbers
    (``runSheet``'s balance counts, ``transferability``'s protein signatures),
    so a mismatch here silently splits one level into two.
  * ``String(1e16)`` is ``"10000000000000000"`` in JavaScript and ``"1e+16"``
    in Python; ``String(1e-5)`` is ``"0.00001"`` and ``"1e-05"``.
  * ``Number("")`` is ``0`` in JavaScript, a ValueError in Python.
  * ``(0.1+0.2).toFixed(6)`` rounds halves towards +infinity in JavaScript
    and to even in Python's ``format``.
  * ``\\d`` is ASCII-only in JavaScript regular expressions and matches Arabic,
    Devanagari and other digits in Python. A column of Devanagari numerals
    would profile as numeric in Python and categorical in JavaScript.
  * ``"".trim()`` strips ``\\ufeff`` in JavaScript and does not in Python.

Nothing here is clever. It is ECMA-262 transcribed, with the section numbers
noted, so that it can be read against the specification rather than trusted.
"""

import math
import re
from decimal import Decimal, ROUND_HALF_UP

# ECMA-262 WhiteSpace plus LineTerminator: what String.prototype.trim removes.
# Python's str.strip() removes a different set (it keeps ﻿ and strips
# \x1c-\x1f), so the set is written out rather than inherited.
JS_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d   "
    "           "
    "    　﻿"
)


def js_trim(s):
    """String.prototype.trim."""
    return s.strip(JS_WHITESPACE)


# ---------------------------------------------------------------- Number -> String

def js_string(value):
    """``String(value)`` for the values this port handles: None, bool, str, number.

    JavaScript has no integer type, so an integral float prints without a
    fractional part. Everything that keys a dictionary or joins a signature in
    the ported code goes through here.
    """
    if value is None:
        return ""          # the port never relies on String(null) == "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return _number_to_string(float(value))
    if isinstance(value, float):
        return _number_to_string(value)
    raise TypeError("js_string does not handle %r" % type(value))


def _number_to_string(x):
    """ECMA-262 6.1.6.1.20, Number::toString with radix 10.

    The specification is written in terms of three integers: ``s`` (the decimal
    digits, no trailing zeros), ``k`` (how many digits) and ``n`` (where the
    decimal point sits), such that ``x == s * 10**(n - k)`` and ``s`` is the
    shortest digit string that round-trips. Python's ``repr`` already produces a
    shortest round-tripping decimal, so the digits are taken from there and only
    the layout rules are implemented.
    """
    if x != x:
        return "NaN"
    if x == math.inf:
        return "Infinity"
    if x == -math.inf:
        return "-Infinity"
    if x == 0:
        return "0"                      # String(-0) is "0", not "-0"
    if x < 0:
        return "-" + _number_to_string(-x)

    digits, n = _shortest_decimal(x)
    k = len(digits)

    if k <= n <= 21:
        return digits + "0" * (n - k)   # step 5: 123 with n=5 -> "12300"
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]   # step 6
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits      # step 7
    # steps 8 and 9: exponential form, exponent is n-1
    exp = n - 1
    sign = "+" if exp >= 0 else "-"
    head = digits[0] if k == 1 else digits[0] + "." + digits[1:]
    return head + "e" + sign + str(abs(exp))


def _shortest_decimal(x):
    """Return (digit string with no trailing zeros, n) for a positive finite x."""
    text = repr(x)
    if "e" in text or "E" in text:
        mantissa, _, exponent = text.replace("E", "e").partition("e")
        exp10 = int(exponent)
    else:
        mantissa, exp10 = text, 0
    int_part, _, frac_part = mantissa.partition(".")
    significand = int(int_part + frac_part)
    exp10 -= len(frac_part)
    # x == significand * 10**exp10; strip trailing zeros so s has none.
    while significand % 10 == 0:
        significand //= 10
        exp10 += 1
    digits = str(significand)
    return digits, exp10 + len(digits)


# ---------------------------------------------------------------- String -> Number

_HEX = re.compile(r"\A0[xX][0-9a-fA-F]+\Z")
_OCT = re.compile(r"\A0[oO][0-7]+\Z")
_BIN = re.compile(r"\A0[bB][01]+\Z")
# StrDecimalLiteral (ECMA-262 7.1.4.1). ASCII digits only, by specification.
_DEC = re.compile(
    r"\A[+-]?(?:[0-9]+\.?[0-9]*(?:[eE][+-]?[0-9]+)?"
    r"|\.[0-9]+(?:[eE][+-]?[0-9]+)?)\Z"
)


def js_number(value):
    """``Number(value)``. Returns a float, or NaN - never raises.

    The cases that matter to this port and differ from ``float()``:
    ``Number("")`` and ``Number("   ")`` are 0, ``Number("0x1f")`` is 31,
    ``Number("1_000")`` is NaN (Python's ``float`` accepts underscores),
    ``Number("nan")`` is NaN but ``Number("Infinity")`` is infinite while
    ``float("inf")`` accepts the lowercase word JavaScript rejects.
    """
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = js_trim(str(value))
    if text == "":
        return 0.0
    if text in ("Infinity", "+Infinity"):
        return math.inf
    if text == "-Infinity":
        return -math.inf
    if _HEX.match(text):
        return float(int(text[2:], 16))
    if _OCT.match(text):
        return float(int(text[2:], 8))
    if _BIN.match(text):
        return float(int(text[2:], 2))
    if _DEC.match(text):
        try:
            return float(text)
        except (ValueError, OverflowError):     # pragma: no cover - unreachable
            return math.nan
    return math.nan


def js_is_finite(value):
    """``isFinite(value)``: coerces with Number() first, unlike Number.isFinite."""
    x = js_number(value)
    return x == x and x not in (math.inf, -math.inf)


def to_fixed(x, digits):
    """``Number.prototype.toFixed``.

    ECMA-262 step 5 takes the sign off first - ``if x < 0, set s to "-" and x to
    -x`` - and only then step 7 picks the integer ``n`` for which
    ``n / 10**f - x`` is closest to zero, *taking the larger n when two are
    equally close*. Because the sign is already gone, "larger" means further from
    zero: ``(-0.5).toFixed(0)`` is ``"-1"``, not ``"-0"``. So this is round half
    away from zero for both signs, which is ``ROUND_HALF_UP`` in Decimal's
    vocabulary.

    This was wrong in the first version of this function, which read "larger n"
    as "towards +infinity" and rounded negative halves towards zero. The
    mutation sweep in ``tests/`` caught it: the test suite at the time contained
    no negative value sitting exactly on a rounding boundary, so both the right
    and the wrong rule passed.

    Python's ``format(x, '.6f')`` rounds halves to even, which is a third answer
    again. The comparison is made on the exact binary value of the double, which
    is what ``Decimal(float)`` gives.
    """
    if x != x:
        return "NaN"
    if x in (math.inf, -math.inf):
        return "Infinity" if x > 0 else "-Infinity"
    if abs(x) >= 1e21:
        return _number_to_string(x)
    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(x).quantize(quantum, rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------- key ordering

_ARRAY_INDEX = re.compile(r"\A(?:0|[1-9][0-9]*)\Z")
_MAX_INDEX = 2 ** 32 - 1


def js_object_keys(mapping):
    """``Object.keys`` ordering for a plain object.

    JavaScript enumerates integer-like keys first, in ascending numeric order,
    and only then the remaining keys in insertion order. Python dictionaries are
    insertion-ordered throughout. The ported code sorts level names by frequency
    with ties broken by this order, so a column whose levels are the strings
    "10", "2" and "Ctrl" enumerates as 2, 10, Ctrl in JavaScript and as whatever
    order the file happened to use in Python.
    """
    indices, rest = [], []
    for k in mapping:
        if _ARRAY_INDEX.match(k) and int(k) < _MAX_INDEX:
            indices.append(k)
        else:
            rest.append(k)
    indices.sort(key=int)
    return indices + rest


def js_compare_strings(a, b):
    """``a < b`` for strings, as the ``<`` operator defines it.

    JavaScript compares UTF-16 code units; Python compares code points. They
    disagree only above U+FFFF, where a Python comparison orders an astral
    character after U+E000-U+FFFF and JavaScript orders it before. Encoding to
    UTF-16 big-endian reproduces the JavaScript order exactly.
    """
    ea, eb = a.encode("utf-16-be", "surrogatepass"), b.encode("utf-16-be", "surrogatepass")
    if ea < eb:
        return -1
    return 1 if ea > eb else 0
