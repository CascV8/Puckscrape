"""Metal Ligaen (Denmark) from statistik.metalligaen.dk's stats endpoint.

Standings come from the league's results provider (the same one behind ICEHL).
"""

from __future__ import annotations

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

STATS = "https://statistik.metalligaen.dk/metal-liga-stats-theme/stats/get"
S3 = "https://s3.dualstack.eu-west-1.amazonaws.com/den.hokejovyzapis.cz"
_DROP = ("id", "image", "image_date", "modified", "created", "modified_by", "created_by", "external_id",
         "season_id", "endgame", "global_id", "metal_liga_stats_theme_player_id")


def _rows(y: int, phase: str, goalies: bool) -> pd.DataFrame:
    params = {"goalies": int(goalies), "endgame": int(phase_key(phase) == "playoffs"),
              "sorter": "points", "season": f"{y}-{y + 1}"}
    rows, page = [], 1
    while True:
        # The endpoint errors on an explicit page=1, so the first page goes without it.
        data = get_json(STATS, **params) if page == 1 else get_json(STATS, **params, page=page)
        rows += data.get("data") or []
        if page >= (data.get("last_page") or 1):
            break
        page += 1
    df = pd.DataFrame(rows)
    return df.drop_duplicates(subset=[c for c in ("name", "team", "games_played") if c in df]) if not df.empty else df


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _rows(y, phase, goalies=False)
    goalie_cols = ("games_played_in", "shot_against", "goal_against", "save_procent", "gaa", "saved_balls")
    return finish(df, "skaters", league, y, phase_key(phase), drop=_DROP + goalie_cols, rename={
        "name": "player", "pos": "position", "games_played": "gp", "goals": "g", "assists": "a",
        "points": "pts", "penalty_minutes": "pim", "plus_minus": "plus_minus", "shirt_number": "number",
        "birthday": "birth_date", "country": "nationality", "hand": "shoots"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _rows(y, phase, goalies=True)
    return finish(df, "goalies", league, y, phase_key(phase), drop=_DROP, rename={
        "name": "player", "games_played_in": "gp", "games_played": "games_dressed",
        "goal_against": "ga", "saved_balls": "saves", "save_procent": "sv_pct", "gaa": "gaa",
        "time_on_ice": "toi", "shot_against": "shots_against", "shirt_number": "number",
        "birthday": "birth_date", "country": "nationality", "hand": "catches"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    groups = get_json(f"{S3}/table/{y}/1.json")
    rows = [dict(c, group=g.get("groupName") or None) for g in groups for c in g.get("clubs", [])]
    df = pd.DataFrame(rows)
    return finish(df, "standings", league, y, "regular",
                  drop=("teamOriginal", "liveGameScore", "positionChange", "last10", "id", "partTeamId", "logo"),
                  rename={"name": "team", "games": "gp", "wins": "w", "losts": "l", "winsOt": "otw",
                          "lostsOt": "otl", "points": "pts", "score1": "gf", "score2": "ga",
                          "position": "rank"})
