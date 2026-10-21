"""ICE Hockey League (Austria and neighbours) from the JSON files behind ice.hockey's stats widgets.

Skaters come from per-part files ("league parts": each season's regular season
and playoffs). The season -> part map lives in the widget script, so it's read
from there and stays current as seasons are added.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from .. import _http
from ._common import Unsupported, finish, get_json, phase_key

S3 = "https://s3.dualstack.eu-west-1.amazonaws.com/icehl.hokejovyzapis.cz"
WIDGET = "https://icestats.at/esp-widget-playerstats-new.js"


@cache
def _parts() -> dict[tuple[int, str], int]:
    js = _http.get(WIDGET).text
    out = {}
    for year, reg, po in re.findall(r"(\d{4}):\{regular:(\d+),playoff:(\d+)\}", js):
        out[(int(year), "regular")] = int(reg)
        out[(int(year), "playoffs")] = int(po)
    return out


def _part(y: int, phase: str) -> int:
    try:
        return _parts()[(y, phase_key(phase))]
    except KeyError:
        raise ValueError(f"ICEHL has no {phase_key(phase)} data for {y}-{y + 1}") from None


@cache
def _team_names(y: int) -> dict[str, str]:
    groups = get_json(f"{S3}/tables/{y}/1.json")
    return {c["shortcut"]: c["name"] for g in groups for c in g.get("clubs", [])}


def _total(v):
    """Some counts are split {'home': x, 'away': y}."""
    return sum(x for x in v.values() if isinstance(x, (int, float))) if isinstance(v, dict) else v


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    players = get_json(f"{S3}/league-part-players-stats/{_part(y, phase)}.json")
    names = _team_names(y)
    rows = []
    for p in players:
        st = p.get("statistics") or {}
        rows.append({
            "player": p.get("name"), "player_id": p.get("id"), "team": names.get(st.get("teamShortcut"), st.get("teamShortcut")),
            "team_code": st.get("teamShortcut"), "position": p.get("position"), "number": p.get("jersey"),
            "birth_date": p.get("birthdate"), "nationality": p.get("nationalityShort"),
            **{k: _total(v) for k, v in st.items() if not k.startswith("visible") and k not in ("teamId", "teamShortcut")},
        })
    df = pd.DataFrame(rows)
    if not df.empty and {"positive", "negative"} <= set(df.columns):
        df["plus_minus"] = df["positive"] - df["negative"]
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "games": "gp", "goals": "g", "assists": "a", "points": "pts", "penaltyMinutes": "pim",
        "shotsOnGoal": "shots", "timeonice": "toi_seconds"})


# The per-year goalie and standings files are complete only from 2025-26; earlier
# years hold a partial table (10 teams, 13-17 games).
FIRST_FULL_YEAR = 2025


def _check_year(y: int, what: str) -> None:
    if y < FIRST_FULL_YEAR:
        raise Unsupported(f"ICEHL {what} files are incomplete before {FIRST_FULL_YEAR}-{FIRST_FULL_YEAR % 100 + 1}")


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("only the ICEHL regular-season goalie file is wired")
    _check_year(y, "goalie")
    df = pd.DataFrame(get_json(f"{S3}/league-top-goalies/{y}/1.json"))
    if df.empty:
        return df
    df.insert(0, "player", df["name"].str.strip() + " " + df["surname"].str.strip())
    df = df.drop(columns=[c for c in df.columns if c in ("name", "surname", "photo", "gateZone")
                          or c.startswith(("visible", "stars", "milestone"))])
    return finish(df, "goalies", league, y, "regular", rename={
        "playerId": "player_id", "teamName": "team", "matches": "gp", "wonMatches": "w",
        "lostMatches": "l", "goalsAgainst": "ga", "savesPercent": "sv_pct", "average": "gaa",
        "zeros": "so", "minutesInPlay": "toi", "jersey": "number"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    _check_year(y, "standings")
    groups = get_json(f"{S3}/tables/{y}/1.json")
    rows = [dict(c, group=g.get("groupName") or None) for g in groups for c in g.get("clubs", [])]
    df = pd.DataFrame(rows)
    return finish(df, "standings", league, y, "regular",
                  drop=("teamOriginal", "liveGameScore", "positionChange", "last10", "id", "partTeamId"),
                  rename={"name": "team", "games": "gp", "wins": "w", "losts": "l", "winsOt": "otw",
                          "lostsOt": "otl", "points": "pts", "score1": "gf", "score2": "ga",
                          "position": "rank"})
