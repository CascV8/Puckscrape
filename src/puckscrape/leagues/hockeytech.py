"""HockeyTech / LeagueStat feed: the CHL and most North American minor leagues.

Each league has its own public site key: the one its website (or HockeyTech's
statview widget config for it) sends to this feed.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

FEED = "https://lscluster.hockeytech.com/feed/index.php"
CHL_KEY = "f1aa699db3d81487"

_SKIP = ("pre-season", "preseason", "pre season", "prospect", "showcase", "combine", "draft", "all-star", "allstar", "exhibition",
         "challenge", "top prospects", "classic", "tournament")


def _key(client: str) -> str:
    return _KEYS.get(client, CHL_KEY)


# Filled in by the registry (leagues/__init__.py) from each league's opts.
_KEYS: dict[str, str] = {}


def _kit(client: str, **params) -> dict:
    base = {"feed": "modulekit", "key": _key(client), "client_code": client, "fmt": "json", "lang": "en"}
    return get_json(FEED, **base, **params)["SiteKit"]


@cache
def seasons(client: str, league_id: int | None = None) -> pd.DataFrame:
    """A client's seasons; ``league_id`` picks one division where a client has several (the CSSHL)."""
    extra = {} if league_id is None else {"league_id": league_id}
    return pd.DataFrame(_kit(client, view="seasons", **extra)["Seasons"])


def _start_year(name: str, playoffs: bool) -> int | None:
    """Season start year from names like '2025-26 Regular Season', 'CCHL 2025-26',
    '26-27 Regular Season', '2025/26', '2026 Playoffs' (single year = playoff end year)."""
    m = re.search(r"(\d{2,4})\s*[-/|]\s*(\d{2,4})", name)
    if m:
        first = int(m.group(1))
        return first + 2000 if first < 100 else first
    m = re.search(r"\b(\d{4})\b", name)
    if m:
        year = int(m.group(1))
        return year - 1 if playoffs else year
    return None


def season_id(client: str, y: int, phase: str, regular: str | None = None,
              league_id: int | None = None) -> str:
    """Regular season: a name with 'regular', nothing but the league and years
    ('2025-26', 'CCHL 2025-26'), or one matching the league's own ``regular``
    pattern ('2025-2026 GOHL Season', '2025-26 U18 Prep'). Playoffs: a name with 'playoff'."""
    want = phase_key(phase)
    for _, s in seasons(client, league_id).iterrows():
        name = s["season_name"].lower()
        if any(w in name for w in _SKIP):
            continue
        is_playoff = "playoff" in name
        if (want == "playoffs") != is_playoff:
            continue
        plain = not re.sub(r"[\d\s\-/|]+", "", name.replace(client, ""))
        if want == "regular" and "regular" not in name and not plain and not (regular and re.search(regular, name)):
            continue  # a tournament or event, not the league season
        if _start_year(name, is_playoff) == y:
            return s["season_id"]
    raise ValueError(f"no {want} season {y}-{y + 1} for {client}")


def _season(opts: dict, y: int, phase: str) -> dict:
    """The feed parameters for one season: season_id, plus league_id for a client
    with divisions (the CSSHL's U18 Prep), trying each listed league_id in order."""
    client = opts["client"]
    for league_id in opts.get("league_ids", [None]):
        try:
            sid = season_id(client, y, phase, opts.get("regular"), league_id)
        except ValueError:
            continue
        return {"season_id": sid} if league_id is None else {"season_id": sid, "league_id": league_id}
    raise ValueError(f"no {phase_key(phase)} season {y}-{y + 1} for {client}")


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
    rows = _kit(client, view="statviewtype", type="topscorers", **_season(opts, y, phase),
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
    rows = _kit(client, view="statviewtype", type="topgoalies", **_season(opts, y, phase),
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
                **_season(opts, y, phase))["Statviewtype"]
    df = pd.DataFrame([r for r in rows if r.get("team_code")])
    if not df.empty:
        # Clinch markers are glued to the name: 'xyz - Brantford Bulldogs'.
        df["clinched"] = df["name"].str.extract(r"^([a-z*]+)\s+-\s+", expand=False)
        df["name"] = df["name"].str.replace(r"^[a-z*]+\s+-\s+", "", regex=True).str.replace(", ", " ", regex=False)
    return finish(df, "standings", league, y, "regular", drop=_DROP, rename={
        "name": "team", "games_played": "gp", "wins": "w", "losses": "l", "ot_losses": "otl",
        "ot_wins": "otw", "points": "pts", "goals_for": "gf", "goals_against": "ga"})
