"""Delimited-text reading, ported from engine.js.

Scope note: engine.js also reads JSON in four shapes (records, enveloped
records, column arrays, newline-delimited). That is not ported here. The vector
selection flow takes three files - historical runs, a parts catalogue and a list
of incoming programmes - and all three are spreadsheet exports in practice. The
JSON reader is 90 lines of shape detection serving a case this tool has not
met, so it is left out rather than ported untested. ``parse_table`` raises on
input that looks like JSON instead of guessing.
"""

from .jsnum import JS_WHITESPACE, js_trim

DELIMITERS = (",", "\t", ";", "|")


def detect_delimiter(text):
    """The delimiter that appears most often in the first non-blank line,
    ignoring occurrences inside quotes."""
    first_line = ""
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip():
            first_line = line
            break
    best, best_count = ",", 0
    for delimiter in DELIMITERS:
        count, in_quotes = 0, False
        for ch in first_line:
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == delimiter and not in_quotes:
                count += 1
        if count > best_count:
            best, best_count = delimiter, count
    return best


def parse_csv(text):
    """A character-by-character reader matching engine.js exactly.

    Two details are deliberate rather than accidental, and are kept because the
    JavaScript has them: a quote only opens a quoted field when the field is so
    far empty (so ``ab"cd`` keeps its quote as data), and a trailing field with
    no newline still produces a row.
    """
    text = str(text or "")
    if text.startswith("﻿"):
        text = text[1:]
    delimiter = detect_delimiter(text)
    rows, row, field, in_quotes = [], [], "", False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field += '"'
                    i += 1
                else:
                    in_quotes = False
            else:
                field += ch
        elif ch == '"' and field == "":
            in_quotes = True
        elif ch == delimiter:
            row.append(field)
            field = ""
        elif ch in ("\n", "\r"):
            if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 1
            row.append(field)
            rows.append(row)
            row, field = [], ""
        else:
            field += ch
        i += 1
    if field != "" or row:
        row.append(field)
        rows.append(row)
    return parse_grid(rows)


def parse_grid(grid):
    """Header row plus body: blank rows dropped, nameless columns named for
    their position, repeated names numbered, rows padded or trimmed to the
    header's width.

    The duplicate-name rule is copied rather than improved. Three columns called
    "Titer" become "Titer", "Titer (2)", "Titer (3)"; a fourth also becomes
    "Titer (2)", because the counter is kept against the original name only and
    the generated names are never registered. Changing that here would make the
    two implementations disagree on a real file, which is worse than the
    duplicate.
    """
    clean = [r for r in grid if any(js_trim(str(c)) != "" for c in r)]
    if not clean:
        return {"columns": [], "rows": []}
    seen = {}
    columns = []
    for i, head in enumerate(clean[0]):
        name = js_trim(str(head)) or "Column %d" % (i + 1)
        if seen.get(name):
            seen[name] += 1
            name = "%s (%d)" % (name, seen[name])
        else:
            seen[name] = 1
        columns.append(name)
    width = len(columns)
    rows = []
    for r in clean[1:]:
        out = [js_trim(str(c)) for c in r[:width]]
        out.extend([""] * (width - len(out)))
        rows.append(out)
    return {"columns": columns, "rows": rows}


def looks_json(text):
    stripped = str(text or "")
    if stripped.startswith("﻿"):
        stripped = stripped[1:]
    stripped = stripped.lstrip(JS_WHITESPACE)
    return stripped[:1] in ("{", "[")


def parse_table(text, name=None):
    """One door for the formats this port reads.

    Unlike engine.js this does not fall back to JSON; see the module docstring.
    """
    if (name or "").lower().endswith((".json", ".ndjson", ".jsonl")) or looks_json(text):
        raise ValueError(
            "This reader handles delimited text only. The JSON shapes the browser "
            "tool accepts are not ported; export the sheet as CSV or TSV."
        )
    return parse_csv(text)


def read_table(path):
    """Read a delimited file from disk. Encoding is UTF-8 with a tolerated BOM,
    which is what Excel writes."""
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return parse_table(fh.read(), path)
