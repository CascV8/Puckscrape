"""Swedish federation leagues from stats.swehockey.se (U18 and U20 Nationell).

Each season of a league is split into series (U18 Nationell Norra / Södra, U18
SM-slutspel...), each with its own id. A league's season dropdown leads to one
series of each season, whose series dropdown lists the rest. Every row keeps its
series in a ``stage`` column; "playoffs" is the SM-slutspel series. Players and
goalies come from the "Players By Team" page: every player of every team, one
page per series.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, cells, clean_team, finish, phase_key, soup

BASE = "https://stats.swehockey.se"
_PLAYOFF = re.compile(r"slutspel|SM-final|kvartsfinal|semifinal", re.I)


def _selects(page) -> list[list[tuple[str, str]]]:
    return [[(o.get("value", ""), o.get_text(strip=True)) for o in sel.find_all("option")] for sel in page.find_all("select")]


@cache
def _seasons(start_id: int) -> dict[str, int]:
    """'2025-26' -> the id of one series of that season, from the season dropdown."""
    for options in _selects(soup(f"{BASE}/ScheduleAndResults/Overview/{start_id}")):
        found = {label: int(m.group(1)) for value, label in options
                 if re.fullmatch(r"\d{4}-\d{2}", label) and (m := re.search(r"/(\d+)$", value))}
        if found:
            return found
    return {}


@cache
def _series(start_id: int, y: int) -> tuple[tuple[int, str], ...]:
    label = f"{y}-{(y + 1) % 100:02d}"
    sid = _seasons(start_id).get(label)
    if sid is None:
        have = sorted(_seasons(start_id))
        raise ValueError(f"stats.swehockey.se has no {label} season here (it has {have[0]} to {have[-1]})")
    for options in _selects(soup(f"{BASE}/ScheduleAndResults/Overview/{sid}")):
        if any(re.fullmatch(r"\d{4}-\d{2}", label) for _, label in options):
            continue   # the season dropdown
        series = [(int(m.group(1)), label) for value, label in options
                  if "/ScheduleAndResults/Overview/" in value and (m := re.search(r"/(\d+)$", value))]
        if series:
            return tuple(series)
    return ((sid, label),)


def _phase_series(opts: dict, y: int, phase: str) -> list[tuple[int, str]]:
    """Series of one phase. ``start_ids`` lists several league trees read as one league
    (U18 Regional: one tree per region); a tree without that season is skipped."""
    want = phase_key(phase) == "playoffs"
    series = []
    for start_id in opts.get("start_ids") or (opts["start_id"],):
        try:
            series += _series(start_id, y)
        except ValueError:
            continue
    found = [s for s in series if bool(_PLAYOFF.search(s[1])) == want]
    if not found:
        raise ValueError(f"no {phase_key(phase)} series in {y}-{y + 1}")
    return found


def _players_by_team(series_id: int) -> tuple[list[dict], list[dict]]:
    """(skater rows, goalie rows) of one series, each tagged with its team."""
    page = soup(f"{BASE}/Teams/Info/PlayersByTeam/{series_id}")
    skaters, goalies, team = [], [], None
    for table in page.find_all("table"):
        if table.find("table"):
            continue
        rows = [cells(tr) for tr in table.find_all("tr")]
        rows = [r for r in rows if any(r)]
        if not rows:
            continue
        if rows[0] and rows[0][-1] == "[Top]":          # team banner: 'AIK', 'AIK', ..., '[Top]'
            team = clean_team(rows[0][0])
            rows = rows[1:]
        for i, r in enumerate(rows):
            if r[:3] == ["Rk", "No", "Name"]:
                header, target = r, goalies if "GPI" in r else skaters
                for data in rows[i + 1:]:
                    if len(data) == len(header) and data[2]:
                        target.append({**dict(zip(header, data)), "team": team})
                break
    return skaters, goalies


def _frame(opts: dict, y: int, phase: str, goalies: bool) -> pd.DataFrame:
    frames = []
    for series_id, name in _phase_series(opts, y, phase):
        rows = _players_by_team(series_id)[1 if goalies else 0]
        if rows:
            frames.append(pd.DataFrame(rows).assign(stage=re.sub(r"\s+", " ", name)))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop(columns=["Rk"])
    df = df.drop_duplicates()
    df.insert(0, "player", df.pop("Name").map(_first_last))
    return df


def _first_last(name: str) -> str:
    """'Forssell, Mio' -> 'Mio Forssell'."""
    last, _, first = str(name).partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _na_text(df: pd.DataFrame) -> pd.DataFrame:
    return df.replace({"N/A": pd.NA, "": pd.NA})


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _frame(opts, y, phase, goalies=False)
    if df.empty:
        return df
    df = df[df["Pos"] != "GK"]   # goalies are listed with empty skater lines; see goalies()
    return finish(_na_text(df), "skaters", league, y, phase_key(phase), rename={
        "No": "jersey", "Pos": "position", "GP": "gp", "G": "g", "A": "a", "TP": "pts", "PIM": "pim",
        "+": "plus", "-": "minus", "+/-": "plus_minus", "GWG": "gwg", "PPG": "ppg", "SHG": "shg", "SOG": "shots",
        "SG%": "shooting_pct", "FO+": "faceoffs_won", "FO-": "faceoffs_lost", "FO": "faceoffs", "FO%": "faceoff_pct"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _frame(opts, y, phase, goalies=True)
    if df.empty:
        return df
    df = _na_text(df)
    df = df[pd.to_numeric(df["GPI"], errors="coerce").fillna(0) > 0].copy()   # dressed but never played
    df["MIP"] = df["MIP"].map(_minutes)
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "No": "jersey", "GPT": "team_gp", "GKD": "games_dressed", "GPI": "gp", "MIP": "toi", "GA": "ga",
        "SVS": "saves", "SOG": "shots_against", "SVS%": "sv_pct", "GAA": "gaa", "SO": "so", "W": "w", "L": "l"})


def _minutes(clock):
    m = re.fullmatch(r"\s*(\d+):(\d{2})\s*", str(clock))
    return round(int(m.group(1)) + int(m.group(2)) / 60, 2) if m else pd.NA


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only (the SM-slutspel is series)")
    frames = []
    for series_id, name in _phase_series(opts, y, phase):
        page = soup(f"{BASE}/ScheduleAndResults/Standings/{series_id}")
        for table in page.find_all("table"):
            if table.find("table"):
                continue
            rows = [r for r in (cells(tr) for tr in table.find_all("tr")) if any(r)]
            # The first table is the full standings (later ones: home, away, last 5...).
            if len(rows) > 2 and rows[1][:2] == ["RK", "Team"]:
                body = [r for r in rows[2:] if len(r) == len(rows[1])]
                frames.append(pd.DataFrame(body, columns=rows[1]).assign(stage=re.sub(r"\s+", " ", name)))
                break
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    score = df.pop("GF:GA (GD)").str.extract(r"(\d+)\s*:\s*(\d+)")
    df["gf"], df["ga"] = score[0], score[1]
    df["Team"] = df["Team"].map(clean_team)
    return finish(df, "standings", league, y, "regular", drop=("GD",), rename={
        "RK": "rank", "Team": "team", "GP": "gp", "W": "w", "T": "t", "L": "l", "TP": "pts", "OTW": "otw",
        "OTL": "otl", "GWSW": "sow", "GWSL": "sol"})
