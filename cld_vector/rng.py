"""The seeded random number generator from engine.js, bit for bit.

Reproducibility is the point. ``candidates()`` samples a catalogue too large to
enumerate and ``runSheet()`` randomises run order, and both are asked to be
reproducible: the same catalogue and seed must give the same run sheet, in the
browser tool and in this port, so that a sheet printed from one can be checked
against the other.

That requires the same generator, not merely a generator with the same
distribution. The JavaScript is mulberry32, which is defined entirely in terms
of 32-bit integer arithmetic. Python integers do not wrap, so every step masks
explicitly, and ``Math.imul`` - a 32-bit signed multiply - is written out.
"""

_U32 = 0xFFFFFFFF


def _imul(a, b):
    """``Math.imul(a, b)``: multiply as 32-bit integers and keep the low 32 bits.

    ``Math.imul`` returns a *signed* 32-bit result, and the first version of this
    converted it. The conversion is unobservable here: multiplication modulo
    2**32 gives the same bit pattern whichever way the operands are read, and
    every use of the result in ``draw`` masks it back to 32 bits immediately. The
    conversion was dropped once a mutation that removed it could not be
    distinguished from the original over 48-element shuffles on eight seeds.
    """
    return (a * b) & _U32


def rng(seed):
    """``MLEngine.rng``: mulberry32 seeded with ``seed >>> 0``, zero becoming one.

    Returns a callable yielding floats in [0, 1).
    """
    state = [(int(seed) & _U32) or 1]

    def draw():
        # a = (a + 0x6D2B79F5) | 0. The `| 0` is a signed 32-bit truncation,
        # which is the same low 32 bits as the unsigned wrap kept here.
        state[0] = (state[0] + 0x6D2B79F5) & _U32
        au = state[0]
        t = _imul(au ^ (au >> 15), 1 | au) & _U32
        t = ((t + (_imul(t ^ (t >> 7), 61 | t) & _U32)) & _U32) ^ t
        return ((t ^ (t >> 14)) & _U32) / 4294967296.0

    return draw


def shuffle(arr, rand):
    """``MLEngine.shuffle``: Fisher-Yates downwards, in place, returning the list."""
    for i in range(len(arr) - 1, 0, -1):
        j = int(rand() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]
    return arr


def js_range(n):
    """``MLEngine.range``: [0, 1, ... n-1]."""
    return list(range(n))
