"""Smoke tests against the real sites. Run with ``pytest -m live``."""

import pytest

import puckscrape as ps

pytestmark = pytest.mark.live


def test_nhl_skater_stats():
    df = ps.nhl.skater_stats("2024-25")
    assert len(df) > 800 and "skater_full_name" in df


def test_nhl_shifts():
    df = ps.nhl.shifts(2024020001)
    assert len(df) > 500 and df["duration_seconds"].gt(0).all()


def test_edge_skater_summary():
    df = ps.edge.skater_summary([8478402, 8479318], 2024)
    assert len(df) == 2 and "top_shot_speed_imperial" in df


def test_moneypuck_skaters():
    df = ps.moneypuck.skaters(2024)
    assert len(df) > 800 and (df["situation"] == "all").all()


def test_eliteprospects_goalies():
    df = ps.eliteprospects.goalies("ahl", "2024-25")
    assert len(df) > 50 and df["gp"].gt(0).all()


def test_espn_standings():
    df = ps.espn.standings(2024)
    assert len(df) == 32 and df["points"].max() > 100


def test_espn_boxscore():
    df = ps.espn.boxscore(401688578)
    assert len(df) > 30 and df["goals"].sum() == 7


def test_espn_add_nhl_ids():
    df = ps.espn.add_nhl_ids(ps.espn.boxscore(401688578), 2024)
    assert (df["nhl_game_id"] == 2024020979).all()
    assert df["nhl_player_id"].notna().all() and set(df["nhl_team_id"]) == {1, 25}
