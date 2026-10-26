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
    League("ahl", "American Hockey League", "USA", "pro second", "theahl.com (HockeyTech)", hockeytech, {"client": "ahl", "key": "ccb91f29d6744675"}),
    League("echl", "ECHL", "USA", "pro third", "echl.com (HockeyTech)", hockeytech, {"client": "echl", "key": "2c2b89ea7345cae8"}),
    League("ushl", "United States Hockey League", "USA", "junior", "ushl.com (HockeyTech)", hockeytech, {"client": "ushl", "key": "e828f89b243dc43f"}),
    League("bchl", "British Columbia Hockey League", "Canada", "junior A", "bchl.ca (HockeyTech)", hockeytech, {"client": "bchl", "key": "f3ed30007ad2124e"}),
    League("ajhl", "Alberta Junior Hockey League", "Canada", "junior A", "ajhl.ca (HockeyTech)", hockeytech, {"client": "ajhl", "key": "cbe60a1d91c44ade"}),
    League("sjhl", "Saskatchewan Junior Hockey League", "Canada", "junior A", "sjhl.ca (HockeyTech)", hockeytech, {"client": "sjhl", "key": "2fb5c2e84bf3e4a8"}),
    League("mjhl", "Manitoba Junior Hockey League", "Canada", "junior A", "mjhlhockey.ca (HockeyTech)", hockeytech, {"client": "mjhl", "key": "f894c324fe5fd8f0"}),
    League("ojhl", "Ontario Junior Hockey League", "Canada", "junior A", "ojhl.ca (HockeyTech)", hockeytech, {"client": "ojhl", "key": "77a0bd73d9d363d3"}),
    League("cchl", "Central Canada Hockey League", "Canada", "junior A", "cchl.ca (HockeyTech)", hockeytech, {"client": "cchl", "key": "b370f3e6c805baf3"}),
    League("mjahl", "Maritime Junior Hockey League", "Canada", "junior A", "themhl.ca (HockeyTech)", hockeytech, {"client": "mhl", "key": "4a948e7faf5ee58d"}),
    League("kijhl", "Kootenay International Junior Hockey League", "Canada", "junior B", "kijhl.ca (HockeyTech)", hockeytech, {"client": "kijhl", "key": "2589e0f644b1bb71"}),
    League("vijhl", "Vancouver Island Junior Hockey League", "Canada", "junior B", "vijhl.ca (HockeyTech)", hockeytech, {"client": "vijhl", "key": "4f1a61df18906b61"}),
    League("gohl", "Greater Ontario Hockey League", "Canada", "junior B", "gohl.ca (HockeyTech)", hockeytech,
           {"client": "gojhl", "key": "34b10d4d34d7b59a", "regular": r"\bgo(j)?hl season$"}),
    League("csshl", "Canadian Sport School Hockey League (U18 Prep)", "Canada", "U18", "csshl.ca (HockeyTech)", hockeytech,
           {"client": "csshl", "key": "dbb3085c9c2968c6", "league_ids": [6], "regular": r"^\d{4}-\d{2} u18 prep$"}),
    # Sweden
    League("shl", "SHL", "Sweden", "top", "shl.se", sportality, {"host": "https://www.shl.se", "series": "SHL"}),
    League("hockeyallsvenskan", "HockeyAllsvenskan", "Sweden", "second", "hockeyallsvenskan.se", hockeyallsvenskan),
    League("sdhl", "SDHL (women)", "Sweden", "women", "sdhl.se", sportality, {"host": "https://www.sdhl.se", "series": "SDHL"}),
    # Finland
    League("liiga", "Liiga", "Finland", "top", "liiga.fi", liiga),
    League("mestis", "Mestis", "Finland", "second", "tulospalvelu.leijonat.fi", leijonat, {"level": "Mestis"}),
    League("suomi-sarja", "Suomi-sarja", "Finland", "third", "tulospalvelu.leijonat.fi", leijonat, {"level": "Suomi-sarja"}),
    League("u20-sm-sarja", "U20 SM-sarja", "Finland", "junior", "tulospalvelu.leijonat.fi", leijonat, {"level": ("U20 SM-sarja", "Nuorten SM-Liiga")}),
    League("u18-sm-sarja", "U18 SM-sarja", "Finland", "junior", "tulospalvelu.leijonat.fi", leijonat, {"level": ("U18 SM-sarja", "B-nuorten SM-sarja")}),
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
hockeytech._KEYS.update({lg.opts["client"]: lg.opts["key"] for lg in _REGISTRY if "key" in lg.opts})


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
