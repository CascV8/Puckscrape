"""Liiga (Finland) from liiga.fi's public API. Liiga numbers seasons by end year."""

from __future__ import annotations

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

API = "https://liiga.fi/api/v2"
_TOURNAMENT = {"regular": "runkosarja", "playoffs": "playoffs"}


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    p = phase_key(phase)
    rows = get_json(f"{API}/players/stats/summed/{y + 1}/{y + 1}/{_TOURNAMENT[p]}/false", dataType="basicStats")
    df = pd.DataFrame([r for r in rows if r.get("games", 0) > 0])
    if df.empty:
        return df
    df.insert(0, "player", df["firstName"].str.strip() + " " + df["lastName"].str.strip().str.title())
    return finish(df, "skaters", league, y, p, drop=(
        "pictureUrl", "previousTeamsForTournament", "firstName", "lastName", "tournament", "removed",
        "current", "lastSeason", "goalkeeper"), rename={
        "playerId": "player_id", "teamName": "team", "role": "position", "games": "gp", "goals": "g",
        "assists": "a", "points": "pts", "penaltyMinutes": "pim", "plusMinus": "plus_minus",
        "expectedGoals": "xg", "timeOnIce": "toi_seconds", "timeOnIceAvg": "toi_per_gp_seconds"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    """liiga.fi's goalie table (the same endpoint as skaters, dataType=basicStatsGk).
    ``games`` there counts games dressed; ``gp`` is games played."""
    p = phase_key(phase)
    rows = get_json(f"{API}/players/stats/summed/{y + 1}/{y + 1}/{_TOURNAMENT[p]}/false", dataType="basicStatsGk")
    df = pd.DataFrame([r for r in rows if r.get("playedGames", 0) > 0 or r.get("timeOnIce", 0) > 0])
    if df.empty:
        return df
    df.insert(0, "player", df["firstName"].str.strip() + " " + df["lastName"].str.strip().str.title())
    df["timeOnIce"] = (df["timeOnIce"] / 60).round(2)   # seconds -> minutes, like every other league
    return finish(df, "goalies", league, y, p, drop=(
        "pictureUrl", "previousTeamsForTournament", "firstName", "lastName", "tournament", "removed",
        "current", "lastSeason", "goalkeeper", "role", "reserveGoalie"), rename={
        "playerId": "player_id", "teamName": "team", "playedGames": "gp", "games": "games_dressed",
        "gkWins": "w", "gkLosses": "l", "gkTies": "t", "goalsAgainst": "ga", "blockedOrSavedShots": "saves",
        "savePercentage": "sv_pct", "goalsAgainstAvg": "gaa", "shutOut": "so", "timeOnIce": "toi",
        "expectedGoalsAgainst": "xga", "penaltyMinutes": "pim", "goals": "g", "assists": "a", "points": "pts"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    data = get_json(f"{API}/standings/", season=y + 1)
    df = pd.DataFrame(data.get("season", []))
    return finish(df, "standings", league, y, "regular", drop=("teamLogos", "internalId", "teamId"), rename={
        "teamName": "team", "games": "gp", "wins": "w", "losses": "l", "overtimeWins": "otw",
        "overtimeLosses": "otl", "points": "pts", "goals": "gf", "goalsAgainst": "ga"})
