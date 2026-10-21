"""HockeyAllsvenskan (Sweden) from the stats API behind hockeyallsvenskan.se.

The site POSTs a filter body to /api/all-time-*-stats; a ``season`` (start
year) gives that season's regular-season table.
"""

from __future__ import annotations

import pandas as pd

from .. import _http
from ._common import Unsupported, finish, phase_key

HOST = "https://hockeyallsvenskan.se"
PAGE = 500


def _all(route: str, y: int) -> tuple[list[dict], dict[str, str]]:
    rows, teams, page = [], {}, 1
    while True:
        data = _http.post_json(f"{HOST}/api/{route}", {"season": str(y), "page": page, "page_size": PAGE})
        rows += data.get("results") or []
        teams.update({t["teamCode"]: t.get("fullName") or t.get("name") for t in data.get("teams") or []})
        if page >= (data.get("total_pages") or 1):
            return rows, teams
        page += 1


def _regular_only(phase: str) -> None:
    if phase_key(phase) != "regular":
        raise Unsupported("the HockeyAllsvenskan stats API is wired for the regular season only")


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    _regular_only(phase)
    rows, teams = _all("all-time-skaters-stats", y)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(1, "team_code", df["team"])
        df["team"] = df["team"].map(teams).fillna(df["team"])
    return finish(df, "skaters", league, y, "regular", rename={
        "GP": "gp", "G": "g", "A": "a", "TP": "pts", "PIM": "pim", "PlusMinus": "plus_minus",
        "SOG": "shots", "PPG": "ppg", "GWG": "gwg", "BKS": "blocks", "TOI_GP": "toi_per_gp",
        "TPPG": "pts_per_gp"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    _regular_only(phase)
    rows, teams = _all("all-time-goalkeepers-stats", y)
    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(1, "team_code", df["team"])
        df["team"] = df["team"].map(teams).fillna(df["team"])
    return finish(df, "goalies", league, y, "regular", rename={
        "GPI": "gp", "GP": "games_dressed", "W": "w", "L": "l", "T": "t", "GA": "ga", "SVS": "saves",
        "SVS_perc": "sv_pct", "GAA": "gaa", "SO": "so", "MIP": "toi"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    _regular_only(phase)
    data = _http.post_json(f"{HOST}/api/all-time-league-stats", {"season": str(y)})
    df = pd.DataFrame(data.get("results") or [])
    if not df.empty:
        # Standings carry team codes only; the skater endpoint lists the names.
        names = _http.post_json(f"{HOST}/api/all-time-skaters-stats", {"season": str(y), "page": 1, "page_size": 1})
        teams = {t["teamCode"]: t.get("fullName") or t.get("name") for t in names.get("teams") or []}
        df.insert(1, "team_code", df["team"])
        df["team"] = df["team"].map(teams).fillna(df["team"])
    return finish(df, "standings", league, y, "regular", rename={
        "GP": "gp", "W": "w", "L": "l", "OTW": "otw", "OTL": "otl", "Points": "pts", "G": "gf", "GA": "ga"})
