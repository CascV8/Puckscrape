"""KHL and MHL from the KHL's own app feed (khl.api.webcaster.pro).

khl.ru, mhl.khl.ru and the VHL's vhlru.ru refuse connections from many networks,
but the feed behind the KHL's mobile apps is served from a different host and
answers keyless JSON. It is the KHL's data: the same players, ids and numbers.

A season has one "stage" per phase (regular season, play-in, playoffs), each with
its own id, listed in ``data.json``. Player stats come 16 players a page from
``players_v2.json`` (about 60 pages for a KHL season, 6 s each: a season takes
several minutes; skaters() and goalies() share the pages). Each player's ``team``
there is his current one, so the team he played for that season comes from his
team history. Standings are rebuilt from the stage's game results, because the
feed's own tables only hold the season under way.
"""

from __future__ import annotations

from collections import defaultdict
from functools import cache

import pandas as pd

from ._common import Unsupported, finish, get_json, phase_key

API = "https://khl.api.webcaster.pro/api/{app}/{endpoint}.json"
_STAGE_TYPE = {"regular": "regular", "playoffs": "playoff"}
_POSITION = {"forward": "F", "defensemen": "D", "defenseman": "D", "goaltender": "G"}


def _get(app: str, endpoint: str, **params):
    data = get_json(API.format(app=app, endpoint=endpoint), locale="en", **params)
    if isinstance(data, dict) and "error" in data:
        raise ValueError(f"{app} {endpoint}: {data['error']}")
    return data


@cache
def _stages(app: str) -> tuple[dict, ...]:
    return tuple(_get(app, "data")["stages_v2"])


def _stage(app: str, y: int, phase: str) -> dict:
    season, kind = f"{y}/{y + 1}", _STAGE_TYPE[phase_key(phase)]
    for st in _stages(app):
        if st["season"] == season and st["type"] == kind:
            return st
    have = sorted({st["season"] for st in _stages(app)})
    raise ValueError(f"no {phase_key(phase)} stage for {season} in the {app.split('_')[0].upper()} feed "
                     f"(it has {have[0]} to {have[-1]})")


@cache
def _stage_teams(app: str, stage_id: int) -> frozenset[int]:
    return frozenset(t["team"]["id"] for t in _get(app, "teams_v2", stage_id=stage_id))


@cache
def _players(app: str, stage_id: int, season: str) -> tuple[dict, ...]:
    """Every player of a stage, flattened to one dict each (stats by their feed ids)."""
    teams = _stage_teams(app, stage_id)
    rows = []
    for page in range(1, 500):
        batch = _get(app, "players_v2", stage_id=stage_id, page=page)
        if not batch:
            break
        for item in batch:
            p = item["player"]
            stats = {s["id"]: s.get("val") for s in p.get("stats") or []}
            if not stats.get("gp"):
                continue
            # Teams that season, leaving out all-star selections (not in the stage's team list).
            played = [t["name"] for t in p.get("teams") or []
                      if season in (t.get("seasons") or "").split(",") and t["id"] in teams]
            rows.append({
                "player": _first_last(p["name"]), "player_id": p.get("khl_id"),
                "team": " / ".join(played) if played else None,
                "position": _POSITION.get(p.get("role_key"), p.get("role_key")),
                **stats,
                "jersey": p.get("shirt_number"), "birth_date": _date(p.get("birthday")),
                "height_cm": p.get("height"), "weight_kg": p.get("weight"), "shoots": (p.get("stick") or "").upper() or None,
                "nationality": p.get("country"), "feed_player_id": p.get("id"),
            })
    return tuple(rows)


def _first_last(name: str) -> str:
    """The feed writes 'Surname Given' ('Kaprizov Kirill', 'Alexeyev Denis V.')."""
    parts = name.split()
    return " ".join(parts[1:] + parts[:1]) if len(parts) > 1 else name


def _date(ts):
    return pd.to_datetime(ts, unit="s").date().isoformat() if ts else None


def _frame(opts, league, y, phase, goalies: bool) -> pd.DataFrame:
    app = opts["app"]
    st = _stage(app, y, phase)
    rows = [r for r in _players(app, st["id"], st["season"]) if (r["position"] == "G") == goalies]
    return pd.DataFrame(rows)


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _frame(opts, league, y, phase, goalies=False)
    return finish(df, "skaters", league, y, phase_key(phase), drop=("time_on_ice",), rename={
        "pm": "plus_minus", "toi_avg": "toi_per_gp", "sft_avg": "shifts_per_gp", "fow": "faceoffs_won",
        "sds": "shootout_winners", "pim_avg": "pim_per_gp", "top_speed": "top_speed_kmh",
        "distance_travelled": "distance_km"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _frame(opts, league, y, phase, goalies=True)
    if not df.empty:
        df = df.drop(columns=[c for c in ("position", "top_speed", "distance_travelled", "time_on_ice")
                              if c in df])
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "sv": "saves", "sop": "shootout_games"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    app = opts["app"]
    st = _stage(app, y, phase)
    table: dict[str, dict] = defaultdict(lambda: dict.fromkeys(
        ("gp", "w", "otw", "sow", "l", "otl", "sol", "gf", "ga"), 0))
    for game in _games(app, st["id"]):
        sc = game.get("scores") or {}
        try:
            a, b = (int(x) for x in game["score"].split(":"))
        except (AttributeError, ValueError):
            continue
        extra = "so" if sc.get("bullitt") else "ot" if sc.get("overtime") else ""
        for team, gf, ga in ((game["team_a"]["name"], a, b), (game["team_b"]["name"], b, a)):
            row = table[team]
            row["gp"] += 1
            row["gf"] += gf
            row["ga"] += ga
            row[extra + ("w" if gf > ga else "l")] += 1   # w/l, otw/otl, sow/sol
    if not table:
        return pd.DataFrame()
    df = pd.DataFrame.from_dict(table, orient="index").rename_axis("team").reset_index()
    df["pts"] = 2 * (df["w"] + df["otw"] + df["sow"]) + df["otl"] + df["sol"]
    df["pts_pct"] = (df["pts"] / (2 * df["gp"])).round(4)
    df = df.sort_values(["pts", "gp"], ascending=[False, True]).reset_index(drop=True)
    return finish(df, "standings", league, y, "regular")


def _games(app: str, stage_id: int) -> list[dict]:
    """Finished games of a stage (the feed pages them 16 at a time)."""
    games = []
    for page in range(1, 500):
        batch = _get(app, "events_v2", stage_id=stage_id, page=page)
        if not batch:
            break
        games += [e["event"] for e in batch
                  if e["event"].get("game_state_key") == "finished" and e["event"].get("stage_id") == stage_id]
    return games
