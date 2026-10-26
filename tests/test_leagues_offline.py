"""Offline tests for the league-website helpers (no network)."""

import pandas as pd
import pytest

import puckscrape as ps
from puckscrape.leagues import _common, chn, delhockey, hockeytech


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


def test_phase_key():
    assert _common.phase_key("Regular") == "regular"
    assert _common.phase_key("playoffs") == "playoffs"
    with pytest.raises(ValueError):
        _common.phase_key("preseason")
