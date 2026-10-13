"""ESPN's NHL data: scores, schedules, standings, rosters, box scores,
play-by-play, player stats and injuries.

These are the undocumented JSON endpoints that espn.com's own pages load
(site.api.espn.com), so no HTML is parsed. ESPN doesn't publish or support
them, which means they can change without notice.

ESPN identifies players, teams and games with its own IDs, not the NHL's.
ESPN labels a season by the year it *ends*; every function here takes the
usual puckscrape spelling (2024 or "2024-25" means 2024-25) and converts.
"""

from __future__ import annotations

import datetime as dt
import logging
import re

import pandas as pd

from . import _http
from ._util import as_list, clock_to_seconds, snake, start_year

log = logging.getLogger("puckscrape.espn")

SITE = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl"
STANDINGS = "https://site.api.espn.com/apis/v2/sports/hockey/nhl/standings"
COMMON = "https://site.web.api.espn.com/apis/common/v3/sports/hockey/nhl"

REGULAR, PLAYOFFS = 2, 3


def espn_season(season) -> int:
    """-> 2025 for the 2024-25 season (ESPN names seasons by their end year)."""
    return start_year(season) + 1


def _season_type(playoffs: bool) -> int:
    return PLAYOFFS if playoffs else REGULAR


def _date_param(d) -> str:
    if d is None:
        d = dt.date.today()
    elif not isinstance(d, dt.date):
        d = dt.date.fromisoformat(str(d))
    return d.strftime("%Y%m%d")


def _numeric(df: pd.DataFrame, skip=()) -> pd.DataFrame:
    """Convert every column that is entirely numeric strings; leave the rest."""
    for col in df.columns:
        if col in skip or not pd.api.types.is_string_dtype(df[col]):
            continue
        converted = pd.to_numeric(df[col], errors="coerce")
        if converted.notna().sum() == df[col].notna().sum():
            df[col] = converted
    return df


def _athlete_id_from_links(athlete: dict) -> int | None:
    for link in athlete.get("links") or []:
        if m := re.search(r"/id/(\d+)", link.get("href", "")):
            return int(m.group(1))
    return None


# --------------------------------------------------------------------------
# Games
# --------------------------------------------------------------------------

def _score(value):
    # The scoreboard sends "4"; team schedules send {"value": 4.0, "displayValue": "4"}.
    if isinstance(value, dict):
        value = value.get("value")
    return None if value is None else int(float(value))


def parse_events(events: list[dict]) -> list[dict]:
    """Rows from a list of ESPN events (scoreboard or team schedule)."""
    rows = []
    for e in events:
        comp = (e.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c for c in comp.get("competitors") or []}
        home, away = teams.get("home", {}), teams.get("away", {})
        status = (comp.get("status") or e.get("status") or {}).get("type") or {}
        season_type = e.get("seasonType") or e.get("season") or {}
        # Unplayed games (scheduled, postponed) report 0-0; postponed games are replayed under a new ID.
        played = status.get("state") in ("in", "post") and status.get("name") != "STATUS_POSTPONED"
        rows.append({
            "game_id": int(e["id"]),
            "date": e.get("date"),
            "season": (e.get("season") or {}).get("year"),
            "season_type": season_type.get("type"),
            "away_team": (away.get("team") or {}).get("abbreviation"),
            "home_team": (home.get("team") or {}).get("abbreviation"),
            "away_team_id": int(away["id"]) if away.get("id") else None,
            "home_team_id": int(home["id"]) if home.get("id") else None,
            "away_score": _score(away.get("score")) if played else None,
            "home_score": _score(home.get("score")) if played else None,
            "completed": status.get("completed"),
            "status": status.get("shortDetail") or status.get("description"),
            "venue": (comp.get("venue") or {}).get("fullName"),
            "attendance": comp.get("attendance"),
        })
    return rows


def _games_frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.drop_duplicates("game_id").sort_values(["date", "game_id"]).reset_index(drop=True)
    for col in ("away_score", "home_score", "attendance"):
        df[col] = df[col].astype("Int64")
    return df


def scoreboard(dates=None) -> pd.DataFrame:
    """Every game on one or more dates (default: today), with scores.

    >>> scoreboard(["2025-04-14", "2025-04-15"])

    ESPN only answers single days, so a list means one request per date.
    For a whole season use :func:`schedule`.
    """
    rows = []
    for d in as_list(dates) if dates is not None else [None]:
        data = _http.get_json(f"{SITE}/scoreboard", params={"dates": _date_param(d)})
        rows.extend(parse_events(data.get("events") or []))
    return _games_frame(rows)


def team_schedule(team, season, *, playoffs: bool = False) -> pd.DataFrame:
    """One team's games for a season. ``team`` is an ESPN ID or abbreviation ("det")."""
    data = _http.get_json(f"{SITE}/teams/{team}/schedule",
                          params={"season": espn_season(season), "seasontype": _season_type(playoffs)})
    return _games_frame(parse_events(data.get("events") or []))


def schedule(season, *, playoffs: bool = False) -> pd.DataFrame:
    """Every game of a season, built from all 32 team schedules (32 requests)."""
    rows = []
    for team_id in teams()["team_id"]:
        data = _http.get_json(f"{SITE}/teams/{team_id}/schedule",
                              params={"season": espn_season(season), "seasontype": _season_type(playoffs)})
        rows.extend(parse_events(data.get("events") or []))
    log.info("ESPN %s schedule: %d team-games", season, len(rows))
    return _games_frame(rows)


# --------------------------------------------------------------------------
# Single game: box score and play-by-play
# --------------------------------------------------------------------------

def _summary(game_id) -> dict:
    return _http.get_json(f"{SITE}/summary", params={"event": game_id})


def parse_boxscore(summary: dict, game_id=None) -> list[dict]:
    """Player rows from a game summary's ``boxscore.players`` block."""
    rows = []
    for team_block in (summary.get("boxscore") or {}).get("players") or []:
        team = team_block.get("team") or {}
        for group in team_block.get("statistics") or []:
            keys = [snake(k) for k in group.get("keys") or []]
            for entry in group.get("athletes") or []:
                a = entry.get("athlete") or {}
                row = {
                    "game_id": game_id,
                    "team": team.get("abbreviation"),
                    "team_id": int(team["id"]) if team.get("id") else None,
                    "group": group.get("name"),
                    "player_id": int(a["id"]) if a.get("id") else None,
                    "player": a.get("displayName"),
                    "jersey": a.get("jersey"),
                    "position": (a.get("position") or {}).get("abbreviation"),
                    "scratched": a.get("scratched"),
                }
                row |= dict(zip(keys, entry.get("stats") or []))
                rows.append(row)
    return rows


def boxscore(game_ids) -> pd.DataFrame:
    """Player box scores (TOI splits, shots, hits, faceoffs, goalie saves...).

    Time-on-ice columns are left as "MM:SS" strings; everything else numeric.
    """
    rows = []
    for gid in as_list(game_ids):
        rows.extend(parse_boxscore(_summary(gid), int(gid)))
    df = pd.DataFrame(rows)
    return _numeric(df, skip=("jersey",)) if not df.empty else df


def parse_plays(summary: dict, game_id=None) -> list[dict]:
    """Event rows from a game summary's ``plays`` list."""
    rows = []
    for p in summary.get("plays") or []:
        coord = p.get("coordinate") or {}
        row = {
            "game_id": game_id,
            "play_id": p.get("id"),
            "sequence": int(p["sequenceNumber"]) if p.get("sequenceNumber") else None,
            "period": (p.get("period") or {}).get("number"),
            "clock": (p.get("clock") or {}).get("displayValue"),
            "event": (p.get("type") or {}).get("text"),
            "team_id": int(p["team"]["id"]) if (p.get("team") or {}).get("id") else None,
            "description": p.get("text"),
            "strength": (p.get("strength") or {}).get("text"),
            "shot_info": (p.get("shotInfo") or {}).get("text"),
            "x": coord.get("x"),
            "y": coord.get("y"),
            "away_score": p.get("awayScore"),
            "home_score": p.get("homeScore"),
            "scoring_play": p.get("scoringPlay"),
            "wallclock": p.get("wallclock"),
        }
        for i, part in enumerate(p.get("participants") or [], 1):
            a = part.get("athlete") or {}
            row[f"player{i}_id"] = int(a["id"]) if a.get("id") else None
            row[f"player{i}"] = a.get("displayName")
            row[f"player{i}_role"] = part.get("type")
        rows.append(row)
    return rows


def play_by_play(game_ids) -> pd.DataFrame:
    """Every event of one or more games, with rink coordinates where ESPN has them.

    ``clock`` is time elapsed in the period; ``period_seconds`` is the same in seconds.
    """
    rows = []
    for gid in as_list(game_ids):
        rows.extend(parse_plays(_summary(gid), int(gid)))
    df = pd.DataFrame(rows)
    if not df.empty:
        df.insert(df.columns.get_loc("clock") + 1, "period_seconds", clock_to_seconds(df["clock"]))
        for col in [c for c in df.columns if c.endswith("_id")]:
            df[col] = df[col].astype("Int64")
    return df


# --------------------------------------------------------------------------
# Teams and standings
# --------------------------------------------------------------------------

def teams() -> pd.DataFrame:
    """ESPN team IDs, abbreviations and names."""
    data = _http.get_json(f"{SITE}/teams")
    rows = []
    for league in (data.get("sports") or [{}])[0].get("leagues") or []:
        for entry in league.get("teams") or []:
            t = entry.get("team") or {}
            rows.append({
                "team_id": int(t["id"]),
                "abbreviation": t.get("abbreviation"),
                "team": t.get("displayName"),
                "location": t.get("location"),
                "name": t.get("name"),
                "slug": t.get("slug"),
                "color": t.get("color"),
                "alternate_color": t.get("alternateColor"),
            })
    return pd.DataFrame(rows)


def parse_standings(data: dict) -> list[dict]:
    """Team rows from a ``level=3`` standings response (league > conference > division)."""
    rows = []

    def walk(node: dict, path: list[str]):
        if node.get("children"):
            for child in node["children"]:
                walk(child, path + [child.get("name")])
            return
        for entry in (node.get("standings") or {}).get("entries") or []:
            t = entry.get("team") or {}
            row = {
                "conference": path[0] if len(path) > 0 else None,
                "division": path[1] if len(path) > 1 else None,
                "team": t.get("displayName"),
                "abbreviation": t.get("abbreviation"),
                "team_id": int(t["id"]) if t.get("id") else None,
            }
            for s in entry.get("stats") or []:
                name = snake(s.get("name") or "")
                # Record splits ("Home", "LastTenGames") only have a display value like "26-9-6";
                # clincher and streak are codes whose display value ("z", "L1") is the useful part.
                if s.get("value") is None or name in ("clincher", "streak"):
                    row[name] = s.get("displayValue")
                else:
                    row[name] = s.get("value")
            rows.append(row)

    walk(data, [])
    return rows


def standings(season=None) -> pd.DataFrame:
    """Final (or current, by default) standings with conference and division."""
    params = {"level": 3}
    if season is not None:
        params["season"] = espn_season(season)
    df = pd.DataFrame(parse_standings(_http.get_json(STANDINGS, params=params)))
    if df.empty:
        return df
    # ESPN's generic standings call goals "points". games_behind is meaningless in hockey;
    # points_diff, differential and overtime_losses duplicate other columns.
    df = df.drop(columns=["games_behind", "points_diff", "differential", "overtime_losses"], errors="ignore")
    df = df.rename(columns={"points_for": "goals_for", "points_against": "goals_against",
                            "point_differential": "goal_differential"})
    count_cols = [c for c in df.columns if df[c].dtype == float and df[c].dropna().mod(1).eq(0).all()]
    df[count_cols] = df[count_cols].astype("Int64")
    sort = [c for c in ("conference", "division", "playoff_seed") if c in df]
    return df.sort_values(sort).reset_index(drop=True)


def parse_roster(data: dict) -> list[dict]:
    team = (data.get("team") or {}).get("abbreviation")
    rows = []
    for group in data.get("athletes") or []:
        for a in group.get("items") or []:
            rows.append({
                "team": team,
                "player_id": int(a["id"]),
                "player": a.get("fullName"),
                "jersey": a.get("jersey"),
                "position": (a.get("position") or {}).get("abbreviation"),
                "shoots": (a.get("hand") or {}).get("abbreviation"),
                "age": a.get("age"),
                "dob": (a.get("dateOfBirth") or "")[:10] or None,
                "height_in": a.get("height"),
                "weight_lb": a.get("weight"),
                "birthplace": (a.get("birthPlace") or {}).get("displayText"),
                "birth_country": (a.get("birthCountry") or {}).get("abbreviation"),
                "college": (a.get("college") or {}).get("name"),
                "debut_year": a.get("debutYear"),
                "injured": bool(a.get("injuries")),
            })
    return rows


def roster(team) -> pd.DataFrame:
    """Current roster for one or more teams (ESPN IDs or abbreviations like "det").

    ESPN only serves the current roster; past seasons come back empty.
    """
    rows = []
    for t in as_list(team):
        rows.extend(parse_roster(_http.get_json(f"{SITE}/teams/{t}/roster")))
    df = pd.DataFrame(rows)
    for col in ("age", "height_in", "weight_lb", "debut_year"):
        if col in df:
            df[col] = df[col].astype("Int64")
    return df


# --------------------------------------------------------------------------
# Players
# --------------------------------------------------------------------------

def parse_player_stats(data: dict) -> list[dict]:
    """Rows from a ``statistics/byathlete`` page. Stat names come from the top-level categories."""
    names = {c["name"]: [snake(n) for n in c.get("names") or []] for c in data.get("categories") or []}
    rows = []
    for entry in data.get("athletes") or []:
        a = entry.get("athlete") or {}
        row = {
            "player_id": int(a["id"]),
            "player": a.get("displayName"),
            "position": (a.get("position") or {}).get("abbreviation"),
            "team": a.get("teamShortName"),
        }
        for cat in entry.get("categories") or []:
            for name, value in zip(names.get(cat.get("name"), []), cat.get("values") or []):
                row.setdefault(name, value)
        rows.append(row)
    return rows


def player_stats(season, *, playoffs: bool = False) -> pd.DataFrame:
    """Season totals for every player, skaters and goalies together.

    Goalie stats (saves, GAA...) are 0 for skaters. ``time_on_ice`` and
    ``time_on_ice_per_game`` are in seconds.
    """
    rows, page = [], 1
    while True:
        data = _http.get_json(f"{COMMON}/statistics/byathlete", params={
            "season": espn_season(season), "seasontype": _season_type(playoffs),
            "limit": 1000, "page": page,
        })
        rows.extend(parse_player_stats(data))
        pages = (data.get("pagination") or {}).get("pages") or 1
        if page >= pages:
            break
        page += 1
    df = pd.DataFrame(rows)
    count_cols = [c for c in df.columns if df[c].dtype == float and df[c].dropna().mod(1).eq(0).all()]
    df[count_cols] = df[count_cols].astype("Int64")
    return df


def parse_game_log(data: dict, player_id=None) -> list[dict]:
    """Per-game rows from an athlete ``gamelog`` response."""
    names = [snake(n) for n in data.get("names") or []]
    events = data.get("events") or {}
    rows, seen = [], set()
    for season_type in data.get("seasonTypes") or []:
        for cat in season_type.get("categories") or []:
            for line in cat.get("events") or []:
                gid = line.get("eventId")
                if gid in seen:
                    continue
                seen.add(gid)
                e = events.get(gid) or {}
                row = {
                    "player_id": player_id,
                    "game_id": int(gid),
                    "date": e.get("gameDate"),
                    "season_type": season_type.get("displayName"),
                    "team": (e.get("team") or {}).get("abbreviation"),
                    "opponent": (e.get("opponent") or {}).get("abbreviation"),
                    "home": e.get("atVs") == "vs",
                    "result": e.get("gameResult"),
                    "score": e.get("score"),
                }
                row |= dict(zip(names, line.get("stats") or []))
                rows.append(row)
    return rows


def game_log(player_ids, season=None) -> pd.DataFrame:
    """Game-by-game stats for one or more ESPN player IDs (current season by default).

    Regular season and playoffs are both included; see ``season_type``.
    """
    rows = []
    for pid in as_list(player_ids):
        params = {"season": espn_season(season)} if season is not None else None
        data = _http.get_json(f"{COMMON}/athletes/{pid}/gamelog", params=params)
        rows.extend(parse_game_log(data, int(pid)))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return _numeric(df, skip=("score",)).sort_values(["player_id", "date"]).reset_index(drop=True)


def parse_injuries(data: dict) -> list[dict]:
    rows = []
    for team in data.get("injuries") or []:
        for i in team.get("injuries") or []:
            a = i.get("athlete") or {}
            details = i.get("details") or {}
            rows.append({
                "team": (a.get("team") or {}).get("abbreviation"),
                "player_id": _athlete_id_from_links(a),
                "player": a.get("displayName"),
                "position": (a.get("position") or {}).get("abbreviation"),
                "status": i.get("status"),
                "injury": details.get("type"),
                "return_date": details.get("returnDate"),
                "updated": i.get("date"),
                "comment": i.get("shortComment"),
            })
    return rows


def injuries() -> pd.DataFrame:
    """ESPN's current league-wide injury report."""
    df = pd.DataFrame(parse_injuries(_http.get_json(f"{SITE}/injuries")))
    if "player_id" in df:
        df["player_id"] = df["player_id"].astype("Int64")
    return df
