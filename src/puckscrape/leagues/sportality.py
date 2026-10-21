"""Sportality 'statnet' API behind shl.se and sdhl.se (SHL, SDHL)."""

from __future__ import annotations

from functools import cache

import pandas as pd

from ._common import finish, get_json, phase_key


@cache
def _ssgts(host: str) -> list[dict]:
    """Every season/series/game-type combination the site knows (back to 1975 for SHL)."""
    out = []
    for block in get_json(f"{host}/api/statistics-v2/layout-info"):
        out.extend(block.get("originalSeasonSeriesGameTypeTeams", []))
    return out


def _ssgt(host: str, series: str, y: int, phase: str) -> str:
    game_type = "regular" if phase_key(phase) == "regular" else "playoff"
    for s in _ssgts(host):
        if (s["series"]["code"] == series and s["season"]["code"] == str(y)
                and s["gameType"]["code"] == game_type):
            return s["ssgtUuid"]
    raise ValueError(f"no {series} {game_type} season {y}-{y + 1}")


def _module(opts: dict, module: str, y: int, phase: str) -> list[dict]:
    uuid = _ssgt(opts["host"], opts["series"], y, phase)
    data = get_json(f"{opts['host']}/api/statistics-v2/stats-info/{module}", ssgtUuid=uuid, count=5000)
    return data[0]["stats"] if data else []


def _with_info(rows: list[dict]) -> pd.DataFrame:
    flat = []
    for r in rows:
        info = r.get("info") or {}
        team = info.get("team") or {}
        flat.append({
            "player": info.get("fullName"), "player_id": info.get("uuid"),
            "team": team.get("name"), "team_code": info.get("teamCode"),
            "position": info.get("position"), "number": info.get("number"),
            "birth_date": info.get("birthDate"), "nationality": info.get("nationality"),
            "shoots": info.get("shoots"),
            "height_cm": (info.get("height") or {}).get("value"),
            "weight_kg": (info.get("weight") or {}).get("value"),
            **{k: v for k, v in r.items() if k not in ("info", "Rank", "Player", "Team")},
        })
    return pd.DataFrame(flat)


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _with_info(_module(opts, "players_summary", y, phase))
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "GP": "gp", "G": "g", "A": "a", "TP": "pts", "PIM": "pim", "PlusMinus": "plus_minus",
        "SOG": "shots", "PPG": "ppg", "GWG": "gwg", "BkS": "blocks", "TOI_GP": "toi_per_gp",
        "TPPG": "pts_per_gp"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _with_info(_module(opts, "goalkeepers_summary", y, phase))
    if "SVSPerc" in df:
        df["SVSPerc"] = pd.to_numeric(df["SVSPerc"], errors="coerce") / 100
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "GPI": "gp", "GP": "games_dressed", "W": "w", "L": "l", "T": "t", "GA": "ga", "SVS": "saves",
        "SVSPerc": "sv_pct", "GAA": "gaa", "SO": "so", "MIP": "toi"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    rows = _module(opts, "teams_result", y, phase)
    df = pd.DataFrame([{
        "team": (r.get("info") or {}).get("siteDisplayName") or (r.get("info") or {}).get("name"),
        **{k: v for k, v in r.items() if k not in ("info", "Team")}} for r in rows])
    return finish(df, "standings", league, y, phase_key(phase), rename={
        "GP": "gp", "W": "w", "L": "l", "OTW": "otw", "OTL": "otl", "Points": "pts", "G": "gf",
        "GA": "ga", "Rank": "rank"})
