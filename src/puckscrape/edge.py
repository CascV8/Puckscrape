"""NHL Edge puck/player-tracking stats (api-web.nhle.com/v1/edge).

Data exists from 2021-22 on. ``season=None`` means the current season.
Summary functions take one id or many and return one row per id; detail
functions return one row per item (shot location, zone, top speed burst...).
"""

from __future__ import annotations

import logging
from functools import cache

import pandas as pd

from . import _http
from ._util import as_list, localized, nhl_season, snake

log = logging.getLogger("puckscrape.edge")

BASE = "https://api-web.nhle.com/v1/edge"
REGULAR, PLAYOFFS = 2, 3

# Noise that doesn't belong in a stats table.
_DROP_KEYS = {"overlay", "teamLogo", "headshot", "__typename", "placeNameWithPreposition", "seasonsWithEdgeStats"}


def raw(endpoint: str, entity_id: int, season=None, game_type: int = REGULAR) -> dict:
    """Escape hatch: the untouched JSON for any Edge endpoint, e.g.
    ``raw("skater-comparison", 8478402, 2024)``.
    """
    tail = f"{nhl_season(season)}/{game_type}" if season is not None else "now"
    return _http.get_json(f"{BASE}/{endpoint}/{entity_id}/{tail}")


def _flatten(obj, prefix: str = "") -> dict:
    """Nested dicts -> one flat dict with snake_case keys. Lists are skipped
    (they're exposed by the detail functions)."""
    out = {}
    for k, v in obj.items():
        if k in _DROP_KEYS:
            continue
        key = f"{prefix}_{snake(k)}" if prefix else snake(k)
        if isinstance(v, dict):
            if set(v) <= {"default", "fr", "cs", "de", "es", "fi", "sk", "sv"}:
                out[key] = localized(v)
            else:
                out |= _flatten(v, key)
        elif not isinstance(v, list):
            out[key] = v
    return out


def _records(items: list[dict], **extra) -> pd.DataFrame:
    return pd.DataFrame([extra | _flatten(i) for i in items])


def _summaries(endpoint: str, id_col: str, ids, season, game_type) -> pd.DataFrame:
    rows = []
    for entity_id in as_list(ids):
        data = raw(endpoint, entity_id, season, game_type)
        head = data.get("player") or data.get("team") or {}
        row = {id_col: entity_id, "season": nhl_season(season) if season is not None else "now"}
        row |= {f"info_{k}": v for k, v in _flatten(head).items()}
        row |= _flatten({k: v for k, v in data.items() if k not in ("player", "team")})
        rows.append(row)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------
# Skaters
# --------------------------------------------------------------------------

def skater_summary(player_ids, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Headline Edge numbers: top shot speed, max skating speed, bursts,
    distance skated, zone time -- each with percentile and league average."""
    return _summaries("skater-detail", "player_id", player_ids, season, game_type)


def skater_shot_locations(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Shots, goals and shooting % by rink area (17 areas)."""
    data = raw("skater-shot-location-detail", player_id, season, game_type)
    return _records(data.get("shotLocationDetails", []), player_id=player_id)


def skater_zone_time(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Offensive/neutral/defensive zone time by strength (all, ES, PP, PK)."""
    data = raw("skater-zone-time", player_id, season, game_type)
    return _records(data.get("zoneTimeDetails", []), player_id=player_id)


def skater_top_speeds(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """The player's 10 fastest skating bursts, with game context."""
    data = raw("skater-skating-speed-detail", player_id, season, game_type)
    return _records(data.get("topSkatingSpeeds", []), player_id=player_id)


def skater_hardest_shots(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """The player's 10 hardest shots, with game context."""
    data = raw("skater-shot-speed-detail", player_id, season, game_type)
    return _records(data.get("hardestShots", []), player_id=player_id)


def skater_distance(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Distance skated in each of the last 10 games."""
    data = raw("skater-skating-distance-detail", player_id, season, game_type)
    return _records(data.get("skatingDistanceLast10", []), player_id=player_id)


# --------------------------------------------------------------------------
# Goalies
# --------------------------------------------------------------------------

def goalie_summary(player_ids, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """GAA, games above .900, goal support, save % by shot location summary."""
    return _summaries("goalie-detail", "player_id", player_ids, season, game_type)


def goalie_shot_locations(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Saves, goals against and save % by rink area."""
    data = raw("goalie-shot-location-detail", player_id, season, game_type)
    return _records(data.get("shotLocationDetails", []), player_id=player_id)


def goalie_save_pct_last10(player_id: int, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    data = raw("goalie-save-percentage-detail", player_id, season, game_type)
    return _records(data.get("savePctgLast10", []), player_id=player_id)


# --------------------------------------------------------------------------
# Teams
# --------------------------------------------------------------------------

@cache
def _team_ids() -> dict[str, int]:
    data = _http.get_json("https://api.nhle.com/stats/rest/en/team")
    return {t["triCode"]: t["id"] for t in data.get("data", [])}


def _team_id(team) -> int:
    if isinstance(team, int) or str(team).isdigit():
        return int(team)
    try:
        return _team_ids()[str(team).upper()]
    except KeyError:
        raise ValueError(f"unknown team {team!r}") from None


def team_summary(teams, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    """Team-level Edge numbers with league ranks. ``teams``: tri-codes or ids."""
    df = _summaries("team-detail", "team_id", [_team_id(t) for t in as_list(teams)], season, game_type)
    return df


def team_zone_time(team, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    tid = _team_id(team)
    data = raw("team-zone-time-details", tid, season, game_type)
    return _records(data.get("zoneTimeDetails", []), team_id=tid)


def team_top_speeds(team, season=None, game_type: int = REGULAR) -> pd.DataFrame:
    tid = _team_id(team)
    data = raw("team-skating-speed-detail", tid, season, game_type)
    return _records(data.get("topSkatingSpeeds", []), team_id=tid)
