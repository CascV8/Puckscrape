"""IIHF tournaments as ps.leagues entries (the top division; see ps.iihf for everything else).

Season 2024-25 is the tournament named 2025: the Worlds in May, the World Juniors
from December 2024, the Olympics in February. Totals are whole-tournament.
"""

from __future__ import annotations

import pandas as pd

from ._common import Unsupported, finish, phase_key


class Tournament:
    def __init__(self, code: str):
        self.code = code

    def _run(self, kind: str, league: str, y: int, phase: str) -> pd.DataFrame:
        from .. import iihf   # imported here: ps.iihf itself imports from ps.leagues
        if phase_key(phase) != "regular":
            raise Unsupported("IIHF tournaments have whole-tournament totals only; use phase='regular'")
        df = getattr(iihf, kind)(self.code, y + 1)
        if df.empty:
            return df
        if kind == "standings":
            df = df.rename(columns={"team_code": "team"})
        return finish(df.drop(columns=["year"]), kind, league, y, "tournament")

    def skaters(self, opts, league, y, phase):
        return self._run("skaters", league, y, phase)

    def goalies(self, opts, league, y, phase):
        return self._run("goalies", league, y, phase)

    def standings(self, opts, league, y, phase):
        return self._run("standings", league, y, phase)
