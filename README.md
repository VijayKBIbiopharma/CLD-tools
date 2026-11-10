# CLD-tools

Small, single-purpose statistical tools for **cell line and strain development**, written in
Python to run on the Digital Cloud Platform.

One tool per question. Not one application that does everything.

## Why small tools

A cell line development group does not arrive with "analyse my data". It arrives with a
specific question, on a specific week, with a specific file:

- *Is my clone ranking real, or is it the luck of the plate?*
- *Which week-one read actually predicts day-14 titer?*
- *Which construct do we build for this incoming molecule?*
- *Where do we set the generation limit?*

Each of those needs different arithmetic, a different input file and a different refusal when
the data cannot answer it. Bundling them into one application means every reviewer has to
read all of it to approve any of it, and every deployment carries code nobody in the room
needs. So they ship separately: one tool, one question, one review.

## What CLD needs, in order

The order is not arbitrary and it is not ours — it comes from the step that has to come
first. **A clone ranking is only as good as the assay that produced it.** If repeat wells on
the same clone scatter as widely as different clones do, the top of the ranking is the plate
and no amount of modelling fixes it.

| # | The question it answers | Status |
|---|---|---|
| 1 | **Screening-assay variance.** Split the spread across plate, day and analyst before trusting any ranking built on it. | not started |
| 2 | **Which early reads predict the late ones.** Day-14 titer and quality against the week-one reads, with a shuffled-target noise floor so a read carrying no evidence is named as carrying none. | not started |
| 3 | **Clone identity as a real input.** Forty-eight strains carried as themselves rather than collapsed to the twelve commonest. Measured: R² 0.70 against 0.49 over eight datasets of 200 runs across 40 strains — a fifth of the achievable fit was in the levels one-hot throws away. | not started |
| 4 | **Vector selection for a programme not yet started.** Historical constructs, the parts they were built from and the protein they were for, turned into a run sheet per incoming programme. Measured: the top 8 candidates built 6 times each finds the truly best vector 61.4% of the time, against 36.4% for building all 36 once, over 4,000 simulated 48-well sheets. | **phase 1 built** |
| 5 | **Generation limits from measured drift.** Titer and quality against generation number, with the confidence limit deciding where the limit sits rather than convention. | not started |

Number 4 is built first rather than number 1 because it is the one with a sponsor and an
agreed home on the platform. That is a sequencing decision, not a statement that assay
qualification matters less — it matters more, and it is the next one worth funding.

## What is built

**`python/cld_vector`** — vector selection. Phase 1.

```
cd python
python3 -m cld_vector.cli \
    --history   examples/history.csv \
    --catalogue examples/catalogue.csv \
    --programs  examples/programs.csv \
    --target    Titer_g_L --target Viability_pct --runs 12
```

Historical runs, a parts catalogue and a list of incoming programmes in. Out comes what the
history can and cannot speak to, which catalogue levels have ever actually been built, and a
balanced run sheet. **No runtime dependencies** — nothing to qualify, pin or watch for
advisories.

What it does *not* yet print is a predicted titre. That needs the model fitting and the
prediction interval, which is phase 2 and is waiting on a decision about which numerical
packages are available. The tool says so rather than leaving a blank column.

The measurement it turns on is refusal. Predicting for a new *vector* is not the same problem
as predicting for a new *protein*: if every historical run was a monoclonal antibody, the
history holds no information about how a bispecific responds to a promoter choice. The
arithmetic will not complain — the model returns a confident number and the interval beside
it is narrow, because nothing in the residuals knows the question changed. So the history is
measured before anything is predicted, and a programme whose protein is unlike anything run
before is told so in those words.

Full detail, including how it is validated: **[`python/README.md`](python/README.md)**.

## The JavaScript in this repository is not a deliverable

`BROWSER-TOOL.md` documents a browser-based suite of ten analysis benches that covers these questions
and about thirty others. It is here, it works, and **it is not what we are proposing to
deploy.** It is written in JavaScript to run inside a browser tab with no install and no
server, which is the right shape for a desk and the wrong shape for the platform, which wants
Python, automated, in a container.

It keeps its place for one reason, and it is a load-bearing one: **it is the reference
implementation.** Every Python tool here is tested by running both over the same inputs and
requiring identical answers — not against hand-written expected values, which are a third
opinion, but against 24,700 lines of implementation carrying 167 tests and over 1,790
assertions in which every numeric claim was empirically measured rather than quoted.

That is a better validation story than a fresh Python tool can offer on its own. We are not
asking anyone to review JavaScript. We are handing over Python that is *proven* to agree with
a reference that was checked first.

## How these are validated

Two things, both in `python/`:

1. **The oracle.** `tests/oracle.js` runs the real JavaScript under node; the Python answers
   the same inputs; the two must be identical.
2. **A mutation sweep.** `tests/mutation_sweep.py` plants 42 defects one at a time and
   requires each to fail a test. A suite that passes tells you nothing on its own.

The first run of that sweep left ten defects standing. Two were real bugs in the port, seven
were missing test cases, one was provably equivalent. That is what the sweep is for.

## What these tools will not do

Stated here rather than discovered later:

- **No imaging.** Colony counts, confluence and morphology have to arrive as numbers in a
  column. These tools read tables, never pictures.
- **No sequence-to-function prediction.** Nothing here says whether a construct will express.
- **Single-cell data is out of scope.** One row per clone or per well, not per cell.
- **Not a validated GxP system.** Decision support with an audit trail. Non-GMP use.

## Layout

| Path | What it is |
|---|---|
| `python/` | The Python tools. Start at `python/README.md`. |
| `python/cld_vector/` | Vector selection (phase 1). |
| `python/tests/` | The oracle comparison and the mutation sweep. |
| `BROWSER-TOOL.md` | Documentation for the JavaScript reference implementation. |
| `*.js`, `index.html`, `learn.html` | The reference implementation itself. |
| `tests/run-tests.js` | Its 167 tests. `node tests/run-tests.js`. |
| `releases/` | Packaged zip of the reference implementation, with SHA-256 sums. |
| `demo-data/` | Practice datasets, biologics only, tagged by function. |

## Contact

Boulder OpEx — vramasubramanian@kbibiopharma.com
