"""Command-line entry point.

Logging goes to the console and nowhere else, as the platform's onboarding
requirements ask: one handler on stdout, no file handler, no rotation, no
directory to create. A container's log collector reads stdout; a file handler
would hide the same lines inside the container and fail when the filesystem is
read-only.

What this prints is the part of the vector-selection flow that does not need a
fitted model: what the history can and cannot speak to, which catalogue levels
have ever been built, how many vectors the catalogue affords, and a balanced
screening sheet. It does not print predicted titres, because the model fitting
is the second half of the port. It says so rather than leaving a blank column.
"""

import argparse
import logging
import sys

from . import __version__
from .design import aliasing, worst_case
from .jsnum import js_string
from .profile import profile
from .rng import rng
from .program import (
    candidates,
    level_coverage,
    parse_catalogue,
    parse_program,
    protein_columns,
    run_sheet,
    transferability,
)
from .table import read_table

log = logging.getLogger("cld_vector")


def configure_logging(verbose=False):
    """One stream handler on stdout. Called once, from main."""
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    root = logging.getLogger("cld_vector")
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.propagate = False


def build_parser():
    parser = argparse.ArgumentParser(
        prog="cld-vector",
        description="Vector selection from historical runs and a parts catalogue.",
    )
    parser.add_argument("--history", required=True,
                        help="delimited file of historical runs, one row per run")
    parser.add_argument("--catalogue", required=True,
                        help="delimited file of factors and the levels available")
    parser.add_argument("--programs", default=None,
                        help="delimited file of incoming programmes, one row each")
    parser.add_argument("--target", action="append", default=[], metavar="COLUMN",
                        help="an outcome column in the history; repeat for more than one")
    parser.add_argument("--runs", type=int, default=12, help="wells available (default 12)")
    parser.add_argument("--seed", type=int, default=29, help="run-order seed (default 29)")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--version", action="version", version="cld-vector %s" % __version__)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    configure_logging(args.verbose)
    log.info("cld-vector %s", __version__)

    history = read_table(args.history)
    prof = profile(history)
    log.info("history: %d runs, %d columns", prof["nRows"], prof["nCols"])

    cat = parse_catalogue(read_table(args.catalogue))
    for problem in cat["problems"]:
        log.warning("catalogue: %s", problem)
    factors = cat["factors"]
    if not factors:
        log.error("The catalogue defines no usable factors, so there is nothing to choose.")
        return 2
    factor_names = [f["name"] for f in factors]
    log.info("catalogue: %d factors (%s)", len(factors), ", ".join(factor_names))

    if not args.target:
        log.error("Name at least one outcome column from the history with --target.")
        return 2
    missing_targets = [t for t in args.target if not any(c["name"] == t for c in prof["columns"])]
    if missing_targets:
        log.error("The history has no column called %s.", " or ".join(missing_targets))
        return 2

    missing = [n for n in factor_names if not any(c["name"] == n for c in prof["columns"])]
    if missing:
        log.warning("Not in the history, so nothing can be predicted about them: %s",
                    ", ".join(missing))

    programs = []
    if args.programs:
        parsed = parse_program(read_table(args.programs), factor_names)
        programs = parsed["programs"]
        if parsed["ignored"]:
            log.info("Ignored in the programme file, because the tool chooses them: %s",
                     ", ".join(parsed["ignored"]))
        if parsed["skipped"]:
            log.info("Read as record-keeping rather than protein attributes: %s",
                     ", ".join(parsed["skipped"]))
        log.info("programmes: %d", len(programs))

    protein = protein_columns(prof, factor_names, args.target)
    log.info("protein attributes read from the history: %s",
             ", ".join(protein) if protein else "none")

    transfer = transferability(prof, protein, programs)
    log.info("distinct proteins in the history: %d - %s", transfer["nProteins"], transfer["why"])
    if transfer["constant"]:
        log.warning("Held constant across every historical run, so the data cannot say what "
                    "changing them does: %s", ", ".join(transfer["constant"]))
    if not transfer["canTransfer"]:
        log.warning("No prediction for a different protein can be defended from this history.")
    for row in transfer["perProgram"]:
        log.info("  %s: %s", row["id"], row["standing"])
        for item in row["novel"] + row["unseen"] + row["noEvidence"]:
            log.info("    %s = %s - %s", item["field"], item["value"], item["why"])

    coverage = level_coverage(prof, factors, None)
    for row in coverage:
        if row["unseen"]:
            log.warning("%s: %d of %d levels have never been built, so no model can place "
                        "them: %s", row["factor"], len(row["unseen"]), row["total"],
                        ", ".join(str(v) for v in row["unseen"]))

    cand = candidates(factors, {"seed": args.seed})
    log.info("buildable vectors: %d of %d%s", len(cand["list"]), cand["total"],
             " (sampled)" if cand["sampled"] else "")

    # No fitted model yet, so nothing ranks the vectors. The selection rule
    # breaks ties between equally-balancing candidates on the predicted value, so
    # handing it one constant value leaves every tie unbroken and it walks the
    # catalogue in enumeration order - which on a catalogue whose factors have
    # similar level counts produces a sheet that is perfectly balanced factor by
    # factor and perfectly aliased between them. Measured on the example
    # catalogue: 3 of 6 factor pairs fully confounded.
    #
    # A seeded random value restores the tie-break, which makes the choice among
    # equally-balancing candidates random rather than alphabetical. That is a
    # randomised balanced design, which is a real design; the walk in enumeration
    # order is not.
    tie_break = rng(args.seed)
    scored = [{"config": cfg, "ok": True, "value": tie_break()} for cfg in cand["list"]]
    log.info("No model is fitted, so the vectors are not ranked: the sheet is balanced "
             "and the choice between equally balancing vectors is random (seed %d).",
             args.seed)
    sheet = run_sheet(scored, cand["axes"], {"runs": args.runs, "seed": args.seed})
    log.info("screening sheet: %d runs over %d distinct vectors, %d repeats",
             len(sheet["sheet"]), sheet["distinct"], sheet["replicated"])
    if sheet["balance"]:
        for name, info in sheet["balance"].items():
            log.info("  %s balance: %s (spread %d)", name, info["counts"], info["spread"])

    # Marginal balance is not enough: a sheet can run every level of every
    # factor equally often and still vary them in lockstep, in which case no
    # factor's effect is estimable. Say so before printing the sheet.
    confounded = aliasing(sheet["sheet"], cand["axes"])
    verdict = worst_case(confounded)
    if verdict:
        log.warning("%s", verdict)
    for row in confounded[:4]:
        log.debug("  %s x %s: %d of %d combinations, counts %d-%d%s",
                  row["factors"][0], row["factors"][1], row["cells"], row["possible"],
                  row["min_cell"], row["max_cell"], ", fully aliased" if row["determined"] else "")

    axis_names = [a["name"] for a in cand["axes"]]
    print("Run\tStd\tReplicate\t" + "\t".join(axis_names))
    for row in sheet["sheet"]:
        print("%d\t%d\t%d\t%s" % (row["run"], row["std"], row["replicate"],
                                  "\t".join(js_string(row["config"][n]) for n in axis_names)))

    log.info("Predicted outcomes are not in this release: the model fitting and the "
             "prediction interval are the second half of the port.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
