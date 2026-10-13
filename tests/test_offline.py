"""Parser tests against saved responses -- no network."""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from puckscrape import _util, edge, eliteprospects as ep, nhl

FIXTURES = Path(__file__).parent / "fixtures"


def soup(name):
    return BeautifulSoup((FIXTURES / name).read_bytes(), "html.parser")


@pytest.mark.parametrize("raw", [2024, "2024", "2024-25", "2024-2025", "20242025"])
def test_season_spellings(raw):
    assert _util.start_year(raw) == 2024
    assert _util.nhl_season(raw) == "20242025"
    assert _util.ep_season(raw) == "2024-2025"


@pytest.mark.parametrize("bad", ["2024-26", "24-25", "season"])
def test_bad_seasons(bad):
    with pytest.raises(ValueError):
        _util.start_year(bad)


def test_snake():
    assert _util.snake("shootingPctgPercentile") == "shooting_pctg_percentile"
    assert _util.snake("burstsOver20") == "bursts_over20"


# ---- Elite Prospects -----------------------------------------------------

def test_ep_skater_json():
    block = ep._stats_block(soup("ep_skaters_page.html"), "skater")
    assert block["pageInfo"]["hasNextPage"] is True
    rows = ep.parse_stats_json(block, "skater")
    assert len(rows) > 90
    top = rows[0]
    assert top["player"] == "Andrew Poturalski"
    assert top["position"] == "C/RW"
    assert (top["gp"], top["g"], top["a"], top["tp"]) == (59, 30, 43, 73)
    assert top["ppg"] == pytest.approx(1.24)
    assert top["link"].startswith("https://www.eliteprospects.com/player/")


def test_ep_goalie_json_types():
    block = ep._stats_block(soup("ep_goalies_page.html"), "goalie")
    rows = ep.parse_stats_json(block, "goalie")
    g = next(r for r in rows if r["gp"] and r["gp"] > 10)
    assert isinstance(g["sv_pct"], float) and 0.8 < g["sv_pct"] < 1
    assert isinstance(g["gaa"], float)
    assert isinstance(g["toi"], int)


def test_ep_postseason_skips_players_without_playoffs():
    block = ep._stats_block(soup("ep_goalies_page.html"), "goalie")
    assert len(ep.parse_stats_json(block, "goalie", "postseason")) < len(ep.parse_stats_json(block, "goalie"))


def test_ep_table_fallback_matches_json():
    s = soup("ep_skaters_page.html")
    table = ep._find_stats_table(s, "skater")
    assert table is not None and ep._find_stats_table(s, "goalie") is None
    rows = ep.parse_stats_table(table)
    assert rows[0]["team"] == "San Jose Barracuda"
    assert rows[0]["tp"] == "73"
    assert rows[0]["link"].endswith("/player/109632/andrew-poturalski")


def test_ep_player_page_parse():
    payload = {"props": {"pageProps": {"playerData": {
        "player": {"id": "1", "name": "Test Guy", "dateOfBirth": "2005-01-01",
                   "height": {"metrics": 185}, "weight": {"metrics": 88},
                   "nationality": {"name": "Sweden"}, "shoots": "L",
                   "nhlRights": {"team": {"name": "Detroit Red Wings"}, "rights": "Signed"}},
        "playerDraftSelections": {"edges": [{"year": 2023, "round": 1, "overall": 9, "teamName": "Detroit Red Wings"}]},
    }}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'
    row = ep.parse_player_page(BeautifulSoup(html, "html.parser"), "x")
    assert row["player"] == "Test Guy" and row["nation"] == "Sweden"
    assert row["nhl_rights"] == "Detroit Red Wings" and row["rights_status"] == "Signed"
    assert (row["draft_year"], row["draft_overall"]) == (2023, 9)


# ---- NHL / Edge ----------------------------------------------------------

def test_play_by_play(monkeypatch):
    data = json.loads((FIXTURES / "pbp_2024020001.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(nhl._http, "get_json", lambda *a, **k: data)
    df = nhl.play_by_play(2024020001)
    assert {"event_type", "period", "game_seconds", "event_team", "shooting_player_name"} <= set(df.columns)
    assert not df.columns.duplicated().any()
    assert (df["home_team"] == "BUF").all() and (df["away_team"] == "NJD").all()
    goals = df[df["event_type"] == "goal"]
    assert len(goals) == data["awayTeam"]["score"] + data["homeTeam"]["score"]
    assert goals["scoring_player_name"].notna().all()
    assert df["game_seconds"].is_monotonic_increasing


def test_edge_flatten_drops_noise():
    data = json.loads((FIXTURES / "edge_skater_detail.json").read_text(encoding="utf-8"))
    flat = edge._flatten(data)
    assert flat["player_last_name"] == "McDavid"
    assert flat["skating_speed_speed_max_imperial"] == pytest.approx(23.969)
    assert not any("overlay" in k or "logo" in k for k in flat)
