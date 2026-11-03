"""Sweden's national junior leagues (U20 Nationell, U18 Nationell) from the Swedish Ice Hockey Association's
stats site, stats.swehockey.se.

A season is split into groups (Norra, Södra, and later series), each a competition with its own id. The
season picker on a competition's overview page links each season's first group, and that season's group
picker links the rest. Per group, two pages per team:

    Teams/Info/PlayersByTeam/<id>    every skater's GP, G, A, TP, PIM...
    Teams/Info/TeamRoster/<id>       his birth date, position, shot and nationality

joined on team and name. Groups whose name says playoffs ("slutspel", "kval") are the playoffs.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from ._common import Unsupported, finish, soup

log = logging.getLogger("puckscrape.leagues")

BASE = "https://stats.swehockey.se"
PLAYOFFS = re.compile(r"slutspel|kval|playoff|final", re.I)
SEASON = re.compile(r"^(\d{4})-\d{2}$")


def _overview(cid: int):
    return soup(f"{BASE}/ScheduleAndResults/Overview/{cid}")


def _season_ids(start: int) -> dict[int, int]:
    """Start year -> the competition id of that season's first group, from the season picker."""
    out = {}
    for sel in _overview(start).find_all("select"):
        for o in sel.find_all("option"):
            m = SEASON.match(o.get_text(strip=True))
            cid = re.search(r"/Overview/(\d+)", o.get("value") or "")
            if m and cid:
                out[int(m.group(1))] = int(cid.group(1))
        if out:
            break
    return out


def _groups(cid: int, series: str) -> list[tuple[str, int]]:
    """The season's groups of this series: (name, competition id), from the group picker."""
    out = []
    for sel in _overview(cid).find_all("select"):
        opts = [(o.get_text(" ", strip=True), re.search(r"/Overview/(\d+)$", o.get("value") or "")) for o in sel.find_all("option")]
        opts = [(name, int(m.group(1))) for name, m in opts if m]
        if any(series.lower() in name.lower() for name, _ in opts) and not all(SEASON.match(n) for n, _ in opts):
            out = [(name, i) for name, i in opts if series.lower() in name.lower()]
            break
    return out or [(series, cid)]


def _first_last(name: str) -> str:
    """'Höglund, Oliver' -> 'Oliver Höglund'."""
    last, _, first = name.partition(",")
    return f"{first.strip()} {last.strip()}".strip()


def _team_tables(page, first: str) -> list[tuple[str, pd.DataFrame]]:
    """Each team's table on a by-team page: (team, rows), the rows under the header row starting ``first``."""
    out = []
    for table in page.find_all("table"):
        if table.find("table"):
            continue
        rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        if not rows or "[Top]" not in rows[0]:
            continue
        team = rows[0][0]
        head = next((i for i, r in enumerate(rows) if r and r[0] == first and "Name" in r), None)
        if head is None:
            continue
        cols = rows[head]
        body = [r for r in rows[head + 1:] if len(r) == len(cols)]
        out.append((team, pd.DataFrame(body, columns=cols)))
    return out


def _group_skaters(cid: int) -> pd.DataFrame:
    stats = _team_tables(soup(f"{BASE}/Teams/Info/PlayersByTeam/{cid}"), "Rk")
    roster = _team_tables(soup(f"{BASE}/Teams/Info/TeamRoster/{cid}"), "No")
    frames = []
    bio = pd.concat([df.assign(team=t) for t, df in roster], ignore_index=True) if roster else pd.DataFrame()
    for team, df in stats:
        if "GP" not in df or "Pos" not in df:   # the goalkeeping table
            continue
        df = df.assign(team=team)
        if len(bio):
            b = bio[bio.team == team][[c for c in ("Name", "Birthdate", "L/R", "Nationality / Club") if c in bio]]
            df = df.merge(b.drop_duplicates("Name"), on="Name", how="left")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    df.insert(0, "player", df.pop("Name").map(_first_last))
    return df


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    seasons = _season_ids(opts["start"])
    if y not in seasons:
        raise Unsupported(f"stats.swehockey.se has no {opts['series']} {y}-{y + 1}")
    playoffs = phase.lower().startswith("play")
    groups = [(n, i) for n, i in _groups(seasons[y], opts["series"]) if bool(PLAYOFFS.search(n)) == playoffs]
    frames = []
    for name, cid in groups:
        df = _group_skaters(cid)
        if len(df):
            frames.append(df.assign(group=name))
        log.info("%s %s %s: %d skaters", league, y, name, len(df))
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return finish(df, "skaters", league, y, "playoffs" if playoffs else "regular", rename={
        "Pos": "position", "GP": "gp", "G": "g", "A": "a", "TP": "pts", "PIM": "pim", "+/-": "plus_minus",
        "Birthdate": "birthdate", "L/R": "shoots", "Nationality / Club": "nationality", "No": "number"},
        drop=("Rk", "+", "-"))


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    raise Unsupported("stats.swehockey.se goalies aren't read yet")


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    raise Unsupported("stats.swehockey.se standings aren't read yet")
