"""Parser tests against saved responses -- no network."""

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from puckscrape import _util, edge, eliteprospects as ep, espn, nhl

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


# ---- ESPN ----------------------------------------------------------------

def espn_fixture(name):
    return json.loads((FIXTURES / f"espn_{name}.json").read_text(encoding="utf-8"))


def fake_espn(monkeypatch, name):
    data = espn_fixture(name)
    monkeypatch.setattr(espn._http, "get_json", lambda *a, **k: data)


def test_espn_season_is_end_year():
    assert espn.espn_season("2024-25") == espn.espn_season(2024) == 2025


def test_espn_scoreboard_and_schedule_shapes(monkeypatch):
    # The scoreboard sends scores as strings, team schedules as {"value": ...} dicts.
    fake_espn(monkeypatch, "scoreboard")
    sb = espn.scoreboard("2025-04-15")
    g = sb[sb["game_id"] == 401688890].iloc[0]
    assert (g["away_team"], g["home_team"], g["home_score"]) == ("NJ", "BOS", 4)
    assert g["status"] == "Final/OT" and g["completed"]

    fake_espn(monkeypatch, "team_schedule")
    ts = espn.team_schedule("det", 2024)
    assert len(ts) == 3 and ts["home_score"].notna().all() and (ts["season"] == 2025).all()


def test_espn_standings():
    rows = espn.parse_standings(espn_fixture("standings"))
    assert len(rows) == 32
    assert {r["division"] for r in rows} == {"Atlantic Division", "Metropolitan Division",
                                             "Central Division", "Pacific Division"}
    wsh = next(r for r in rows if r["abbreviation"] == "WSH")
    assert (wsh["wins"], wsh["points"], wsh["clincher"], wsh["home"]) == (51, 111, "z", "26-9-6")


def test_espn_boxscore_and_plays():
    summary = espn_fixture("summary_401688578")
    box = espn.parse_boxscore(summary, 401688578)
    groups = {r["group"] for r in box}
    assert {"forwards", "defenses", "goalies"} <= groups
    bastian = next(r for r in box if r["player"] == "Nathan Bastian")
    assert bastian["time_on_ice"] == "10:04" and bastian["shifts"] == "17"
    goalie = next(r for r in box if r["group"] == "goalies")
    assert "saves" in goalie and "hits" not in goalie

    plays = espn.parse_plays(summary, 401688578)
    goals = [p for p in plays if p["event"] == "Goal"]
    assert len(goals) == 7
    assert goals[0]["player1"] == "Wyatt Johnston" and goals[0]["player1_role"] == "scorer"
    assert (goals[0]["x"], goals[0]["y"]) == (-72, 7)


def test_espn_play_by_play_clock_is_elapsed(monkeypatch):
    fake_espn(monkeypatch, "summary_401688578")
    df = espn.play_by_play(401688578)
    ends = df[df["event"] == "Period End"]
    assert (ends["period_seconds"] == 1200).all()


def test_espn_player_stats():
    rows = espn.parse_player_stats(espn_fixture("byathlete"))  # 2024-25 playoffs
    leon = next(r for r in rows if r["player"] == "Leon Draisaitl")
    assert (leon["goals"], leon["points"], leon["team"]) == (11, 33, "EDM")
    assert "save_pct" in leon


def test_espn_game_log():
    rows = espn.parse_game_log(espn_fixture("gamelog"), 3114727)
    assert len(rows) == 93 and len({r["game_id"] for r in rows}) == 93
    assert {r["season_type"] for r in rows} == {"2024-25 Regular Season", "2024-25 Postseason"}
    assert all("goals" in r and "time_on_ice_per_game" in r for r in rows)


def test_espn_roster_and_injuries():
    roster = espn.parse_roster(espn_fixture("roster"))
    assert roster and all(r["team"] == "DET" and r["player_id"] for r in roster)
    injuries = espn.parse_injuries(espn_fixture("injuries"))
    assert injuries and all(r["player_id"] and r["status"] for r in injuries)
