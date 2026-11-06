"""The aliasing report, which is new code rather than a port.

There is no oracle for this module, so these tests assert against designs whose
confounding is known by construction: a sheet built to vary two factors in
lockstep must be reported as inseparable, and a full factorial must not be.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fixtures                                                        # noqa: E402
from boss_vector import program, table                                 # noqa: E402
from boss_vector.design import aliasing, pair_table, worst_case        # noqa: E402

AXES = [{"name": "A", "values": ["a1", "a2", "a3"]},
        {"name": "B", "values": ["b1", "b2", "b3"]}]


def sheet_of(pairs):
    return [{"config": {"A": a, "B": b}} for a, b in pairs]


def test_lockstep_pair_is_reported_inseparable():
    sheet = sheet_of([("a1", "b1"), ("a2", "b2"), ("a3", "b3")] * 3)
    report = aliasing(sheet, AXES)
    assert len(report) == 1
    assert report[0]["determined"] is True
    assert report[0]["cells"] == 3 and report[0]["possible"] == 9
    assert "cannot separate A with B" in worst_case(report)


def test_full_factorial_is_not_reported():
    sheet = sheet_of([(a, b) for a in ("a1", "a2", "a3") for b in ("b1", "b2", "b3")])
    report = aliasing(sheet, AXES)
    assert report[0]["determined"] is False
    assert report[0]["coverage"] == 1.0
    assert worst_case(report) is None


def test_partial_coverage_is_called_mostly_unmeasured_not_aliased():
    # Four of nine cells, and no level determines the other, so it is thin
    # rather than confounded. The two must not be reported the same way.
    sheet = sheet_of([("a1", "b1"), ("a1", "b2"), ("a2", "b1"), ("a2", "b2")])
    report = aliasing(sheet, AXES)
    assert report[0]["determined"] is False
    message = worst_case(report)
    assert "mostly unmeasured" in message and "cannot separate" not in message


def test_one_sided_determination_counts():
    # Every a maps to one b, but b1 serves two levels of a. Knowing a tells you
    # b, which is enough to make the pair inseparable.
    sheet = sheet_of([("a1", "b1"), ("a2", "b1"), ("a3", "b2")])
    report = aliasing(sheet, AXES)
    assert report[0]["determined"] is True


def test_pair_table_counts_numeric_levels_as_the_tool_prints_them():
    sheet = [{"config": {"A": 2.0, "B": "b1"}}, {"config": {"A": 2, "B": "b1"}}]
    axes = [{"name": "A", "values": [1, 2]}, {"name": "B", "values": ["b1"]}]
    assert pair_table(sheet, "A", "B") == {("2", "b1"): 2}


def test_the_degenerate_no_model_sheet_is_what_the_module_claims():
    """The case that caused this module to exist: one constant predicted value
    over the example catalogue leaves the tie-break unbroken, and the sheet comes
    out marginally balanced and pairwise aliased."""
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})
    flat = [{"config": c, "ok": True, "value": None} for c in cand["list"]]
    out = program.run_sheet(flat, cand["axes"], {"runs": 12, "seed": 29})
    assert all(info["spread"] == 0 for info in out["balance"].values()), "marginally balanced"
    report = aliasing(out["sheet"], cand["axes"])
    assert sum(1 for r in report if r["determined"]) == 3, "and three pairs inseparable"


def test_a_randomised_tie_break_removes_the_aliasing():
    """What the command line does instead of a constant value.

    The claim is measured over 200 seeds rather than asserted for one, and it is
    stated as the measurement found it, which is not as tidy as "always":

        wells   sheets with no aliased pair   worst marginal spread
        8                   180 / 200                   1
        12                  200 / 200                   2
        16                  200 / 200                   1
        24                  200 / 200                   2
        48                  200 / 200                   2

    Eight wells over a catalogue of 4 x 3 x 4 x 4 cannot cover the factor pairs,
    so a tenth of those sheets still confound a pair however the ties break. That
    is a property of the budget, not of the rule, and the command line reports it
    per sheet rather than relying on this table.

    The marginal spread reaching 2 is also measured rather than assumed: the
    greedy rule minimises the summed count over factors, which can leave one
    three-level factor at 5/4/3 when that choice balances the others better.
    """
    from boss_vector.rng import rng
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})

    def sweep(runs, seeds):
        clean, worst = 0, 0
        for seed in range(1, seeds + 1):
            draw = rng(seed)
            scored = [{"config": c, "ok": True, "value": draw()} for c in cand["list"]]
            out = program.run_sheet(scored, cand["axes"], {"runs": runs, "seed": seed})
            worst = max(worst, max(i["spread"] for i in out["balance"].values()))
            if not any(r["determined"] for r in aliasing(out["sheet"], cand["axes"])):
                clean += 1
        return clean, worst

    clean, worst = sweep(12, 200)
    assert clean == 200, "12 wells: %d of 200 sheets were separable, not 200" % clean
    assert worst == 2, "12 wells: worst marginal spread was %d, not 2" % worst

    clean, _ = sweep(8, 200)
    assert clean == 180, "8 wells: %d of 200 were separable, not 180" % clean


def test_eight_wells_is_reported_rather_than_hidden():
    """The sheets that stay aliased on a short budget must say so. One of the
    seeds the sweep above counts as confounded, checked end to end."""
    from boss_vector.rng import rng
    factors = program.parse_catalogue(table.parse_csv(fixtures.CATALOGUE_WIDE))["factors"]
    cand = program.candidates(factors, {})
    found = None
    for seed in range(1, 201):
        draw = rng(seed)
        scored = [{"config": c, "ok": True, "value": draw()} for c in cand["list"]]
        out = program.run_sheet(scored, cand["axes"], {"runs": 8, "seed": seed})
        report = aliasing(out["sheet"], cand["axes"])
        if any(r["determined"] for r in report):
            found = report
            break
    assert found is not None, "no confounded 8-well sheet in 200 seeds; the table is stale"
    assert "cannot separate" in worst_case(found)
