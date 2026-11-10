/* The oracle: the original JavaScript, driven over JSON.

   The Python port is not checked against hand-written expected values. It is
   checked against the implementation it was ported from, over the same inputs,
   with the answers required to be identical. This file is the JavaScript half of
   that: it reads a list of calls on stdin and writes the list of results on
   stdout, so the Python test can run the real engine.js and program.js rather
   than a transcription of them.

   Run from anywhere; the paths are resolved against this file. The three files it
   loads are the only JavaScript in this repository, and they are here to be run by
   this harness - not to be deployed, read line by line, or ported further. */
'use strict';
const path = require('path');
const ROOT = path.resolve(__dirname, '..', 'reference');
const E = require(path.join(ROOT, 'engine.js'));
const P = require(path.join(ROOT, 'program.js'));

const FNS = {
  parseTable: (text, name) => E.parseTable(text, name),
  profile: text => E.profile(E.parseTable(text)),
  parseCatalogue: text => P.parseCatalogue(E.parseTable(text)),
  parseProgram: (text, factorNames) => P.parseProgram(E.parseTable(text), factorNames),
  proteinColumns: (text, factorNames, targets) => P.proteinColumns(E.profile(E.parseTable(text)), factorNames, targets),
  attributeChoices: (text, name) => P.attributeChoices(E.profile(E.parseTable(text)), name),
  transferability: (histText, factorNames, targets, progText) => {
    const prof = E.profile(E.parseTable(histText));
    const cols = P.proteinColumns(prof, factorNames, targets);
    const programs = progText === null ? [] : P.parseProgram(E.parseTable(progText), factorNames).programs;
    return P.transferability(prof, cols, programs);
  },
  candidates: (catText, opt) => P.candidates(P.parseCatalogue(E.parseTable(catText)).factors, opt),
  levelCoverage: (histText, catText, enc) =>
    P.levelCoverage(E.profile(E.parseTable(histText)), P.parseCatalogue(E.parseTable(catText)).factors, enc),
  replicatesFor: r2 => P.replicatesFor(r2),
  runSheet: (scored, axes, opt) => P.runSheet(scored, axes, opt),
  /* The primitives the port had to reimplement. Checked directly, because a
     disagreement here reaches every function above and is far easier to read at
     this level than as a differing run sheet twelve calls later. */
  jsString: values => values.map(v => String(v)),
  jsNumber: texts => texts.map(t => { const n = Number(t); return Number.isFinite(n) ? n : String(n); }),
  toFixed: (values, digits) => values.map(v => v.toFixed(digits)),
  rngDraws: (seed, count) => { const r = E.rng(seed); return Array.from({length: count}, () => r()); },
  shuffled: (n, seed) => E.shuffle(E.range(n), E.rng(seed)),
  jsTrim: values => values.map(v => v.trim()),
  objectKeys: pairs => { const o = {}; for (const [k, v] of pairs) o[k] = v; return Object.keys(o); }
};

let input = '';
process.stdin.on('data', d => { input += d; });
process.stdin.on('end', () => {
  const calls = JSON.parse(input);
  const out = calls.map((c, i) => {
    const fn = FNS[c.fn];
    if (!fn) return { error: 'no such function: ' + c.fn };
    try {
      return { value: fn.apply(null, c.args) };
    } catch (e) {
      return { error: e.message };
    }
  });
  process.stdout.write(JSON.stringify(out));
});
