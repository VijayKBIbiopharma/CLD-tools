"""The Python port against the JavaScript it was ported from.

Every test in this file works the same way: build an input, ask the JavaScript
for the answer by running ``oracle.js`` under node, ask the Python for the answer,
and require the two to be identical. Nothing here asserts a hand-written expected
value, because a hand-written expected value is a third opinion and the question
is whether the port agrees with the original.

Comparison is on canonical JSON. ``JSON.stringify`` writes an integral number
without a fractional part and a non-finite number as ``null``; ``canon`` puts the
Python answer in the same form, so ``3`` and ``3.0`` compare equal and a NaN on
one side cannot pass for a NaN on the other by accident.

If node is not installed the oracle tests skip rather than fail: they are a
cross-check, and a machine without node can still run the port. The skip is loud.
"""

import json
import math
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from cld_vector import program, table                                    # noqa: E402
from cld_vector.profile import profile as profile_of                    # noqa: E402
import fixtures                                                        # noqa: E402

ORACLE = os.path.join(HERE, "oracle.js")
NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed; the oracle cannot run")

MAX_SAFE = 2 ** 53


def canon(value):
    """Put a Python answer into the form ``JSON.stringify`` would have written."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        if value != value or value in (math.inf, -math.inf):
            return None
        if value == int(value) and abs(value) < MAX_SAFE:
            return int(value)
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, dict):
        return {k: canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [canon(v) for v in value]
    return value


def ask_js(calls):
    """Run the JavaScript over a list of {fn, args} and return its answers."""
    proc = subprocess.run(
        [NODE, ORACLE], input=json.dumps(calls), capture_output=True, text=True, timeout=180
    )
    if proc.returncode != 0:
        raise AssertionError("oracle.js failed: %s" % (proc.stderr.strip() or proc.returncode))
    return json.loads(proc.stdout)


def agree(calls, answers, labels):
    """Assert the JavaScript and the Python gave the same answer to each call."""
    js = ask_js(calls)
    assert len(js) == len(answers) == len(labels)
    for i, label in enumerate(labels):
        if "error" in js[i]:
            assert isinstance(answers[i], Exception), (
                "%s: the JavaScript refused (%s) and the Python did not"
                % (label, js[i]["error"]))
            assert str(answers[i]) == js[i]["error"], (
                "%s: both refused but with different words\n  js: %s\n  py: %s"
                % (label, js[i]["error"], answers[i]))
            continue
        assert not isinstance(answers[i], Exception), (
            "%s: the Python refused (%s) and the JavaScript did not" % (label, answers[i]))
        want, got = js[i]["value"], canon(answers[i])
        assert got == want, (
            "%s disagrees.\n  js: %s\n  py: %s"
            % (label, json.dumps(want, sort_keys=True)[:1400],
               json.dumps(got, sort_keys=True)[:1400]))


def attempt(fn, *args, **kwargs):
    """Call and return the answer, or the exception, so a refusal can be compared."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:                       # noqa: BLE001 - comparing refusals
        return exc


# --------------------------------------------------------------- the primitives

@needs_node
def test_js_string_matches():
    """``String(x)`` over the shapes a profiled value can take.

    A disagreement here would not announce itself: it would split one factor
    level into two in a run sheet's balance counts, or make one protein look like
    two in a transferability signature.
    """
    from cld_vector.jsnum import js_string
    values = [
        0, -0.0, 1, 5, 100, 148.0, 3.2, 0.1, 1 / 3, 2 / 3, 1e-5, 1e-6, 1e-7, 1.5e-7,
        1e15, 1e16, 1e20, 1e21, 1e22, 5e-324, 1.7976931348623157e308,
        1234567890123456.0, 123456789012345678901.0, -2.5, -0.000001, 9.95, 0.07,
        2.675, 1.005, 37.0, 6.8, 0.5, 1.25, 99.99999999999999,
    ]
    js = ask_js([{"fn": "jsString", "args": [values]}])[0]["value"]
    assert [js_string(float(v)) for v in values] == js


@needs_node
def test_js_number_matches():
    """``Number(text)`` over what a cell can hold. ``float()`` disagrees on at
    least six of these."""
    from cld_vector.jsnum import js_number
    texts = [
        "", "   ", "0", "5", "-5", "5.5", ".5", "5.", "1e3", "1E3", "1e-3", "+1",
        "0x1f", "0X1F", "0o17", "0b101", "1_000", "Infinity", "-Infinity", "+Infinity",
        "inf", "nan", "NaN", "abc", "1,200", "93%", "  12  ", "12\t", "\u00a012",
        "1.", "--1", "1e", "1e+", "0.0000001", "1e400", "-0",
    ]
    js = ask_js([{"fn": "jsNumber", "args": [texts]}])[0]["value"]
    got = []
    for t in texts:
        n = js_number(t)
        got.append(n if (n == n and abs(n) != float("inf")) else ("NaN" if n != n else ("Infinity" if n > 0 else "-Infinity")))
    assert canon(got) == js


@needs_node
def test_to_fixed_matches():
    """``toFixed(6)`` over values that sit on or near a rounding boundary.

    ``candidates()`` runs every numeric catalogue level through this, so the
    rounding rule decides which levels exist. JavaScript rounds a half towards
    +infinity and Python's ``format`` rounds to even.
    """
    from cld_vector.jsnum import to_fixed
    values = [# Exact halves: representable in binary, so the rounding rule decides.
              0.5, -0.5, 1.5, -1.5, 2.5, -2.5, 3.5, -3.5, 0.125, -0.125, 0.375, -0.375,
              0.0625, 1.0625, -1.0625, 0.005, 2.675, 1.005,
              0.1 + 0.2, 1 / 3, 2 / 3, 1.0000005, -1.0000005, 0.0000005, -0.0000005,
              0.0000015, 0.0000025, 1.5e-6, 2.5e-6, 8.333333333333334, 37.0, -37.0,
              1.9999995, 0.1, 0.7, 1.1 * 3, 1e-9, -1e-9, 123.4567895, 0.0]
    for digits in (0, 1, 2, 3, 6):
        js = ask_js([{"fn": "toFixed", "args": [values, digits]}])[0]["value"]
        assert [to_fixed(v, digits) for v in values] == js, "toFixed(%d)" % digits


@needs_node
def test_object_key_order_matches():
    """``Object.keys`` puts integer-like keys first, ascending. Python keeps
    insertion order. Level frequency ties break on this order."""
    from cld_vector.jsnum import js_object_keys
    cases = [
        [["10", 1], ["2", 1], ["Ctrl", 1], ["abc", 1]],
        [["b", 1], ["a", 1], ["0", 1]],
        [["1", 1], ["01", 1], ["-1", 1], ["1.0", 1], ["4294967295", 1], ["4294967294", 1]],
        [["CMV", 3], ["EF1a", 3], ["CAG", 2]],
    ]
    js = ask_js([{"fn": "objectKeys", "args": [c]} for c in cases])
    for i, case in enumerate(cases):
        mapping = {}
        for k, v in case:
            mapping[k] = v
        assert js_object_keys(mapping) == js[i]["value"], "case %d" % i


@needs_node
def test_rng_matches():
    """The seeded generator, bit for bit.

    Everything reproducible in this package rests on this: ``candidates()``
    samples a catalogue too large to enumerate and ``run_sheet()`` randomises run
    order, and a sheet printed from the browser tool must be checkable against a
    sheet printed from here. Seed zero is included because ``rng`` maps it to one
    and the callers above never pass it.
    """
    from cld_vector.rng import rng, shuffle, js_range
    seeds = [0, 1, 2, 13, 29, 42, 99, 12345, 2 ** 31 - 1, 2 ** 31, 2 ** 32 - 1]
    calls = [{"fn": "rngDraws", "args": [s, 24]} for s in seeds]
    answers = []
    for s in seeds:
        draw = rng(s)
        answers.append([draw() for _ in range(24)])
    agree(calls, answers, ["rng(%d)" % s for s in seeds])

    sizes = [0, 1, 2, 3, 12, 36, 48, 101]
    calls = [{"fn": "shuffled", "args": [n, 29]} for n in sizes]
    answers = [shuffle(js_range(n), rng(29)) for n in sizes]
    agree(calls, answers, ["shuffle(%d)" % n for n in sizes])


@needs_node
def test_js_trim_matches():
    """``trim`` removes the byte-order mark and keeps the ASCII file separators;
    Python's ``strip`` does the opposite. Both appear in real exports: the mark
    from Excel, the separators from mainframe extracts."""
    from cld_vector.jsnum import js_trim
    values = [" CMV ", "\ufeffCMV\ufeff", "\x1cCMV\x1c", "\u00a0CMV\u00a0",
              "\u3000CMV\u3000", "\u2028CMV\u2029", "\tCMV\n", "\x0bCMV\x0c",
              "CMV", "", "   ", "\u200bCMV\u200b"]
    js = ask_js([{"fn": "jsTrim", "args": [values]}])[0]["value"]
    assert [js_trim(v) for v in values] == js


# ------------------------------------------------------------------ the readers

@needs_node
def test_parse_table_matches():
    texts = [
        "A,B,C\n1,2,3\n4,5,6\n",
        "A\tB\n1\t2\n",
        "A;B;C\n1;2;3\n",
        "A|B\n1|2\n",
        'Name,Note\n"Smith, J.","said ""fine"""\n',
        "A,B\n1\n2,3,4\n",                                  # short and long rows
        "A,A,A\n1,2,3\n",                                   # repeated headers
        ",B,\n1,2,3\n",                                     # nameless columns
        "A,B\n\n\n1,2\n",                                   # blank lines
        "﻿A,B\n1,2\n",                                 # Excel's byte-order mark
        "A,B\r\n1,2\r\n",                                   # Windows line endings
        "A,B\n1,2",                                         # no trailing newline
        'A,B\nab"cd,2\n',                                   # a quote mid-field is data
        "A,B\n\ufeffx\ufeff,\x1cy\x1c\n",                            # trim keeps one, strip the other
        "A\ufeff,\x1cB\n1,2\n",                                    # and in the header row
        "A,B\n\u00a0x\u00a0,\u3000y\u3000\n",                           # non-breaking and ideographic space
        "Titer,Titer,Titer,Titer\n1,2,3,4\n",               # the duplicate-name rule
        "",
    ]
    calls = [{"fn": "parseTable", "args": [t, None]} for t in texts]
    answers = [attempt(table.parse_csv, t) for t in texts]
    agree(calls, answers, ["parse_table %d" % i for i in range(len(texts))])


@needs_node
def test_profile_matches():
    texts = [
        fixtures.history_csv(),
        fixtures.history_csv(n_runs=12, n_proteins=1),
        "A,B,C,D,E\n1,x,,3.5,2\n2,y,,4.5,2\n3,x,,,2\n",     # id, categorical, empty, numeric, constant
        "Pct,Thousands\n93%,\"1,200\"\n88%,\"2,400\"\n71%,\"900\"\n",
        "Mixed\n1\n2\nthree\n4\n5\n6\n7\n8\n9\n10\n",       # 90% numeric is not numeric
        "Mixed\n1\n2\n3\n4\n5\n6\n7\n8\n9\n10\n11\n12\n13\n14\n15\n16\n17\n18\n19\nx\n",
        "Blank\nNA\nn/a\n-\n?\n#N/A\nmissing\nnull\nnone\n",
        # parse_grid trims with JavaScript's rules, which keep the ASCII file
        # separators, so these reach is_missing and to_number still wrapped.
        "Marker,Number\n\x1cNA\x1c,\x1c5\x1c\n\x1c-\x1c,\x1c6\x1c\n\x1cok\x1c,\x1c7\x1c\n",
        "Marker\n\x1cNA\x1c\nreal\n\x1cnull\x1c\n",
        "Seq\n1\n2\n3\n4\n5\n6\n7\n",                       # a row counter, however named
        "Devanagari\n१\n२\n३\n४\n५\n६\n",
        "Neg,Sci\n-1.5,1e3\n-2.5,2e3\n-3.5,3e-2\n",
    ]
    calls = [{"fn": "profile", "args": [t]} for t in texts]
    answers = [attempt(lambda t=t: profile_of(table.parse_csv(t))) for t in texts]
    agree(calls, answers, ["profile %d" % i for i in range(len(texts))])


# --------------------------------------------------------------- the catalogue

@needs_node
def test_parse_catalogue_matches():
    texts = [
        fixtures.CATALOGUE_WIDE,
        fixtures.CATALOGUE_LONG,
        fixtures.CATALOGUE_AWKWARD,
        fixtures.CATALOGUE_NO_FACTOR_COLUMN,
        fixtures.CATALOGUE_EMPTY,
        "factor,levels\nPromoter,CMV;EF1a\n",                    # lower-case headers
        "Parameter,Options,Minimum,Maximum,Increment\nTemp,,31,37,2\n",
        "Factor,Levels\nPromoter,CMV\nPromoter,CMV\n",           # a level repeated
        "Factor,Levels,Min,Max\nBoth,CMV;EF1a,1,4\n",            # levels win over a range
        "Factor,Min,Max,Step\nTiny,1,1.0000005,0.0000001\n",     # a step that needs rounding
        "Factor,Min,Max,Step\nMany,0,100,1\n",                   # 101 levels: too many to use
    ]
    calls = [{"fn": "parseCatalogue", "args": [t]} for t in texts]
    answers = [attempt(lambda t=t: program.parse_catalogue(table.parse_csv(t))) for t in texts]
    agree(calls, answers, ["parse_catalogue %d" % i for i in range(len(texts))])


@needs_node
def test_parse_program_matches():
    factors = ["Promoter", "Marker", "Helper", "Copies"]
    cases = [
        (fixtures.PROGRAMS_CSV, factors),
        (fixtures.PROGRAMS_NO_ID, factors),
        (fixtures.PROGRAMS_CSV, []),
        (fixtures.PROGRAMS_CSV, ["promoter"]),                   # loose name matching
        ("Construct,Thing\n,x\nC2,y\n", []),                     # a blank id gets numbered
        ("Program_ID,Notes,Operator,Date,Site\nP1,a,b,c,d\n", []),
        # Notes matches the skip list but not the pick list. If the id search
        # used the skip list it would name programmes after their notes.
        ("Notes,Program_ID,ProteinClass\nrush,PRG-9,mAb\n", []),
        ("Date,Operator,Clone,ProteinClass\n2026-01-01,AB,C9,mAb\n", []),
        ("", factors),
    ]
    calls = [{"fn": "parseProgram", "args": [t, f]} for t, f in cases]
    answers = [attempt(lambda t=t, f=f: program.parse_program(table.parse_csv(t), f))
               for t, f in cases]
    agree(calls, answers, ["parse_program %d" % i for i in range(len(cases))])


# -------------------------------------------------------- protein attributes

@needs_node
def test_protein_columns_and_choices_match():
    hist = fixtures.history_csv()
    factors = ["Promoter", "Marker", "Helper", "Copies"]
    targets = ["Titer_g_L", "Viability_pct"]
    prof = profile_of(table.parse_csv(hist))

    calls = [{"fn": "proteinColumns", "args": [hist, factors, targets]},
             {"fn": "proteinColumns", "args": [hist, [], []]},
             {"fn": "proteinColumns", "args": [hist, factors, []]}]
    answers = [program.protein_columns(prof, factors, targets),
               program.protein_columns(prof, [], []),
               program.protein_columns(prof, factors, [])]
    agree(calls, answers, ["protein_columns full", "protein_columns none", "protein_columns no targets"])

    names = [c["name"] for c in prof["columns"]] + ["Nonexistent"]
    calls = [{"fn": "attributeChoices", "args": [hist, n]} for n in names]
    answers = [attempt(program.attribute_choices, prof, n) for n in names]
    agree(calls, answers, ["attribute_choices %s" % n for n in names])


@needs_node
def test_transferability_matches():
    factors = ["Promoter", "Marker", "Helper", "Copies"]
    targets = ["Titer_g_L", "Viability_pct"]
    cases = [
        # The ordinary case: five proteins in the history, four programmes, one
        # of them a modality never run and one far outside the weight range.
        (fixtures.history_csv(), fixtures.PROGRAMS_CSV),
        # One protein in the history: the flat refusal.
        (fixtures.history_csv(n_runs=20, n_proteins=1), fixtures.PROGRAMS_CSV),
        # Two proteins: supported arithmetic, "thin" standing.
        (fixtures.history_csv(n_runs=30, n_proteins=2), fixtures.PROGRAMS_CSV),
        # No programmes at all.
        (fixtures.history_csv(), None),
        # Three proteins and a programme that matches one of them: the only
        # input that distinguishes "thin" at two proteins from "thin" at three.
        (fixtures.history_csv(n_runs=36, n_proteins=3),
         "Program_ID,ProteinClass,MW_kDa,pI\nP,mAb,148,8.2\n"),
        (fixtures.history_csv(n_runs=36, n_proteins=4),
         "Program_ID,ProteinClass,MW_kDa,pI\nP,mAb,148,8.2\n"),
        # A protein column that holds one value and some blanks. It profiles as
        # constant, so no attribute varies, but the blanks make two distinct
        # protein signatures - which is the one input where canTransfer's
        # varying-attribute test is not implied by the protein count.
        ("Run_ID,ProteinClass,Promoter,Titer_g_L\n"
         "R1,mAb,CMV,2.1\nR2,,EF1a,2.4\nR3,mAb,CAG,2.9\nR4,,SV40,2.2\n",
         "Program_ID,ProteinClass\nP,mAb\n"),
        # A programme that matches the history exactly.
        (fixtures.history_csv(), "Program_ID,ProteinClass,MW_kDa,pI\nP,mAb,148,8.2\n"),
        # A protein attribute held constant across the whole history.
        ("Run_ID,ProteinClass,MW_kDa,Promoter,Titer_g_L\n"
         "R1,mAb,148,CMV,2.1\nR2,mAb,148,EF1a,2.4\nR3,mAb,148,CAG,2.9\n",
         "Program_ID,ProteinClass,MW_kDa\nP,bispecific,104\n"),
        # An attribute the history does not have at all.
        (fixtures.history_csv(), "Program_ID,Glycoform\nP,afucosylated\n"),
    ]
    calls = [{"fn": "transferability", "args": [h, factors, targets, p]} for h, p in cases]
    answers = []
    for h, p in cases:
        prof = profile_of(table.parse_csv(h))
        cols = program.protein_columns(prof, factors, targets)
        programs = [] if p is None else program.parse_program(table.parse_csv(p), factors)["programs"]
        answers.append(attempt(program.transferability, prof, cols, programs))
    agree(calls, answers, ["transferability %d" % i for i in range(len(cases))])


# ------------------------------------------------------------------ enumeration

@needs_node
def test_candidates_matches():
    cases = [
        (fixtures.CATALOGUE_WIDE, {}),
        (fixtures.CATALOGUE_WIDE, {"cap": 20}),               # forces the sampling branch
        (fixtures.CATALOGUE_WIDE, {"cap": 20, "seed": 99}),
        (fixtures.CATALOGUE_WIDE, {"cap": 1}),
        (fixtures.CATALOGUE_LONG, {}),
        (fixtures.CATALOGUE_AWKWARD, {}),                     # fixed plus a step-less range
        (fixtures.CATALOGUE_EMPTY, {}),
        ("Factor,Levels\nOnly,A\n", {}),                      # everything fixed: no axes
        ("Factor,Min,Max,Step\nF,1,4,0.5\n", {}),             # seven steps
        ("Factor,Min,Max,Step\nF,0,100,1\n", {}),             # 101 steps, so three settings
        ("Factor,Min,Max,Step\nF,1,2,0.1\n", {}),             # steps that do not land exactly
        # 15,625 combinations: enumerated under the default cap, sampled under a
        # lower one. Without this pair the value of the cap is never checked.
        ("Factor,Min,Max,Step\nF,0,15,1\n", {}),               # 16 steps: inside the guard
        ("Factor,Min,Max,Step\nF,0,12,1\n", {}),               # 13 steps: just inside
        ("Factor,Min,Max,Step\nF,0,11,1\n", {}),               # 12 steps: just outside
        ("Factor,Min,Max,Step\nF,0,19,1\n", {}),               # 20 steps
        (fixtures.CATALOGUE_BIG, {}),
        (fixtures.CATALOGUE_BIG, {"cap": 2000}),
        (fixtures.CATALOGUE_BIG, {"cap": 15625}),
        (fixtures.CATALOGUE_BIG, {"cap": 15624}),
    ]
    calls = [{"fn": "candidates", "args": [t, o]} for t, o in cases]
    answers = []
    for t, o in cases:
        factors = program.parse_catalogue(table.parse_csv(t))["factors"]
        answers.append(attempt(program.candidates, factors, o))
    agree(calls, answers, ["candidates %d" % i for i in range(len(cases))])


@needs_node
def test_level_coverage_matches():
    hist = fixtures.history_csv()
    # pHelper-D is in the catalogue and has never been run; with a smoothing
    # prior in the encoding, thinly-run levels are reported too.
    encs = [None, {"parts": []},
            {"parts": [{"col": {"name": "Helper"}, "type": "high"},
                       {"col": {"name": "Promoter"}, "type": "onehot"}]}]
    cases = [(hist, fixtures.CATALOGUE_WIDE, e) for e in encs]
    cases.append((fixtures.history_csv(n_runs=14), fixtures.CATALOGUE_WIDE, encs[2]))
    cases.append((hist, fixtures.CATALOGUE_AWKWARD, None))
    # Shrink is prior / (runs + prior) with a prior of 10, so a level with 10 to
    # 14 runs lands between 0.4 and 0.5 - either side of THIN_SHRINK. Histories
    # of 36 and 60 runs put a helper on each side of the line.
    for n in (24, 36, 48, 60, 90):
        cases.append((fixtures.history_csv(n_runs=n), fixtures.CATALOGUE_WIDE, encs[2]))
    calls = [{"fn": "levelCoverage", "args": [h, c, e]} for h, c, e in cases]
    answers = []
    for h, c, e in cases:
        prof = profile_of(table.parse_csv(h))
        factors = program.parse_catalogue(table.parse_csv(c))["factors"]
        answers.append(attempt(program.level_coverage, prof, factors, e))
    agree(calls, answers, ["level_coverage %d" % i for i in range(len(cases))])


# -------------------------------------------------------------------- run sheet

@needs_node
def test_replicates_for_matches():
    values = [None, -1, 0, 0.1, 0.2024, 0.2025, 0.2026, 0.48, 0.49, 0.5, 0.7, 0.99, 1, 1.5]
    calls = [{"fn": "replicatesFor", "args": [v]} for v in values]
    answers = [program.replicates_for(v) for v in values]
    agree(calls, answers, ["replicates_for %s" % v for v in values])


@needs_node
def test_run_sheet_matches():
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})
    axes, configs = cand["axes"], cand["list"]
    scored = fixtures.scored_fixture(configs)
    small = fixtures.scored_fixture(configs[:6], seed=5)

    cases = [
        (scored, axes, {"runs": 12, "seed": 29}),
        (scored, axes, {"runs": 12, "seed": 29, "purpose": "select", "replicates": 3}),
        (scored, axes, {"runs": 48, "seed": 29, "purpose": "select", "replicates": 6}),
        (scored, axes, {"runs": 50, "seed": 29, "purpose": "select", "replicates": 6}),
        (small, axes, {"runs": 48, "seed": 29}),            # sheet longer than the catalogue
        (small, axes, {"runs": 48, "seed": 29, "purpose": "select", "replicates": 4}),
        (scored, axes, {}),                                  # the defaults
        (scored, axes, {"runs": 1}),                         # clamped to two
        ([], axes, {"runs": 12}),                            # nothing scored
        (small, axes, {"runs": 3, "purpose": "select", "replicates": 10}),
        (scored, axes, {"runs": 12, "purpose": "select", "replicates": 1}),
        (scored, axes, {"runs": 12, "purpose": "select", "replicates": 0}),
        (scored, axes, {"runs": 12, "purpose": "select"}),
    ]
    calls = [{"fn": "runSheet", "args": [s, a, o]} for s, a, o in cases]
    answers = [attempt(program.run_sheet, s, a, o) for s, a, o in cases]
    agree(calls, answers, ["run_sheet %d" % i for i in range(len(cases))])


# ------------------------------------------------- claims the port makes itself

def test_run_sheet_balance_is_what_it_claims():
    """The docstring says balance comes first. This measures it rather than
    repeating it: on a full catalogue, a screening sheet of twelve runs should
    use every promoter level about equally."""
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})
    scored = fixtures.scored_fixture(cand["list"])
    out = program.run_sheet(scored, cand["axes"], {"runs": 12, "seed": 29})
    assert len(out["sheet"]) == 12
    assert out["distinct"] == 12 and out["replicated"] == 0
    for name, info in out["balance"].items():
        assert info["spread"] <= 1, "%s is unbalanced: %s" % (name, info["counts"])


def test_sheet_longer_than_catalogue_replicates_and_says_so():
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})
    scored = fixtures.scored_fixture(cand["list"][:6], seed=5)
    out = program.run_sheet(scored, cand["axes"], {"runs": 48, "seed": 29})
    assert len(out["sheet"]) == 48
    assert out["distinct"] == 6, "six candidates should give six distinct vectors"
    assert out["replicated"] == 42
    assert max(r["replicate"] for r in out["sheet"]) == 8


def test_one_protein_history_refuses_to_transfer():
    hist = fixtures.history_csv(n_runs=20, n_proteins=1)
    prof = profile_of(table.parse_csv(hist))
    cols = program.protein_columns(prof, ["Promoter", "Marker", "Helper", "Copies"],
                                   ["Titer_g_L", "Viability_pct"])
    out = program.transferability(prof, cols, [])
    assert out["nProteins"] == 1
    assert out["canTransfer"] is False
    assert "same protein" in out["why"]


def test_constant_attribute_is_untested_not_thin():
    hist = ("Run_ID,ProteinClass,MW_kDa,Promoter,Titer_g_L\n"
            "R1,mAb,148,CMV,2.1\nR2,mAb,148,EF1a,2.4\nR3,mAb,148,CAG,2.9\n")
    prof = profile_of(table.parse_csv(hist))
    cols = program.protein_columns(prof, ["Promoter"], ["Titer_g_L"])
    programs = program.parse_program(
        table.parse_csv("Program_ID,ProteinClass,MW_kDa\nP,bispecific,104\n"), ["Promoter"]
    )["programs"]
    out = program.transferability(prof, cols, programs)
    assert out["perProgram"][0]["standing"] == "untested"
    assert [e["field"] for e in out["perProgram"][0]["noEvidence"]] == ["ProteinClass", "MW_kDa"]


def test_unseen_catalogue_level_is_named():
    hist = fixtures.history_csv()
    prof = profile_of(table.parse_csv(hist))
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    out = program.level_coverage(prof, factors, None)
    helper = next(r for r in out if r["factor"] == "Helper")
    assert helper["unseen"] == ["pHelper-D"]
    assert helper["total"] == 4 and len(helper["modelled"]) == 3


def test_nothing_here_opens_a_socket_or_touches_disk():
    """The browser tool's guarantee is that it sends nothing anywhere. The port
    keeps it for the selection logic: the only file access in this package is the
    explicit ``read_table`` helper."""
    import pathlib
    root = pathlib.Path(program.__file__).parent
    banned = ("socket", "urllib", "requests", "http.client", "subprocess", "boto3")
    for path in sorted(root.glob("*.py")):
        text = path.read_text()
        for word in banned:
            assert "import %s" % word not in text and "from %s" % word not in text, (
                "%s imports %s" % (path.name, word))
        if path.name != "table.py":
            assert "open(" not in text, "%s opens a file" % path.name
