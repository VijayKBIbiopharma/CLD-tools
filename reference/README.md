# reference/

Three JavaScript files. **They are test fixtures, not part of the product.**

| File | Lines | Why it is here |
|---|---|---|
| `engine.js` | 1,457 | CSV reading, column profiling, encoding, model fitting, cross-validation |
| `program.js` | 562 | Vector selection: catalogue, programmes, transferability, run sheets |
| `plasmid.js` | 490 | Model choice and the split-conformal prediction interval |

## What they are for

The Python tool in this repository is a port. A port is only trustworthy if you
can show it gives the same answers as the thing it was ported from, so
`tests/oracle.js` runs these three files under node, the Python answers the same
inputs, and the test suite requires the two to be identical.

That is a stronger check than hand-written expected values, which are a third
opinion about what the answer should be. These files were themselves validated
first — the suite they came from carried 167 tests and over 1,790 assertions, in
which every numeric claim was empirically measured rather than quoted from a
textbook.

## What they are not for

- **Not deployed.** Nothing serves them. There is no page, no server, no build.
- **Not for review.** Nobody is being asked to read or approve JavaScript. The
  deliverable is the Python.
- **Not maintained here.** They are frozen reference material. If the Python needs
  to change behaviour, the change is made in the Python and the oracle test is
  updated to say so deliberately.

## Where they came from

The full browser suite they were extracted from — ten analysis benches, a
69-lesson academy, its own 167-test suite — is preserved on the
`browser-tool-final` branch of this repository:

```
git checkout browser-tool-final
```

Only these three files came across, because these are the only ones the vector
selection tool's validation touches.

## Running the oracle without node

The oracle tests skip, loudly, if node is not installed. The Python tool itself
needs neither node nor these files; they are needed only to re-verify agreement.
