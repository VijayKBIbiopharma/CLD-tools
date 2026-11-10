"""Vector selection for a programme that has not run yet.

Ported from program.js. The shape of the flow is unchanged: historical runs in,
a parts catalogue in, a list of incoming programmes in, a scored run sheet out,
and no sliders anywhere.

The one thing in here that is harder than it looks, and that getting wrong would
be the most damaging thing this code could do, is ``transferability``.
Predicting for a new *vector* is not the same problem as predicting for a new
*protein*. A vector factor can be extrapolated a little: the history has four
promoters, you ask about a fifth, the tool maps it to the nearest and says so. A
protein attribute cannot be treated that way, because if every historical run
was a monoclonal antibody then the history contains no information whatsoever
about how a bispecific responds to a promoter choice. The arithmetic will not
complain: a model fitted on one protein class returns a confident number for
another, and the prediction interval beside it is narrow, because nothing in the
residuals knows the question changed.

So transferability is measured before anything is predicted, and a programme
whose protein is unlike anything run before is told so in those words rather
than handed a number with a tight band on it.

What is not in this module
--------------------------
``plan()`` - the end-to-end flow - is not ported yet. It needs the model fitting
and the split-conformal prediction interval from plasmid.js, which is the second
half of this port and the point at which a decision is needed about which
Python packages are available for qualification. Everything in this module is
pure enumeration, classification and arithmetic, so it stands on its own and is
checked against the JavaScript directly.
"""

import math
import re

from .jsnum import js_is_finite, js_number, js_string, js_trim, to_fixed
from .profile import TARGET_PRIOR, column_value_as_text
from .rng import js_range, rng, shuffle
from .stats import quantile


def _norm(value):
    """``norm`` from program.js: stringify, then trim. ``None`` becomes empty."""
    return js_trim(js_string(value))


def _key(value):
    """``key`` from program.js: a loose column-name match. "Protein Class",
    "protein_class" and "proteinclass" all key the same."""
    return re.sub(r"[^a-z0-9]", "", _norm(value).lower())


# Two lists, not one. ID_PICK is what can name a programme; ID_SKIP is
# everything that is record-keeping rather than data. They were one list in an
# earlier version of the JavaScript, and the bug that exposed the difference was
# quiet: only the first match was dropped, so a sheet with Program_ID and Notes
# kept Notes as a protein attribute. The history has no Notes column, so the
# attribute read as "not in the historical runs at all" and flipped a
# well-supported programme to untested - a scheduling note silently
# discrediting the prediction.
ID_PICK = re.compile(
    r"^(id|.*_id|id_.*|construct|clone|name|lot|batch|programme?|project|molecule)$",
    re.IGNORECASE,
)
ID_SKIP = re.compile(
    r"^(id|.*_id|id_.*|construct|clone|name|lot|batch|programme?|project|molecule"
    r"|run|runorder|stdorder|std|date|.*_date|date_.*|time|operator|analyst"
    r"|scientist|owner|notes?|comment|comments|remarks?|status|priority|site"
    r"|customer|client)$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------- step 2

def parse_catalogue(table):
    """The factors the site can choose between, and the levels available.

    Two shapes are accepted because both are what people actually have: one row
    per factor with the levels in one cell, or one row per factor-level pair. A
    numeric factor is declared by giving a Min and Max instead of levels.
    """
    if not table or not table.get("columns"):
        return {"factors": [], "problems": ["The factor file is empty."]}
    cols = [_key(c) for c in table["columns"]]

    def find(*names):
        for n in names:
            k = _key(n)
            if k in cols:
                return cols.index(k)
        return -1

    fi = find("factor", "parameter", "name", "attribute")
    li = find("levels", "level", "values", "value", "options")
    mi, ma, si = find("min", "low", "minimum"), find("max", "high", "maximum"), find("step", "increment")
    problems = []
    if fi < 0:
        return {"factors": [], "problems": [
            'No "Factor" column found. Expected a column naming each factor, and '
            'either a "Levels" column or "Min" and "Max" columns.'
        ]}

    by_name = {}
    order = []
    for r in table["rows"]:
        name = _norm(r[fi])
        if not name:
            continue
        rec = by_name.get(name)
        if rec is None:
            rec = {"name": name, "levels": [], "min": None, "max": None, "step": None}
            by_name[name] = rec
            order.append(name)
        for idx, field in ((mi, "min"), (ma, "max"), (si, "step")):
            if idx >= 0 and _norm(r[idx]) != "" and js_is_finite(r[idx]):
                rec[field] = js_number(r[idx])
        if li >= 0:
            # "CMV; EF1a; CAG" in one cell, or one level per row - both end up here.
            for v in re.split(r"[;,|]", _norm(r[li])):
                v = _norm(v)
                if v and v not in rec["levels"]:
                    rec["levels"].append(v)

    factors = []
    for name in order:
        rec = by_name[name]
        if len(rec["levels"]) >= 2:
            factors.append({"name": rec["name"], "kind": "categorical", "levels": list(rec["levels"])})
        elif rec["min"] is not None and rec["max"] is not None and rec["max"] > rec["min"]:
            factors.append({"name": rec["name"], "kind": "numeric",
                            "min": rec["min"], "max": rec["max"], "step": rec["step"]})
        elif len(rec["levels"]) == 1:
            problems.append('"%s" has only one level (%s), so there is nothing to choose. '
                            "It is held fixed." % (rec["name"], rec["levels"][0]))
            factors.append({"name": rec["name"], "kind": "fixed", "levels": list(rec["levels"])})
        else:
            problems.append('"%s" has neither two or more levels nor a usable Min and Max, '
                            "so it was skipped." % rec["name"])
    return {"factors": factors, "problems": problems}


# --------------------------------------------------------------------- step 3

def parse_program(table, factor_names):
    """One row per future programme, described by its protein's attributes.

    Any column matching a catalogue factor is ignored with a note: the point of
    this flow is that the tool chooses those, not the sheet.
    """
    if not table or not table.get("rows"):
        return {"programs": [], "ignored": [], "skipped": []}
    fset = {_key(n) for n in (factor_names or [])}
    id_idx = -1
    for j, c in enumerate(table["columns"]):
        if ID_PICK.match(_norm(c)):
            id_idx = j
            break
    ignored = [c for c in table["columns"] if _key(c) in fset]
    skipped = [c for j, c in enumerate(table["columns"])
               if j != id_idx and _key(c) not in fset and ID_SKIP.match(_norm(c))]
    programs = []
    for i, r in enumerate(table["rows"]):
        attributes = {}
        for j, c in enumerate(table["columns"]):
            if _key(c) in fset or j == id_idx:
                continue
            # Every record-keeping column, not just the one that names the programme.
            if ID_SKIP.match(_norm(c)):
                continue
            v = _norm(r[j])
            if v != "":
                attributes[c] = v
        name = _norm(r[id_idx]) if id_idx >= 0 else ""
        programs.append({"id": name if (id_idx >= 0 and name) else "Programme %d" % (i + 1),
                         "attributes": attributes})
    return {"programs": programs, "ignored": ignored, "skipped": skipped}


def protein_columns(prof, factor_names, targets):
    """Protein attributes are whatever the history has that is not a chosen
    factor, not an outcome and not a record-keeping column.

    Shared with the interface for a reason: the form for entering a programme by
    hand offers one field per protein attribute. Two implementations of this
    would drift, and the symptom would be a form offering a field the planner
    then ignores, or worse omitting one it needs.
    """
    chosen = factor_names or []
    outs = targets or []
    return [c["name"] for c in prof["columns"]
            if c["name"] not in chosen and c["name"] not in outs
            and not ID_SKIP.match(c["name"]) and c["kind"] != "id"]


def attribute_choices(prof, name):
    """What the history holds for one attribute, so a hand-entry form can offer
    the real levels instead of a free-text box.

    A typo in a protein class reads downstream as "a value the historical runs
    do not contain", which correctly but pointlessly marks the programme
    untested. Offering the levels prevents the typo rather than reporting it.
    """
    col = next((c for c in prof["columns"] if c["name"] == name), None)
    if col is None:
        return None
    vals = [v for v in col["values"] if v is not None and _norm(v) != ""]
    if col["kind"] == "numeric":
        nums = sorted(v for v in (js_number(x) for x in vals) if v == v and abs(v) != math.inf)
        return {"kind": "numeric", "min": nums[0], "max": nums[-1],
                "median": quantile(nums, 0.5)}
    counts = {}
    for v in vals:
        k = _norm(v)
        counts[k] = counts.get(k, 0) + 1
    from .jsnum import js_object_keys
    keys = js_object_keys(counts)
    # JavaScript's sort is stable and this comparator has no tie-break, so equal
    # counts keep enumeration order.
    levels = sorted(keys, key=lambda k: -counts[k])
    return {"kind": "categorical", "levels": levels}


# --------------------------------------------------------------- the measurement

def transferability(prof, protein_cols, programs):
    """How much the history can say about a protein it has never seen.

    This is the measurement the whole module turns on, so it is separate, it
    returns numbers, and it is tested directly.

    An attribute that never varies carries no evidence at all: a model fitted
    where every row says "mAb" has not learnt what "mAb" does, it has learnt the
    intercept. Counting distinct proteins matters for the same reason - four
    hundred runs of one molecule are four hundred runs of one molecule, and the
    effective sample size for a cross-protein question is one, not four hundred.
    """
    varying, constant = [], []
    seen = {}
    for name in protein_cols:
        col = next((c for c in prof["columns"] if c["name"] == name), None)
        if col is None:
            continue
        vals = [v for v in col["values"] if v is not None and _norm(v) != ""]
        distinct = []
        for v in vals:
            d = js_number(v) if col["kind"] == "numeric" else _norm(v)
            if d not in distinct:
                distinct.append(d)
        info = {"distinct": len(distinct), "kind": col["kind"],
                "levels": None if col["kind"] == "numeric" else list(distinct)}
        if col["kind"] == "numeric":
            nums = sorted(v for v in (js_number(x) for x in vals) if v == v and abs(v) != math.inf)
            info["min"], info["max"] = nums[0], nums[-1]
        seen[name] = info
        (varying if len(distinct) > 1 else constant).append(name)

    # Distinct protein identities: the unique combinations, which is the sample
    # size that matters for a question about a different molecule.
    sigs = set()
    for i in range(prof["nRows"]):
        parts = []
        for nm in protein_cols:
            col = next((c for c in prof["columns"] if c["name"] == nm), None)
            parts.append(column_value_as_text(col, i) if col else "")
        sigs.add("\u0001".join(parts))
    n_proteins = len(sigs) if protein_cols else 0
    # With no protein columns at all there is nothing to transfer across, which
    # is a different situation from one protein and is reported as its own case.

    per_program = []
    for pg in (programs or []):
        novel, unseen, no_evidence = [], [], []
        for name in pg["attributes"]:
            info = seen.get(name)
            v = pg["attributes"][name]
            if info is None:
                novel.append({"field": name, "value": v,
                              "why": "this attribute is not in the historical runs at all"})
                continue
            if name in constant:
                no_evidence.append({
                    "field": name, "value": v,
                    "held": info["levels"][0] if info["levels"] else None,
                    "why": "every historical run has the same value for it, so the data "
                           "cannot say what changing it does"})
                continue
            if info["kind"] == "numeric":
                num = js_number(v)
                if js_is_finite(num) and (num < info["min"] or num > info["max"]):
                    unseen.append({"field": name, "value": num, "min": info["min"],
                                   "max": info["max"],
                                   "why": "outside the range of the historical runs"})
            elif info["levels"] is not None and _norm(v) not in info["levels"]:
                unseen.append({"field": name, "value": v, "levels": info["levels"],
                               "why": "a value the historical runs do not contain"})
        # The verdict, in the only three states that are honest here.
        # noEvidence belongs with untested, not with thin: if every historical
        # run holds the attribute fixed, a prediction for a different value is
        # not weakly supported, it is unsupported, and the tight interval beside
        # it comes from residuals that never saw the question change.
        if novel or unseen or no_evidence:
            standing = "untested"
        elif n_proteins <= 2:
            standing = "thin"
        else:
            standing = "supported"
        per_program.append({"id": pg["id"], "novel": novel, "unseen": unseen,
                            "noEvidence": no_evidence, "standing": standing})

    if n_proteins < 2:
        why = ("Every historical run is the same protein, so nothing here can say how a "
               "different one behaves.")
    elif not varying:
        why = ("No protein attribute varies across the historical runs, so the data cannot "
               "separate protein effects from anything else.")
    elif n_proteins <= 2:
        why = ("Only %d distinct proteins appear in the history. A protein effect fitted on "
               "two molecules is a line through two points." % n_proteins)
    else:
        why = "%d distinct proteins appear in the history." % n_proteins

    return {
        "nProteins": n_proteins, "varying": varying, "constant": constant,
        "detail": seen, "perProgram": per_program,
        # The flat refusal condition. With one protein in the history there is
        # no protein effect to learn, so any number this tool prints for a
        # different protein is the shape of the fit rather than evidence,
        # however tight the interval looks.
        "canTransfer": n_proteins >= 2 and len(varying) > 0,
        "why": why,
    }


# ------------------------------------------------------------------ enumeration

def candidates(factors, opt=None):
    """Every buildable vector from the catalogue.

    Capped, because a catalogue with six factors at four levels is four thousand
    combinations - but the cap samples rather than truncating, so the set still
    spans the catalogue instead of being the alphabetical first chunk of it.

    The cap is high because scoring a candidate is cheap and sampling means the
    best build may simply not be among the ones scored, which is a failure that
    is invisible in the output. Full enumeration is preferred wherever it is
    affordable, and the result says which happened.
    """
    opt = opt or {}
    cap = opt.get("cap") or 20000
    axes = []
    for f in factors:
        if f["kind"] == "fixed":
            continue
        if f["kind"] == "categorical":
            axes.append({"name": f["name"], "values": list(f["levels"])})
            continue
        lv = []
        if f.get("step") and f["step"] > 0:
            v = f["min"]
            while v <= f["max"] + 1e-9:
                lv.append(js_number(to_fixed(v, 6)))
                v += f["step"]
        # Without a step, three settings is the most a screen can use from one
        # numeric factor.
        if len(lv) < 2 or len(lv) > 12:
            lv = [f["min"], js_number(to_fixed((f["min"] + f["max"]) / 2, 6)), f["max"]]
        axes.append({"name": f["name"], "values": lv})

    fixed = {f["name"]: f["levels"][0] for f in factors if f["kind"] == "fixed"}
    if not axes:
        return {"list": [], "axes": axes, "fixed": fixed, "total": 0, "sampled": False}

    total = 1
    for a in axes:
        total *= len(a["values"])

    out = []
    if total <= cap:
        acc = {}

        def walk(i):
            if i == len(axes):
                merged = dict(fixed)
                merged.update(acc)
                out.append(merged)
                return
            for v in axes[i]["values"]:
                acc[axes[i]["name"]] = v
                walk(i + 1)
            acc.pop(axes[i]["name"], None)

        walk(0)
        return {"list": out, "axes": axes, "fixed": fixed, "total": total, "sampled": False}

    rand = rng(opt.get("seed") or 13)
    picked = set()
    while len(out) < cap and len(picked) < cap * 4:
        acc = {}
        for a in axes:
            acc[a["name"]] = a["values"][int(rand() * len(a["values"]))]
        sig = "\u0001".join(js_string(acc[a["name"]]) for a in axes)
        if sig in picked:
            continue
        picked.add(sig)
        merged = dict(fixed)
        merged.update(acc)
        out.append(merged)
    return {"list": out, "axes": axes, "fixed": fixed, "total": total, "sampled": True}


# --------------------------------------------------------------- level coverage

THIN_SHRINK = 0.5


def level_coverage(prof, factors, enc=None):
    """Which catalogue levels the model can actually tell apart.

    A text factor can fail in two quiet ways, and a catalogue of helper plasmids
    hits both. A level the historical runs never used cannot be placed at all,
    so every combination containing it is refused - on a catalogue offering six
    helpers where only three have ever been run, that is half the catalogue
    gone, and the only sign of it was a smaller number of scored candidates than
    the arithmetic implied. And a level that has been run only a handful of times
    is modelled, but on a number that is mostly the overall average rather than
    anything about that level.

    Neither is wrong as a decision. Both are indefensible as silent ones,
    because the reader has no way to tell a helper that scored badly from a
    helper the model could not see. So every catalogue level is classified
    against what the model actually holds: the levels whose own runs carry less
    weight in their own number than the prior does, with the weight stated
    rather than left for the reader to work out.
    """
    out = []
    for f in factors:
        if f["kind"] not in ("categorical", "fixed"):
            continue
        col = next((c for c in prof["columns"] if c["name"] == f["name"]), None)
        part = None
        if enc and enc.get("parts"):
            part = next((x for x in enc["parts"]
                         if x.get("col") and x["col"].get("name") == f["name"]), None)
        counts = {}
        for v in ((col or {}).get("values") or []):
            if v is None:
                continue
            k = _norm(v)
            if k != "":
                counts[k] = counts.get(k, 0) + 1
        seen = set(counts)
        # Only the smoothed encoding has a prior to be outweighed by; a one-hot
        # level has none.
        prior = TARGET_PRIOR if (part and part.get("type") == "high") else 0
        modelled, unseen, thin = [], [], []
        for lv in f["levels"]:
            v = _norm(lv)
            if v not in seen:
                unseen.append(lv)
                continue
            modelled.append(lv)
            if prior:
                shrink = prior / (counts[v] + prior)
                if shrink > THIN_SHRINK:
                    thin.append({"level": lv, "runs": counts[v], "shrink": shrink})
        if unseen or thin:
            out.append({"factor": f["name"], "modelled": modelled, "unseen": unseen,
                        "thin": thin, "total": len(f["levels"])})
    return out


# -------------------------------------------------------------------- run sheet

def replicates_for(r2):
    """How to spend the wells: on more vectors, or on more repeats of fewer.

    The first version of this spread them - every buildable vector once, then
    repeats - which is right for mapping a design space and wrong for the job
    this tool has, which is picking a vector to build. Measured over 4,000
    simulated sheets of 48 wells drawn from 36 candidates, scoring how often the
    sheet identifies the truly best vector:

      ==========================  ===============  ===============
      strategy                    poor prediction  good prediction
      ==========================  ===============  ===============
      36 distinct x 1                       33.1%            36.4%
      top 24 x 2                            39.1%            42.3%
      top 16 x 3                            41.9%            48.4%
      top 12 x 4                            41.4%            55.9%
      top 8 x 6                             37.2%            61.4%
      ==========================  ===============  ===============

    Running everything once is the worst option in every column, because a
    single observation of a vector is mostly noise and the sheet ends up ranking
    noise. How far to concentrate depends on how much the prediction can be
    trusted, which is not a matter of taste - cross-validation measured it. So
    the replicate count is read off that R-squared rather than guessed, and a
    model that cannot predict spreads wider because its ranking deserves less
    weight.
    """
    # Correlation, not variance explained: the ranking is what matters here.
    value = 0 if r2 is None else r2
    r = math.sqrt(max(0.0, min(1.0, value)))
    return 3 if r < 0.45 else (4 if r < 0.70 else 6)


def _balance_of(axes, rows, counts_of):
    bal = {}
    for a in axes:
        vs = [counts_of(a, v) for v in a["values"]]
        bal[a["name"]] = {"counts": vs, "spread": max(vs) - min(vs)}
    return bal


def run_sheet(scored, axes, opt=None):
    """A run sheet chosen from the scored candidates.

    Balance first, then promise: every level of every factor should appear about
    equally often, because a sheet that runs CMV eight times and SV40 once
    cannot tell you anything about SV40 whatever its predictions say. Among
    equally balancing choices the better-predicted one wins, so the sheet leans
    towards configurations worth building without becoming a list of
    near-duplicates.

    The balance achieved is returned, and asserted in the tests rather than
    claimed here.
    """
    opt = opt or {}
    if not scored:
        return {"sheet": [], "balance": None, "counts": {}, "distinct": 0, "replicated": 0}

    # A plate holds more wells than a catalogue holds vectors. Forty-eight
    # strains built from a catalogue of thirty-six used to come back as
    # thirty-six, quietly - the sheet simply stopped and nothing said why half a
    # plate was missing.
    #
    # So a sheet longer than the catalogue replicates, deliberately and evenly,
    # and says which rows are repeats. That is not padding: replication is the
    # only thing that measures pure error, and without an estimate of pure error
    # there is no way to tell a real lack of fit from ordinary run-to-run
    # scatter. What it does not buy is information about settings nobody is
    # running, which is why the count of distinct vectors is reported beside the
    # number of runs rather than folded into it.
    runs = max(2, opt.get("runs") or 12)

    if opt.get("purpose") == "select":
        # Spend the budget on the best-predicted few, repeated. The candidates
        # arrive already sorted best-first, so this is a prefix of them.
        reps = max(2, opt.get("replicates") or 3)
        k = max(2, min(len(scored), runs // reps))
        picked = scored[:k]
        rows = []
        for copy in range(1, reps + 1):
            for c in picked:
                row = dict(c)
                row["replicate"] = copy
                rows.append(row)
        # Any wells left over by the division go to the very best candidates.
        i = 0
        while len(rows) < runs:
            c = picked[i % len(picked)]
            row = dict(c)
            row["replicate"] = reps + 1 + i // len(picked)
            rows.append(row)
            i += 1
        counts = {}
        for a in axes:
            cnt = {js_string(v): 0 for v in a["values"]}
            for x in rows:
                kk = js_string(x["config"][a["name"]])
                cnt[kk] = cnt.get(kk, 0) + 1
            counts[a["name"]] = cnt
        bal = _balance_of(axes, rows, lambda a, v: counts[a["name"]].get(js_string(v), 0))
        order = shuffle(js_range(len(rows)), rng(opt.get("seed") or 29))
        sheet = []
        for i, c in enumerate(rows):
            row = dict(c)
            row["std"] = i + 1
            sheet.append(row)
        for pos, ri in enumerate(order):
            sheet[ri]["run"] = pos + 1
        sheet.sort(key=lambda r: r["run"])
        return {"sheet": sheet, "balance": bal, "counts": {}, "distinct": k,
                "replicated": len(rows) - k, "purpose": "select", "replicates": reps}

    counts = {}
    for a in axes:
        counts[a["name"]] = {js_string(v): 0 for v in a["values"]}
    chosen = []
    times_used = [0] * len(scored)

    # How badly a pick would skew the sheet: the count it would push up, summed
    # over factors.
    def cost(c):
        return sum(counts[a["name"]].get(js_string(c["config"][a["name"]]), 0) for a in axes)

    for _ in range(runs):
        best, best_rep, best_cost, best_val = None, math.inf, math.inf, -math.inf
        for i in range(len(scored)):
            rep, cst = times_used[i], cost(scored[i])
            value = scored[i].get("value")
            val = value if (value is not None and js_is_finite(value)) else -math.inf
            # Everything unused comes first, so a sheet shorter than the
            # catalogue behaves exactly as before and only a longer one starts a
            # second pass. Then balance, then the better-predicted build.
            if rep < best_rep or (rep == best_rep and (cst < best_cost or
                                  (cst == best_cost and val > best_val))):
                best, best_rep, best_cost, best_val = i, rep, cst, val
        if best is None:
            break
        times_used[best] += 1
        c = scored[best]
        for a in axes:
            k = js_string(c["config"][a["name"]])
            counts[a["name"]][k] = counts[a["name"]].get(k, 0) + 1
        row = dict(c)
        row["replicate"] = times_used[best]
        chosen.append(row)

    distinct = sum(1 for v in times_used if v > 0)
    # What balance actually came out, per factor: the gap between the most and
    # least used level. Zero means every level appears the same number of times.
    # Reported as absent rather than as zero spread when nothing was chosen: a
    # spread of 0 over all-zero counts reads as "perfectly balanced", which is
    # the most flattering possible description of an empty sheet.
    balance = None
    if chosen:
        balance = _balance_of(axes, chosen,
                              lambda a, v: counts[a["name"]].get(js_string(v), 0))
    order = shuffle(js_range(len(chosen)), rng(opt.get("seed") or 29))
    sheet = []
    for i, c in enumerate(chosen):
        row = dict(c)
        row["std"] = i + 1
        sheet.append(row)
    for pos, ri in enumerate(order):
        sheet[ri]["run"] = pos + 1
    sheet.sort(key=lambda r: r["run"])
    return {"sheet": sheet, "balance": balance, "counts": counts, "distinct": distinct,
            "replicated": len(chosen) - distinct, "purpose": "screen", "replicates": 1}
