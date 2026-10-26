# puckscrape

Hockey stats from the NHL API, NHL Edge, Elite Prospects, MoneyPuck, ESPN, HockeyDB and league/federation websites
(NCAA, the CHL, the AHL/ECHL, junior A leagues, and leagues across Europe), as pandas DataFrames.

```python
import puckscrape as ps

ps.nhl.skater_stats("2024-25")                          # every NHL skater, stats.nhl.com summary report
ps.edge.skater_summary([8478402, 8479318], 2024)        # Edge tracking: speed, shot speed, zone time
ps.eliteprospects.skaters(["ahl", "ohl"], "2024-25")    # any EP league
ps.moneypuck.skaters(2024)                              # xG, Corsi, game score
ps.espn.standings(2024)                                 # ESPN standings, box scores, injuries
ps.leagues.skaters(["ohl", "shl", "ncaa"], "2025-26")    # straight from league websites
ps.hockeydb.skaters("khl", "2024-25")                   # HockeyDB rosters, any league
```

Seasons can be written any way: `2024`, `"2024-25"`, `"2024-2025"` or `"20242025"`.
A bare year is the season that **starts** that year, so `2024` means 2024-25.

## Install

```
uv add git+https://github.com/CascV8/Puckscrape.git      # or: pip install git+https://github.com/CascV8/Puckscrape.git
pip install "puckscrape[tdh] @ git+https://github.com/CascV8/Puckscrape.git"   # adds nhl.full_play_by_play
```

## What's in it

| Module | Functions |
|---|---|
| `nhl` | `schedule`, `team_schedule`, `boxscore`, `play_by_play`, `shifts`, `full_play_by_play`*, `roster`, `player_info`, `game_log`, `standings`, `skater_stats`, `goalie_stats`, `team_stats`, `teams` |
| `edge` | `skater_summary`, `skater_shot_locations`, `skater_zone_time`, `skater_top_speeds`, `skater_hardest_shots`, `skater_distance`, `goalie_summary`, `goalie_shot_locations`, `goalie_save_pct_last10`, `team_summary`, `team_zone_time`, `team_top_speeds`, `raw` |
| `eliteprospects` | `skaters`, `goalies`, `player_info`, `add_player_info` |
| `moneypuck` | `skaters`, `goalies`, `teams`, `lines`, `shots` |
| `leagues` | `leagues`, `skaters`, `goalies`, `standings` |
| `hockeydb` | `leagues`, `seasons`, `skaters` |
| `espn` | `scoreboard`, `schedule`, `team_schedule`, `boxscore`, `play_by_play`, `standings`, `teams`, `roster`, `player_stats`, `game_log`, `injuries`, `add_nhl_ids`, `player_ids`, `game_ids`, `team_ids` |

\* `full_play_by_play` (play-by-play with every on-ice player) needs the `tdh` extra.

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

## League and federation websites (`ps.leagues`)

Stats taken directly from each league's or federation's own site, for leagues the NHL and ESPN
don't cover. Every table starts with the same core columns (`league, season, phase, player, team,
gp, g, a, pts, pim, plus_minus`; goalies `gp, w, l, ga, saves, sv_pct, gaa, so, toi`), followed by
whatever else that site publishes (TOI, shots, faceoffs, bios, xG...). Save percentage is always a
fraction (0.915).

```python
ps.leagues.leagues()                                      # coverage table
ps.leagues.skaters("whl", "2025-26")
ps.leagues.goalies(["del", "del2"], 2025, phase="playoffs")
ps.leagues.standings("mestis", 2025)
```

| Code | League | Source | Notes |
|---|---|---|---|
| `ncaa` | NCAA Division I (men) | collegehockeynews.com | ~64 requests a season; whole-season totals; standings are team stats (no W-L) |
| `ohl`, `whl`, `qmjhl` | CHL | HockeyTech feed behind chl.ca | full history; playoffs too |
| `ahl`, `echl` | AHL, ECHL | HockeyTech (theahl.com, echl.com) | full history; playoffs too |
| `ushl`, `bchl`, `ajhl`, `sjhl`, `mjhl`, `ojhl`, `cchl`, `mjahl`, `kijhl`, `vijhl` | US/Canadian junior | HockeyTech (each league's site key) | `mjahl` is the Maritime Junior Hockey League |
| `shl`, `sdhl` | SHL, SDHL (women) | shl.se, sdhl.se | SHL back to 1975-76 |
| `hockeyallsvenskan` | HockeyAllsvenskan | hockeyallsvenskan.se | regular season only |
| `liiga` | Liiga | liiga.fi | no goalie stats in the public API |
| `mestis`, `suomi-sarja`, `u20-sm-sarja`, `u18-sm-sarja`, `auroraliiga` | Finland | tulospalvelu.leijonat.fi | multi-stage seasons keep a `stage` column |
| `nl`, `sl`, `myhl` | Switzerland | data.sihf.ch | no standings (the API's table is incomplete for recent seasons) |
| `del`, `del2` | Germany | penny-del.org, del-2.org | |
| `extraliga`, `maxa-liga` | Czechia | hokej.cz | no standings yet |
| `icehl` | ICE Hockey League | ice.hockey data files | skaters back to 2012-13; goalies and standings from 2025-26 (earlier files are partial) |
| `metal-ligaen` | Denmark | statistik.metalligaen.dk | standings verified; the stats host stopped responding mid-testing, so skaters/goalies are checked by hand only |
| `eihl` | UK Elite League | eliteleague.co.uk | |

Not covered: the KHL, VHL and MHL (khl.ru answers every request with 403), Slovakia (behind a
Cloudflare challenge), France (stats host unreachable), and the Alps League, Norway, Poland,
Hungary, Italy and J20 Nationell, which aren't wired yet. The NAHL's stats widget needs a
CSRF session cookie, so it isn't wired either. `ps.eliteprospects` covers most of these.

## HockeyDB (`ps.hockeydb`)

Season rosters with stats for almost any league, from hockeydb.com: including the KHL, VHL, MHL,
Slovakia and the NAHL, whose own sites are blocked or missing here. One row per player and team:
`pid, player, team, pos`, regular season `gp, g, a, pts, pim, plus_minus`, playoffs `po_gp ... po_pim`,
`birthplace, age`. The `pid` is HockeyDB's player id, the same in every league, so a player's stints
in different leagues join exactly.

```python
ps.hockeydb.skaters("nahl", 2024)          # short names for common leagues: ps.hockeydb.LEAGUES
ps.hockeydb.skaters(479, "2023-24")        # or any HockeyDB league id (479 = MHL)
ps.hockeydb.leagues()                      # every league and its id
```

A league-season is one request per team (about 25 for the KHL), at one request every 3 seconds:
HockeyDB puts a Cloudflare challenge on clients that go faster, and that block lasts a while.

## Being polite

Every request goes through one throttled session (`puckscrape/_http.py`): 1.5 s between
Elite Prospects requests, 3 s for HockeyDB, 1 s for MoneyPuck and league websites, 0.5 s for league JSON APIs,
0.25 s for ESPN, 0.1 s for the NHL. 403/429/5xx are retried
with exponential backoff, and Elite Prospects pages that come back empty are retried
because EP sometimes soft-blocks instead of returning 403.

Elite Prospects sits behind a Cloudflare bot challenge that fingerprints the connection itself,
so a browser User-Agent isn't enough. EP requests go through [curl_cffi](https://github.com/lexiforest/curl_cffi),
which makes the same TLS/HTTP2 handshake as a real browser. If Cloudflare still challenges it,
puckscrape backs off and retries as a different browser (Chrome, then Safari, then Firefox).

Long Elite Prospects scrapes can be stopped with Ctrl-C, which returns everything scraped so far.

To see progress:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## Credits and terms

- Elite Prospects scraping is for personal use: commercial use should go through the EP API.
- HockeyDB data is from [hockeydb.com](https://www.hockeydb.com): keep it to personal use and the
  default rate limit.
- MoneyPuck data is from [MoneyPuck.com](https://moneypuck.com). Credit them if you publish with it.
- `ps.leagues` reads the same public pages and data feeds each league's website loads in a
  browser (the CHL key, for instance, is the public site key chl.ca sends). They're unofficial,
  can change without notice, and each site's terms apply: keep it to personal use, and keep the
  default rate limits.
- ESPN data comes from the undocumented JSON endpoints behind espn.com. They're unofficial and
  unsupported, can change without notice, and ESPN's terms of use apply: keep it to personal use.
- Licenses for code adapted from other projects are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

## Tests

```
uv run pytest -m "not live"   # offline parser tests
uv run pytest -m live         # hits the real sites
```
