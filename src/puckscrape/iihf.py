"""IIHF tournaments, men's and women's, from the IIHF's statistics archive (stats.iihf.com/Hydra).

    import puckscrape as ps

    ps.iihf.events(year=2025, gender="women")       # the catalog: every event and its id
    ps.iihf.skaters("ww", 2025)                     # Women's World Championship 2025, top division
    ps.iihf.goalies("wm20", 2026)                   # World Juniors 2026 (played Dec 2025 - Jan 2026)
    ps.iihf.skaters("wm", 2025, division="all")     # every division of the 2025 Men's Worlds
    ps.iihf.skaters(510)                            # any event by its Hydra id
    ps.iihf.standings("ww18", 2025)                 # group standings
    ps.iihf.final_ranking("wm", 2025)

Tournaments: ``wm`` (Men's World Championship), ``ww`` (Women's), ``wm20`` (U20, the
World Juniors), ``wm18`` (Men's U18), ``ww18`` (Women's U18), ``oly-m`` / ``oly-w``
(Olympic tournaments, where the archive has them) and ``olyq-m`` / ``olyq-w`` (Olympic
qualification). Years are the year the tournament is named for: the 2026 World Juniors
started in December 2025.

Every Hydra event (each division and group has its own) has an index page linking
its reports as PDFs. Player stats come from "Player Statistics by Team" (one PDF per
team), so a 10-team event is 11 requests. The PDFs carry no readable text layer; see
``puckscrape._pdftext`` for how they're decoded.
"""

from __future__ import annotations

import logging
import re
from functools import cache, lru_cache
from importlib import resources

import pandas as pd
import requests

from . import _http, _pdftext
from ._util import as_list
from .leagues._common import to_numbers

log = logging.getLogger("puckscrape.iihf")

BASE = "https://stats.iihf.com/Hydra"

TOURNAMENTS = {
    "wm": "IIHF Men's World Championship",
    "ww": "IIHF Women's World Championship",
    "wm20": "IIHF U20 World Championship (World Juniors)",
    "wm18": "IIHF U18 World Championship (men)",
    "ww18": "IIHF U18 Women's World Championship",
    "oly-m": "Olympic Games, men",
    "oly-w": "Olympic Games, women",
    "olyq-m": "Olympic qualification, men",
    "olyq-w": "Olympic qualification, women",
}


# ---------------------------------------------------------------- catalog

# Events the title alone gets wrong.
_DIVISION_OVERRIDES = {750: "Top (abandoned Dec 2021)"}   # the 2022 World Juniors' first try; 393 is the replay
_OLYMPIC_YEARS = {2014, 2022, 2026}   # the archive's bare "Men's Tournament" / "Women's Tournament" events


def fix_text(text: str) -> str:
    """Undo UTF-8 read as Latin-1 ('Womenâ\\x80\\x99s' -> 'Women’s'), as some archive titles come out."""
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def classify(title: str, event_id: int | None = None) -> dict:
    """Year, gender, tournament code and division from a Hydra event title.

    '2025 IIHF Ice Hockey Women's World Championship Div II Group A' ->
    {year: 2025, gender: women, tournament: ww, division: Div II Group A}"""
    t = re.sub(r"\s+", " ", fix_text(title)).strip()
    m = re.match(r"(\d{4})\s*(.*)$", t)
    year, rest = (int(m.group(1)), m.group(2)) if m else (None, t)
    low = rest.lower().replace("’", "'")
    women = bool(re.search(r"\bwom[ae]n'?s?\b|\bwomens\b|\bladies\b|\bgirls\b", low))
    gender = "women" if women else "men"
    # 'Div II Group A', 'Div IIIQ' / 'Div IBQ' (qualification), 'Div Q'
    div = re.search(r"\b(?:Div(?:ision)?\.?\s*(?:[IV]+[AB]?Q?|Q|\d)\b.*|Qualification.*)$", rest, re.I)
    division = "Top"
    if div:
        division = re.sub(r"^Division", "Div", div.group(0).strip(), flags=re.I)
    elif (g := re.search(r"\bGroup\s+\w+$", rest)):
        division = g.group(0)
    if "olympic" in low and "qualif" in low:
        tournament = "olyq-w" if women else "olyq-m"
        g = re.search(r"\b(Pre-|Final|Preliminary).*", rest, re.I)
        division = g.group(0).strip() if g else division
    elif ("olympic winter games" in low and "youth" not in low) or (
            year in _OLYMPIC_YEARS and re.fullmatch(r"(?:wo)?men'?s? tournament", low)):
        tournament = "oly-w" if women else "oly-m"
    elif "asia" in low or "oceania" in low or "challenge cup" in low:
        tournament = "other"   # regional events (U18/U20 Asia and Oceania, Challenge Cup of Asia)
    elif "u20" in low or "junior" in low:
        tournament = "wm20"
    elif "u18" in low:
        tournament = "ww18" if women else "wm18"
    elif "in-line" in low or "inline" in low:
        tournament = "other"
    elif re.search(r"world (?:women'?s )?championship|world womens championship", low):
        tournament = "ww" if women else "wm"
    else:
        tournament = "other"
    division = _DIVISION_OVERRIDES.get(event_id, division)
    return {"year": year, "gender": gender, "tournament": tournament, "division": division}


@cache
def _catalog() -> pd.DataFrame:
    text = resources.files("puckscrape").joinpath("data/iihf_events.csv").read_text("utf-8")
    from io import StringIO
    return pd.read_csv(StringIO(text))


def events(year: int | None = None, gender: str | None = None, tournament: str | None = None) -> pd.DataFrame:
    """Every event in the IIHF's stats archive: ``event_id, year, title, gender, tournament,
    division, teams``. Filter by ``year``, ``gender`` ("men"/"women") or ``tournament`` code.

    The list ships with puckscrape (the archive has no index page; building it means
    asking for every id). ``scan_events`` rebuilds it."""
    df = _catalog()
    if year is not None:
        df = df[df["year"].isin(as_list(year))]
    if gender is not None:
        df = df[df["gender"] == gender.lower()]
    if tournament is not None:
        df = df[df["tournament"].isin([t.lower() for t in as_list(tournament)])]
    return df.reset_index(drop=True)


def scan_events(ids=range(1, 1101)) -> pd.DataFrame:
    """Ask the archive for every id in ``ids`` and classify what's there: about 1,100
    requests, so slow; ``events()`` already has the result. Returns the same columns."""
    rows = []
    for i in ids:
        try:
            page = _index_page(i)
        except _http.PuckscrapeError:
            continue
        except Exception as e:   # 404s and dead ids
            log.debug("Hydra %s: %s", i, e)
            continue
        title = _title(page)
        if not title:
            continue
        info = classify(title, i)
        prefix = re.search(r'href="(IH[MW])\d', page)
        if prefix:
            info["gender"] = "women" if prefix.group(1) == "IHW" else "men"
        rows.append({"event_id": i, "year": info["year"], "title": title, "gender": info["gender"],
                     "tournament": info["tournament"], "division": info["division"],
                     "teams": len(_team_reports(page))})
    return pd.DataFrame(rows)


def _resolve(event, year, division) -> list[int]:
    """Event ids from an id (or ids), an events() frame, or a tournament code and year."""
    if isinstance(event, pd.DataFrame):
        return [int(i) for i in event["event_id"]]
    if isinstance(event, int) or (isinstance(event, str) and event.isdigit()):
        return [int(event)]
    if isinstance(event, (list, tuple)) and all(isinstance(e, int) for e in event):
        return list(event)
    code = str(event).lower()
    if code not in TOURNAMENTS:
        raise ValueError(f"unknown IIHF tournament {event!r}; one of {', '.join(TOURNAMENTS)}, or an event id")
    if year is None:
        raise ValueError("give the tournament's year, e.g. ps.iihf.skaters('ww', 2025)")
    df = events(year=year, tournament=code)
    df = df[df["teams"] > 0]
    if str(division).lower() != "all":
        want = str(division).lower().replace("division", "div")
        df = df[df["division"].str.lower() == want]
    if df.empty:
        raise ValueError(f"no {code} {year} event (division {division!r}) in the IIHF archive; "
                         f"see ps.iihf.events(year={year}, tournament={code!r})")
    return [int(i) for i in df["event_id"]]


# ---------------------------------------------------------------- pages

@lru_cache(maxsize=256)
def _index_page(event_id: int) -> str:
    # The pages are UTF-8 but say nothing about it, so requests would guess Latin-1.
    return _http.get(f"{BASE}/{event_id}/").content.decode("utf-8", errors="replace")


@lru_cache(maxsize=1024)
def _pdf(event_id: int, name: str) -> bytes:
    return _http.get(f"{BASE}/{event_id}/{name}").content


def _title(page: str) -> str:
    m = re.search(r"<title>([^<]*)", page)
    t = " ".join(fix_text(m.group(1)).split()) if m else ""
    return "" if "not found" in t.lower() else t


def _team_reports(page: str) -> dict[str, str]:
    """{team code: 'Player Statistics by Team' PDF} (report 83). Files are named
    'IHW5100USA_83_7_0_USA.pdf' or, at the 2014 Olympics, 'IHM400000_83_60_0_CAN.pdf'."""
    out = {}
    for href in re.findall(r'href="(IH[MW]\w+?_83_[^"]*\.pdf)"', page):
        m = re.match(r"IH[MW]\d+?([A-Z]{3})_83", href) or re.search(r"_([A-Z]{3})\.pdf$", href)
        if m:
            out.setdefault(m.group(1), href)
    return out


def _event_report(page: str, pattern: str) -> str | None:
    m = re.search(rf'href="(IH[MW]\d+?000_{pattern}[^"]*\.pdf)"', page)
    return m.group(1) if m else None


def _event_info(event_id: int) -> dict:
    page = _index_page(event_id)
    title = _title(page)
    info = classify(title, event_id)
    prefix = re.search(r'href="(IH[MW])\d', page)
    if prefix:
        info["gender"] = "women" if prefix.group(1) == "IHW" else "men"
    return {"event_id": event_id, "event": title, **info}


# ---------------------------------------------------------------- player stats

_SKATER_COLS = {"GP": "gp", "G": "g", "A": "a", "PTS": "pts", "PIM": "pim", "+/-": "plus_minus",
                "GWG": "gwg", "PPG": "ppg", "SHG": "shg", "SOG": "shots", "SG%": "sh_pct", "TM": "toi",
                "M/G": "toi_per_gp", "TSh": "shifts", "AT/S": "toi_per_shift"}
_GOALIE_COLS = {"GPT": "team_gp", "GKD": "dressed", "GPI": "gp", "MIP": "toi", "MIP%": "toi_pct", "GA": "ga",
                "SVS": "saves", "SOG": "shots_against", "SVS%": "sv_pct", "GAA": "gaa", "SO": "so",
                "W": "w", "L": "l"}
_POS = r"GK|G|D|F|LW|RW|C|W"


def _is_family(token: str) -> bool:
    """Family names are printed in capitals: 'KNIGHT', 'ST.', and 'McKENNA' (mostly capitals)."""
    letters = re.sub(r"[^\w]|[\d_]", "", token)
    upper = sum(c.isupper() for c in letters)
    return len(letters) >= 2 and upper > len(letters) - upper


def _split_name(name: str) -> tuple[str, str]:
    """'COYNE SCHOFIELD Kendall' -> ('Kendall', 'COYNE SCHOFIELD'); 'McKENNA Gavin' -> ('Gavin', 'McKENNA')."""
    tokens = name.split()
    i = 0
    while i < len(tokens) and _is_family(tokens[i]):
        i += 1
    if i == 0 or i == len(tokens):
        return "", name
    return " ".join(tokens[i:]), " ".join(tokens[:i])


def _display(first: str, last: str) -> str:
    if all(_is_family(t) for t in last.split()):
        last = last.title()   # 'COYNE SCHOFIELD' -> 'Coyne Schofield', "O'NEILL" -> "O'Neill"
        last = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), last)
    return f"{first} {last}".strip()


def _clock_minutes(v):
    if isinstance(v, str) and re.fullmatch(r"\d+:\d{2}", v):
        mm, ss = v.split(":")
        return round(int(mm) + int(ss) / 60, 2)
    return v


def _team_tables(event_id: int, code: str, href: str) -> tuple[list[dict], list[dict]]:
    """(skater rows, goalie rows) from one team's report 83."""
    skaters, goalies = [], []
    team = code
    for page in _pdftext.spans(_pdf(event_id, href)):
        section, header = None, []
        for line in _pdftext.rows(page):
            text = " ".join(s.text.strip() for s in line)
            if m := re.fullmatch(rf"{code} - (.+)", text):
                team = m.group(1).strip()
            elif text.startswith("Playing Statistics"):
                section = "skaters"
            elif text.startswith("Goalkeeping Statistics"):
                section = "goalies"
            elif re.match(r"No\.? Name\b", text):   # 'No. Name Pos.' (2019 on), 'No Name Pos' (earlier)
                header = [h for h in text.split()[2:] if h not in ("Pos.", "Pos")]
                # '+/ -' is printed in two pieces; joining tokens above can leave '+/' and '-'.
                fixed = []
                for h in header:
                    if h == "-" and fixed and fixed[-1] == "+/":
                        fixed[-1] = "+/-"
                    else:
                        fixed.append(h)
                header = fixed
            elif text.startswith("Legend"):
                section = None
            elif section == "skaters" and header:
                m = re.match(rf"^(\d+)\s+(.+?)\s+({_POS})\s+([-+\d].*)$", text)
                if not m or m.group(3) in ("GK", "G"):
                    continue
                first, last = _split_name(m.group(2))
                values = m.group(4).split()
                rec = {"jersey": m.group(1), "first_name": first, "last_name": last, "position": m.group(3)}
                rec.update({_SKATER_COLS.get(h, h): v for h, v in zip(header, values)})
                skaters.append(rec)
            elif section == "goalies" and header:
                m = re.match(r"^(\d+)\s+(.+?)\s+(\d.*)$", text)
                if not m:
                    continue
                first, last = _split_name(m.group(2))
                values = m.group(3).split()
                rec = {"jersey": m.group(1), "first_name": first, "last_name": last}
                rec.update({_GOALIE_COLS.get(h, h): v for h, v in zip(header, values)})
                goalies.append(rec)
    for rec in skaters + goalies:
        rec["team"], rec["team_code"] = team, code
        rec["player"] = _display(rec["first_name"], rec["last_name"])
    return skaters, goalies


def _players(event, year, division, goalie: bool) -> pd.DataFrame:
    frames = []
    for event_id in _resolve(event, year, division):
        info = _event_info(event_id)
        reports = _team_reports(_index_page(event_id))
        rows = []
        for i, (code, href) in enumerate(sorted(reports.items()), 1):
            try:
                sk, gk = _team_tables(event_id, code, href)
            except requests.HTTPError as e:
                # Some events link reports the server no longer has (the 2022 Olympics').
                log.warning("IIHF %s: %s's report is missing (%s)", info["event"], code, e)
                continue
            rows += gk if goalie else sk
            log.info("IIHF %s: %d/%d teams", info["event"], i, len(reports))
        if not rows:
            continue
        df = pd.DataFrame(rows)
        if "toi" in df:
            df["toi"] = df["toi"].map(_clock_minutes) if goalie else df["toi"]
        for col, val in reversed(list(info.items())):
            df.insert(0, col, val)
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _shape(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Core column order (like ps.leagues), with the event's columns up front."""
    if df.empty:
        return df
    front = ["event_id", "event", "year", "gender", "tournament", "division"]
    df = to_numbers(df)
    if kind == "goalies" and "sv_pct" in df and pd.api.types.is_numeric_dtype(df["sv_pct"]) and df["sv_pct"].max() > 1:
        df["sv_pct"] = (df["sv_pct"] / 100).round(4)
    core = {"skaters": ["player", "team", "team_code", "position", "gp", "g", "a", "pts", "pim", "plus_minus"],
            "goalies": ["player", "team", "team_code", "gp", "w", "l", "ga", "saves", "sv_pct", "gaa", "so", "toi"]}[kind]
    first = [c for c in front + core if c in df]
    return df[first + [c for c in df.columns if c not in first]]


def skaters(event, year: int | None = None, *, division: str = "Top") -> pd.DataFrame:
    """Skater stats for a tournament: a code and year (``"ww", 2025``), an event id, a list
    of ids, or a frame from ``events()``. ``division`` picks one division ("Top",
    "Div I Group A", ...) or ``"all"``. Totals cover the whole tournament."""
    return _shape(_players(event, year, division, goalie=False), "skaters")


def goalies(event, year: int | None = None, *, division: str = "Top") -> pd.DataFrame:
    """Goalie stats for a tournament (same arguments as ``skaters``). ``toi`` is in minutes."""
    return _shape(_players(event, year, division, goalie=True), "goalies")


# ---------------------------------------------------------------- standings

_STANDING = re.compile(r"^([A-Z]{3})\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([-+]?\d+)\s+(\d+)\s*:\s*(\d+)$")
_GROUP_TITLE = re.compile(r"\b(Round|Group|Final|Placement|Relegation|Qualification|Playoff|Medal)\b")
_STANDING_COLS = ["team_code", "gp", "w", "otw", "otl", "l", "pts", "goal_diff", "gf", "ga"]


def _ranking_pages(event_id: int):
    """The final ranking report's pages; none (with a warning) for events without one
    (older events, and events not finished yet)."""
    href = _event_report(_index_page(event_id), "FINAL_RANKING")
    if href is None:
        log.warning("IIHF event %s has no final ranking report", event_id)
        return []
    return _pdftext.spans(_pdf(event_id, href))


def standings(event, year: int | None = None, *, division: str = "Top") -> pd.DataFrame:
    """Group standings (preliminary round groups, placement rounds...) from the final ranking report:
    ``group, rank, team_code, gp, w, otw, otl, l, pts, goal_diff, gf, ga``."""
    frames = []
    for event_id in _resolve(event, year, division):
        info = _event_info(event_id)
        rows = []
        for page in _ranking_pages(event_id):
            groups: dict[int, str] = {}   # column (0 left, 1 right) -> its current group title
            split = 290.0
            for line in _pdftext.rows(page):
                spans = line
                text = " ".join(s.text.strip() for s in spans)
                if text in ("Final Ranking", "Final Standing"):
                    break
                # A group's title can share a line with the other column's rows.
                for s in spans:
                    if _GROUP_TITLE.search(s.text) and not _STANDING.match(s.text.strip()):
                        groups[int(s.x > split)] = s.text.strip()
                cells = [s for s in spans if s.text.strip()]
                for j, s in enumerate(cells):
                    m = _STANDING.match(s.text.strip())
                    if m and j > 0 and cells[j - 1].text.strip().isdigit():
                        col = int(s.x > split)
                        rows.append({"group": groups.get(col, ""), "rank": int(cells[j - 1].text),
                                     **dict(zip(_STANDING_COLS, m.groups()))})
        if rows:
            df = pd.DataFrame(rows)
            for col, val in reversed(list(info.items())):
                df.insert(0, col, val)
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    df = to_numbers(pd.concat(frames, ignore_index=True))
    return df.sort_values(["event_id", "group", "rank"], kind="stable").reset_index(drop=True)


def final_ranking(event, year: int | None = None, *, division: str = "Top") -> pd.DataFrame:
    """Final placings: ``rank, team_code, team``."""
    frames = []
    for event_id in _resolve(event, year, division):
        info = _event_info(event_id)
        rows = []
        for page in _ranking_pages(event_id):
            started = False
            for line in _pdftext.rows(page):
                text = " ".join(s.text.strip() for s in line)
                if text in ("Final Ranking", "Final Standing"):
                    started = True
                    continue
                if started and (m := re.fullmatch(r"(\d+)\s+([A-Z]{3})\s+(.+)", text)):
                    rows.append({"rank": int(m.group(1)), "team_code": m.group(2), "team": m.group(3).strip()})
                elif started and text.startswith("Note"):
                    break
        if not rows:
            # A single round robin prints its standings and no separate ranking list.
            st = standings(event_id)
            if not st.empty and st["group"].nunique() == 1:
                rows = [{"rank": r["rank"], "team_code": r["team_code"], "team": None} for _, r in st.iterrows()]
        if rows:
            df = pd.DataFrame(rows)
            for col, val in reversed(list(info.items())):
                df.insert(0, col, val)
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


__all__ = ["events", "scan_events", "skaters", "goalies", "standings", "final_ranking", "classify", "TOURNAMENTS"]
