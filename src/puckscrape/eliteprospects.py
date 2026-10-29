"""Elite Prospects league stats, player bios and NHL draft rankings.

Stats come from the Next.js ``__NEXT_DATA__`` JSON embedded in each page,
with the header-matched HTML table as a fallback.

For personal use only. For commercial or professional use, look into the
Elite Prospects API.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import pandas as pd
import requests
from bs4 import BeautifulSoup

from . import _http
from ._util import as_list, ep_season

log = logging.getLogger("puckscrape.eliteprospects")

BASE = "https://www.eliteprospects.com"
MAX_PAGES = 200

_STATS_KEYS = {"regular": "regularStats", "postseason": "postseasonStats", "total": "totalStats"}
_STAT_RENAMES = {"PTS": "tp", "PPG": "ppg", "PM": "plus_minus", "SVP": "sv_pct", "SVS": "svs"}

# Soft-block handling: EP sometimes answers 200 with a page that has no data
# in it rather than an honest 403. Retry a few times before believing it.
SOFT_BLOCK_RETRIES = 3
SOFT_BLOCK_BACKOFF = 8


# --------------------------------------------------------------------------
# Fetching
# --------------------------------------------------------------------------

def _fetch_soup(url: str, params: dict | None, ok: Callable[[BeautifulSoup], bool],
                strict_path: bool = False) -> BeautifulSoup | None:
    """Fetch a page, retrying with a growing delay while ``ok(soup)`` is false.

    Returns None on 404, or -- with ``strict_path`` -- when EP redirects
    elsewhere (an unknown league lands on /leagues with a 200). Returns the
    last soup even if it never became ``ok`` so callers can decide what that means.
    """
    for attempt in range(SOFT_BLOCK_RETRIES + 1):
        try:
            resp = _http.get(url, params=params, retry_403=True, backoff=15)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise
        if strict_path and urlsplit(resp.url).path.rstrip("/") != urlsplit(url).path.rstrip("/"):
            return None
        soup = BeautifulSoup(resp.content, "html.parser")
        if ok(soup) or attempt == SOFT_BLOCK_RETRIES:
            return soup
        wait = SOFT_BLOCK_BACKOFF * (attempt + 1)
        log.info("No data on %s (attempt %d/%d), possibly soft-blocked; waiting %ds",
                 resp.url, attempt + 1, SOFT_BLOCK_RETRIES, wait)
        time.sleep(wait)
    raise AssertionError("unreachable")


def _next_data(soup: BeautifulSoup) -> dict:
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return {}
    try:
        return json.loads(tag.string)
    except json.JSONDecodeError:
        return {}


def _page_props(soup: BeautifulSoup) -> dict:
    return _next_data(soup).get("props", {}).get("pageProps", {})


# --------------------------------------------------------------------------
# League stats pages
# --------------------------------------------------------------------------

def _stats_block(soup: BeautifulSoup, kind: str) -> dict | None:
    key = "goalieStats" if kind == "goalie" else "skaterStats"
    block = (_page_props(soup).get(key) or {}).get("stats")
    return block if isinstance(block, dict) and "edges" in block else None


def _find_stats_table(soup: BeautifulSoup, kind: str):
    """EP's 2025 redesign dropped the old table classes; match on headers instead."""
    for table in soup.find_all("table"):
        headers = {th.get_text(strip=True).upper() for th in table.find_all("th")}
        if kind == "skater" and {"TP", "GP"} <= headers:
            return table
        if kind == "goalie" and {"GAA", "SV%"} <= headers:
            return table
    return None


def _has_stats(kind: str) -> Callable[[BeautifulSoup], bool]:
    return lambda soup: _stats_block(soup, kind) is not None or _find_stats_table(soup, kind) is not None


def _stat_value(key: str, value):
    if key in ("SVP", "GAA", "PPG") and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if key == "TOI" and isinstance(value, str) and value.isdigit():
        return int(value)
    return value


def parse_stats_json(block: dict, kind: str, stats: str = "regular") -> list[dict]:
    """Turn a ``skaterStats``/``goalieStats`` block into flat row dicts."""
    stats_key = _STATS_KEYS[stats]
    rows = []
    for edge in block.get("edges", []):
        line = edge.get(stats_key)
        if not line:
            continue
        player = edge.get("player") or {}
        team = edge.get("team") or {}
        row = {
            "player": player.get("name"),
            "player_id": int(player["id"]) if player.get("id") else None,
            "position": "/".join(player.get("detailedPosition") or []) or None,
            "nation": (player.get("nationality") or {}).get("name"),
            "team": edge.get("teamName") or team.get("name"),
            "team_id": int(team["id"]) if team.get("id") else None,
        }
        for k, v in line.items():
            if k != "__typename":
                row[_STAT_RENAMES.get(k, k.lower())] = _stat_value(k, v)
        path = player.get("eliteprospectsUrlPath")
        row["link"] = BASE + path if path else None
        rows.append(row)
    return rows


def parse_stats_table(table) -> list[dict]:
    """Fallback parser for the HTML table (originally by Marcus Sjölin)."""
    trs = table.find_all("tr")
    header = [th.get_text(strip=True) for th in trs[0].find_all("th")]
    links = [a["href"] for a in table.find_all("a", href=True) if "/player/" in a["href"]]
    rows = []
    for tr in trs[1:]:
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cells) != len(header) or not cells[0]:
            continue
        rows.append(dict(zip(header, cells)))
    for row, link in zip(rows, links):
        row["link"] = link if link.startswith("http") else BASE + link
    renames = {"+/-": "plus_minus", "P/GP": "ppg", "SV%": "sv_pct", "#": None}
    return [
        {renames.get(k, k.lower()): v for k, v in row.items() if renames.get(k, k) is not None}
        for row in rows
    ]


def _scrape_league_season(league: str, season: str, kind: str, stats: str) -> list[dict]:
    url = f"{BASE}/league/{league}/stats/{season}"
    rows: list[dict] = []
    seen: set[tuple] = set()

    for page in range(1, MAX_PAGES + 1):
        params = {"page": page}
        if kind == "goalie":
            params["tab"] = "goalies"
        soup = _fetch_soup(url, params, _has_stats(kind), strict_path=True)
        if soup is None:
            log.warning("%s %s: page not found -- no data for this league/season", league, season)
            break

        block = _stats_block(soup, kind)
        if block is not None:
            page_rows = parse_stats_json(block, kind, stats)
            has_next = bool((block.get("pageInfo") or {}).get("hasNextPage"))
        elif (table := _find_stats_table(soup, kind)) is not None:
            page_rows = parse_stats_table(table)
            has_next = bool(page_rows)
        else:
            if page == 1:
                log.warning("%s %s: no stats found (blocked, or no data)", league, season)
            break

        for row in page_rows:
            key = (row.get("player_id") or row.get("link"), row.get("team_id") or row.get("team"))
            if key not in seen:
                seen.add(key)
                rows.append(row | {"league": league, "season": season})
        log.info("%s %s %ss: page %d, %d rows", league, season, kind, page, len(page_rows))

        if not has_next or not page_rows:
            break
    return rows


def _scrape(kind: str, leagues, seasons, stats: str) -> pd.DataFrame:
    if stats not in _STATS_KEYS:
        raise ValueError(f"stats must be one of {list(_STATS_KEYS)}")
    rows: list[dict] = []
    try:
        for league in as_list(leagues):
            for season in as_list(seasons):
                rows.extend(_scrape_league_season(league.lower(), ep_season(season), kind, stats))
    except (KeyboardInterrupt, _http.BlockedError) as e:
        log.warning("Stopped early (%s); returning the %d rows scraped so far", type(e).__name__, len(rows))
    return pd.DataFrame(rows)


def skaters(leagues, seasons, *, stats: str = "regular") -> pd.DataFrame:
    """League skater stats from Elite Prospects.

    >>> skaters(["ahl", "nhl"], ["2024-25", "2025-26"])

    ``leagues`` are EP slugs ("nhl", "ahl", "ohl", "shl", "mhl"...). ``seasons``
    takes any spelling: 2024, "2024-25", "2024-2025". ``stats`` is "regular",
    "postseason" or "total". Ctrl-C returns whatever was scraped so far.
    """
    return _scrape("skater", leagues, seasons, stats)


def goalies(leagues, seasons, *, stats: str = "regular") -> pd.DataFrame:
    """League goalie stats from Elite Prospects. Same arguments as :func:`skaters`.

    Goalies with no games played are dropped.
    """
    df = _scrape("goalie", leagues, seasons, stats)
    if not df.empty and "gp" in df:
        gp = pd.to_numeric(df["gp"], errors="coerce")
        df = df[gp.fillna(0) > 0].reset_index(drop=True)
    return df


# --------------------------------------------------------------------------
# Player bio pages
# --------------------------------------------------------------------------

def parse_player_page(soup: BeautifulSoup, link: str) -> dict:
    """Bio fields from a player page's ``__NEXT_DATA__`` payload."""
    player_data = _page_props(soup).get("playerData") or {}
    p = player_data.get("player") or {}

    row = {"player": p.get("name"), "player_id": int(p["id"]) if p.get("id") else None}
    if not p:
        title = soup.find("title")
        row["player"] = title.string.replace(" - Stats, Contract, Salary & More", "") if title and title.string else None

    rights = p.get("nhlRights") if isinstance(p.get("nhlRights"), dict) else {}
    nation = p.get("nationality") or p.get("nation")
    height, weight = p.get("height"), p.get("weight")
    row |= {
        "nhl_rights": ((rights.get("team") or {}).get("name")) if rights else None,
        "rights_status": rights.get("rights") if rights else None,
        "dob": p.get("dateOfBirth"),
        "height_cm": height.get("metrics") if isinstance(height, dict) else None,
        "weight_kg": weight.get("metrics") if isinstance(weight, dict) else None,
        "birthplace": p.get("placeOfBirth"),
        "nation": nation.get("name") if isinstance(nation, dict) else None,
        "shoots": p.get("shoots") or p.get("catches"),
    }

    drafts = player_data.get("playerDraftSelections")
    edges = drafts.get("edges", []) if isinstance(drafts, dict) else []
    d = edges[0] if edges else {}
    row |= {
        "draft_year": d.get("year"),
        "draft_round": d.get("round"),
        "draft_overall": d.get("overall"),
        "draft_team": d.get("teamName"),
        "link": link,
    }
    return row


def player_info(links) -> pd.DataFrame:
    """Bio data for one or more players.

    ``links`` can be player URLs/paths, or a DataFrame from :func:`skaters` /
    :func:`goalies` (its ``link`` column is used). One request per player, so
    this is slow for big lists. Ctrl-C returns what's been scraped so far.
    """
    if isinstance(links, pd.DataFrame):
        links = links["link"]
    unique = list(dict.fromkeys(l for l in as_list(links) if isinstance(l, str)))
    log.info("Scraping bios for %d players", len(unique))

    rows = []
    try:
        for i, link in enumerate(unique, 1):
            url = link if link.startswith("http") else BASE + link
            try:
                soup = _fetch_soup(url, None, lambda s: bool(_page_props(s).get("playerData")))
            except requests.RequestException as e:
                log.warning("Skipping %s: %s", url, e)
                continue
            if soup is None:
                log.warning("Skipping %s: not found", url)
                continue
            row = parse_player_page(soup, url)
            rows.append(row)
            log.info("[%d/%d] %s", i, len(unique), row["player"])
    except (KeyboardInterrupt, _http.BlockedError) as e:
        log.warning("Stopped early (%s); returning %d players", type(e).__name__, len(rows))
    df = pd.DataFrame(rows)
    for col in ("draft_year", "draft_round", "draft_overall", "height_cm", "weight_kg"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df


def add_player_info(df: pd.DataFrame) -> pd.DataFrame:
    """Left-join bio columns onto a :func:`skaters` / :func:`goalies` frame."""
    bios = player_info(df)
    if bios.empty:
        return df
    bios = bios.drop(columns=["player", "player_id", "nation"], errors="ignore")
    return df.merge(bios, on="link", how="left")


# --------------------------------------------------------------------------
# Draft rankings (Draft Center)
# --------------------------------------------------------------------------

def _draft_page(scout: str | None = None) -> dict:
    """pageProps of the Draft Center, or of one scout's list in it."""
    path = f"/draft-center/{scout}" if scout else "/draft-center"
    soup = _fetch_soup(BASE + path, None, lambda s: bool(_page_props(s).get("draftRankings")),
                       strict_path=True)
    if soup is None:
        raise ValueError(f"no Elite Prospects draft ranking called {scout!r}; see draft_scouts()")
    return _page_props(soup)


def draft_scouts() -> pd.DataFrame:
    """Every ranking in EP's Draft Center: its ``scout`` slug, name and last update.

    EP collects its own lists (``eliteprospects-com``, ``consolidated-ranking``)
    and other outlets' (``tsn-craig-button``, ``daily-faceoff``, ``nhl-central-scouting-na``...).
    ``last_update`` says "NO RANKING PUBLISHED" for lists that are empty so far.
    """
    props = _draft_page()
    return pd.DataFrame([
        {
            "scout": s.get("slug"),
            "name": s.get("name"),
            "source": (s.get("rankingSource") or {}).get("name"),
            "last_update": s.get("lastUpdateInformation"),
            "draft_year": props.get("year"),
            "link": BASE + s["eliteprospectsUrlPath"] if s.get("eliteprospectsUrlPath") else None,
        }
        for s in (props.get("draftRankingScouts") or {}).get("scouts", [])
    ])


def parse_draft_rankings(props: dict) -> list[dict]:
    """Rows from a Draft Center page's ``draftRankings``. Unranked prospects have rank None."""
    scout = (props.get("scout") or {}).get("slug")
    rows = []
    for entry in (props.get("draftRankings") or {}).get("rankings", []):
        p = entry.get("player") or {}
        line = entry.get("playerStats") or {}
        height, weight = p.get("height"), p.get("weight")
        row = {
            "draft_year": props.get("year"),
            "scout": scout,
            "rank": entry.get("rank"),
            "player": p.get("name"),
            "player_id": int(p["id"]) if p.get("id") else None,
            "position": "/".join(p.get("detailedPosition") or []) or None,
            "dob": p.get("dateOfBirth"),
            "shoots": p.get("shoots"),
            "nation": (p.get("nationality") or {}).get("name"),
            "height_cm": height.get("metrics") if isinstance(height, dict) else None,
            "weight_kg": weight.get("metrics") if isinstance(weight, dict) else None,
            "team": (line.get("team") or {}).get("name"),
            "league": (line.get("league") or {}).get("name"),
        }
        for k, v in (line.get("regularStats") or {}).items():
            if k != "__typename":
                row[_STAT_RENAMES.get(k, k.lower())] = _stat_value(k, v)
        path = p.get("eliteprospectsUrlPath")
        row["link"] = BASE + path if path else None
        rows.append(row)
    return rows


def draft_rankings(scouts="consolidated-ranking", *, unranked: bool = False) -> pd.DataFrame:
    """NHL draft rankings from EP's Draft Center, one row per player and list.

    >>> draft_rankings(["eliteprospects-com", "tsn-craig-button"])

    ``scouts`` are slugs from :func:`draft_scouts`, or "all". The default is
    EP's consolidated ranking. EP only keeps lists for the upcoming draft
    (``draft_year``); past years' rankings aren't available. ``unranked=True``
    also returns the prospects in EP's pool that a list doesn't rank.
    Player stats are the current season's, at the player's current team.
    """
    if isinstance(scouts, str) and scouts == "all":
        scouts = draft_scouts()["scout"]
    rows: list[dict] = []
    try:
        for scout in as_list(scouts):
            page = parse_draft_rankings(_draft_page(scout))
            ranked = [r for r in page if r["rank"] is not None]
            if not ranked:
                log.info("%s: no ranking published yet", scout)
            rows.extend(page if unranked else ranked)
            log.info("%s: %d ranked", scout, len(ranked))
    except (KeyboardInterrupt, _http.BlockedError) as e:
        log.warning("Stopped early (%s); returning the %d rows scraped so far", type(e).__name__, len(rows))
    df = pd.DataFrame(rows)
    for col in ("rank", "height_cm", "weight_kg", "gp", "g", "a", "tp", "pim", "w", "l", "t", "so"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    return df
