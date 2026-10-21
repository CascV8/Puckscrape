"""HockeyTech / LeagueStat feed: OHL, WHL, QMJHL.

The key is the public site key the CHL's own pages (chl.ca) send to this feed.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

FEED = "https://lscluster.hockeytech.com/feed/index.php"
KEY = "f1aa699db3d81487"


def _kit(client: str, **params) -> dict:
    base = {"feed": "modulekit", "key": KEY, "client_code": client, "fmt": "json", "lang": "en"}
    return get_json(FEED, **base, **params)["SiteKit"]


@cache
def seasons(client: str) -> pd.DataFrame:
    return pd.DataFrame(_kit(client, view="seasons")["Seasons"])


def season_id(client: str, y: int, phase: str) -> str:
    """Names vary by league: '2025-26 Regular Season', '2025 - 26 Regular Season',
    '2025-26 | Regular Season'; playoffs are named by end year ('2026 Playoffs')."""
    want = phase_key(phase)
    for _, s in seasons(client).iterrows():
        name = s["season_name"].lower()
        years = [int(x) for x in re.findall(r"\d{4}", name)]
        if not years or "pre" in name or "prospect" in name or "showcase" in name:
            continue
        if want == "regular" and "regular" in name and years[0] == y:
            return s["season_id"]
        if want == "playoffs" and "playoff" in name and years[0] == y + 1:
            return s["season_id"]
    raise ValueError(f"no {want} season {y}-{y + 1} for {client}")


def _first_last(name):
    """The QMJHL writes 'Massé, Maxim' and 'Chicoutimi, Saguenéens'; the others don't."""
    if isinstance(name, str) and name.count(", ") == 1:
        last, first = name.split(", ")
        return f"{first} {last}"
    return name


_DROP = ("phonetic_name", "shortname", "suspension_games_remaining", "suspension_indefinite",
         "placeholder", "team_logo", "logo", "player_image", "flags")


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    client = opts["client"]
    rows = _kit(client, view="statviewtype", type="topscorers", season_id=season_id(client, y, phase),
                first=0, limit=5000)["Statviewtype"]
    df = pd.DataFrame(rows)
    if client == "lhjmq" and not df.empty:
        df["name"] = df["name"].map(_first_last)
        df["team_name"] = df["team_name"].str.replace(", ", " ", regex=False)
    return finish(df, "skaters", league, y, phase_key(phase), drop=_DROP, rename={
        "name": "player", "team_name": "team", "games_played": "gp", "goals": "g", "assists": "a",
        "points": "pts", "penalty_minutes": "pim"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    client = opts["client"]
    rows = _kit(client, view="statviewtype", type="topgoalies", season_id=season_id(client, y, phase),
                first=0, limit=1000)["Statviewtype"]
    df = pd.DataFrame(rows)
    if client == "lhjmq" and not df.empty:
        df["name"] = df["name"].map(_first_last)
        df["team_name"] = df["team_name"].str.replace(", ", " ", regex=False)
    return finish(df, "goalies", league, y, phase_key(phase), drop=_DROP, rename={
        "name": "player", "team_name": "team", "games_played": "gp", "wins": "w", "losses": "l",
        "goals_against": "ga", "save_percentage": "sv_pct", "goals_against_average": "gaa",
        "shutouts": "so", "minutes_played": "toi"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    client = opts["client"]
    rows = _kit(client, view="statviewtype", stat="conference", type="standings",
                season_id=season_id(client, y, phase))["Statviewtype"]
    df = pd.DataFrame([r for r in rows if r.get("team_code")])
    if not df.empty:
        # Clinch markers are glued to the name: 'xyz - Brantford Bulldogs'.
        df["clinched"] = df["name"].str.extract(r"^([a-z*]+)\s+-\s+", expand=False)
        df["name"] = df["name"].str.replace(r"^[a-z*]+\s+-\s+", "", regex=True).str.replace(", ", " ", regex=False)
    return finish(df, "standings", league, y, "regular", drop=_DROP, rename={
        "name": "team", "games_played": "gp", "wins": "w", "losses": "l", "ot_losses": "otl",
        "ot_wins": "otw", "points": "pts", "goals_for": "gf", "goals_against": "ga"})
