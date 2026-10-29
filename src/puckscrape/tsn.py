"""TSN NHL draft rankings: Craig Button's "Craig's List" and TSN's scouting-survey ranking.

Each ranking is a table inside a tsn.ca article, so :func:`draft_ranking` takes
article URLs. :func:`draft_ranking_articles` lists the rankings linked from
TSN's NHL draft centre, which only shows the latest ones: for older lists,
pass the article URL (any tsn.ca ranking article works, old or new URL style).

TSN's terms of use apply: keep it to personal use.
"""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup

from . import _http
from ._util import as_list

log = logging.getLogger("puckscrape.tsn")

BASE = "https://www.tsn.ca"
DRAFT_CENTRE = BASE + "/nhl/draftcentre/"

_COLUMNS = {"RK": "rank", "PLAYER": "player", "TEAM": "team", "POS": "position",
            "HT": "height", "WT": "weight_lb", "GP": "gp", "G": "g", "A": "a", "P": "pts", "PTS": "pts"}
_NUMERIC = ("rank", "weight_lb", "gp", "g", "a", "pts")
_FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75}
_RANKING_LINK = re.compile(r"craig.?s.list|draft.ranking|prospect.ranking|draft.prospect", re.I)


def height_inches(text: str | None) -> float | None:
    """TSN heights to inches: "5′11" -> 71, "6'1 ¾" -> 73.75, "6′0" -> 72.

    The foot mark is optional, because the odd row drops it ("511 ¾").
    """
    m = re.match(r"\s*(\d)\s*['′’]?\s*(\d{1,2})?\s*([¼½¾])?", text or "")
    if not m:
        return None
    return int(m.group(1)) * 12 + int(m.group(2) or 0) + _FRACTIONS.get(m.group(3), 0)


def _article_meta(soup: BeautifulSoup) -> dict:
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for d in data if isinstance(data, list) else [data]:
            if isinstance(d, dict) and d.get("@type") in ("NewsArticle", "Article"):
                authors = d.get("author") or []
                authors = authors if isinstance(authors, list) else [authors]
                return {
                    "headline": d.get("headline"),
                    "author": ", ".join(a.get("name", "") for a in authors if isinstance(a, dict)) or None,
                    "published": (d.get("datePublished") or "")[:10] or None,
                }
    title = soup.find("title")
    return {"headline": title.get_text(strip=True) if title else None, "author": None, "published": None}


def _draft_year(published: str | None) -> int | None:
    """The NHL draft is in late June, so lists from July on are for next year's draft."""
    if not published:
        return None
    year, month = int(published[:4]), int(published[5:7])
    return year + 1 if month >= 7 else year


def parse_ranking_page(soup: BeautifulSoup, url: str) -> list[dict]:
    """Rows from every ranking table (an RK and a Player column) in a TSN article."""
    meta = _article_meta(soup)
    meta = {"draft_year": _draft_year(meta["published"])} | meta | {"url": url}
    rows = []
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [th.get_text(" ", strip=True).upper() for th in trs[0].find_all(["th", "td"])]
        if not {"RK", "PLAYER"} <= set(header):
            continue
        for tr in trs[1:]:
            cells = [td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) != len(header) or not cells[header.index("RK")]:
                continue
            row = {_COLUMNS.get(h, h.lower()): c for h, c in zip(header, cells)}
            if row.get("position") == "G":
                # Goalie rows reuse the G and P columns for GAA and save percentage.
                row["gaa"], row["sv_pct"] = row.pop("g", None), row.pop("pts", None)
            if m := re.fullmatch(r"(.*?)\s*\(([^()]+)\)", row.get("team") or ""):
                row["team"], row["league"] = m.group(1), m.group(2)
            if "height" in row:
                row["height_in"] = height_inches(row["height"])
            rows.append(row | meta)
    return rows


def draft_ranking(urls) -> pd.DataFrame:
    """One or more TSN draft-ranking articles as a DataFrame, one row per ranked player.

    >>> draft_ranking("https://www.tsn.ca/nhl/article/dupont-opens-the-season-at-no-1-on-craigs-list/")

    ``urls`` can be full URLs, tsn.ca paths, or a frame from
    :func:`draft_ranking_articles` (its ``url`` column is used). Columns follow
    the article's table (rank, player, team, league, position, height, weight,
    stats), plus the article's headline, author, publish date and the
    ``draft_year`` it's for (worked out from the date).
    """
    if isinstance(urls, pd.DataFrame):
        urls = urls["url"]
    rows: list[dict] = []
    try:
        for url in as_list(urls):
            url = urljoin(BASE, url)
            soup = BeautifulSoup(_http.get(url).content, "html.parser")
            page = parse_ranking_page(soup, url)
            if not page:
                log.warning("No ranking table in %s", url)
            log.info("%s: %d players", url, len(page))
            rows.extend(page)
    except (KeyboardInterrupt, _http.BlockedError) as e:
        log.warning("Stopped early (%s); returning the %d rows scraped so far", type(e).__name__, len(rows))
    df = pd.DataFrame(rows)
    for col in _NUMERIC:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("gaa", "sv_pct"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def draft_ranking_articles() -> pd.DataFrame:
    """Draft-ranking articles linked from TSN's NHL draft centre: ``title`` and ``url``.

    The draft centre only links the latest few. Feed the result to :func:`draft_ranking`.
    """
    soup = BeautifulSoup(_http.get(DRAFT_CENTRE).content, "html.parser")
    found: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/article/" not in href or not _RANKING_LINK.search(href):
            continue
        url = urljoin(BASE, href).split("?")[0]
        title = a.get_text(" ", strip=True)
        if len(title) >= len(found.get(url, "")):   # a page links an article more than once; keep the headline
            found[url] = title
    return pd.DataFrame({"title": list(found.values()), "url": list(found)})
