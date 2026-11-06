"""Input files for the oracle comparison.

The same text is handed to both implementations, so these are built here rather
than committed as files: a fixture that drifted between the two sides would make
the comparison meaningless. The history is generated from the ported seeded
generator, which is itself checked against the JavaScript one, so the sheet is
identical on every machine and on every run.
"""

from boss_vector.rng import rng

PROMOTERS = ["CMV", "EF1a", "CAG", "SV40"]
MARKERS = ["Puromycin", "Hygromycin", "Blasticidin"]
HELPERS = ["pHelper-A", "pHelper-B", "pHelper-C"]
PROTEINS = [
    ("mAb", 148.0, 8.2),
    ("bispecific", 104.0, 7.1),
    ("Fc-fusion", 126.0, 6.4),
    ("enzyme", 62.0, 5.9),
    ("VHH", 28.0, 9.3),
]


def history_csv(n_runs=90, n_proteins=5, seed=7):
    """Historical runs: protein attributes, the vector that was built, outcome."""
    rand = rng(seed)
    lines = ["Run_ID,ProteinClass,MW_kDa,pI,Promoter,Marker,Helper,Copies,Titer_g_L,Viability_pct"]
    for i in range(n_runs):
        cls, mw, pi = PROTEINS[i % n_proteins]
        promoter = PROMOTERS[int(rand() * len(PROMOTERS))]
        marker = MARKERS[int(rand() * len(MARKERS))]
        helper = HELPERS[int(rand() * len(HELPERS))]
        copies = 1 + int(rand() * 4)
        titer = (2.0 + 0.9 * PROMOTERS.index(promoter) * 0.4 - 0.004 * mw
                 + 0.18 * copies + rand() * 0.6)
        viability = 78.0 + rand() * 18.0
        lines.append("R%03d,%s,%s,%s,%s,%s,%s,%d,%.3f,%.1f" % (
            i + 1, cls, mw, pi, promoter, marker, helper, copies, titer, viability))
    return "\n".join(lines) + "\n"


# One row per factor, levels in one cell, plus a numeric factor by Min/Max/Step.
CATALOGUE_WIDE = (
    "Factor,Levels,Min,Max,Step\n"
    "Promoter,CMV; EF1a; CAG; SV40,,,\n"
    "Marker,Puromycin; Hygromycin; Blasticidin,,,\n"
    "Helper,pHelper-A| pHelper-B| pHelper-C| pHelper-D,,,\n"
    "Copies,,1,4,1\n"
)

# The other shape people actually have: one row per factor-level pair.
CATALOGUE_LONG = (
    "Parameter,Value\n"
    "Promoter,CMV\nPromoter,EF1a\nPromoter,CAG\n"
    "Marker,Puromycin\nMarker,Hygromycin\n"
)

# A one-level factor is held fixed and said so; a factor with neither levels nor
# a usable range is dropped and said so; a reversed range is not a range.
CATALOGUE_AWKWARD = (
    "Factor,Levels,Min,Max,Step\n"
    "Backbone,pTT5,,,\n"
    "Mystery,,,,\n"
    "Temperature,,37,31,1\n"
    "Feed_mL,,5,20,\n"
)

CATALOGUE_NO_FACTOR_COLUMN = "Thing,Options\nPromoter,CMV; EF1a\n"
CATALOGUE_EMPTY = "\n"

# Incoming programmes. Program_ID names them; Notes and Date are record-keeping
# and must not become protein attributes; Promoter is a catalogue factor and must
# be ignored with a note, because the tool chooses it.
PROGRAMS_CSV = (
    "Program_ID,ProteinClass,MW_kDa,pI,Promoter,Notes,Date\n"
    "PRG-1,mAb,148,8.2,CMV,rush,2026-01-04\n"
    "PRG-2,bispecific,104,7.1,,standard,2026-01-11\n"
    "PRG-3,nanobody-fusion,41,9.8,,new modality,2026-02-02\n"
    "PRG-4,mAb,310,8.0,,very large,2026-02-09\n"
)

# No ID column at all, so programmes are numbered.
PROGRAMS_NO_ID = (
    "ProteinClass,MW_kDa,pI\n"
    "mAb,148,8.2\n"
    "enzyme,62,5.9\n"
)


def axes_of(factors):
    """The axes a scored-candidate fixture is built over."""
    out = []
    for f in factors:
        if f["kind"] == "fixed":
            continue
        if f["kind"] == "categorical":
            out.append({"name": f["name"], "values": list(f["levels"])})
    return out


def scored_fixture(configs, seed=3):
    """Scored candidates for ``run_sheet``: a predicted value, a lower bound and
    a half width, in the shape ``plan()`` produces them."""
    rand = rng(seed)
    out = []
    for cfg in configs:
        value = 2.0 + rand() * 3.0
        half = 0.2 + rand() * 0.5
        out.append({"config": cfg, "ok": True, "value": value,
                    "low": value - half, "high": value + half, "halfWidth": half})
    out.sort(key=lambda s: -s["value"])
    return out


# Six factors at five levels each: 15,625 combinations. Enumerated under the
# default cap of 20,000 and sampled under anything smaller, so the cap itself is
# exercised rather than assumed.
CATALOGUE_BIG = "Factor,Levels\n" + "".join(
    "F%d,%s\n" % (i, "; ".join("L%d-%d" % (i, j) for j in range(1, 6)))
    for i in range(1, 7)
)
