"""Hockey stats from the NHL API, NHL Edge, Elite Prospects, MoneyPuck and ESPN,
returned as pandas DataFrames.

    import puckscrape as ps

    ps.nhl.skater_stats("2024-25")
    ps.edge.skater_summary(8478402, 2024)
    ps.eliteprospects.skaters(["ahl", "nhl"], ["2024-25", "2025-26"])
    ps.moneypuck.skaters(2024)
    ps.espn.standings(2024)
    ps.leagues.skaters("ohl", "2025-26")          # league and federation websites
    ps.hockeydb.skaters("khl", "2024-25")         # HockeyDB rosters, any league
    ps.eliteprospects.draft_rankings("all")       # NHL draft rankings
    ps.tsn.draft_ranking(ps.tsn.draft_ranking_articles())
    ps.tsn.mckenzie_ranking(2025, "final")        # Bob McKenzie's lists
    ps.nhl.draft_rankings(2025)                   # NHL Central Scouting

Progress is reported through the ``puckscrape`` logger; call
``logging.basicConfig(level=logging.INFO)`` to see it.
"""

from . import edge, eliteprospects, espn, hockeydb, leagues, moneypuck, nhl, tsn
from ._http import BlockedError, PuckscrapeError

__all__ = ["nhl", "edge", "eliteprospects", "moneypuck", "espn", "leagues", "hockeydb", "tsn",
           "BlockedError", "PuckscrapeError"]
__version__ = "0.1.0"
