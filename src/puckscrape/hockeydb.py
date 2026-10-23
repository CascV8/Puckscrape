"""HockeyDB (hockeydb.com): season rosters with stats for hundreds of leagues,
including ones whose own sites are blocked or missing (the KHL, VHL, MHL,
Slovakia, the NAHL...).

    import puckscrape as ps

    ps.hockeydb.leagues()                     # id, name of every league
    ps.hockeydb.LEAGUES["khl"]                # 280: short names for common ones
    ps.hockeydb.skaters("khl", "2017-18")     # every rostered player, by team
    ps.hockeydb.skaters(148, 2024)            # by HockeyDB league id (148 = NAHL)

Every player has a HockeyDB id (``pid``) that's the same in every league, so a
player's stints in different leagues link exactly. A league-season is one page
per team (about 25 requests for the KHL), at one request every 3 seconds.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd
from bs4 import BeautifulSoup

from . import _http
from ._util import start_year

HOST = "https://www.hockeydb.com"

# Short names for the leagues used most (ids that cover 2010-11 on; HockeyDB
# splits some leagues into several ids by era). Any id from leagues() works too.
LEAGUES = {
    "nhl": 141, "ahl": 112, "echl": 70, "khl": 280, "vhl": 352, "mhl": 479,
    "slovakia": 218, "czechia": 66, "liiga": 84, "mestis": 348, "shl": 239,
    "nl": 241, "sl": 242, "del": 69, "del2": 96,
    "nahl": 149, "ushl": 251, "bchl": 31, "ajhl": 3, "sjhl": 212, "mjhl": 123, "ojhl": 175, "ohl": 167,
}

_STATS = ["gp", "g", "a", "pts", "pim"]


def _soup(path: str) -> BeautifulSoup:
    resp = _http.get(HOST + path)
    return BeautifulSoup(resp.content, "html.parser")


@cache
def leagues() -> pd.DataFrame:
    """Every league HockeyDB lists: ``id`` and ``name``."""
    soup = _soup("/ihdb/stats/leagues.html")
    rows = []
    for a in soup.find_all("a", href=re.compile(r"^/ihdb/stats/leagues/\d+\.html$")):
        rows.append({"id": int(re.search(r"(\d+)\.html", a["href"]).group(1)), "name": a.get_text(strip=True)})
    return pd.DataFrame(rows).drop_duplicates("id").reset_index(drop=True)


def _league_id(league: int | str) -> int:
    if isinstance(league, int) or str(league).isdigit():
        return int(league)
    try:
        return LEAGUES[str(league).lower()]
    except KeyError:
        raise ValueError(f"unknown HockeyDB league {league!r}: use an id from ps.hockeydb.leagues()") from None


@cache
def seasons(league: int | str) -> dict[int, str]:
    """{season start year: season page path} for one league."""
    soup = _soup(f"/ihdb/stats/leagues/{_league_id(league)}.html")
    out = {}
    for a in soup.find_all("a", href=re.compile(r"^/ihdb/stats/leagues/seasons/[^/]+\.html$")):
        m = re.fullmatch(r"(\d{4})-(\d{2})", a.get_text(strip=True))
        if m:
            out[int(m.group(1))] = a["href"]
    return out


def _num(text: str):
    text = text.strip()
    return pd.NA if text in ("", "--", "-") else pd.to_numeric(text, errors="coerce")


def _team_table(soup: BeautifulSoup) -> list[dict]:
    rows = []
    table = soup.find("table", class_="sortable")
    if table is None or table.tbody is None:
        return rows
    for tr in table.tbody.find_all("tr"):
        td = tr.find_all("td")
        link = tr.find("a", href=re.compile(r"pdisplay\.php\?pid=\d+"))
        if len(td) < 16 or link is None:
            continue
        cells = [c.get_text(" ", strip=True) for c in td]
        row = {"pid": int(re.search(r"pid=(\d+)", link["href"]).group(1)), "player": link.get_text(strip=True),
               "pos": cells[2]}
        row.update({k: _num(v) for k, v in zip(_STATS + ["plus_minus"], cells[3:9])})
        row.update({f"po_{k}": _num(v) for k, v in zip(_STATS, cells[9:14])})
        row["birthplace"], row["age"] = cells[14], _num(cells[15])
        rows.append(row)
    return rows


def skaters(league: int | str, season: int | str) -> pd.DataFrame:
    """Every player on a roster that season, one row per player and team:
    ``pid, player, team, pos``, regular season ``gp, g, a, pts, pim, plus_minus``,
    playoffs ``po_gp ... po_pim``, ``birthplace`` and ``age``. Goalies are
    included (``pos == "G"``) with their skater lines."""
    lid, y = _league_id(league), start_year(season)
    path = seasons(lid).get(y)
    if path is None:
        raise ValueError(f"HockeyDB has no {y}-{str(y + 1)[2:]} season for league {league!r}")
    base = path.rsplit("/", 1)[0]
    soup = _soup(path)
    teams = [(a.get_text(strip=True), a["href"]) for a in soup.find_all("a", href=re.compile(r"^teams/\d+\.html$"))]
    frames = []
    for name, href in dict.fromkeys(teams):
        rows = _team_table(_soup(f"{base}/{href}"))
        if rows:
            frames.append(pd.DataFrame(rows).assign(team=name))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    for c in _STATS + ["plus_minus"] + [f"po_{k}" for k in _STATS] + ["age"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    df.insert(0, "season", f"{y}-{str(y + 1)[2:]}")
    df.insert(0, "league", league if isinstance(league, str) and not str(league).isdigit() else lid)
    cols = ["league", "season", "pid", "player", "team", "pos"] + _STATS + ["plus_minus"] + \
        [f"po_{k}" for k in _STATS] + ["birthplace", "age"]
    return df[cols]
