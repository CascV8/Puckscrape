"""Leagues whose own sites can't be reached, read from HockeyDB rosters instead
(``ps.hockeydb``). Skaters only: HockeyDB gives every rostered player the same
GP-G-A-PTS-PIM line (goalies included, with ``position`` "G"), and has no goalie
stats or standings. One request per team, 3 s apart.
"""

from __future__ import annotations

from functools import cache

import pandas as pd

from .. import hockeydb
from ._common import Unsupported, finish, phase_key

_STATS = ("gp", "g", "a", "pts", "pim")


@cache
def _rosters(league: str, y: int) -> pd.DataFrame:
    """One HockeyDB scrape per league-season: the same team pages hold the regular
    season and the playoffs, and HockeyDB blocks clients that re-read them quickly."""
    return hockeydb.skaters(league, y)


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _rosters(opts["hockeydb"], y).copy()
    if df.empty:
        return df
    p = phase_key(phase)
    if p == "playoffs":
        df = df.drop(columns=[*_STATS, "plus_minus"]).rename(columns={f"po_{s}": s for s in _STATS})
    else:
        df = df.drop(columns=[f"po_{s}" for s in _STATS])
    df = df[df["gp"].fillna(0) > 0].drop(columns=["league", "season"])
    return finish(df, "skaters", league, y, p, rename={"pid": "player_id", "pos": "position"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    raise Unsupported("HockeyDB has no goalie stats; goalies are in skaters() with position 'G'")


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    raise Unsupported("HockeyDB has no standings")
