"""Hockey stats from the NHL API, NHL Edge, Elite Prospects and MoneyPuck,
returned as pandas DataFrames.

    import puckscrape as ps

    ps.nhl.skater_stats("2024-25")
    ps.edge.skater_summary(8478402, 2024)
    ps.eliteprospects.skaters(["ahl", "nhl"], ["2024-25", "2025-26"])
    ps.moneypuck.skaters(2024)

Progress is reported through the ``puckscrape`` logger; call
``logging.basicConfig(level=logging.INFO)`` to see it.
"""

from . import edge, eliteprospects, moneypuck, nhl
from ._http import BlockedError, PuckscrapeError

__all__ = ["nhl", "edge", "eliteprospects", "moneypuck", "BlockedError", "PuckscrapeError"]
__version__ = "0.1.0"
