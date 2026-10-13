"""NHL's public APIs: api-web.nhle.com (game center, schedule, players)
and api.nhle.com/stats (the stats.nhl.com reports).
"""

from __future__ import annotations

import datetime as dt
import logging

import pandas as pd

from . import _http
from ._util import as_list, clock_to_seconds, localized, nhl_season, snake, snake_columns

log = logging.getLogger("puckscrape.nhl")

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"

REGULAR, PLAYOFFS = 2, 3


def _date(d) -> dt.date:
    if d is None:
        return dt.date.today()
    if isinstance(d, dt.date):
        return d
    return dt.date.fromisoformat(str(d))


# --------------------------------------------------------------------------
# Schedule
# --------------------------------------------------------------------------

def _game_row(g: dict) -> dict:
    away, home = g.get("awayTeam", {}), g.get("homeTeam", {})
    return {
        "game_id": g.get("id"),
        "season": g.get("season"),
        "game_type": g.get("gameType"),
        "date": g.get("gameDate"),
        "start_time_utc": g.get("startTimeUTC"),
        "venue": localized(g.get("venue")),
        "away_team": away.get("abbrev"),
        "home_team": home.get("abbrev"),
        "away_score": away.get("score"),
        "home_score": home.get("score"),
        "game_state": g.get("gameState"),
        "last_period_type": (g.get("gameOutcome") or {}).get("lastPeriodType"),
    }


def schedule(start=None, end=None) -> pd.DataFrame:
    """Every game between two dates (inclusive). Defaults to today only.

    >>> schedule("2025-10-07", "2025-10-31")
    """
    start = _date(start)
    end = _date(end) if end is not None else start
    rows, cursor = [], start
    while cursor <= end:
        data = _http.get_json(f"{WEB}/schedule/{cursor.isoformat()}")
        for day in data.get("gameWeek", []):
            if start.isoformat() <= day["date"] <= end.isoformat():
                for g in day.get("games", []):
                    rows.append(_game_row(g) | {"date": day["date"]})
        nxt = data.get("nextStartDate")
        if not nxt or _date(nxt) <= cursor:
            break
        cursor = _date(nxt)
    return pd.DataFrame(rows)


def team_schedule(team: str, season) -> pd.DataFrame:
    """A team's full season schedule. ``team`` is a tri-code like "TOR"."""
    data = _http.get_json(f"{WEB}/club-schedule-season/{team.upper()}/{nhl_season(season)}")
    return pd.DataFrame([_game_row(g) for g in data.get("games", [])])


# --------------------------------------------------------------------------
# Single games
# --------------------------------------------------------------------------

def boxscore(game_id: int) -> pd.DataFrame:
    """Per-player boxscore for one game: skaters and goalies in one frame.

    ``group`` is forwards/defense/goalies; columns that don't apply are NaN.
    """
    data = _http.get_json(f"{WEB}/gamecenter/{game_id}/boxscore")
    rows = []
    for side in ("awayTeam", "homeTeam"):
        team = data[side]["abbrev"]
        for group, players in data.get("playerByGameStats", {}).get(side, {}).items():
            for p in players:
                rows.append({"game_id": game_id, "team": team, "venue": side[:4], "group": group}
                            | p | {"name": localized(p.get("name"))})
    df = snake_columns(pd.DataFrame(rows))
    if "toi" in df:
        df["toi_seconds"] = clock_to_seconds(df["toi"])
    return df


def play_by_play(game_id: int) -> pd.DataFrame:
    """Event-level play-by-play from the API, with player and team names filled in.

    For shift-based on-ice players use :func:`full_play_by_play`.
    """
    data = _http.get_json(f"{WEB}/gamecenter/{game_id}/play-by-play")
    names = {
        r["playerId"]: f"{localized(r['firstName'])} {localized(r['lastName'])}"
        for r in data.get("rosterSpots", [])
    }
    teams = {data[s]["id"]: data[s]["abbrev"] for s in ("awayTeam", "homeTeam")}

    df = pd.json_normalize(data.get("plays", []), sep="_")
    if df.empty:
        return df
    df = df.rename(columns={"periodDescriptor_number": "period", "periodDescriptor_periodType": "period_type",
                            "typeDescKey": "event_type"})
    # Strip "details_" unless that collides (details.typeCode is the penalty type).
    df.columns = [c if c.removeprefix("details_") in df.columns else c.removeprefix("details_") for c in df.columns]
    df = snake_columns(df).drop(columns=["period_descriptor_max_regulation_periods"], errors="ignore")
    df.insert(0, "game_id", game_id)
    df.insert(1, "season", data.get("season"))
    df.insert(2, "game_type", data.get("gameType"))
    df.insert(3, "away_team", data["awayTeam"]["abbrev"])
    df.insert(4, "home_team", data["homeTeam"]["abbrev"])

    df["period_seconds"] = clock_to_seconds(df["time_in_period"])
    df["game_seconds"] = (df["period"] - 1) * 1200 + df["period_seconds"]
    if "event_owner_team_id" in df:
        df["event_team"] = df["event_owner_team_id"].map(teams)
    for col in [c for c in df.columns if c.endswith("_player_id") or c == "goalie_in_net_id"]:
        df[col.removesuffix("_id") + "_name"] = df[col].map(names)
    return df


def shifts(game_id: int) -> pd.DataFrame:
    """Every player shift in a game, from the shift charts endpoint."""
    data = _http.get_json(f"{STATS}/shiftcharts", params={"cayenneExp": f"gameId={game_id}"})
    df = pd.DataFrame(data.get("data", []))
    if df.empty:
        return df
    df = df[df["typeCode"] == 517]  # 505 rows are goal markers, not shifts
    df = snake_columns(df).drop(columns=["hex_value", "event_description", "event_details", "type_code", "detail_code"], errors="ignore")
    df["player"] = df["first_name"] + " " + df["last_name"]
    df["start_seconds"] = clock_to_seconds(df["start_time"])
    df["end_seconds"] = clock_to_seconds(df["end_time"])
    df["duration_seconds"] = clock_to_seconds(df["duration"])
    return df.sort_values(["period", "start_seconds", "team_abbrev"]).reset_index(drop=True)


def full_play_by_play(game_ids, **kwargs) -> pd.DataFrame:
    """Full play-by-play with on-ice players, via TopDownHockey's ``full_scrape``.

    Needs the optional extra: ``pip install puckscrape[tdh]``. ``kwargs`` pass
    straight through (e.g. ``live=False``, ``verbose=True``).
    """
    try:
        from TopDownHockey_Scraper.TopDownHockey_NHL_Scraper import full_scrape
    except ImportError as e:
        raise ImportError("full_play_by_play needs TopDownHockey_Scraper: pip install puckscrape[tdh]") from e
    return full_scrape([int(g) for g in as_list(game_ids)], **kwargs)


# --------------------------------------------------------------------------
# Players and teams
# --------------------------------------------------------------------------

def roster(team: str, season) -> pd.DataFrame:
    data = _http.get_json(f"{WEB}/roster/{team.upper()}/{nhl_season(season)}")
    rows = []
    for group, players in data.items():
        for p in players:
            rows.append({k: localized(v) for k, v in p.items()} | {"group": group, "team": team.upper()})
    df = snake_columns(pd.DataFrame(rows))
    if not df.empty:
        df.insert(1, "name", df["first_name"] + " " + df["last_name"])
    return df


def player_info(player_ids) -> pd.DataFrame:
    """Bio + draft details, one row per player."""
    rows = []
    for pid in as_list(player_ids):
        p = _http.get_json(f"{WEB}/player/{pid}/landing")
        draft = p.get("draftDetails") or {}
        rows.append({
            "player_id": p.get("playerId"),
            "name": f"{localized(p.get('firstName'))} {localized(p.get('lastName'))}",
            "position": p.get("position"),
            "shoots_catches": p.get("shootsCatches"),
            "team": p.get("currentTeamAbbrev"),
            "sweater_number": p.get("sweaterNumber"),
            "is_active": p.get("isActive"),
            "birth_date": p.get("birthDate"),
            "birth_city": localized(p.get("birthCity")),
            "birth_country": p.get("birthCountry"),
            "height_cm": p.get("heightInCentimeters"),
            "weight_kg": p.get("weightInKilograms"),
            "draft_year": draft.get("year"),
            "draft_round": draft.get("round"),
            "draft_overall": draft.get("overallPick"),
            "draft_team": draft.get("teamAbbrev"),
            "headshot": p.get("headshot"),
        })
    return pd.DataFrame(rows)


def game_log(player_id: int, season, game_type: int = REGULAR) -> pd.DataFrame:
    data = _http.get_json(f"{WEB}/player/{player_id}/game-log/{nhl_season(season)}/{game_type}")
    rows = [{k: localized(v) for k, v in g.items()} for g in data.get("gameLog", [])]
    df = snake_columns(pd.DataFrame(rows))
    if not df.empty:
        df.insert(0, "player_id", player_id)
        df["toi_seconds"] = clock_to_seconds(df["toi"])
    return df


def standings(date=None) -> pd.DataFrame:
    """League standings as of a date (default: now)."""
    data = _http.get_json(f"{WEB}/standings/{_date(date).isoformat() if date else 'now'}")
    rows = [{k: localized(v) for k, v in t.items()} for t in data.get("standings", [])]
    return snake_columns(pd.DataFrame(rows))


# --------------------------------------------------------------------------
# stats.nhl.com reports
# --------------------------------------------------------------------------

def _stats_report(entity: str, report: str, seasons, game_type: int) -> pd.DataFrame:
    frames = []
    for season in as_list(seasons):
        exp = f"seasonId={nhl_season(season)} and gameTypeId={game_type}"
        data = _http.get_json(f"{STATS}/{entity}/{report}", params={"limit": -1, "cayenneExp": exp})
        frames.append(pd.DataFrame(data.get("data", [])))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return df.rename(columns=snake)


def skater_stats(seasons, report: str = "summary", game_type: int = REGULAR) -> pd.DataFrame:
    """Season totals for every skater, from stats.nhl.com.

    ``report`` is any stats.nhl.com skater report: summary, realtime, bios,
    faceoffwins, penalties, powerplay, penaltykill, timeonice, shottype,
    scoringpergame, puckPossessions, ...
    """
    return _stats_report("skater", report, seasons, game_type)


def goalie_stats(seasons, report: str = "summary", game_type: int = REGULAR) -> pd.DataFrame:
    """Season totals for every goalie. Reports: summary, advanced, bios, savesByStrength, ..."""
    return _stats_report("goalie", report, seasons, game_type)


def team_stats(seasons, report: str = "summary", game_type: int = REGULAR) -> pd.DataFrame:
    """Season totals for every team. Reports: summary, realtime, powerplay, penaltykill, ..."""
    return _stats_report("team", report, seasons, game_type)


def teams() -> pd.DataFrame:
    """All franchises ever, with ids and tri-codes."""
    return snake_columns(pd.DataFrame(_http.get_json(f"{STATS}/team").get("data", [])))
