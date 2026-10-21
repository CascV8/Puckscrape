"""Swiss Ice Hockey Federation statistics API (National League, Swiss League, MyHockey League).

Seasons are keyed by end year (2026 = 2025-26) and each season has its own
phase ids, which the API lists when asked for '<season>/0'.
"""

from __future__ import annotations

from functools import cache

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

API = "https://data.sihf.ch/Statistic/api/cms/cache300"
_PHASE_NAME = {"regular": "Regular Season", "playoffs": "Playoff Overall"}


def _query(alias: str, league_id: int, filter_query: str, take: int = 2000, skip: int = 0) -> dict:
    return get_json(API, alias=alias, searchQuery=f"1//{league_id}", filterQuery=filter_query,
                    filterBy="Season,Phase", orderBy="", orderByDescending="true", take=take, skip=skip,
                    language="en")


@cache
def _phase_ids(league_id: int, y: int, phase: str) -> tuple[tuple[str, str], ...]:
    """(id, name) of the phase(s) making up a season's regular season or playoffs.
    Usually one ('Regular Season'); the MyHockey League has 'Regular Season Gr. West'
    and 'Gr. Ost'."""
    data = _query("player", league_id, f"{y + 1}/0", take=1)
    entries = [(e["alias"], e["name"]) for f in data.get("filters", []) if f["alias"] == "Phase"
               for e in f["entries"]]
    exact = [e for e in entries if e[1] == _PHASE_NAME[phase]]
    if exact:
        return tuple(exact)
    groups = [e for e in entries if phase == "regular" and e[1].startswith("Regular Season")]
    if groups:
        return tuple(groups)
    raise ValueError(f"no {phase} phase for season {y}-{y + 1}")


def _table(alias: str, opts: dict, y: int, phase: str) -> pd.DataFrame:
    p = phase_key(phase)
    flat = []
    for phase_id, phase_name in _phase_ids(opts["league_id"], y, p):
        for rec in _phase_rows(alias, opts["league_id"], f"{y + 1}/{phase_id}"):
            if phase_name != _PHASE_NAME[p]:
                rec["group"] = phase_name
            flat.append(rec)
    return pd.DataFrame(flat)


def _phase_rows(alias: str, league_id: int, fq: str) -> list[dict]:
    first = _query(alias, league_id, fq)
    header = [h["alias"] for h in first["header"]]
    rows = list(first["data"])
    for page in range(2, (first.get("pages") or 1) + 1):
        rows += _query(alias, league_id, fq, skip=(page - 1) * 2000)["data"]
    rows = [r for r in rows if len(r) == len(header)]
    flat = []
    for r in rows:
        rec = {}
        for k, v in zip(header, r):
            if isinstance(v, dict):
                rec[k] = v.get("name")
                rec[f"{k}_id"] = v.get("id")
                if v.get("acronym"):
                    rec[f"{k}_code"] = v["acronym"]
            else:
                rec[k] = v
        flat.append(rec)
    return flat


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _table("player", opts, y, phase)
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "gamesPlayed": "gp", "goals": "g", "assists": "a", "points": "pts", "pimTotal": "pim",
        "plusMinus": "plus_minus"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _table("goalkeeper", opts, y, phase)
    if "savesPercentage" in df:
        pct = pd.to_numeric(df["savesPercentage"], errors="coerce")
        df["savesPercentage"] = pct / 100 if pct.max() > 1 else pct
    if "secondsPlayed" in df:
        df["toi"] = pd.to_numeric(df["secondsPlayed"], errors="coerce") / 60
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "gamesPlayed": "gp", "goalsAgainst": "ga", "saves": "saves", "savesPercentage": "sv_pct",
        "goalsAgainstAverage": "gaa"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    # The standings table stops at 26 games for 2024-25 and 2025-26 (full 52 for
    # 2023-24), so it isn't trustworthy yet.
    raise Unsupported("SIHF's standings table is incomplete for recent seasons")
    df = _table("standing", opts, y, phase)
    return finish(df, "standings", league, y, phase_key(phase), rename={
        "gamesPlayed": "gp", "points": "pts", "goalsFor": "gf", "goalsAgainst": "ga",
        "gamesWonInTime": "w", "gamesLostInTime": "l", "gamesWonExtraTime": "otw",
        "gamesLostExtraTime": "otl"})
