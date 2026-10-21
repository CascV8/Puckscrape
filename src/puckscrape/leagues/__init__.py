"""Player and team stats straight from league and federation websites.

    import puckscrape as ps

    ps.leagues.leagues()                              # what's covered, and from where
    ps.leagues.skaters("ohl", "2025-26")
    ps.leagues.goalies(["shl", "liiga"], 2025, phase="playoffs")
    ps.leagues.standings("ncaa", 2024)

Every table starts with the same core columns (league, season, phase, player,
team, gp, g, a, pts, ...) and keeps whatever else the site publishes after them.
Seasons take any spelling ps accepts elsewhere: 2025, "2025-26", "20252026".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import ModuleType

import pandas as pd

from .._util import as_list, start_year
from . import (chn, delhockey, eihl, hockeyallsvenskan, hockeytech, hokejcz, icehl, leijonat, liiga,
               metalligaen, sihf, sportality)
from ._common import Unsupported

log = logging.getLogger("puckscrape.leagues")


@dataclass(frozen=True)
class League:
    code: str
    name: str
    country: str
    level: str
    source: str
    adapter: object
    opts: dict = field(default_factory=dict)


class _Split:
    """Adapter whose functions are named per league (DEL vs DEL2 live in one module)."""

    def __init__(self, module: ModuleType, prefix: str):
        self.skaters = getattr(module, f"{prefix}_skaters")
        self.goalies = getattr(module, f"{prefix}_goalies")
        self.standings = getattr(module, f"{prefix}_standings")


_DEL, _DEL2 = _Split(delhockey, "del"), _Split(delhockey, "del2")

_REGISTRY = [
    # North America
    League("ncaa", "NCAA Division I (men)", "USA", "college", "collegehockeynews.com", chn),
    League("ohl", "Ontario Hockey League", "Canada", "major junior", "chl.ca (HockeyTech)", hockeytech, {"client": "ohl"}),
    League("whl", "Western Hockey League", "Canada", "major junior", "chl.ca (HockeyTech)", hockeytech, {"client": "whl"}),
    League("qmjhl", "Quebec Maritimes Junior Hockey League", "Canada", "major junior", "chl.ca (HockeyTech)", hockeytech, {"client": "lhjmq"}),
    # Sweden
    League("shl", "SHL", "Sweden", "top", "shl.se", sportality, {"host": "https://www.shl.se", "series": "SHL"}),
    League("hockeyallsvenskan", "HockeyAllsvenskan", "Sweden", "second", "hockeyallsvenskan.se", hockeyallsvenskan),
    League("sdhl", "SDHL (women)", "Sweden", "women", "sdhl.se", sportality, {"host": "https://www.sdhl.se", "series": "SDHL"}),
    # Finland
    League("liiga", "Liiga", "Finland", "top", "liiga.fi", liiga),
    League("mestis", "Mestis", "Finland", "second", "tulospalvelu.leijonat.fi", leijonat, {"level": "Mestis"}),
    League("suomi-sarja", "Suomi-sarja", "Finland", "third", "tulospalvelu.leijonat.fi", leijonat, {"level": "Suomi-sarja"}),
    League("u20-sm-sarja", "U20 SM-sarja", "Finland", "junior", "tulospalvelu.leijonat.fi", leijonat, {"level": "U20 SM-sarja"}),
    League("u18-sm-sarja", "U18 SM-sarja", "Finland", "junior", "tulospalvelu.leijonat.fi", leijonat, {"level": "U18 SM-sarja"}),
    League("auroraliiga", "Auroraliiga (women)", "Finland", "women", "tulospalvelu.leijonat.fi", leijonat, {"level": "Auroraliiga"}),
    # Switzerland
    League("nl", "National League", "Switzerland", "top", "data.sihf.ch", sihf, {"league_id": 1}),
    League("sl", "Swiss League", "Switzerland", "second", "data.sihf.ch", sihf, {"league_id": 2}),
    League("myhl", "MyHockey League", "Switzerland", "third", "data.sihf.ch", sihf, {"league_id": 3}),
    # Germany
    League("del", "PENNY DEL", "Germany", "top", "penny-del.org", _DEL),
    League("del2", "DEL2", "Germany", "second", "del-2.org", _DEL2),
    # Czechia
    League("extraliga", "Tipsport Extraliga", "Czechia", "top", "hokej.cz", hokejcz, {"slug": "tipsport-extraliga"}),
    League("maxa-liga", "Maxa liga", "Czechia", "second", "hokej.cz", hokejcz, {"slug": "maxa-liga"}),
    # Austria and neighbours, UK
    League("icehl", "ICE Hockey League", "Austria", "top", "ice.hockey", icehl),
    League("eihl", "Elite Ice Hockey League", "United Kingdom", "top", "eliteleague.co.uk", eihl),
    League("metal-ligaen", "Metal Ligaen", "Denmark", "top", "statistik.metalligaen.dk", metalligaen),
]
LEAGUES: dict[str, League] = {lg.code: lg for lg in _REGISTRY}


def leagues() -> pd.DataFrame:
    """Every league covered, with the site its numbers come from."""
    return pd.DataFrame([{"code": lg.code, "name": lg.name, "country": lg.country, "level": lg.level,
                          "source": lg.source} for lg in _REGISTRY])


def _get(code: str) -> League:
    try:
        return LEAGUES[code.lower()]
    except KeyError:
        raise ValueError(f"unknown league {code!r}; see ps.leagues.leagues()") from None


def _run(kind: str, codes, seasons, phase: str) -> pd.DataFrame:
    frames = []
    for code in as_list(codes):
        lg = _get(code)
        for season in as_list(seasons):
            y = start_year(season)
            log.info("%s %s %s %d-%02d", lg.code, kind, phase, y, (y + 1) % 100)
            frames.append(getattr(lg.adapter, kind)(lg.opts, lg.code, y, phase))
    frames = [f for f in frames if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def skaters(leagues, seasons, *, phase: str = "regular") -> pd.DataFrame:
    """Skater stats for one or more leagues and seasons. ``phase`` is "regular" or "playoffs"."""
    return _run("skaters", leagues, seasons, phase)


def goalies(leagues, seasons, *, phase: str = "regular") -> pd.DataFrame:
    """Goalie stats for one or more leagues and seasons."""
    return _run("goalies", leagues, seasons, phase)


def standings(leagues, seasons, *, phase: str = "regular") -> pd.DataFrame:
    """Standings (or team stats, where that's all a site has)."""
    return _run("standings", leagues, seasons, phase)


__all__ = ["leagues", "skaters", "goalies", "standings", "LEAGUES", "League", "Unsupported"]
