# CLD Tools

Small, single-purpose statistical tools for **cell line and strain development**,
written in Python.

One tool per question. No framework, no build step, and — for the tool that exists
today — **no runtime dependencies at all.**

```
pip install .

cld-vector --history   examples/history.csv \
           --catalogue examples/catalogue.csv \
           --programs  examples/programs.csv \
           --target    Titer_g_L --target Viability_pct \
           --runs 12
```

## Plasmid design and vector selection

The first tool, and the one that is built.

**The question it answers:** a new molecule is coming in. Which construct should we
build for it, and what should the screening plate look like?

**What it takes:** three spreadsheet exports.

| File | One row per | Holds |
|---|---|---|
| History | historical run | the protein's attributes, the vector that was built, the outcome |
| Catalogue | factor | the levels the site can actually build with |
| Programmes | incoming programme | the protein's attributes, nothing else |

**What it gives back:** what the history can and cannot speak to, which catalogue
levels have ever actually been built, how many vectors the catalogue affords, and a
balanced run sheet.

### The part that matters most is a refusal

Predicting for a new *vector* is not the same problem as predicting for a new
*protein*, and treating them the same way is the most damaging thing this tool
could do.

A vector factor can be extrapolated a little: the history has four promoters, you
ask about a fifth, the tool maps it to the nearest and says so. A protein attribute
cannot be treated that way. If every historical run was a monoclonal antibody, the
history contains **no information whatsoever** about how a bispecific responds to a
promoter choice.

The arithmetic will not complain. A model fitted on one protein class returns a
confident number for another, and the prediction interval beside it is *narrow*,
because nothing in the residuals knows the question changed.

So the history is measured before anything is predicted — how many distinct
proteins it actually holds, which protein attributes vary at all, and whether the
incoming programme sits inside that. A protein attribute that never varies is
reported as carrying no evidence. A programme whose protein is unlike anything run
before is told so in those words, rather than handed a number with a tight band on
it.

Four hundred runs of one molecule are four hundred runs of one molecule. The
effective sample size for a cross-protein question is one.

### Where the wells go

Measured over 4,000 simulated 48-well sheets drawn from 36 candidates, scoring how
often the sheet identifies the truly best vector:

| Strategy | Poor prediction | Good prediction |
|---|---|---|
| 36 distinct × 1 | 33.1% | 36.4% |
| top 24 × 2 | 39.1% | 42.3% |
| top 16 × 3 | 41.9% | 48.4% |
| top 12 × 4 | 41.4% | 55.9% |
| **top 8 × 6** | 37.2% | **61.4%** |

Building everything once is the worst option in both columns, because a single
observation of a vector is mostly noise and the sheet ends up ranking noise. How far
to concentrate depends on how much the ranking can be trusted, so the replicate
count is read off the model's cross-validated R², not guessed.

### Not in this release

**A predicted titre.** Model fitting and the prediction interval are phase 2. The
tool says so rather than leaving a blank column — it prints the transferability
verdict, the coverage and a balanced sheet, and states plainly that nothing in the
output ranks the vectors.

## Roadmap

The order below is not arbitrary, and it is not ours. It is the order the work has
to happen in, because **a clone ranking is only as good as the assay that produced
it.** If repeat wells on the same clone scatter as widely as different clones do,
the top of the ranking is the luck of the plate and no amount of modelling fixes it.

| # | Tool | The question | Status |
|---|---|---|---|
| 1 | Screening-assay variance | Split the spread across plate, day and analyst before trusting any ranking built on it. | not started |
| 2 | Early-read screening | Which week-one reads actually predict day-14 titer and quality, with a shuffled-target noise floor so a read carrying no evidence is named as carrying none. | not started |
| 3 | Clone identity modelling | Forty-eight strains carried as themselves rather than collapsed to the twelve commonest. Measured: R² 0.70 against 0.49 over eight datasets of 200 runs across 40 strains. | not started |
| 4 | **Vector selection** | Which construct to build for an incoming programme, and the plate to confirm it. | **phase 1 built** |
| 5 | Generation limits | Titer and quality against generation number, with the confidence limit setting the limit rather than convention. | not started |

Number 4 is built first because it has a sponsor and an agreed home on the platform.
That is a funding decision, not a claim that assay qualification matters less — it
matters more, and it is the next one worth building.

## How this is validated

Not against hand-written expected values. A hand-written expectation is a third
opinion about what the answer should be, and the question is whether this tool
agrees with the implementation it was ported from.

**1. The oracle.** `tests/oracle.js` runs the reference JavaScript in `reference/`
under node; the Python answers the same inputs; the two must be identical. Getting
there required reimplementing six JavaScript primitives exactly, because the
languages disagree:

- `String(5.0)` is `"5"` in JavaScript and `"5.0"` in Python. Stringified numbers
  key the run sheet's balance counts and join the protein signatures, so a mismatch
  silently splits one factor level into two.
- `String(1e16)` is `"10000000000000000"` and `"1e+16"`.
- `Number("")` is `0` and a `ValueError`.
- `(-0.5).toFixed(0)` is `"-1"`; Python's `format` gives `"-0"` and round-half-even
  gives `"0"`.
- `\d` is ASCII-only in a JavaScript regular expression, so a column of Devanagari
  numerals profiles as numeric in Python and categorical in JavaScript.
- `trim()` removes the byte-order mark and keeps the ASCII file separators;
  `str.strip()` does the opposite. Both appear in real exports.

**2. A mutation sweep.** `tests/mutation_sweep.py` plants 42 defects one at a time
and requires each to fail a test, because a suite that passes proves nothing on its
own. Its first run left ten defects standing: two were real bugs in the port, seven
were missing test cases, one was provably equivalent and is declared as such.

```
pytest -q                     # 30 tests
python tests/mutation_sweep.py   # 42 defects, each must fail a test
```

The oracle tests skip, loudly, if node is not installed. The tool itself needs
neither node nor the reference files.

Where the port deliberately differs from the reference, and why:
[`KNOWN-DIVERGENCES.md`](KNOWN-DIVERGENCES.md).

## What these tools will not do

Stated here rather than discovered later:

- **No imaging.** Colony counts, confluence and morphology must arrive as numbers in
  a column. These tools read tables, never pictures.
- **No sequence-to-function prediction.** Nothing here says whether a construct will
  express.
- **Single-cell data is out of scope.** One row per clone or per well, not per cell.
- **No live data connection.** Every input is a file somebody exported.
- **Not a validated GxP system.** Decision support with an audit trail. Non-GMP use.

## Layout

| Path | What it is |
|---|---|
| `cld_vector/` | The vector selection tool. |
| `tests/` | The oracle comparison, the mutation sweep, and the design checks. |
| `examples/` | A worked history, catalogue and programme list. |
| `reference/` | Three frozen JavaScript files, used **only** by the test harness. Not deployed, not for review. See `reference/README.md`. |
| `KNOWN-DIVERGENCES.md` | Where the port differs from the reference, with reasons. |

The browser-based suite this tool was ported from is preserved on the
`browser-tool-final` branch. It is not part of this repository's product and nothing
here depends on it at runtime.

## Contact

Boulder OpEx — vramasubramanian@kbibiopharma.com
