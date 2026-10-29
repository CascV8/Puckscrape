"""TSN NHL draft rankings: Bob McKenzie's scout-survey ranking, Craig Button's
"Craig's List", and TSN's scout-survey ranking that took over from McKenzie's.

Each ranking is a tsn.ca article, so :func:`draft_ranking` takes article URLs.
:func:`mckenzie_ranking` fetches McKenzie's lists by year and edition from a
built-in index (:data:`MCKENZIE_RANKINGS`). :func:`draft_ranking_articles`
lists the rankings linked from TSN's NHL draft centre, which only shows the
latest ones: for older lists, pass the article URL (old or new URL style).

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
            "HT": "height", "WT": "weight_lb", "GP": "gp", "G": "g", "A": "a", "P": "pts", "PTS": "pts",
            "GAA": "gaa", "SV%": "sv_pct"}
_NUMERIC = ("rank", "last_rank", "weight_lb", "gp", "g", "a", "pts")
_FRACTIONS = {"¼": 0.25, "½": 0.5, "¾": 0.75, "1/4": 0.25, "1/2": 0.5, "3/4": 0.75}
_RANKING_LINK = re.compile(r"craig.?s.list|draft.ranking|prospect.ranking|draft.prospect", re.I)

# Older lists are player cards ("2. Cole Eiserman, LW - USA NTDP", "Last Rank: 4", then a
# one-row stats table) or plain numbered lines ("11. Yaroslav Askarov (G)", "76 Aidan Hreschuk",
# "T4 Mason McTavish" for a tie, "HM Ryan Mast").
_CARD_HEADING = re.compile(r"(\d{1,3})\.\s+([^,]+?),\s*([A-Z]{1,2}(?:/[A-Z]{1,2})?)(?:\s+[-–]\s+.+)?")
_LAST_RANK = re.compile(r"Last Rank:\s*(\S+)")
_NAME = r"([A-Z][^:.()\d]{1,40}?)(?:\s*\(([A-Z]{1,2}(?:/[A-Z]{1,2})?)\))?"
_TEXT_LINE = re.compile(r"(T?\d{1,3}|HM)\.?\s+" + _NAME)
_HONOURABLE = re.compile(r"honou?rable mentions?", re.I)


def height_inches(text: str | None) -> float | None:
    """TSN heights to inches: "5′11" -> 71, "6'1 ¾" -> 73.75, "6'1 3/4" -> 73.75, "6′0" -> 72.

    The foot mark is optional, because the odd row drops it ("511 ¾").
    """
    m = re.match(r"\s*(\d)\s*['′’]?\s*(\d{1,2})?\s*([¼½¾]|[13]/4|1/2)?", text or "")
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


def _table_rows(table) -> tuple[list[str], list[list[str]]]:
    trs = table.find_all("tr")
    if not trs:
        return [], []
    header = [th.get_text(" ", strip=True).upper() for th in trs[0].find_all(["th", "td"])]
    body = [[td.get_text(" ", strip=True) for td in tr.find_all(["td", "th"])] for tr in trs[1:]]
    return header, [cells for cells in body if len(cells) == len(header) and any(cells)]


def _from_tables(soup: BeautifulSoup) -> list[dict]:
    """Ranking tables (an RK and a Player column), plus honourable-mention tables (no RK)."""
    rows = []
    for table in soup.find_all("table"):
        header, body = _table_rows(table)
        if "PLAYER" not in header:
            continue
        if "RK" not in header:
            if not table.find_previous(string=_HONOURABLE):
                continue
            header, body = ["RK"] + header, [["HM"] + cells for cells in body]
        rows += [{_COLUMNS.get(h, h.lower()): c for h, c in zip(header, cells)}
                 for cells in body if cells[header.index("RK")]]
    return rows


def _from_cards(soup: BeautifulSoup) -> list[dict]:
    """One card per player: a "N. Name, POS" heading, maybe "Last Rank: N", then a stats table."""
    rows, card = [], None
    for el in soup.descendants:
        if el.name == "table":
            header, body = _table_rows(el)
            if card and body and "PLAYER" not in header:
                rows.append(card | {_COLUMNS.get(h, h.lower()): c for h, c in zip(header, body[0])})
                card = None
        elif isinstance(el, str) and el.parent.name not in ("td", "th", "script", "style"):
            text = el.strip()
            if m := _CARD_HEADING.fullmatch(text):
                card = {"rank": m.group(1), "player": m.group(2), "position": m.group(3)}
            elif card and (m := _LAST_RANK.fullmatch(text)):
                card["last_rank"] = m.group(1)
    return rows


def _from_text(soup: BeautifulSoup) -> list[dict]:
    """A plain numbered list ("1. Alexis Lafreniere" ...), then any honourable mentions."""
    body = soup.find(class_=re.compile("article-body")) or soup
    lines = body.get_text("\n", strip=True).split("\n")
    rows: list[dict] = []
    for i, line in enumerate(lines):
        m = _TEXT_LINE.fullmatch(line)
        if not m:
            continue
        rank, ranked = m.group(1), [r["rank"].lstrip("T") for r in rows if r["rank"] != "HM"]
        expected = str(len(ranked) + 1)
        tie = rank.startswith("T") and ranked and rank[1:] == ranked[-1]
        if rank.lstrip("T") == expected or tie or (rank == "HM" and rows):
            rows.append({"rank": rank, "player": m.group(2), "position": m.group(3)})
            end = i
    if sum(r["rank"] != "HM" for r in rows) < 10:      # a few numbered sentences, not a list
        return []
    mentions = False
    for line in lines[end + 1:]:
        if _HONOURABLE.match(line):
            mentions = True
        elif not mentions and re.fullmatch(r"[—–-]+", line):
            continue        # a divider between the list and the mentions
        elif mentions and (m := re.fullmatch(_NAME, line)) and len(line.split()) <= 4:
            rows.append({"rank": "HM", "player": m.group(1), "position": m.group(2)})
        else:
            break
    return rows


def _clean(row: dict) -> dict:
    if row.get("position") == "G" and "g" in row and "gaa" not in row:
        # In ranking tables, goalie rows reuse the G and P columns for GAA and save percentage.
        row["gaa"], row["sv_pct"] = row.pop("g", None), row.pop("pts", None)
    if m := re.fullmatch(r"T(\d{1,3})", str(row.get("rank"))):
        row["rank"], row["tied"] = m.group(1), True
    if not str(row.get("rank") or "").isdigit():
        row["rank_note"] = row.pop("rank", None)    # "HM": honourable mention
    if m := re.fullmatch(r"(.*?)\s*\(([^()]+)\)", row.get("team") or ""):
        row["team"], row["league"] = m.group(1), m.group(2)
    if "height" in row:
        row["height_in"] = height_inches(row["height"])
    return row


def parse_ranking_page(soup: BeautifulSoup, url: str) -> list[dict]:
    """Rows from a TSN ranking article: its ranking table, player cards, or numbered list."""
    meta = _article_meta(soup)
    meta = {"draft_year": _draft_year(meta["published"])} | meta | {"url": url}
    rows = _from_tables(soup)
    if not any(str(r["rank"]).isdigit() for r in rows):
        # No ranking table: the ranked players are cards (any mentions table stays) or plain text.
        cards = _from_cards(soup)
        rows = cards + rows if cards else _from_text(soup)
    return [_clean(row) | meta for row in rows]


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
    if "tied" in df:
        df["tied"] = df["tied"].eq(True)
    return df


# Bob McKenzie's rankings: a consensus of 10 NHL scouts he surveyed, published in
# up to four editions a season. TSN ran the same survey without him from 2026
# (the author column says who wrote each one). (draft year, edition) -> article.
# Lists TSN no longer serves (2022, the 2024 final...) aren't here.
EDITIONS = ("pre-season", "mid-season", "lottery", "final")
MCKENZIE_RANKINGS = {
    (2020, "final"): "/nhl/draftcentre/alexis-lafreniere-tops-tsn-hockey-insider-bob-mckenzie-s-final-draft-rankings-1.1488269",
    (2021, "pre-season"): "/nhl/draftcentre/owen-power-leads-first-ranking-of-2021-draft-prospects-compiled-by-tsn-hockey-insider-bob-mckenzie-1.1564391",
    (2021, "final"): "/nhl/draftcentre/bob-mckenzie-s-2021-final-draft-rankings-1.1669727",
    (2023, "mid-season"): "/nhl/connor-bedard-locked-in-at-no-1-in-bob-mckenzie-s-mid-season-nhl-draft-ranking-1.1909910",
    (2023, "lottery"): "/nhl/plenty-of-intrigue-after-connor-bedard-in-bob-mckenzie-s-nhl-draft-lottery-edition-ranking-1.1956585",
    (2023, "final"): "/nhl/intrigue-and-excitement-in-the-year-of-connor-bedard-at-the-nhl-draft-1.1976262",
    (2024, "pre-season"): "/nhl/macklin-celebrini-leads-big-three-atop-bob-mckenzie-s-tsn-pre-season-nhl-draft-ranking-1.2007499",
    (2024, "mid-season"): "/nhl/macklin-celebrini-the-unanimous-no-1-prospect-in-bob-mckenzie-s-mid-season-draft-ranking-1.2066050",
    (2024, "lottery"): "/nhl/bob-mckenzie-s-nhl-draft-ranking-an-unpredictable-ride-after-macklin-celebrini-1.2116004",
    (2025, "pre-season"): "/nhl/james-hagens-in-pole-position-for-top-spot-at-2025-nhl-draft-1.2176638",
    (2025, "mid-season"): "/nhl/matthew-schaefer-a-unanimous-no-1-in-bob-mckenzie-s-mid-season-nhl-draft-ranking-1.2240142",
    (2025, "lottery"): "/nhl/matthew-schaefer-roger-mcqueen-generate-intriguing-talking-points-in-mckenzie-s-nhl-draft-ranking-1.2299495",
    (2025, "final"): "/nhl/with-prodigious-talent-and-boundless-potential-matthew-schaefer-tops-mckenzie-s-nhl-draft-ranking-1.2325555",
    (2026, "final"): "/nhl/article/mckenna-edges-stenberg-to-finish-atop-tsns-final-draft-ranking/",
    (2027, "pre-season"): "/nhl/article/dupont-the-definitive-no1-player-in-tsns-pre-season-draft-ranking/",
}


def mckenzie_ranking(years=None, editions=None) -> pd.DataFrame:
    """Bob McKenzie's NHL draft rankings (and TSN's continuation of them), by draft year and edition.

    >>> mckenzie_ranking(2025, "final")
    >>> mckenzie_ranking(editions="final")     # every final list

    ``years`` are draft years and ``editions`` any of "pre-season",
    "mid-season", "lottery", "final"; leave either out for all of them.
    Lists not in :data:`MCKENZIE_RANKINGS` are skipped with a warning. Same
    columns as :func:`draft_ranking`, plus ``edition``. Honourable mentions
    have no rank and "HM" in ``rank_note``; tied players share a rank and have
    ``tied`` set. Pre-season and lottery lists are short (12-20 players); mid-season
    and final lists run to 80-96.
    """
    years = None if years is None else {int(y) for y in as_list(years)}
    editions = EDITIONS if editions is None else as_list(editions)
    if bad := set(editions) - set(EDITIONS):
        raise ValueError(f"editions must be among {EDITIONS}, not {sorted(bad)}")
    wanted = [(y, e) for (y, e) in MCKENZIE_RANKINGS if (years is None or y in years) and e in editions]
    for y in sorted(years or ()):
        for e in editions:
            if (y, e) not in MCKENZIE_RANKINGS:
                log.warning("No %d %s McKenzie ranking in the index", y, e)
    frames = []
    for key in sorted(wanted, key=lambda k: (k[0], EDITIONS.index(k[1]))):
        df = draft_ranking(MCKENZIE_RANKINGS[key])
        if not df.empty:
            df["draft_year"] = key[0]
            df.insert(0, "edition", key[1])
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


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
