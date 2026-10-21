"""Elite Ice Hockey League (UK) from eliteleague.co.uk's stats pages."""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, cells, clean_team, finish, phase_key, soup, table_rows

BASE = "https://www.eliteleague.co.uk"
PAGE = 50


@cache
def _season_ids() -> dict[tuple[int, str], tuple[str, str]]:
    """(start year, phase) -> (id_season, id_stage), from the season dropdown.
    League seasons only; Challenge Cup entries are skipped."""
    out = {}
    page = soup(f"{BASE}/stats/players")
    for opt in page.select('select[name="id_season"] option'):
        text, value = opt.get_text(" ", strip=True), opt.get("value", "")
        m = re.search(r"(\d{4})/\d{2,4}", text)
        ids = dict(re.findall(r"(id_season|id_stage)=(\d+)", value))
        if not m or "cup" in text.lower() or "id_season" not in ids:
            continue
        phase = "playoffs" if ids.get("id_stage") == "2" else "regular"
        out[(int(m.group(1)), phase)] = (ids["id_season"], ids.get("id_stage", "1"))
    return out


def _ids(y: int, phase: str) -> tuple[str, str]:
    try:
        return _season_ids()[(y, phase_key(phase))]
    except KeyError:
        raise ValueError(f"EIHL has no {phase_key(phase)} season {y}-{y + 1}") from None


def _paged(path: str, y: int, phase: str) -> pd.DataFrame:
    sid, stage = _ids(y, phase)
    frames, seen = [], set()
    for start in range(0, 5000, PAGE):
        page = soup(f"{BASE}{path}", id_season=sid, id_stage=stage, start=start)
        table = page.find("table")
        if table is None:
            break
        head = [th.get_text(" ", strip=True) for th in table.select("thead th")] or cells(table.find("tr"))
        rows = [cells(r) for r in table.select("tbody tr")]
        rows = [r for r in rows if len(r) == len(head)]
        key = tuple(map(tuple, rows))
        if not rows or key in seen:
            break
        seen.add(key)
        frames.append(pd.DataFrame(rows, columns=_unique(head)))
        if len(rows) < PAGE:
            break
    return pd.concat(frames, ignore_index=True).drop_duplicates() if frames else pd.DataFrame()


def _unique(cols):
    out, seen = [], {}
    for c in cols:
        c = c or "col"
        seen[c] = seen.get(c, -1) + 1
        out.append(c if seen[c] == 0 else f"{c}_{seen[c]}")
    return out


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _paged("/stats/players", y, phase)
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "Player name": "player", "Team": "team", "Position": "position", "Gp": "gp", "G": "g", "A": "a",
        "PTS": "pts", "PIM": "pim", "+/-": "plus_minus", "Jersey": "number", "SOG": "shots",
        "S": "sh_pct"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _paged("/stats/goalies", y, phase)
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "Player name": "player", "Team": "team", "Gp": "gp", "W": "w", "L": "l", "SO": "so",
        "SA": "shots_against", "GA": "ga", "MIN": "toi", "GAA": "gaa", "SVS%": "sv_pct", "Jersey": "number"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    sid, _ = _ids(y, phase)
    page = soup(f"{BASE}/standings/{y + 1}/{sid}-elite-ice-hockey-league")
    table = page.find("table")
    if table is None:
        return pd.DataFrame()
    df = table_rows(table)
    if "Team" in df:
        df["Team"] = df["Team"].map(clean_team)
    return finish(df, "standings", league, y, "regular", rename={
        "Team": "team", "GP": "gp", "W": "w", "L": "l", "OTW": "otw", "OTL": "otl", "PTS": "pts",
        "Pts": "pts", "GF": "gf", "GA": "ga", "#": "rank", "Pos": "rank"})
