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


def test_eliteprospects_draft_rankings():
    df = ps.eliteprospects.draft_rankings("eliteprospects-com")
    assert len(df) >= 32 and df["rank"].tolist() == list(range(1, len(df) + 1))


def test_tsn_draft_ranking():
    url = "https://www.tsn.ca/nhl/article/dupont-opens-the-season-at-no-1-on-craigs-list/"
    df = ps.tsn.draft_ranking(url)
    assert len(df) == 32 and df["player"].iloc[0] == "Landon DuPont" and (df["draft_year"] == 2027).all()


def test_nhl_central_scouting():
    df = ps.nhl.draft_rankings(2025)
    assert df["category"].nunique() == 4 and len(df) > 400
    top = df[(df["category"] == "north-american-skater") & (df["final_rank"] == 1)]
    assert top["name"].tolist() == ["Matthew Schaefer"]


def test_mckenzie_ranking():
    df = ps.tsn.mckenzie_ranking(2025, "final")
    assert df["rank"].max() == 80 and (df["rank_note"] == "HM").sum() == 20
    assert df.loc[df["rank"] == 1, "player"].tolist() == ["Matthew Schaefer"]


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


# ---- league and federation websites (one league per platform) --------------

@pytest.mark.parametrize("league,min_rows", [
    ("ohl", 500), ("shl", 300), ("hockeyallsvenskan", 300), ("liiga", 400), ("mestis", 250),
    ("nl", 300), ("del", 300), ("del2", 300), ("extraliga", 300), ("icehl", 300), ("eihl", 200),
    ("metal-ligaen", 200),
])
def test_league_skaters(league, min_rows):
    df = ps.leagues.skaters(league, "2025-26")
    assert len(df) >= min_rows
    assert {"player", "team", "gp", "g", "a", "pts"} <= set(df.columns)
    assert df["pts"].max() > 30


def test_league_goalies_save_pct_is_a_fraction():
    df = ps.leagues.goalies(["whl", "del", "mestis"], "2025-26")
    assert df["sv_pct"].dropna().between(0, 1).all()
