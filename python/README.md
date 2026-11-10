# cld-vector

Vector selection for biologics programmes: the Python port of the vector bench in
CLD Tools (Cell line and strain development statistics).

Historical runs in, a parts catalogue in, a list of incoming programmes in. Out
comes what the history can and cannot speak to, which catalogue levels have ever
been built, and a balanced run sheet.

**Runtime dependencies: none.** The selection logic is arithmetic, string
handling and enumeration, all of which the standard library covers.

## What is here, and what is not

| | |
|---|---|
| Catalogue parsing, both file shapes | ported |
| Programme parsing, record-keeping columns excluded | ported |
| Protein-transferability measurement | ported |
| Candidate enumeration and sampling | ported |
| Catalogue level coverage | ported |
| Run-sheet construction, both purposes | ported |
| Delimited-text reading and column profiling | ported |
| The seeded generator, bit for bit | ported |
| Confounding report | **new**, see below |
| **Model fitting and predicted outcomes** | **not yet** |
| JSON input shapes | not ported, deliberately |

`plan()` — the end-to-end flow that scores every candidate — needs the model
fitting and the split-conformal prediction interval from `plasmid.js`. That is
the second half of the port, and it is the point at which a decision is needed
about which numerical packages are available to qualify. Nothing in this release
prints a predicted titre, and the command line says so rather than leaving a
blank column.

The JSON reader in `engine.js` handles four export shapes. It is not ported: all
three inputs to this flow are spreadsheet exports in practice, and 90 lines of
shape detection serving a case the tool has not met is not worth carrying
untested. `parse_table` raises on JSON instead of guessing.

## How it is checked

The port is not checked against hand-written expected values. It is checked
against the JavaScript it was ported from: `tests/oracle.js` runs the real
`engine.js` and `program.js` under node, the Python answers the same inputs, and
the two are required to be identical.

```
python3 -m pytest tests/              # 30 tests
python3 tests/mutation_sweep.py       # 42 planted defects, each must fail a test
```

The oracle tests skip if node is not installed, loudly.

Agreeing with the original required reimplementing six JavaScript primitives
exactly, which `cld_vector/jsnum.py` does with the specification section numbers
noted. They are not pedantry:

- `String(5.0)` is `"5"` in JavaScript and `"5.0"` in Python. Stringified numbers
  key the run sheet's balance counts and join the protein signatures, so a
  mismatch splits one factor level into two.
- `String(1e16)` is `"10000000000000000"` and `"1e+16"`.
- `Number("")` is `0` and a `ValueError`.
- `(-0.5).toFixed(0)` is `"-1"`; Python's `format` gives `"-0"`, and rounding
  half to even gives `"0"`.
- `\d` is ASCII-only in a JavaScript regular expression. A column of Devanagari
  numerals profiles as numeric in Python and categorical in JavaScript.
- `"".trim()` removes the byte-order mark and keeps the ASCII file separators;
  `str.strip()` does the opposite. Both appear in real exports.

The mutation sweep found two of those by planting a defect the suite could not
distinguish from the original. It is worth running after any change.

## The confounding report

`cld_vector/design.py` is new code, not a port. It exists because running the
ported `run_sheet` with no model behind it produced a sheet that was perfectly
balanced and completely useless: twelve wells in which CMV appeared only with
pHelper-A and one copy, EF1a only with pHelper-B and two, and so on. Every
balance figure read zero, and no factor's effect was estimable.

That is a property of the no-model case, not of the ported rule. The selection
rule breaks ties between equally-balancing candidates on the predicted value, so
one constant value leaves every tie unbroken and it walks the catalogue in
enumeration order. With predictions that vary — which is every use in the
browser tool — no pair is confounded at any sheet size tested. The command line
now supplies a seeded random tie-break instead of a constant, and reports the
pairwise picture per sheet rather than trusting any of this.

Measured over 200 seeds on the example catalogue (4 x 3 x 4 x 4):

| wells | sheets with no confounded pair |
|---|---|
| 8 | 180 / 200 |
| 12 | 200 / 200 |
| 16 | 200 / 200 |
| 24 | 200 / 200 |
| 48 | 200 / 200 |

Eight wells cannot cover the factor pairs, so a tenth of those sheets confound a
pair however the ties break. That is the budget, not the rule, and it is reported
per sheet.

## Running it

```
python3 -m cld_vector.cli \
    --history   examples/history.csv \
    --catalogue examples/catalogue.csv \
    --programs  examples/programs.csv \
    --target    Titer_g_L \
    --target    Viability_pct \
    --runs 12
```

Logging goes to stdout and nowhere else: one stream handler, no file handler, no
directory to create, nothing to fail on a read-only filesystem. The run sheet
goes to stdout as tab-separated text; the commentary goes to the log.

## Input files

**History** — one row per historical run. Any column that is not a catalogue
factor, not an outcome and not record-keeping is read as a protein attribute.
Columns named `Run`, `Date`, `Operator`, `Notes`, `Site`, `Status` and the like
are read as record-keeping and take no part in anything.

**Catalogue** — one row per factor with the levels in one cell, or one row per
factor-level pair. A numeric factor is declared with `Min` and `Max`, optionally
`Step`. A factor with one level is held fixed and said so; a factor with neither
two levels nor a usable range is dropped and said so.

**Programmes** — one row per incoming programme, described by its protein's
attributes. A column matching a catalogue factor is ignored with a note, because
choosing those is the tool's job.

## The measurement this turns on

`transferability` is separate from everything else, returns numbers, and is
tested directly, because getting it wrong would be the most damaging thing this
code could do.

Predicting for a new vector is not the same problem as predicting for a new
protein. A vector factor can be extrapolated a little. A protein attribute cannot:
if every historical run was a monoclonal antibody, the history contains no
information whatsoever about how a bispecific responds to a promoter choice. The
arithmetic will not complain — a model fitted on one protein class returns a
confident number for another, and the interval beside it is narrow, because
nothing in the residuals knows the question changed.

So the history is measured before anything is predicted: how many distinct
proteins it actually contains, which protein attributes vary at all, and whether
the incoming programme sits inside that. An attribute held constant across the
whole history is reported as carrying no evidence. A programme whose protein is
unlike anything run before is told so in those words.
