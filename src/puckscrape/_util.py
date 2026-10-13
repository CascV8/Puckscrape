"""Season parsing and small DataFrame helpers shared by the scrapers."""

from __future__ import annotations

import re
from collections.abc import Iterable

import pandas as pd


def start_year(season: int | str) -> int:
    """Normalize any season spelling to its starting year.

    Accepts 2024, "2024", "2024-25", "2024-2025", "20242025" -> 2024.
    A bare year always means the season that *starts* that year.
    """
    s = str(season).strip()
    if m := re.fullmatch(r"(\d{4})(?:-?(\d{2}|\d{4}))?", s):
        first = int(m.group(1))
        if m.group(2):
            second = int(m.group(2)[-2:])
            if second != (first + 1) % 100:
                raise ValueError(f"not a consecutive season: {season!r}")
        return first
    raise ValueError(f"can't parse season {season!r}; try 2024, '2024-25' or '20242025'")


def nhl_season(season: int | str) -> str:
    """-> '20242025' (NHL API format)."""
    y = start_year(season)
    return f"{y}{y + 1}"


def ep_season(season: int | str) -> str:
    """-> '2024-2025' (Elite Prospects format)."""
    y = start_year(season)
    return f"{y}-{y + 1}"


def as_list(x) -> list:
    """Let every public function take one value or many."""
    if isinstance(x, (str, int)):
        return [x]
    if isinstance(x, Iterable):
        return list(x)
    return [x]


def snake(name: str) -> str:
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()


def snake_columns(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns=snake)


def clock_to_seconds(clock: pd.Series) -> pd.Series:
    """'MM:SS' -> integer seconds (NaN-safe)."""
    parts = clock.str.split(":", expand=True)
    if parts.shape[1] < 2:
        return pd.Series(pd.NA, index=clock.index, dtype="Int64")
    return (pd.to_numeric(parts[0]) * 60 + pd.to_numeric(parts[1])).astype("Int64")


def localized(value) -> str | None:
    """NHL API wraps names as {'default': 'X', 'fr': ...}."""
    if isinstance(value, dict):
        return value.get("default")
    return value
