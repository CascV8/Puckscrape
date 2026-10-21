"""Shared helpers for the league-website adapters."""

from __future__ import annotations

import re
from functools import lru_cache

import pandas as pd
from bs4 import BeautifulSoup

from .. import _http

# Core columns every adapter maps onto where the site has them. Anything else a
# site publishes is kept too, after these, in snake_case.
CORE = {
    "skaters": ["league", "season", "phase", "player", "player_id", "team", "position",
                "gp", "g", "a", "pts", "pim", "plus_minus"],
    "goalies": ["league", "season", "phase", "player", "player_id", "team",
                "gp", "w", "l", "ga", "saves", "sv_pct", "gaa", "so", "toi"],
    "standings": ["league", "season", "phase", "team", "gp", "w", "l", "otw", "otl", "pts", "gf", "ga"],
}



def season_label(y: int) -> str:
    return f"{y}-{(y + 1) % 100:02d}"


@lru_cache(maxsize=512)
def fetch(url: str, params: tuple = ()) -> bytes:
    """GET with the shared throttle, cached for the session (pages are re-read
    when, say, skaters() and goalies() both need the same team page)."""
    return _http.get(url, params=dict(params) or None).content


def soup(url: str, **params) -> BeautifulSoup:
    return BeautifulSoup(fetch(url, tuple(sorted(params.items()))), "html.parser")


def get_json(url: str, **params):
    return _http.get_json(url, params=params or None)


def cells(row) -> list[str]:
    return [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]


def find_table(page: BeautifulSoup, *labels: str):
    """The innermost table whose header row contains every label."""
    for table in page.find_all("table"):
        if table.find("table"):
            continue
        for row in table.find_all("tr")[:3]:
            head = cells(row)
            if all(l in head for l in labels):
                return table
    return None


def table_rows(table, header_labels: tuple[str, ...] = ()) -> pd.DataFrame:
    """Rows of an HTML table as a DataFrame, using the first row that holds the
    header labels (or the <thead>). Repeated header rows are dropped."""
    rows = table.find_all("tr")
    header, start = None, 0
    for i, r in enumerate(rows[:3]):
        c = cells(r)
        if not header_labels or all(l in c for l in header_labels):
            header, start = c, i + 1
            break
    if header is None:
        return pd.DataFrame()
    header = _dedupe(header)
    data = [c for c in (cells(r) for r in rows[start:]) if len(c) == len(header) and c != header]
    return pd.DataFrame(data, columns=header)


def _dedupe(cols: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for c in cols:
        c = c or "col"
        if c in seen:
            seen[c] += 1
            c = f"{c}_{seen[c]}"
        else:
            seen[c] = 0
        out.append(c)
    return out


def to_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric-looking text columns -> numbers. 'MM:SS' clocks and names stay text;
    decimal commas ('2,45') are understood."""
    for col in df.columns:
        s = df[col]
        if s.dtype != object and not pd.api.types.is_string_dtype(s):
            continue
        t = s.astype("string").str.strip()
        t = t.mask(t.str.fullmatch(r"[-–—]*\s*\**"), pd.NA)  # '', '-', '–', '– *' mean "no value"
        t = t.str.rstrip("%").str.strip().str.replace(r"^\+(?=\d)", "", regex=True)
        nonnull = t.dropna()
        if nonnull.empty:
            continue
        if nonnull.str.fullmatch(r"-?\d+(?:,\d+)?").all() and nonnull.str.contains(",").any():
            t = t.str.replace(",", ".", regex=False)
        num = pd.to_numeric(t, errors="coerce")
        if num.notna().sum() == nonnull.size:
            df[col] = num
    return df


def finish(df: pd.DataFrame, kind: str, league: str, y: int, phase: str,
           rename: dict[str, str] | None = None, drop: tuple[str, ...] = ()) -> pd.DataFrame:
    """Rename to core names, add league/season/phase, coerce numbers, order columns."""
    if df.empty:
        return df
    df = df.rename(columns=rename or {}).drop(columns=[c for c in drop if c in df], errors="ignore")
    df.columns = [_snake(c) for c in df.columns]
    df = df.loc[:, ~df.columns.duplicated()]
    df.insert(0, "league", league)
    df.insert(1, "season", season_label(y))
    df.insert(2, "phase", phase)
    df = to_numbers(df)
    if kind == "goalies" and "sv_pct" in df and pd.api.types.is_numeric_dtype(df["sv_pct"]) \
            and df["sv_pct"].max() > 1:
        df["sv_pct"] = df["sv_pct"] / 100  # '92.3' -> 0.923, like every other league
    for col in df.columns:
        if pd.api.types.is_float_dtype(df[col]):
            vals = df[col].dropna()
            if len(vals) and (vals == vals.round()).all():
                df[col] = df[col].astype("Int64")
            else:
                df[col] = df[col].round(4)
    core = [c for c in CORE[kind] if c in df.columns]
    return df[core + [c for c in df.columns if c not in core]].reset_index(drop=True)


def _snake(name: str) -> str:
    name = str(name).replace("%", "_pct").replace("+/-", "plus_minus").replace("/", "_per_")
    name = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    return re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower() or "col"


def phase_key(phase: str) -> str:
    p = phase.lower()
    if p.startswith("reg"):
        return "regular"
    if p.startswith("play"):
        return "playoffs"
    raise ValueError(f"phase must be 'regular' or 'playoffs', not {phase!r}")


def clean_team(name):
    """Drop rank numbers and clinch markers some sites glue to team names:
    '1 c - Belfast Giants', 'Krefeld Pinguine KEV ✓ *'."""
    if not isinstance(name, str):
        return name
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"^\d+\s+", "", name)
    name = re.sub(r"^[a-z*]{1,4}\s+-\s+", "", name)
    return re.sub(r"[\s✓✔✗*†‡]+$", "", name).strip()


class Unsupported(NotImplementedError):
    """This league's site doesn't publish that table."""
