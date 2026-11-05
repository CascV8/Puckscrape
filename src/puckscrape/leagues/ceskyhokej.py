"""Czech leagues from the Czech Ice Hockey Association's site (ceskyhokej.cz).

Every federation competition has the same pages: Tipsport Extraliga, Maxa liga,
2. liga, the women's Extraliga, and the junior and youth extraligas (U20,
older and younger "dorost"). Seasons go back to 2019-20.

A season is split into parts, each with its own id: the base round (sometimes in
groups), placement and qualification rounds, relegation rounds, the play-off
preliminary round and the title play-offs. Every row keeps its part in a
``stage`` column; "regular" is every part but the play-offs. Stats pages hold
50 rows each.
"""

from __future__ import annotations

import re
from functools import cache

import pandas as pd

from ._common import Unsupported, cells, finish, phase_key, soup

BASE = "https://ceskyhokej.cz"
W = "playerCompetitionStatsWidget"
PAGE_ROWS = 50
_POSITION = {"Ú": "F", "O": "D", "B": "G"}
# Parts that are the play-offs: the title series ("Play-off o titul", "O titul Mistr České
# republiky", "finále") and its preliminary round. "O pořadí v play-off" / "O účast v play-off"
# (seeding and qualification rounds) and relegation rounds are regular season.
_PLAYOFF = re.compile(r"play-?off|o titul|finále", re.I)
_PLAYOFF_NOT = re.compile(r"o pořadí|o účast|o udržení|play-?down", re.I)


def _is_playoff(part_name: str) -> bool:
    return bool(_PLAYOFF.search(part_name)) and not _PLAYOFF_NOT.search(part_name)


@cache
def _season_ids(comp: int) -> dict[str, str]:
    """'2025/26' -> the site's season id, from the season dropdown."""
    page = soup(f"{BASE}/competition/standings/{comp}")
    select = page.find("select", {"name": "season"})
    return {o.get_text(strip=True): o["value"] for o in select.find_all("option")} if select else {}


def _season_id(comp: int, y: int) -> str:
    label = f"{y}/{(y + 1) % 100:02d}"
    sid = _season_ids(comp).get(label)
    if sid is None:
        raise ValueError(f"ceskyhokej.cz has no {label} season for competition {comp}")
    return sid


@cache
def _parts(comp: int, y: int) -> tuple[tuple[str, str], ...]:
    """(part id, part name) for every part of a season."""
    page = soup(f"{BASE}/competition/player-stats/{comp}", seasonId=_season_id(comp, y),
                **{f"{W}-filter[type]": "field"})
    select = page.find("select", {"name": "competitionPart"})
    return tuple((o["value"], o.get_text(" ", strip=True)) for o in select.find_all("option") if o.get("value")) \
        if select else ()


def _phase_parts(comp: int, y: int, phase: str) -> list[tuple[str, str]]:
    want = phase_key(phase) == "playoffs"
    parts = [p for p in _parts(comp, y) if _is_playoff(p[1]) == want]
    if not parts:
        raise ValueError(f"no {phase_key(phase)} parts for competition {comp} in {y}-{y + 1} on ceskyhokej.cz")
    return parts


def _stage_name(part_name: str, y: int) -> str:
    """Drop the season the site appends to every part name."""
    return re.sub(rf"\s*{y}/{(y + 1) % 100:02d}\s*", " ", part_name).strip(" -–")


def _stats(comp: int, y: int, phase: str, kind: str) -> pd.DataFrame:
    frames = []
    for part_id, part_name in _phase_parts(comp, y, phase):
        rows, first = [], None
        for page_no in range(1, 100):
            page = soup(f"{BASE}/competition/player-stats/{comp}", seasonId=_season_id(comp, y), **{
                f"{W}-filter[type]": kind, f"{W}-filter[competitionPart]": part_id, f"{W}-page": page_no})
            batch = _rows(page)
            if not batch or batch[0]["player_id"] == first:
                break
            first = batch[0]["player_id"]
            rows += batch
            if len(batch) < PAGE_ROWS:
                break
        if rows:
            frames.append(pd.DataFrame(rows).assign(stage=_stage_name(part_name, y)))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _rows(page) -> list[dict]:
    table = page.find("table")
    if table is None or table.find("thead") is None:
        return []
    header = [h.get_text(" ", strip=True) for h in table.find("thead").find_all("th")]
    out = []
    for tr in (table.find("tbody") or table).find_all("tr"):
        link = tr.find("a", href=re.compile(r"/player/detail/\d+"))
        values = cells(tr)
        if link is None or len(values) != len(header):
            continue
        row = dict(zip(header, values))
        row["player_id"] = int(re.search(r"/player/detail/(\d+)", link["href"]).group(1))
        out.append(row)
    return out


def skaters(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _stats(opts["comp"], y, phase, "field")
    if df.empty:
        return df
    df["P"] = df["P"].map(_POSITION).fillna(df["P"])
    return finish(df, "skaters", league, y, phase_key(phase), drop=("#",), rename={
        "HRÁČ": "player", "P": "position", "TÝM": "team", "Z": "gp", "G": "g", "A": "a", "B": "pts",
        "TM": "pim", "+/-": "plus_minus"})


def goalies(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    df = _stats(opts["comp"], y, phase, "goalie")
    if df.empty:
        return df
    df["TOI"] = df["TOI"].map(_minutes)
    df = finish(df, "goalies", league, y, phase_key(phase), drop=("#", "P"), rename={
        "HRÁČ": "player", "TÝM": "team", "Z": "gp", "TOI": "toi", "OG": "ga", "OG/Z": "gaa", "ZÁS": "saves",
        "ZÁS %": "sv_pct", "ČK": "so"})
    # Lower leagues (2. liga) don't log saves: 0 saves against goals allowed means "not recorded".
    unrecorded = (df["saves"] == 0) & (df["ga"] > 0)
    df.loc[unrecorded, ["saves", "sv_pct"]] = pd.NA
    return df


def _minutes(clock: str):
    """'240:00' (minutes:seconds) -> 240.0."""
    m = re.fullmatch(r"\s*(\d+):(\d{2})\s*", str(clock))
    return round(int(m.group(1)) + int(m.group(2)) / 60, 2) if m else pd.NA


def standings(opts: dict, league: str, y: int, phase: str) -> pd.DataFrame:
    """One table per part, from the season's standings page (each table follows a
    heading naming its part)."""
    if phase_key(phase) != "regular":
        raise Unsupported("standings are regular season only (the play-offs are series)")
    comp = opts["comp"]
    wanted = {_stage_name(name, y) for _, name in _phase_parts(comp, y, phase)}
    page = soup(f"{BASE}/competition/standings/{comp}", seasonId=_season_id(comp, y))
    frames = []
    for table in page.find_all("table"):
        heading = table.find_previous(["h2", "h3", "h4"])
        stage = _stage_name(heading.get_text(" ", strip=True), y) if heading else ""
        if stage not in wanted:
            continue
        rows = [cells(tr) for tr in table.find_all("tr")]
        header, body = rows[0], [r for r in rows[1:] if len(r) == len(rows[0])]
        if body:
            frames.append(pd.DataFrame(body, columns=header).assign(stage=stage))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    score = df["SKÓRE"].str.extract(r"(\d+)\s*:\s*(\d+)")
    df["gf"], df["ga"] = score[0], score[1]
    df["#"] = df["#"].str.rstrip(".")
    return finish(df, "standings", league, y, "regular", drop=("SKÓRE",), rename={
        "#": "rank", "TÝM": "team", "Z": "gp", "v": "w", "V": "w", "VP": "otw", "PP": "otl", "P": "l", "R": "t", "r": "t", "B": "pts"})
