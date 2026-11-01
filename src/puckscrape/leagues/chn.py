"""NCAA Division I men's and women's hockey from College Hockey News.

There's no league-wide player table, so each team's stats page is read (about 64
requests a season for the men, about 45 for the women, cached for the session).
Seasons are whole seasons: regular season and playoffs combined. The women's
pages sit under /women/, with the index at /women/stats.php.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from ._common import Unsupported, finish, find_table, soup, table_rows

log = logging.getLogger("puckscrape.leagues")

BASE = "https://www.collegehockeynews.com"


def _index_url(opts: dict) -> str:
    return f"{BASE}/women/stats.php" if opts.get("women") else f"{BASE}/stats/index.php"


def _team_pages(opts: dict, y: int) -> list[str]:
    prefix = "/women" if opts.get("women") else ""
    index = soup(_index_url(opts), season=f"{y}{y + 1}")
    # Past seasons link '/stats/team/Michigan/31/overall,20252026'; the season under way links plain
    # '/stats/team/Michigan/31', so both are read and pointed at the season asked for.
    links = set()
    for a in index.find_all("a", href=True):
        m = re.match(rf"({prefix}/stats/team/[^/]+/\d+)(?:/overall,\d{{8}})?$", a["href"])
        if m:
            links.add(f"{m.group(1)}/overall,{y}{y + 1}")
    if not links:
        raise ValueError(f"College Hockey News has no {y}-{y + 1} season")
    return sorted(links)


def league_name(opts: dict) -> str:
    return "NCAA women" if opts.get("women") else "NCAA"


def _split_name(text: str, goalie: bool) -> tuple[str, str | None, str | None]:
    """'Jack Beck, F, So' -> (Jack Beck, F, So); goalies: 'Samuel Urban, So'."""
    parts = [p.strip() for p in text.split(",")]
    if goalie:
        return parts[0], "G", parts[1] if len(parts) > 1 else None
    return parts[0], parts[1] if len(parts) > 1 else None, parts[2] if len(parts) > 2 else None


def _collect(opts: dict, y: int, goalie: bool) -> pd.DataFrame:
    frames = []
    pages = _team_pages(opts, y)
    for i, href in enumerate(pages, 1):
        page = soup(BASE + href)
        team = re.sub(r"\s*Statistics.*$", "", (page.title.string or "")).strip()
        team = re.sub(r"^(?:Women's\s+)?\d{4}\S*\s+", "", team)
        table = find_table(page, "Name, Yr", "SV%") if goalie else find_table(page, "Name, Yr", "Pts.")
        if table is None:
            continue
        df = table_rows(table, ("Name, Yr",))
        df = df[~df["Name, Yr"].str.contains(r"^(?:Totals?|Opponents?|Team)\b", regex=True, case=False)]
        split = [_split_name(n, goalie) for n in df["Name, Yr"]]
        df.insert(0, "player", [s[0] for s in split])
        df.insert(1, "position", [s[1] for s in split])
        df.insert(2, "class", [s[2] for s in split])
        df.insert(3, "team", team)
        df.insert(4, "team_id", int(href.rstrip("/").split("/")[-2]))
        frames.append(df.drop(columns=["Name, Yr"]))
        log.info("%s %s: %d/%d teams", league_name(opts), "goalies" if goalie else "skaters", i, len(pages))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase.lower().startswith("play"):
        raise Unsupported("College Hockey News publishes whole-season totals only; use phase='regular'")
    df = _collect(opts, y, goalie=False)
    return finish(df, "skaters", league, y, "season", rename={
        "GP": "gp", "G": "g", "A": "a", "Pts.": "pts", "PIM": "pim", "+/-": "plus_minus",
        "Pt/GP": "pts_per_gp", "Sh%": "sh_pct", "TOI/G": "toi_per_gp"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    if phase.lower().startswith("play"):
        raise Unsupported("College Hockey News publishes whole-season totals only; use phase='regular'")
    df = _collect(opts, y, goalie=True)
    return finish(df, "goalies", league, y, "season", rename={
        "GP": "gp", "W": "w", "L": "l", "T": "t", "GA": "ga", "MIN": "toi", "GAA": "gaa",
        "SH": "so", "SV": "saves", "SV%": "sv_pct"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    """CHN's national team stats table (no conference W-L records)."""
    page = soup(_index_url(opts), season=f"{y}{y + 1}")
    table = find_table(page, "Team", "GP", "GA")
    df = table_rows(table, ("Team", "GP"))
    df = df.drop(columns=[c for c in ("Rk",) if c in df])
    return finish(df, "standings", league, y, "season", rename={
        "Team": "team", "GP": "gp", "G": "gf", "GA": "ga"})
