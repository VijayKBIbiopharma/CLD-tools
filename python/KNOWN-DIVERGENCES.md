# Where the Python port does not match the JavaScript

The oracle tests require the two implementations to give identical answers. These
are the places where they deliberately do not, each with the reason. There are
four.

## 1. JSON input is refused rather than read

`engine.js` reads four JSON export shapes (a list of records, records inside an
envelope, one array per column, one record per line) and reports which it found.
`parse_table` here raises on anything that looks like JSON.

All three inputs to the vector flow are spreadsheet exports in practice. Porting
90 lines of shape detection for a case this tool has not met would mean carrying
untested code, and a shape-detection bug reads a file wrongly rather than
failing. Refusing it is louder.

## 2. `parse_program` on empty input

The JavaScript's early return for an empty programme file omitted the `skipped`
field that its main return provides, so a caller reading `res.skipped` got
`undefined`. The browser interface guards for it (`program-ui.js:131`), so
nothing was broken, but the two return shapes differed.

Resolved by changing the JavaScript to return `skipped: []` on that path, so both
implementations now have one contract. This is listed because it was a change to
the original, not to the port.

## 3. No prototype inheritance on frequency counters

`profileColumn` in `engine.js` counts level frequencies into `{}`, which
inherits from `Object.prototype`. A categorical column containing the literal
value `constructor`, `toString`, `valueOf` or `hasOwnProperty` therefore reads an
inherited function rather than a missing key, and `counts[v] || 0` returns the
function. `(function + 1)` is string concatenation in JavaScript, so that level's
count becomes a string and the frequency sort silently stops working for the
whole column.

`parse_grid`'s duplicate-name counter has the same exposure: a column literally
named `constructor` becomes `constructor (NaN)`.

Python dictionaries have no prototype, so the port does not reproduce either. The
JavaScript's own newer code already avoids it — `levelCoverage` in `program.js`
uses `Object.create(null)` for exactly this reason — so the port matches the
safer of the two choices the original makes.

Reachable only with a column or value named after an `Object.prototype` member.

## 4. `run_sheet` increments a missing balance key defensively

In the screening branch the JavaScript writes
`counts[a.name][String(c.config[a.name])]++`, with no guard. If a scored
candidate carried a level that is not among its axis's values, that count would
become `NaN` and every balance figure for that factor would follow. The select
branch in the same function guards it (`(cnt[...] || 0) + 1`), so the original is
inconsistent with itself.

The port uses the guarded form in both branches. Unreachable through
`candidates()`, which only ever emits levels drawn from the axes.

---

## Two things that are not divergences, but were checked

**`Math.imul`'s signed result.** `Math.imul` returns a signed 32-bit integer, and
an earlier version of `rng.py` converted it. The conversion is unobservable:
multiplication modulo 2^32 gives the same bits whichever way the operands are
read, and every use of the result masks it immediately. A mutation removing the
conversion could not be distinguished from the original over 48-element shuffles
on eleven seeds, so it was dropped. The generator remains bit-for-bit identical.

**`canTransfer`'s second clause.** `nProteins >= 2 && varying.length > 0` looks
redundant, because distinct protein signatures normally imply a varying
attribute. It is not: a protein column holding one value and some blanks profiles
as constant, so `varying` is empty, while the blanks still make two distinct
signatures. The clause is load-bearing on that input, and there is a test for it.
