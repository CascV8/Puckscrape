"""Offline tests for the league-website helpers (no network)."""

import pandas as pd
import pytest

import puckscrape as ps
from puckscrape.leagues import _common, ceskyhokej, chn, delhockey, hockeytech, khl


def test_registry_is_consistent():
    df = ps.leagues.leagues()
    assert df["code"].is_unique
    for lg in ps.leagues.LEAGUES.values():
        for kind in ("skaters", "goalies", "standings"):
            assert callable(getattr(lg.adapter, kind))


def test_unknown_league():
    with pytest.raises(ValueError):
        ps.leagues.skaters("nope", 2025)


def test_to_numbers():
    df = pd.DataFrame({"a": ["1", "2", "-"], "pct": ["95,0", "100", "92,5"], "pm": ["+4", "-5", "– *"],
                       "toi": ["20:14", "18:02", "19:00"], "name": ["A", "B", "C"]})
    out = _common.to_numbers(df)
    assert out["a"].tolist()[:2] == [1, 2] and pd.isna(out["a"].iloc[2])
    assert out["pct"].tolist() == [95.0, 100.0, 92.5]
    assert out["pm"].tolist()[:2] == [4, -5] and pd.isna(out["pm"].iloc[2])
    assert out["toi"].dtype == object or pd.api.types.is_string_dtype(out["toi"])
    assert out["name"].tolist() == ["A", "B", "C"]


def test_finish_core_columns_and_save_pct():
    raw = pd.DataFrame({"Name": ["X"], "GP": ["10"], "SV%": ["92.3"], "Extra stat": ["7"]})
    df = _common.finish(raw, "goalies", "test", 2025, "regular", rename={"Name": "player", "GP": "gp", "SV%": "sv_pct"})
    assert list(df.columns[:5]) == ["league", "season", "phase", "player", "gp"]
    assert df["season"].iloc[0] == "2025-26"
    assert df["sv_pct"].iloc[0] == pytest.approx(0.923)
    assert "extra_stat" in df.columns


@pytest.mark.parametrize("raw,clean", [
    ("1 c - \n   Belfast Giants", "Belfast Giants"),
    ("Krefeld Pinguine KEV ✓ *", "Krefeld Pinguine KEV"),
    ("xyz - Brantford Bulldogs", "Brantford Bulldogs"),
    ("Frölunda HC", "Frölunda HC"),
])
def test_clean_team(raw, clean):
    assert _common.clean_team(raw) == clean


def test_name_flips():
    assert hockeytech._first_last("Massé, Maxim") == "Maxim Massé"
    assert hockeytech._first_last("Cole Beaudoin") == "Cole Beaudoin"
    assert delhockey._flip("Barratt, Evan") == "Evan Barratt"
    assert chn._split_name("Jack Beck, F, So", goalie=False) == ("Jack Beck", "F", "So")
    assert chn._split_name("Samuel Urban, So", goalie=True) == ("Samuel Urban", "G", "So")


def test_hockeytech_season_names(monkeypatch):
    seasons = pd.DataFrame({"season_id": ["10", "11", "12", "13", "14"], "season_name": [
        "2026 - 27 Regular Season", "2026 Playoffs", "2025-26 | Regular Season",
        "2025-26 OHL Top Prospects", "Pre-Season 2025"]})
    monkeypatch.setattr(hockeytech, "seasons", lambda client, league_id=None: seasons)
    assert hockeytech.season_id("x", 2026, "regular") == "10"
    assert hockeytech.season_id("x", 2025, "regular") == "12"
    assert hockeytech.season_id("x", 2025, "playoffs") == "11"
    with pytest.raises(ValueError):
        hockeytech.season_id("x", 2019, "regular")


def test_hockeytech_league_regular_pattern(monkeypatch):
    # The GOHL calls its season "2025-2026 GOHL Season"; the CSSHL's U18 Prep "2025-26 U18 Prep",
    # which the pre-season skip must not catch.
    seasons = pd.DataFrame({"season_id": ["1", "2", "3", "4"], "season_name": [
        "2025-2026 Special Events", "2025-2026 GOHL Season", "2026 GOHL Pre-Season", "2025-26 U18 Prep"]})
    monkeypatch.setattr(hockeytech, "seasons", lambda client, league_id=None: seasons)
    assert hockeytech.season_id("gojhl", 2025, "regular", r"\bgo(j)?hl season$") == "2"
    assert hockeytech.season_id("csshl", 2025, "regular", r"^\d{4}-\d{2} u18 prep$") == "4"
    with pytest.raises(ValueError):   # without its pattern, a league's own name isn't a regular season
        hockeytech.season_id("gojhl", 2025, "regular")


@pytest.mark.parametrize("part,playoff", [
    ("Extraliga dorostu - Play-off o titul Mistr České republiky 2025/26", True),
    ("Extraliga dorostu - Předkolo play-off 2025/26", True),
    ("Extraliga žen - O titul Mistr České republiky 2025/26", True),
    ("Extraliga žen - finále 2019/20", True),
    ("2. liga - Play-off 2025/26", True),
    ('Tipsport extraliga - Generali play-off o titul "Mistr České republiky" 2019/20', True),
    ("Extraliga dorostu - O pořadí v play-off 2025/26", False),
    ("Extraliga dorostu - O účast v play-off 2025/26", False),
    ("CHANCE LIGA - o účast v předkole play-off 2019/20", False),
    ("Extraliga dorostu - Play-down 2022/23", False),
    ("Tipsport extraliga - o udržení, resp. o postup do Tipsport ELH 2025/26", False),
    ("Extraliga dorostu - sk. A 2024/25", False),
])
def test_czech_playoff_parts(part, playoff):
    assert ceskyhokej._is_playoff(part) is playoff


def test_czech_stage_name_and_minutes():
    assert ceskyhokej._stage_name("Extraliga dorostu - sk. A 2024/25", 2024) == "Extraliga dorostu - sk. A"
    assert ceskyhokej._stage_name("DHL extraliga juniorů 2024/25 - O udržení", 2024) == "DHL extraliga juniorů - O udržení"
    assert ceskyhokej._minutes("240:00") == 240.0 and ceskyhokej._minutes("01:48") == 1.8


def test_khl_names_and_standings(monkeypatch):
    assert khl._first_last("Kaprizov Kirill") == "Kirill Kaprizov"
    assert khl._first_last("Alexeyev Denis V.") == "Denis V. Alexeyev"
    assert khl._first_last("Belozyorov Andrei Al.") == "Andrei Al. Belozyorov"
    assert khl._first_last("Da Costa Stephane") == "Stephane Da Costa"
    monkeypatch.setattr(khl, "_stage", lambda app, y, phase: {"id": 1, "season": "2025/2026"})
    monkeypatch.setattr(khl, "_stage_teams", lambda app, stage_id: frozenset({1, 2}))
    ids = {"A": 1, "B": 2, "Stars": 99}
    def game(a, b, score, ot=None, so=None):
        return {"team_a": {"name": a, "id": ids[a]}, "team_b": {"name": b, "id": ids[b]}, "score": score,
                "scores": {"overtime": ot, "bullitt": so}}
    monkeypatch.setattr(khl, "_games", lambda app, stage_id: [
        game("A", "B", "3:1"), game("A", "B", "2:3", ot="0:1"), game("B", "A", "4:3", so="1:0"),
        game("Stars", "A", "9:1")])
    st = khl.standings({"app": "khl_mobile"}, "khl", 2025, "regular").set_index("team")
    assert st.loc["A", ["gp", "w", "otl", "sol", "pts", "gf", "ga"]].tolist() == [3, 1, 1, 1, 4, 8, 8]
    assert st.loc["B", ["w", "otw", "sow", "l", "pts"]].tolist() == [0, 1, 1, 1, 4]


def test_vhl_from_hockeydb_splits_phases_with_one_scrape(monkeypatch):
    from puckscrape.leagues import hockeydb as hdb
    calls = []
    def fake(league, y):
        calls.append((league, y))
        return pd.DataFrame({"league": ["vhl"] * 2, "season": ["2024-25"] * 2, "pid": [1, 2], "player": ["A", "B"],
                             "team": ["T", "T"], "pos": ["F", "G"], "gp": [10, 5], "g": [3, 0], "a": [4, 0],
                             "pts": [7, 0], "pim": [2, 0], "plus_minus": [1, 0], "po_gp": [2, 0], "po_g": [1, 0],
                             "po_a": [0, 0], "po_pts": [1, 0], "po_pim": [0, 0], "birthplace": ["", ""], "age": [20, 25]})
    monkeypatch.setattr(hdb.hockeydb, "skaters", fake)
    hdb._rosters.cache_clear()
    reg = hdb.skaters({"hockeydb": "vhl"}, "vhl", 2024, "regular")
    po = hdb.skaters({"hockeydb": "vhl"}, "vhl", 2024, "playoffs")
    assert reg["pts"].tolist() == [7, 0] and reg["player_id"].tolist() == [1, 2]
    assert po["player"].tolist() == ["A"] and po["pts"].tolist() == [1] and "plus_minus" not in po
    assert calls == [("vhl", 2024)]
    hdb._rosters.cache_clear()


def test_phase_key():
    assert _common.phase_key("Regular") == "regular"
    assert _common.phase_key("playoffs") == "playoffs"
    with pytest.raises(ValueError):
        _common.phase_key("preseason")
