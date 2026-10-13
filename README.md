# puckscrape

Hockey stats from the NHL API, NHL Edge, Elite Prospects, MoneyPuck and ESPN, as pandas DataFrames.

```python
import puckscrape as ps

ps.nhl.skater_stats("2024-25")                          # every NHL skater, stats.nhl.com summary report
ps.edge.skater_summary([8478402, 8479318], 2024)        # Edge tracking: speed, shot speed, zone time
ps.eliteprospects.skaters(["ahl", "ohl"], "2024-25")    # any EP league
ps.moneypuck.skaters(2024)                              # xG, Corsi, game score
ps.espn.standings(2024)                                 # ESPN standings, box scores, injuries
```

Seasons can be written any way: `2024`, `"2024-25"`, `"2024-2025"` or `"20242025"`.
A bare year is the season that **starts** that year, so `2024` means 2024-25.

## Install

```
uv add ../puckscrape            # or: pip install -e ../puckscrape
pip install -e "../puckscrape[tdh]"   # adds full play-by-play via TopDownHockey
```

## What's in it

| Module | Functions |
|---|---|
| `nhl` | `schedule`, `team_schedule`, `boxscore`, `play_by_play`, `shifts`, `full_play_by_play`*, `roster`, `player_info`, `game_log`, `standings`, `skater_stats`, `goalie_stats`, `team_stats`, `teams` |
| `edge` | `skater_summary`, `skater_shot_locations`, `skater_zone_time`, `skater_top_speeds`, `skater_hardest_shots`, `skater_distance`, `goalie_summary`, `goalie_shot_locations`, `goalie_save_pct_last10`, `team_summary`, `team_zone_time`, `team_top_speeds`, `raw` |
| `eliteprospects` | `skaters`, `goalies`, `player_info`, `add_player_info` |
| `moneypuck` | `skaters`, `goalies`, `teams`, `lines`, `shots` |
| `espn` | `scoreboard`, `schedule`, `team_schedule`, `boxscore`, `play_by_play`, `standings`, `teams`, `roster`, `player_stats`, `game_log`, `injuries`, `add_nhl_ids`, `player_ids`, `game_ids`, `team_ids` |

\* `full_play_by_play` wraps Patrick Bacon's TopDownHockey `full_scrape` (play-by-play with every on-ice player) and needs the `tdh` extra.

`nhl.skater_stats` / `goalie_stats` / `team_stats` take any stats.nhl.com report name:
`ps.nhl.skater_stats(2024, report="realtime")`, `report="timeonice"`, `report="bios"`, ...

`edge.raw(endpoint, id, season)` returns the untouched JSON for any Edge endpoint not wrapped here.

ESPN uses its own player, team and game IDs, not the NHL's. `espn.add_nhl_ids` adds the NHL ones
next to them, so ESPN data joins onto everything from `nhl`, `edge` and `moneypuck`:

```python
box = ps.espn.add_nhl_ids(ps.espn.boxscore(401688578), 2024)   # + nhl_game_id, nhl_player_id, nhl_team_id
pbp = ps.espn.add_nhl_ids(ps.espn.play_by_play(401688578), 2024)  # + nhl_player1_id, nhl_player2_id, ...
```

ESPN publishes no NHL IDs, so they're matched: teams by abbreviation, games by matchup and start
time, players by name, team and games played. For 2024-25 and 2022-23 every game and all but one
player matched. Postponed games have no NHL ID, because the NHL keeps only the replayed game.
The crosswalks themselves are `espn.player_ids(season)`, `espn.game_ids(season)` and
`espn.team_ids()`. The first call for a season makes about 60 requests (the game schedules);
after that the crosswalks are cached for the session.

ESPN's `roster` is current-season only, and `injuries` is today's injury report.

## Being polite

Every request goes through one throttled session (`puckscrape/_http.py`): 1.5 s between
Elite Prospects requests, 1 s for MoneyPuck, 0.25 s for ESPN, 0.1 s for the NHL. 403/429/5xx are retried
with exponential backoff, and Elite Prospects pages that come back empty are retried
because EP sometimes soft-blocks instead of returning 403.

Long Elite Prospects scrapes can be stopped with Ctrl-C, which returns everything scraped so far.

To see progress:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Tests

```
uv run pytest -m "not live"   # offline parser tests
uv run pytest -m live         # hits the real sites
```
