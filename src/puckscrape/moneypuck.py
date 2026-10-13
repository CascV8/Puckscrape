"""MoneyPuck advanced stats (xG, Corsi, Fenwick, game score...).

MoneyPuck publishes these as CSV downloads, so nothing is scraped from HTML.
Please credit MoneyPuck.com if you publish anything built on their data.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd

from . import _http
from ._util import as_list, start_year

BASE = "https://moneypuck.com/moneypuck/playerData"
SHOTS = "https://peter-tanner.com/moneypuck/downloads"

SITUATIONS = ("all", "5on5", "4on5", "5on4", "other")


def _season_summary(kind: str, seasons, playoffs: bool, situation: str | None) -> pd.DataFrame:
    if situation is not None and situation not in SITUATIONS:
        raise ValueError(f"situation must be one of {SITUATIONS}")
    part = "playoffs" if playoffs else "regular"
    frames = []
    for season in as_list(seasons):
        resp = _http.get(f"{BASE}/seasonSummary/{start_year(season)}/{part}/{kind}.csv")
        frames.append(pd.read_csv(io.BytesIO(resp.content)))
    df = pd.concat(frames, ignore_index=True)
    if situation is not None and "situation" in df:
        df = df[df["situation"] == situation].reset_index(drop=True)
    return df


def skaters(seasons, *, playoffs: bool = False, situation: str | None = "all") -> pd.DataFrame:
    """Season skater stats. One row per player per ``situation``
    (all, 5on5, 4on5, 5on4, other); pass ``situation=None`` for every split.
    Seasons are by start year: 2024 means 2024-25."""
    return _season_summary("skaters", seasons, playoffs, situation)


def goalies(seasons, *, playoffs: bool = False, situation: str | None = "all") -> pd.DataFrame:
    return _season_summary("goalies", seasons, playoffs, situation)


def teams(seasons, *, playoffs: bool = False, situation: str | None = "all") -> pd.DataFrame:
    return _season_summary("teams", seasons, playoffs, situation)


def lines(seasons, *, playoffs: bool = False, situation: str | None = None) -> pd.DataFrame:
    """Forward lines and defense pairs. MoneyPuck only publishes 5on5 for these."""
    return _season_summary("lines", seasons, playoffs, situation)


def shots(season) -> pd.DataFrame:
    """Every unblocked shot of a season with MoneyPuck's xG and ~100 features.

    Big: about 20 MB zipped and 120k+ rows per season.
    """
    resp = _http.get(f"{SHOTS}/shots_{start_year(season)}.zip", timeout=300)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".csv"))
        with zf.open(name) as f:
            return pd.read_csv(f, low_memory=False)
