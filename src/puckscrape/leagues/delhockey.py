"""German leagues: DEL (penny-del.org) and DEL2 (del-2.org) stats pages."""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, clean_team, finish, find_table, phase_key, soup, table_rows

DEL = "https://www.penny-del.org"
DEL2 = "https://www.del-2.org"
_DEL_PHASE = {"regular": "hauptrunde", "playoffs": "playoffs"}

_SKATER_NAMES = {"Spieler": "player", "Team": "team", "Club": "team", "POS": "position", "Pos": "position",
                 "GP": "gp", "G": "g", "T": "g", "A": "a", "P": "pts", "PIM": "pim", "+/-": "plus_minus",
                 "Nat": "nationality", "Nr": "number", "#_1": "number", "#": "rank"}
_GOALIE_NAMES = {"Spieler": "player", "Team": "team", "Club": "team", "GP": "gp", "S": "w", "W": "w",
                 "N": "l", "L": "l", "SO": "so", "GT": "ga", "GA": "ga", "SV": "saves", "SV%": "sv_pct",
                 "GTS": "gaa", "GAA": "gaa", "Min.": "toi", "MIP": "toi", "Nat": "nationality",
                 "Nr": "number", "#_1": "number", "#": "rank"}


def _del_url(y: int, phase: str, page: str) -> str:
    return f"{DEL}/statistik/saison-{y}-{(y + 1) % 100:02d}/{_DEL_PHASE[phase_key(phase)]}/{page}"


def _one_table(url: str, *labels: str, **params) -> pd.DataFrame:
    page = soup(url, **params)
    for short in page.select(".player-name-short"):  # DEL2 prints 'Carter Turnbull' and 'C. Turnbull'
        short.decompose()
    table = find_table(page, *labels)
    return table_rows(table, labels) if table is not None else pd.DataFrame()


def _flip(name):
    """DEL writes 'Barratt, Evan'."""
    if isinstance(name, str) and name.count(",") == 1:
        last, first = (p.strip() for p in name.split(","))
        return f"{first} {last}"
    return name


@cache
def _del_logos(y: int) -> dict[str, str]:
    """DEL's player tables show only a team logo; the standings page pairs logos with names."""
    page = soup(_del_url(y, "regular", "tabelle"))
    out = {}
    for row in page.find_all("tr"):
        img = row.find("img")
        names = [td.get_text(" ", strip=True) for td in row.find_all("td")
                 if td.get_text(strip=True) and not td.get_text(strip=True).isdigit()]
        if img is not None and names:
            out[img.get("src", "")] = names[0]
    return out


def _del_table(y: int, phase: str, page_name: str) -> pd.DataFrame:
    page = soup(_del_url(y, phase, page_name))
    table = find_table(page, "Spieler", "GP")
    if table is None:
        return pd.DataFrame()
    df = table_rows(table, ("Spieler", "GP"))
    logos = _del_logos(y)
    body = [r for r in table.find_all("tr") if r.find("td")]
    teams = [logos.get(r.find("img").get("src", "")) if r.find("img") is not None else None for r in body]
    df["Team"] = teams[:len(df)]
    df["Spieler"] = df["Spieler"].map(_flip)
    return df


# ---- DEL -------------------------------------------------------------------

def del_skaters(opts, league, y, phase):
    df = _del_table(y, phase, "playerstats/basis")
    return finish(df, "skaters", league, y, phase_key(phase), rename=_SKATER_NAMES)


def del_goalies(opts, league, y, phase):
    df = _del_table(y, phase, "goaliestats/basis")
    return finish(df, "goalies", league, y, phase_key(phase), rename=_GOALIE_NAMES)


def del_standings(opts, league, y, phase):
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    df = _one_table(_del_url(y, phase, "tabelle"), "Team", "GP")
    return finish(df, "standings", league, y, "regular", rename={
        "Team": "team", "GP": "gp", "W": "w", "OTW": "otw", "L": "l", "OTL": "otl", "P": "pts",
        "GF": "gf", "GA": "ga", "#": "rank"})


# ---- DEL2 ------------------------------------------------------------------

@cache
def _del2_rounds() -> dict[tuple[int, str], str]:
    out = {}
    for opt in soup(f"{DEL2}/stats/").find_all("option"):
        m = re.search(r"(\d{4})/\d{2}\s*-\s*(Hauptrunde|Playoffs)", opt.get_text(" ", strip=True))
        r = re.search(r"round=(\d+)", opt.get("value", ""))
        if m and r:
            out[(int(m.group(1)), "regular" if m.group(2) == "Hauptrunde" else "playoffs")] = r.group(1)
    return out


def _round(y: int, phase: str) -> str:
    try:
        return _del2_rounds()[(y, phase_key(phase))]
    except KeyError:
        raise ValueError(f"DEL2 has no {phase_key(phase)} season {y}-{y + 1}") from None


@cache
def _del2_scorer_seasons() -> dict[int, str]:
    """The scorer and goalie pages pick seasons by their own ids ('32' = 2025/2026), not by round."""
    select = soup(f"{DEL2}/stats/scorer/").find("select", {"name": "season_from"})
    out = {}
    for opt in select.find_all("option") if select else []:
        m = re.match(r"(\d{4})/\d{4}", opt.get_text(strip=True))
        if m:
            out[int(m.group(1))] = opt["value"]
    return out


def del2_skaters(opts, league, y, phase):
    sid = _del2_scorer_seasons().get(y)
    if sid is None:
        raise ValueError(f"DEL2 has no season {y}-{y + 1}")
    df = _one_table(f"{DEL2}/stats/scorer/", "Spieler", "GP", season_from=sid, season_to=sid,
                    phase=phase_key(phase), view="sum")
    return finish(df, "skaters", league, y, phase_key(phase), rename=_SKATER_NAMES)


def del2_goalies(opts, league, y, phase):
    sid = _del2_scorer_seasons().get(y)
    if sid is None:
        raise ValueError(f"DEL2 has no season {y}-{y + 1}")
    df = _one_table(f"{DEL2}/stats/goalies/", "Spieler", "GP", season_from=sid, season_to=sid,
                    phase=phase_key(phase), view="sum")
    return finish(df, "goalies", league, y, phase_key(phase), rename=_GOALIE_NAMES)


def del2_standings(opts, league, y, phase):
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only")
    df = _one_table(f"{DEL2}/tabelle", "Club", "Sp", round=_round(y, phase))
    if not df.empty:
        df["Club"] = df["Club"].map(clean_team)
    return finish(df, "standings", league, y, "regular", drop=("Clublogo",), rename={
        "Club": "team", "Sp": "gp", "S": "w", "OTG": "otw", "OTV": "otl", "P": "pts", "T": "gf",
        "GT": "ga", "#": "rank", "PSG": "sow"})
