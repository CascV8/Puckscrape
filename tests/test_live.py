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
    df = ps.leagues.goalies(["whl", "del", "mestis", "liiga", "czech-u18"], "2025-26")
    assert df["sv_pct"].dropna().between(0, 1).all()
    assert set(df["league"]) == {"whl", "del", "mestis", "liiga", "czech-u18"}


# ---- Russia and Czech youth --------------------------------------------------

def test_khl_from_the_app_feed():
    sk = ps.leagues.skaters("khl", "2024-25")          # ~60 pages: a few minutes
    assert len(sk) > 600 and sk["pts"].max() > 60 and sk["team"].notna().mean() > 0.98
    gk = ps.leagues.goalies("khl", "2024-25")           # same pages, cached
    assert gk["sv_pct"].dropna().between(0, 1).all() and len(gk) > 40
    st = ps.leagues.standings("khl", "2024-25")
    assert len(st) == 23 and (st["gp"] == 68).all()


@pytest.mark.parametrize("league,min_rows", [
    ("u18-nationell", 500), ("u18-elit", 350), ("czech-u18", 800), ("u18-sm-sarja", 300),
])
def test_european_u18_leagues(league, min_rows):
    sk = ps.leagues.skaters(league, "2025-26")
    gk = ps.leagues.goalies(league, "2025-26")
    assert len(sk) >= min_rows and sk["pts"].max() > 30 and len(gk) > 20


def test_czech_youth_stages():
    df = ps.leagues.skaters("czech-u18", "2025-26")
    assert df["stage"].nunique() >= 3 and len(df) > 800
    po = ps.leagues.skaters("czech-u18", "2025-26", phase="playoffs")
    assert po["stage"].str.contains("Play-off o titul").any()
    assert not set(df["stage"]) & set(po["stage"])


# ---- women's leagues and IIHF tournaments ----------------------------------

@pytest.mark.parametrize("league,season,min_rows", [
    ("pwhl", "2025-26", 150), ("pwhl", "2023-24", 100), ("swhl", "2025-26", 150),
    ("naisten-mestis", "2025-26", 200),
])
def test_womens_league_skaters(league, season, min_rows):
    df = ps.leagues.skaters(league, season)
    assert len(df) >= min_rows and df["pts"].max() > 20


def test_iihf_womens_worlds():
    df = ps.iihf.skaters("ww", 2025)
    assert df["team_code"].nunique() == 10 and (df["gender"] == "women").all()
    poulin = df[df["player"] == "Marie-Philip Poulin"].iloc[0]
    assert (poulin["g"], poulin["a"], poulin["pts"]) == (4, 8, 12)
    assert not df["player"].str.contains("�").any()


def test_iihf_mens_worlds_ranking_and_goalies():
    assert ps.iihf.final_ranking("wm", 2025)["team_code"].iloc[0] == "USA"
    df = ps.iihf.goalies("wm", 2025)
    assert df["sv_pct"].dropna().between(0, 1).all() and len(df) > 30


def test_iihf_as_a_league():
    df = ps.leagues.skaters("iihf-wm20", "2025-26")   # the 2026 World Juniors
    assert len(df) > 200 and (df["phase"] == "tournament").all()
