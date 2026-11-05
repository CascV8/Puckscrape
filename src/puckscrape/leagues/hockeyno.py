"""Norwegian leagues from the Norwegian Ice Hockey Federation's results service
(the keyless API behind live.hockey.no).

A season is one federation "season"; each league is a tournament in it ("U18
Elite", "U20 Elite Innledende", "U20 Elite A"...). The national championship
play-offs (NM) are separate tournaments ("U18 NM kvartfinaler", "NM sluttspill
U18"...). Every row keeps its tournament in a ``stage`` column.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

API = "https://sf34-terminlister-prod-app.azurewebsites.net/"
_SPORT, _FEDERATION = 152, "373"   # ice hockey; the Norwegian federation's org id
_SKIP = re.compile(r"trening|samling|test|intern|nations|cup|turnering|region", re.I)


@cache
def _season_id(y: int) -> str:
    seasons = (get_json(API + "ta/Seasons/", sportId=_SPORT, year=y) or {}).get("seasons") or []
    for s in seasons:
        if str(s.get("orgIdOwner")) == _FEDERATION and f"{y}/{y + 1}" in s.get("seasonName", ""):
            return str(s["seasonId"])
    raise ValueError(f"no Norwegian federation season {y}-{y + 1}")


@cache
def _tournaments(y: int) -> tuple[tuple[int, str], ...]:
    data = get_json(API + f"ta/Tournament/Season/{_season_id(y)}") or {}
    return tuple((t["tournamentId"], t["tournamentName"].strip()) for t in data.get("tournamentsInSeason") or []
                 if not _SKIP.search(t["tournamentName"]))


def _phase_tournaments(opts: dict, y: int, phase: str) -> list[tuple[int, str]]:
    age = opts["age"]
    if phase_key(phase) == "playoffs":
        pattern = rf"^({age} NM\b|NM sluttspill {age}\b)"
    else:
        pattern = rf"^{age} elite\b"
    found = [t for t in _tournaments(y) if re.search(pattern, t[1], re.I)]
    if not found:
        raise ValueError(f"no {phase_key(phase)} tournament for {age} Elite in {y}-{y + 1}")
    return found


def _stats(opts: dict, y: int, phase: str, kind: str) -> pd.DataFrame:
    frames = []
    for tid, name in _phase_tournaments(opts, y, phase):
        rows = get_json(API + f"wise/tournaments/{tid}/{kind}/statistics") or []
        if rows:
            frames.append(pd.DataFrame(rows).assign(stage=name))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "player", df["firstName"].str.strip() + " " + df["lastName"].str.strip())
    return df.drop(columns=["firstName", "lastName", "rank", "timeOnIce"], errors="ignore")


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _stats(opts, y, phase, "players")
    if df.empty:
        return df
    # 'points' in this feed repeats the penalty minutes; 'pts' is goals + assists.
    df = df.drop(columns=["points", "minutesPlayed"], errors="ignore")
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "personId": "player_id", "teamName": "team", "teamShortName": "team_code", "orgId": "team_id",
        "gamesPlayed": "gp", "goalsScored": "g", "assists": "a", "pts": "pts", "pim": "pim",
        "powerPlayGoals": "ppg", "powerPlayGoalAssists": "ppa", "shortHandedGoals": "shg",
        "shortHandedGoalAssists": "sha", "shotsPct": "shooting_pct", "faceOffs": "faceoffs",
        "faceoffsWinPct": "faceoff_pct"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _stats(opts, y, phase, "goalies")
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "personId": "player_id", "teamName": "team", "teamShortName": "team_code", "orgId": "team_id",
        "gamesPlayed": "gp", "minutesPlayed": "toi", "wins": "w", "losses": "l", "so": "so", "ga": "ga",
        "gaa": "gaa", "sv": "saves", "svPct": "sv_pct"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only (the NM play-offs are series)")
    frames = []
    for tid, name in _phase_tournaments(opts, y, phase):
        rows = get_json(API + "ta/TournamentStandings/", tournamentId=tid) or []
        if rows:
            frames.append(pd.DataFrame(rows).assign(stage=name))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    keep = {"orgName": "team", "orgId": "team_id", "matches": "gp", "victoriesFulltimeTotal": "w",
            "victoriesOvertimeTotal": "otw", "victoriesPenaltiesTotal": "sow", "lossesFulltimeTotal": "l",
            "lossesOvertimeTotal": "otl", "lossesPenaltiesTotal": "sol", "draws": "t", "totalPoints": "pts",
            "goalsScored": "gf", "goalsConceeded": "ga", "position": "rank", "stage": "stage"}
    df = df[[c for c in keep if c in df]].rename(columns=keep)
    return finish(df, "standings", league, y, "regular")
