"""BOSS vector selection - the Python port of the browser tool's vector bench.

Scope: the selection logic (catalogue parsing, programme parsing, protein
transferability, candidate enumeration, level coverage and run-sheet
construction). Model fitting and prediction intervals are the second half of the
port and are not here yet; see ``program.py``'s module docstring.

Everything in this package is pure computation. It opens no sockets, writes no
files and reads nothing but the paths it is handed.
"""

from .program import (
    attribute_choices,
    candidates,
    level_coverage,
    parse_catalogue,
    parse_program,
    protein_columns,
    replicates_for,
    run_sheet,
    transferability,
)
from .profile import profile
from .table import parse_table, read_table

__version__ = "0.1.0"

__all__ = [
    "attribute_choices", "candidates", "level_coverage", "parse_catalogue",
    "parse_program", "parse_table", "profile", "protein_columns", "read_table",
    "replicates_for", "run_sheet", "transferability", "__version__",
]
