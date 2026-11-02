"""Offline tests for ps.iihf (the IIHF archive's PDFs) and the new women's leagues' plumbing."""

import struct
from pathlib import Path

import pandas as pd
import pytest

import puckscrape as ps
from puckscrape import _pdftext, iihf
from puckscrape.leagues import chn, hockeytech

FIX = Path(__file__).parent / "fixtures"

INDEX_510 = """<html><head><title>2019 IIHF Ice Hockey Women's World Championship</title></head><body>
<a href="IHW510000_FINAL_RANKING_1_0.pdf">Final Ranking</a>
<a href="IHW5100USA_83_7_0_USA.pdf">USA</a></body></html>"""
INDEX_351 = """<html><head><title>2026 IIHF Ice Hockey World Championship Div III Group B</title></head><body>
<a href="IHM351000_FINAL_RANKING_1_0.pdf">Final Ranking</a></body></html>"""
INDEX_200 = """<html><head><title>2009 IIHF World Championship</title></head><body>
<a href="IHM2000AUT_83_8_0.pdf">AUT</a></body></html>"""
PDFS = {
    (510, "IHW5100USA_83_7_0_USA.pdf"): "iihf_510_usa_83.pdf",
    (510, "IHW510000_FINAL_RANKING_1_0.pdf"): "iihf_510_final_ranking.pdf",
    (351, "IHM351000_FINAL_RANKING_1_0.pdf"): "iihf_351_final_ranking.pdf",
    (200, "IHM2000AUT_83_8_0.pdf"): "iihf_200_aut_83.pdf",
}


@pytest.fixture
def archive(monkeypatch):
    pages = {510: INDEX_510, 351: INDEX_351, 200: INDEX_200}
    monkeypatch.setattr(iihf, "_index_page", lambda i: pages[i])
    monkeypatch.setattr(iihf, "_pdf", lambda i, name: (FIX / PDFS[(i, name)]).read_bytes())


def test_pdf_text_is_decoded():
    lines = [" ".join(s.text for s in line) for line in _pdftext.rows(_pdftext.spans((FIX / "iihf_510_usa_83.pdf").read_bytes())[0])]
    assert "PLAYER STATISTICS BY TEAM" in lines
    assert "USA - United States" in lines
    assert not any(_pdftext.UNKNOWN in line for line in lines)


def test_skaters_2019(archive):
    df = iihf.skaters(510)
    assert list(df.columns[:6]) == ["event_id", "event", "year", "gender", "tournament", "division"]
    knight = df[df["player"] == "Hilary Knight"].iloc[0]
    assert (knight["gp"], knight["g"], knight["a"], knight["pts"], knight["plus_minus"]) == (7, 7, 4, 11, 13)
    assert knight["team"] == "United States" and knight["team_code"] == "USA" and knight["gender"] == "women"
    assert knight["shots"] == 37 and knight["toi"] == "126:04"
    assert "Kendall Coyne Schofield" in set(df["player"])
    assert set(df["position"]) <= {"D", "F"}          # goalies are in goalies()
    assert len(df) == 20


def test_goalies_2019(archive):
    df = iihf.goalies(510)
    rigsby = df[df["player"] == "Alex Rigsby"].iloc[0]
    assert (rigsby["gp"], rigsby["ga"], rigsby["saves"], rigsby["so"], rigsby["w"], rigsby["l"]) == (5, 5, 101, 2, 4, 0)
    assert rigsby["sv_pct"] == pytest.approx(0.9528)
    assert rigsby["toi"] == pytest.approx(320.0)
    assert len(df) == 3


def test_skaters_2009_layout(archive):
    # 2009 reports write 'No Name Pos' without the periods.
    df = iihf.skaters(200)
    koch = df[df["player"] == "Thomas Koch"].iloc[0]
    assert (koch["gp"], koch["g"], koch["a"], koch["pts"], koch["plus_minus"]) == (6, 4, 3, 7, 2)
    assert df["team"].unique().tolist() == ["Austria"]


def test_standings_two_columns(archive):
    df = iihf.standings(510)
    group_b = df[df["group"] == "Preliminary Round Group B"]
    assert group_b["team_code"].tolist() == ["CZE", "GER", "JPN", "SWE", "FRA"]
    usa = df[(df["group"] == "Preliminary Round Group A") & (df["team_code"] == "USA")].iloc[0]
    assert (usa["gp"], usa["w"], usa["pts"], usa["gf"], usa["ga"], usa["goal_diff"]) == (4, 4, 12, 27, 4, 23)
    assert set(df["group"]) == {"Placement Round (9-10)", "Preliminary Round Group A", "Preliminary Round Group B"}


def test_final_ranking(archive):
    df = iihf.final_ranking(510)
    assert df["team_code"].tolist()[:3] == ["USA", "FIN", "CAN"]
    assert df["team"].iloc[0] == "United States" and len(df) == 10
    # A single round robin has only its standings; the ranking comes from them.
    rr = iihf.final_ranking(351)
    assert rr["team_code"].tolist() == ["UZB", "PRK", "HKG", "LUX", "MGL", "PHI"]
    assert iihf.standings(351)["group"].unique().tolist() == ["Round Robin"]


@pytest.mark.parametrize("title,expected", [
    ("2025 IIHF Ice Hockey Women's World Championship Div II Group A", ("women", "ww", "Div II Group A")),
    ("2019 IIHF Ice Hockey Women's World Championship", ("women", "ww", "Top")),
    ("2026 IIHF Ice Hockey World Championship Div III Group B", ("men", "wm", "Div III Group B")),
    ("2009 IIHF World Championship", ("men", "wm", "Top")),
    ("2020 IIHF Ice Hockey U20 World Championship Div I Group A", ("men", "wm20", "Div I Group A")),
    ("2012 IIHF Ice Hockey U18 Women's World Championship", ("women", "ww18", "Top")),
    ("2018 IIHF Ice Hockey U18 World Championship", ("men", "wm18", "Top")),
    ("2012 European Women Champions Cup Group F", ("women", "other", "Group F")),
    ("2018 IIHF Ice Hockey U18 Women's World Championship Div IBQ", ("women", "ww18", "Div IBQ")),
    ("2013 IIHF Ice Hockey World Championship Div IIIQ", ("men", "wm", "Div IIIQ")),
    ("2014 Women Tournament", ("women", "oly-w", "Top")),
    ("2022 Men's Tournament", ("men", "oly-m", "Top")),
    ("2023 IIHF Ice Hockey U18 Asia and Oceania Championship", ("men", "other", "Top")),
    ("2019 IIHF Ice Hockey Womenâ\x80\x99s Challenge Cup of Asia", ("women", "other", "Top")),
])
def test_classify(title, expected):
    c = iihf.classify(title)
    assert (c["gender"], c["tournament"], c["division"]) == expected
    assert c["year"] == int(title[:4])


def test_events_catalog():
    df = iihf.events()
    assert {"event_id", "year", "title", "gender", "tournament", "division", "teams"} <= set(df.columns)
    assert df["event_id"].is_unique
    top_ww_2019 = iihf.events(year=2019, tournament="ww")
    assert 510 in top_ww_2019["event_id"].tolist()
    assert set(iihf.events(gender="women")["gender"]) == {"women"}


def test_resolve(archive, monkeypatch):
    assert iihf._resolve(510, None, "Top") == [510]
    assert iihf._resolve([510, 351], None, "Top") == [510, 351]
    with pytest.raises(ValueError):
        iihf._resolve("nope", 2025, "Top")
    with pytest.raises(ValueError):
        iihf._resolve("ww", None, "Top")


def test_hyphen_by_shape():
    # A lone rectangle, wider than tall, at mid-height: the 2013-14 reports' bold hyphen,
    # which matches no outline in the glyph table.
    glyph = (struct.pack(">hhhhh", 1, 65, 391, 617, 672) + struct.pack(">HH", 3, 0) + bytes([1, 1, 1, 1])
             + struct.pack(">hhhh", 65, 0, 552, 0) + struct.pack(">hhhh", 391, 281, 0, -281))
    assert _pdftext._by_shape(glyph) == "-"
    tall = (struct.pack(">hhhhh", 1, 0, 0, 100, 1400) + struct.pack(">HH", 3, 0) + bytes([1, 1, 1, 1])
            + struct.pack(">hhhh", 0, 0, 100, 0) + struct.pack(">hhhh", 0, 1400, 0, -1400))
    assert _pdftext._by_shape(tall) == _pdftext.UNKNOWN


def test_names():
    assert iihf._split_name("COYNE SCHOFIELD Kendall") == ("Kendall", "COYNE SCHOFIELD")
    assert iihf._split_name("McKENNA Gavin") == ("Gavin", "McKENNA")
    assert iihf._display("Gavin", "McKENNA") == "Gavin McKenna"
    assert iihf._split_name("ST. LOUIS Martin") == ("Martin", "ST. LOUIS")
    assert iihf._display("Ryan", "O'REILLY") == "Ryan O'Reilly"
    assert iihf._display("Ryan", "MCDONAGH") == "Ryan McDonagh"


def test_new_leagues_registered():
    codes = set(ps.leagues.leagues()["code"])
    assert {"pwhl", "ncaa-w", "swhl", "naisten-mestis", "iihf-wm", "iihf-ww", "iihf-wm20", "iihf-wm18", "iihf-ww18"} <= codes
    with pytest.raises(ps.leagues.Unsupported):
        ps.leagues.skaters("iihf-ww", 2024, phase="playoffs")


def test_hockeytech_single_year_season(monkeypatch):
    # The PWHL's first season (January to May 2024) is named '2024 Regular Season'.
    seasons = pd.DataFrame({"season_id": ["5", "3", "1"], "season_name": [
        "2024-25 Regular Season", "2024 Playoffs", "2024 Regular Season"],
        "start_date": ["2024-11-25", "2024-05-06", "2024-01-01"]})
    monkeypatch.setattr(hockeytech, "seasons", lambda client, league_id=None: seasons)
    assert hockeytech.season_id("pwhl", 2024, "regular") == "5"
    assert hockeytech.season_id("pwhl", 2023, "regular") == "1"
    assert hockeytech.season_id("pwhl", 2023, "playoffs") == "3"


def test_chn_women_urls():
    assert chn._index_url({"women": True}).endswith("/women/stats.php")
    assert chn._index_url({}).endswith("/stats/index.php")
