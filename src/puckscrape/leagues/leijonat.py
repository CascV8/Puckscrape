"""Finnish Ice Hockey Association results service (tulospalvelu.leijonat.fi).

Covers every level the federation runs: Mestis, U20/U18 SM-sarja, Auroraliiga
(women) and more. Seasons are numbered by end year. A level can have several
stages in one season; each row keeps its stage in a ``stage`` column.
"""

from __future__ import annotations

from functools import cache

import pandas as pd

from ._common import finish, get_json, phase_key

MAIN = "https://tulospalvelu.leijonat.fi/helpers/"
SERIE = "https://tulospalvelu.leijonat.fi/serie/helpers/"


def _filters(sorted_by: str) -> dict:
    f = {"Games": "", "Strength": "", "Rookies": 0, "Total": 0, "Period": "", "SortOrder": "DESC",
         "SortedBy": sorted_by, "PlayerName": ""}
    return {f"filters[{k}]": v for k, v in f.items()}


@cache
def _level_id(season: int, level_name: str) -> int:
    for lv in get_json(MAIN + "getlevels", season=season):
        if lv.get("LevelName") == level_name:
            return lv["LevelID"]
    raise ValueError(f"no level {level_name!r} in season {season - 1}-{season}")


def _stages(y: int, level_name: str, phase: str) -> list[tuple[int, str, int]]:
    season = y + 1
    level = _level_id(season, level_name)
    subs = get_json(SERIE + "getsubseries", season=season, levelid=level, districtid=0)
    want_playoffs = phase_key(phase) == "playoffs"
    out = []
    for s in subs:
        name = s["subSerieName"].lower()
        if "harjoitus" in name or "karsin" in name:
            continue
        is_playoff = "pudotus" in name or "playoff" in name
        if is_playoff == want_playoffs:
            out.append((s["subSerieId"], s["subSerieName"], level))
    if not out:
        raise ValueError(f"no {phase_key(phase)} stage for {level_name} {y}-{y + 1}")
    return out


def _players(y: int, opts: dict, phase: str, goalies: bool) -> pd.DataFrame:
    frames = []
    for sub_id, sub_name, level in _stages(y, opts["level"], phase):
        params = {"season": y + 1, "type": 0, "teamid": 0, "nop": 5000, "subSerieId": sub_id}
        if goalies:
            data = get_json(MAIN + "getgoalkeepers", gamesratio=0, levelid=level, **params,
                            **_filters("GoalieSavesPerc"))
        else:
            data = get_json(MAIN + "getplayers", **params, **_filters("PlayerPoints"))
        df = pd.DataFrame(data.get("Players") or [])
        if not df.empty:
            df.insert(0, "stage", sub_name)
            frames.append(df)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if df.empty:
        return df
    df.insert(0, "player", df["FirstName"].str.strip() + " " + df["LastName"].str.strip().str.title())
    return df.drop(columns=[c for c in df.columns if c in (
        "FirstName", "LastName", "TeamStats", "Img", "TeamImg", "LinkID", "TeamIDs") or c.endswith("Img")])


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _players(y, opts, phase, goalies=False)
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "PlayerID": "player_id", "TeamAbbrv": "team", "RoleAbbrv": "position", "DateOfBirth": "birth_date",
        "PlayerGames": "gp", "PlayerGoals": "g", "PlayerAssists": "a", "PlayerPoints": "pts",
        "PlayerPenaltyMin": "pim", "PlayerPlusMinus": "plus_minus"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _players(y, opts, phase, goalies=True)
    if not df.empty:
        # Lower levels don't log goalie minutes; their GA/60 then reads 0.00, which is meaningless.
        df["GoalieGA60Min"] = df["GoalieGA60MinNum"].where(df["GoalieTimeOnIce"] > 0)
        df = df.drop(columns=["GoalieGA60MinNum", "GoalieSavesPercNum", "GoalieWinPercNum"], errors="ignore")
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "PlayerID": "player_id", "TeamAbbrv": "team", "Yob": "birth_year", "GoaliePlayedGames": "gp",
        "GoalieGames": "games_dressed", "GoalieWinGames": "w", "GoalieLossGames": "l",
        "GoalieGoalsAgainst": "ga", "GoalieSaves": "saves", "GoalieSavesPerc": "sv_pct",
        "GoalieGA60Min": "gaa", "GoalieZeroGames": "so", "GoalieTimeOnIce": "toi"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    frames = []
    for sub_id, sub_name, _ in _stages(y, opts["level"], phase):
        data = get_json(SERIE + "getstandings", season=y + 1, subSerieId=sub_id)
        df = pd.DataFrame(data.get("Teams") or [])
        if not df.empty:
            df.insert(0, "stage", sub_name)
            frames.append(df)
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return finish(df, "standings", league, y, phase_key(phase), drop=("TeamImg",), rename={
        "TeamAbbrv": "team", "Games": "gp", "Wins": "w", "Looses": "l", "OtWins": "otw",
        "OtLooses": "otl", "Points": "pts", "GoalsFor": "gf", "GoalsAgainst": "ga"})
