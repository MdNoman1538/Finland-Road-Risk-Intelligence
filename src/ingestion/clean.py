"""Cleaning rules for the raw crash data, written once as SQL expressions.

Every rule here comes from a measurement of the real 2014-2025 files (devlog 2026-11-22).
Each function takes a column expression and returns a SQL expression, so the same rule is
used for both source formats (2014-21 and 2022+) and for participants: no second copy that
could drift.

Canonical forms in the database:
- missing                -> NULL (never a string such as 'Unknown'); labelled at the output layer
- category text          -> trimmed, inner whitespace collapsed, original Finnish spelling kept
- heavy_vehicle          -> BOOLEAN
- speed_limit            -> positive INTEGER or NULL
"""

# Spellings of "no value" found in the raw files (compared lower-case after trimming).
# 'tuntematon kulkuväline' ("unknown vehicle") appears only in participant vehicle types.
MISSING_TOKENS: tuple[str, ...] = (
    "",
    "-",
    "ei arvoa",
    "ei tiedossa",
    "unknown",
    "tuntematon",
    "tuntematon kulkuväline",
)

# heavy_vehicle was spelled on/ei (2014-21), true/false (2022), kyllä/ei (2023+).
# Checked against participants: 99.8-100 % of "yes" crashes have a lorry or bus participant,
# 0 % of "no" crashes do.
HEAVY_TRUE: tuple[str, ...] = ("on", "true", "kyllä")
HEAVY_FALSE: tuple[str, ...] = ("ei", "false")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def _normalised(col: str) -> str:
    return f"TRIM(regexp_replace(CAST({col} AS VARCHAR), '\\s+', ' ', 'g'))"


def text(col: str) -> str:
    """Category text: whitespace normalised; any spelling of "missing" becomes NULL."""
    norm = _normalised(col)
    return f"CASE WHEN LOWER({norm}) IN ({_sql_list(MISSING_TOKENS)}) THEN NULL ELSE {norm} END"


def lower_text(col: str) -> str:
    """Like text(), lower-cased (participant vehicle types are matched case-insensitively)."""
    return f"LOWER({text(col)})"


def heavy_vehicle(col: str) -> str:
    """One boolean for three spellings. An unseen spelling stops the build (error()) instead
    of being guessed, so a new source format is noticed the day it arrives."""
    norm = f"LOWER({_normalised(col)})"
    return (
        f"CASE WHEN {col} IS NULL OR {norm} IN ({_sql_list(MISSING_TOKENS)}) THEN NULL "
        f"WHEN {norm} IN ({_sql_list(HEAVY_TRUE)}) THEN TRUE "
        f"WHEN {norm} IN ({_sql_list(HEAVY_FALSE)}) THEN FALSE "
        f"ELSE error('unmapped heavy_vehicle value: ' || {norm}) END"
    )


def positive_int(col: str) -> str:
    """-1 (2014-21) and empty (2022+) both mean "not recorded"; 0 is never a real value."""
    value = f"TRY_CAST({col} AS INTEGER)"
    return f"CASE WHEN {value} > 0 THEN {value} END"


def non_negative_int(col: str) -> str:
    """For values where 0 is real (a vehicle under one year old); -1 means "not recorded"."""
    value = f"TRY_CAST({col} AS INTEGER)"
    return f"CASE WHEN {value} >= 0 THEN {value} END"


def month(col: str) -> str:
    """1-12, NULL if empty. Anything else stops the build: a bad month means a format change."""
    value = f"TRY_CAST({col} AS INTEGER)"
    return (
        f"CASE WHEN NULLIF(TRIM(CAST({col} AS VARCHAR)), '') IS NULL THEN NULL "
        f"WHEN {value} BETWEEN 1 AND 12 THEN {value} "
        f"ELSE error('impossible month value: ' || CAST({col} AS VARCHAR)) END"
    )


speed_limit = positive_int
