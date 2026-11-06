"""Does the oracle actually catch anything?

A test suite that passes tells you nothing on its own. This script plants a
defect in the port, one at a time, and requires ``tests/test_oracle.py`` to fail.
A mutation that survives means the suite does not test that decision, whatever
its name suggests - and every one that survived the first run of this script
turned out to be a real gap in the fixtures or, twice, a real bug in the port.

Run it directly; it is not a pytest test because it runs the whole suite once per
mutation::

    python3 tests/mutation_sweep.py

One trap is worth knowing about, because it cost an hour: several mutations here
replace a name with another of exactly the same length (``ID_PICK`` for
``ID_SKIP``). CPython invalidates a cached ``.pyc`` on the source's size and its
modification time *in whole seconds*, so a mutation written and reverted inside
the same second leaves the mutated bytecode in place and the next run silently
uses it. Bytecode writing is therefore switched off here, and the cache is
cleared before each run.
"""
import os, pathlib, shutil, subprocess, sys, tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
MUTATIONS = [
 ("stats.py", "quantile: linear interpolation -> nearest order statistic",
  "return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)",
  "return sorted_values[round(pos)]"),
 ("stats.py", "variance: divide by n rather than n-1",
  "return total / (len(values) - 1)", "return total / len(values)"),
 ("profile.py", "numeric threshold 95% -> 90% of present values",
  "numeric_ok / present >= 0.95", "numeric_ok / present >= 0.90"),
 ("profile.py", "numeric threshold measured over rows, not present values",
  "numeric_ok / present >= 0.95", "numeric_ok / n >= 0.95"),
 ("profile.py", "level order: commonest first -> insertion order",
  "        levels = sorted(\n            keys,\n            key=functools.cmp_to_key(\n                lambda a, b: (counts[b] - counts[a]) or js_compare_strings(a, b)\n            ),\n        )",
  "        levels = list(keys)"),
 ("profile.py", "high-cardinality cut 12 -> 10",
  "HIGH_CARD = 12", "HIGH_CARD = 10"),
 ("profile.py", "to_number: percent divided by 100",
  '    if text.endswith("%"):\n        text = text[:-1]',
  '    if text.endswith("%"):\n        return js_number(text[:-1]) / 100'),
 ("program.py", "replicates_for: uses r2 rather than its square root",
  "r = math.sqrt(max(0.0, min(1.0, value)))", "r = max(0.0, min(1.0, value))"),
 ("program.py", "replicates_for: band edge 0.45 -> 0.5",
  "return 3 if r < 0.45 else", "return 3 if r < 0.5 else"),
 ("program.py", "transferability: a frozen attribute counts as thin, not untested",
  "if novel or unseen or no_evidence:", "if novel or unseen:"),
 ("program.py", "transferability: thin threshold 2 -> 3 proteins",
  "elif n_proteins <= 2:\n            standing", "elif n_proteins <= 3:\n            standing"),
 ("program.py", "transferability: canTransfer drops the varying-attribute test",
  '"canTransfer": n_proteins >= 2 and len(varying) > 0',
  '"canTransfer": n_proteins >= 2'),
 ("program.py", "candidates: default cap 20000 -> 2000",
  'cap = opt.get("cap") or 20000', 'cap = opt.get("cap") or 2000'),
 ("program.py", "candidates: step-less numeric factor gets 2 settings, not 3",
  'lv = [f["min"], js_number(to_fixed((f["min"] + f["max"]) / 2, 6)), f["max"]]',
  'lv = [f["min"], f["max"]]'),
 ("program.py", "candidates: too-many-steps guard 12 -> 20",
  "if len(lv) < 2 or len(lv) > 12:", "if len(lv) < 2 or len(lv) > 20:"),
 ("program.py", "candidates: step loop drops the 1e-9 tolerance",
  'while v <= f["max"] + 1e-9:', 'while v <= f["max"]:'),
 ("program.py", "run_sheet: promise before balance",
  "if rep < best_rep or (rep == best_rep and (cst < best_cost or\n                                  (cst == best_cost and val > best_val))):",
  "if rep < best_rep or (rep == best_rep and (val > best_val or\n                                  (val == best_val and cst < best_cost))):"),
 ("program.py", "run_sheet: no second pass, so a long sheet stops short",
  "if rep < best_rep or (rep == best_rep and (cst < best_cost or",
  "if (rep == 0 and best_rep > 0) or (rep == best_rep and (cst < best_cost or"),
 ("program.py", "run_sheet: select mode floor 2 replicates -> 1",
  'reps = max(2, opt.get("replicates") or 3)', 'reps = max(1, opt.get("replicates") or 3)'),
 ("program.py", "level_coverage: THIN_SHRINK 0.5 -> 0.4",
  "THIN_SHRINK = 0.5", "THIN_SHRINK = 0.4"),
 ("program.py", "level_coverage: prior applied to one-hot parts too",
  'prior = TARGET_PRIOR if (part and part.get("type") == "high") else 0',
  "prior = TARGET_PRIOR"),
 ("program.py", "ID_SKIP: 'notes' no longer record-keeping",
  "|scientist|owner|notes?|comment", "|scientist|owner|comment"),
 ("program.py", "parse_catalogue: a reversed Min/Max range is accepted",
  'rec["max"] > rec["min"]', 'rec["max"] != rec["min"]'),
 ("program.py", "parse_catalogue: levels split on semicolon only",
  'r"[;,|]"', 'r"[;]"'),
 ("program.py", "parse_program: first matching column wins the id, not ID_PICK",
  "if ID_PICK.match(_norm(c)):", "if ID_SKIP.match(_norm(c)):"),
 ("jsnum.py", "js_string: Python repr instead of Number::toString",
  "    digits, n = _shortest_decimal(x)", "    return repr(x)\n    digits, n = _shortest_decimal(x)"),
 ("jsnum.py", "js_string: exponent threshold 21 -> 17",
  "if k <= n <= 21:", "if k <= n <= 17:"),
 ("jsnum.py", "js_string: small-number exponent threshold -6 -> -4",
  "if -6 < n <= 0:", "if -4 < n <= 0:"),
 ("jsnum.py", "js_number: empty string is NaN rather than zero",
  '    if text == "":\n        return 0.0', '    if text == "":\n        return math.nan'),
 ("jsnum.py", "js_number: Python float() accepts what JavaScript rejects",
  "    if _DEC.match(text):\n        try:\n            return float(text)",
  "    if True:\n        try:\n            return float(text)"),
 ("jsnum.py", "to_fixed: round half to even",
  "rounding=ROUND_HALF_UP", "rounding=__import__('decimal').ROUND_HALF_EVEN"),
 ("jsnum.py", "to_fixed: negative halves round towards zero",
  "return str(Decimal(x).quantize(quantum, rounding=ROUND_HALF_UP))",
  "return str(Decimal(x).quantize(quantum, rounding=__import__('decimal').ROUND_HALF_DOWN if x < 0 else ROUND_HALF_UP))"),
 ("jsnum.py", "js_object_keys: insertion order throughout",
  "    indices.sort(key=int)\n    return indices + rest", "    return list(mapping)"),
 ("jsnum.py", "js_trim: Python's whitespace set",
  "return s.strip(JS_WHITESPACE)", "return s.strip()"),
 ("table.py", "parse_grid: Python strip on cells rather than JavaScript trim",
  "out = [js_trim(str(c)) for c in r[:width]]", "out = [str(c).strip() for c in r[:width]]"),
 ("profile.py", "is_missing: Python strip",
  "return js_trim(str(value)).lower() in MISSING", "return str(value).strip().lower() in MISSING"),
 ("rng.py", "rng: seed 0 not mapped to 1",
  "state = [(int(seed) & _U32) or 1]", "state = [int(seed) & _U32]"),
 ("rng.py", "rng: >>> 15 becomes >>> 14",
  "_imul(au ^ (au >> 15), 1 | au)", "_imul(au ^ (au >> 14), 1 | au)"),
 # Expected to survive: every use of _imul's result in draw() masks it to 32
 # bits immediately, so masking inside _imul as well is belt and braces. Listed
 # so that the sweep can require every OTHER survivor to be a real gap.
 ("rng.py", "rng: low 32 bits not kept on the multiply",
  "    return (a * b) & _U32", "    return a * b", True),
 ("rng.py", "rng: 61 | t becomes 61 ^ t",
  "_imul(t ^ (t >> 7), 61 | t)", "_imul(t ^ (t >> 7), 61 ^ t)"),
 ("rng.py", "rng: final >>> 14 becomes >>> 13",
  "return ((t ^ (t >> 14)) & _U32) / 4294967296.0",
  "return ((t ^ (t >> 13)) & _U32) / 4294967296.0"),
 ("rng.py", "shuffle: ascending Fisher-Yates instead of descending",
  "for i in range(len(arr) - 1, 0, -1):", "for i in range(0, len(arr) - 1):"),
]

src = ROOT / "boss_vector"
backup = pathlib.Path(tempfile.mkdtemp()) / "boss_vector"
shutil.copytree(src, backup, ignore=shutil.ignore_patterns("__pycache__"))
CLEAN_ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
for cache in ROOT.rglob("__pycache__"):
    shutil.rmtree(cache, ignore_errors=True)

print("%d mutations, one pytest run each.\n" % len(MUTATIONS))

caught = missed = invalid = 0
EXPECTED_SURVIVORS = sum(1 for m in MUTATIONS if len(m) > 4 and m[4])

for mutation in MUTATIONS:
    filename, label, old, new = mutation[:4]
    equivalent = len(mutation) > 4 and mutation[4]
    target = src / filename
    text = (backup / filename).read_text()
    if old not in text:
        print("  %-62s PATTERN NOT FOUND" % label[:62]); invalid += 1; continue
    target.write_text(text.replace(old, new, 1))
    assert target.read_text() != text, "mutation did not land"
    proc = subprocess.run([sys.executable, "-B", "-m", "pytest", "tests/test_oracle.py",
                           "-q", "-x", "--no-header", "-p", "no:cacheprovider"],
                          cwd=ROOT, capture_output=True, text=True, env=CLEAN_ENV)
    shutil.copyfile(backup / filename, target)
    if proc.returncode == 0:
        if equivalent:
            print("  %-62s survived, as expected" % label[:62])
        else:
            print("  %-62s SURVIVED" % label[:62]); missed += 1
    else:
        first = next((l for l in proc.stdout.splitlines() if l.startswith("FAILED")), "")
        print("  %-62s caught by %s" % (label[:62], first.replace("FAILED tests/test_oracle.py::", "").split(" - ")[0]))
        caught += 1

print("\n%d mutations: %d caught, %d survived unexpectedly, %d survived as expected, "
      "%d invalid" % (len(MUTATIONS), caught, missed, EXPECTED_SURVIVORS, invalid))
final = subprocess.run([sys.executable, "-B", "-m", "pytest", "tests/test_oracle.py",
                        "-q", "--no-header"], cwd=ROOT, capture_output=True, text=True,
                       env=CLEAN_ENV)
print("baseline after restore:", final.stdout.strip().splitlines()[-1])
sys.exit(1 if (missed or invalid or final.returncode != 0) else 0)
