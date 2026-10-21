"""Czech leagues from hokej.cz's stats centre (Extraliga, Maxa liga).

Tables hold 30 rows a page; asking past the last page returns the last page
again, so paging stops when the ranks stop moving.
"""

from __future__ import annotations

import pandas as pd

from functools import cache

from ._common import Unsupported, finish, find_table, phase_key, soup, table_rows

BASE = "https://www.hokej.cz"


@cache
def _competition(slug: str, y: int, phase: str) -> str:
    """Each season's regular season and playoffs have their own competition id,
    listed in the season's dropdown ('Tipsport extraliga', 'Play off ...')."""
    page = soup(f"{BASE}/{slug}/stats-center", season=y)
    select = page.find("select", {"name": "competition"})
    for opt in select.find_all("option") if select else []:
        name = opt.get_text(" ", strip=True).lower()
        is_playoff = "play off" in name or "playoff" in name
        is_extra = any(w in name for w in ("baráž", "kvalifikace", "předkolo", "play-out", "play out", "udržení"))
        if phase == "playoffs" and is_playoff:
            return opt["value"]
        if phase == "regular" and not is_playoff and not is_extra:
            return opt["value"]
    raise ValueError(f"no {phase} competition for {slug} {y}-{y + 1}")


def _paged(slug: str, y: int, section: str | None, first_label: str, phase: str = "regular") -> pd.DataFrame:
    frames, last_first = [], None
    competition = _competition(slug, y, phase)
    for page_no in range(1, 200):
        params = {"season": y, "competition": competition, "stats-page": page_no}
        if section:
            params["stats-section"] = section
        page = soup(f"{BASE}/{slug}/stats-center", **params)
        table = find_table(page, first_label, "TÝM")
        if table is None:
            break
        df = table_rows(table, (first_label,))
        if df.empty or df.iloc[0, 0] == last_first:
            break
        last_first = df.iloc[0, 0]
        frames.append(df)
        if len(df) < 30:
            break
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _paged(opts["slug"], y, None, "JMÉNO", phase_key(phase))
    return finish(df, "skaters", league, y, phase_key(phase), rename={
        "POŘ.": "rank", "JMÉNO": "player", "TÝM": "team", "POZ.": "position", "GP": "gp", "G": "g",
        "A": "a", "P": "pts", "S": "shots", "plus/minus": "plus_minus", "TOI": "toi_per_gp"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _paged(opts["slug"], y, "goalkeeper", "JMÉNO", phase_key(phase))
    return finish(df, "goalies", league, y, phase_key(phase), rename={
        "POŘ.": "rank", "JMÉNO": "player", "TÝM": "team", "GP": "gp", "W": "w", "L": "l", "GA": "ga",
        "SV": "saves", "SV%": "sv_pct", "GAA": "gaa", "SO": "so", "TOI": "toi"})


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    raise Unsupported("standings not wired for hokej.cz yet")
