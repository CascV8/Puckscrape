# puckscrape

Hockey stats from the NHL API, NHL Edge, Elite Prospects, MoneyPuck, ESPN, HockeyDB and league/federation websites
(NCAA, the CHL, the AHL/ECHL, junior A leagues, and leagues across Europe), plus NHL draft rankings
from Elite Prospects and TSN, as pandas DataFrames.

```python
import puckscrape as ps

ps.nhl.skater_stats("2024-25")                          # every NHL skater, stats.nhl.com summary report
ps.edge.skater_summary([8478402, 8479318], 2024)        # Edge tracking: speed, shot speed, zone time
ps.eliteprospects.skaters(["ahl", "ohl"], "2024-25")    # any EP league
ps.moneypuck.skaters(2024)                              # xG, Corsi, game score
ps.espn.standings(2024)                                 # ESPN standings, box scores, injuries
ps.leagues.skaters(["ohl", "shl", "ncaa"], "2025-26")    # straight from league websites
ps.hockeydb.skaters("khl", "2024-25")                   # HockeyDB rosters, any league
ps.eliteprospects.draft_rankings("all")                 # NHL draft rankings: EP's and other outlets'
ps.tsn.draft_ranking(ps.tsn.draft_ranking_articles())   # TSN's draft rankings
ps.tsn.mckenzie_ranking(editions="final")               # Bob McKenzie's final lists, 2020 on
ps.nhl.draft_rankings(2025)                             # NHL Central Scouting, 2008 on
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
| `nhl` | `schedule`, `team_schedule`, `boxscore`, `play_by_play`, `shifts`, `full_play_by_play`*, `roster`, `player_info`, `game_log`, `standings`, `skater_stats`, `goalie_stats`, `team_stats`, `teams`, `draft_rankings` |
| `edge` | `skater_summary`, `skater_shot_locations`, `skater_zone_time`, `skater_top_speeds`, `skater_hardest_shots`, `skater_distance`, `goalie_summary`, `goalie_shot_locations`, `goalie_save_pct_last10`, `team_summary`, `team_zone_time`, `team_top_speeds`, `raw` |
| `eliteprospects` | `skaters`, `goalies`, `player_info`, `add_player_info`, `draft_rankings`, `draft_scouts` |
| `tsn` | `draft_ranking`, `mckenzie_ranking`, `draft_ranking_articles` |
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
| `gohl`, `csshl` | GOHL (Ontario junior B), CSSHL U18 Prep | HockeyTech | CSSHL from 2021-22 (earlier seasons mix every age division) |
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
Hungary, Italy, J20 Nationell, the GTHL (no public stats pages) and the PJHL (an old Ramp
frameset site), which aren't wired yet. The NAHL's stats widget needs a
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

## NHL draft rankings (`ps.nhl`, `ps.tsn`, `ps.eliteprospects`)

NHL Central Scouting's lists come from the NHL's own API, for every draft from 2008. Each of its
four categories (North American and international skaters and goalies) is ranked separately,
with the January midterm and April final ranks side by side, plus bio and last amateur club:

```python
ps.nhl.draft_rankings()                                   # the latest draft, all four categories
ps.nhl.draft_rankings(2015, "north-american-skater")      # also "international-skater", "...-goalie"
```

Players Central Scouting lists as "LV" (limited viewing) have no rank, and "LV" in `midterm_note` / `final_note`.

Bob McKenzie's ranking, a consensus of 10 NHL scouts he surveyed for TSN, came out up to four times
a season. `tsn.mckenzie_ranking` fetches them by draft year and edition (`"pre-season"`,
`"mid-season"`, `"lottery"`, `"final"`) from a built-in index of the articles, `tsn.MCKENZIE_RANKINGS`:

```python
ps.tsn.mckenzie_ranking(2025, "final")          # 80 ranked + 20 honourable mentions
ps.tsn.mckenzie_ranking(editions="final")       # every final list
ps.tsn.mckenzie_ranking([2024, 2025])           # every edition of both years
```

The index covers the lists TSN still serves: 2020 and 2021 finals, every 2023-2025 edition but the
2024 final, and from 2026 TSN's own scout-survey ranking, which replaced McKenzie's (`author` says
who wrote each). The 2022 lists and the 2024 final weren't found on tsn.ca (their old links 404);
if you find one, add its URL to the index or pass it to `tsn.draft_ranking`. Honourable mentions have
no rank and "HM" in `rank_note`; tied players share a rank and have `tied` set.

Elite Prospects' Draft Center collects rankings for the upcoming draft: its own, a consolidated
ranking, and other outlets' (TSN's Craig Button and Chris Peters, NHL Central Scouting, Daily Faceoff,
Sportsnet, THN, McKeen's...). One row per player and list, with EP's player id, bio and current-season stats:

```python
ps.eliteprospects.draft_scouts()                                       # every list, and when it was last updated
ps.eliteprospects.draft_rankings()                                     # EP's consolidated ranking
ps.eliteprospects.draft_rankings(["eliteprospects-com", "tsn-craig-button"])
ps.eliteprospects.draft_rankings("all")                                # every list with a ranking published
ps.eliteprospects.draft_rankings("tsn-chris-peters", unranked=True)    # + EP's unranked prospects
```

EP only keeps lists for the upcoming draft, not past years'.

TSN publishes each ranking (Craig Button's "Craig's List", the scout-survey ranking) in a tsn.ca
article, so `tsn.draft_ranking` takes article URLs, old or new URL style. It reads the ranking
table, or on older articles the player cards or numbered list, and returns it as printed (rank, team, league, position, height, weight, stats; goalies get `gaa` and `sv_pct`)
plus the article's headline, author, publish date and the `draft_year` it's for:

```python
ps.tsn.draft_ranking_articles()     # the rankings linked from TSN's draft centre (only the latest few)
ps.tsn.draft_ranking("https://www.tsn.ca/nhl/article/dupont-opens-the-season-at-no-1-on-craigs-list/")
ps.tsn.draft_ranking(ps.tsn.draft_ranking_articles())
```

For older TSN lists, pass the article's URL. TSN's stats columns are whatever the article printed
(usually the player's previous season), and its heights are converted to inches in `height_in`.

## Being polite

Every request goes through one throttled session (`puckscrape/_http.py`): 1.5 s between
Elite Prospects requests, 3 s for HockeyDB, 1 s for MoneyPuck, TSN and league websites, 0.5 s for league JSON APIs,
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
- NHL Central Scouting rankings come from the same public NHL API as the rest of `ps.nhl`.
- TSN draft rankings are Bob McKenzie's, Craig Button's and TSN's work, read from public tsn.ca articles. TSN's
  terms of use apply: keep it to personal use, and credit TSN if you publish with them.
- Licenses for code adapted from other projects are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

## Tests

```
uv run pytest -m "not live"   # offline parser tests
uv run pytest -m live         # hits the real sites
```
