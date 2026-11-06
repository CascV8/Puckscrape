# puckscrape

Hockey stats from the NHL API, NHL Edge, Elite Prospects, MoneyPuck, ESPN, HockeyDB and league/federation websites
(NCAA men and women, the PWHL, the CHL, the AHL/ECHL, junior A leagues, the KHL, MHL and VHL, and leagues across Europe including Czech youth), IIHF
tournaments (men's and women's, every division), plus NHL draft rankings from Elite Prospects and TSN,
as pandas DataFrames.

```python
import puckscrape as ps

ps.nhl.skater_stats("2024-25")                          # every NHL skater, stats.nhl.com summary report
ps.edge.skater_summary([8478402, 8479318], 2024)        # Edge tracking: speed, shot speed, zone time
ps.eliteprospects.skaters(["ahl", "ohl"], "2024-25")    # any EP league
ps.moneypuck.skaters(2024)                              # xG, Corsi, game score
ps.espn.standings(2024)                                 # ESPN standings, box scores, injuries
ps.leagues.skaters(["ohl", "shl", "ncaa"], "2025-26")    # straight from league websites
ps.leagues.skaters(["pwhl", "ncaa-w", "sdhl"], 2025)    # women's leagues too
ps.leagues.goalies(["khl", "czech-u18"], 2025)          # KHL, MHL, Czech youth
ps.iihf.skaters("ww", 2025)                             # IIHF tournaments, men's and women's
ps.hockeydb.skaters("khl", "2024-25")                   # HockeyDB rosters, any league
ps.eliteprospects.draft_rankings("all")                 # NHL draft rankings: EP's and other outlets'
ps.tsn.draft_ranking(ps.tsn.draft_ranking_articles())   # TSN's draft rankings
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
| `eliteprospects` | `skaters`, `goalies`, `player_info`, `add_player_info`, `draft_rankings`, `draft_scouts` |
| `tsn` | `draft_ranking`, `draft_ranking_articles` |
| `moneypuck` | `skaters`, `goalies`, `teams`, `lines`, `shots` |
| `leagues` | `leagues`, `skaters`, `goalies`, `standings` |
| `iihf` | `events`, `skaters`, `goalies`, `standings`, `final_ranking`, `scan_events`, `classify` |
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
| `ncaa-w` | NCAA Division I (women) | collegehockeynews.com | ~45 requests a season; same tables as `ncaa` |
| `pwhl` | Professional Women's Hockey League | HockeyTech (thepwhl.com) | from 2023-24 (its first season, Jan-May 2024); playoffs too |
| `ohl`, `whl`, `qmjhl` | CHL | HockeyTech feed behind chl.ca | full history; playoffs too |
| `ahl`, `echl` | AHL, ECHL | HockeyTech (theahl.com, echl.com) | full history; playoffs too |
| `ushl`, `bchl`, `ajhl`, `sjhl`, `mjhl`, `ojhl`, `cchl`, `mjahl`, `kijhl`, `vijhl` | US/Canadian junior | HockeyTech (each league's site key) | `mjahl` is the Maritime Junior Hockey League |
| `gohl`, `csshl` | GOHL (Ontario junior B), CSSHL U18 Prep | HockeyTech | CSSHL from 2021-22 (earlier seasons mix every age division) |
| `shl`, `sdhl` | SHL, SDHL (women) | shl.se, sdhl.se | SHL back to 1975-76 |
| `hockeyallsvenskan` | HockeyAllsvenskan | hockeyallsvenskan.se | regular season only |
| `liiga` | Liiga | liiga.fi | goalies from 2009-10 (`gp` is games played; `games_dressed` counts backups too) |
| `mestis`, `suomi-sarja`, `u20-sm-sarja`, `u18-sm-sarja`, `auroraliiga`, `naisten-mestis` | Finland | tulospalvelu.leijonat.fi | multi-stage seasons keep a `stage` column; Auroraliiga and Naisten Mestis are the women's top two |
| `u18-nationell`, `u20-nationell` | Sweden U18 and U20 Nationell (J18, J20) | stats.swehockey.se (the federation) | from 2011-12 (no 2020-21); one request per series; every row keeps its series in `stage` (Norra, Södra, kvalserie...); playoffs = SM-slutspel. Before 2021-22 the U18 tree holds J18 Allsvenskan (the season's second half), not the autumn J18 Elit |
| `u18-regional` | Sweden U18 Regional: the autumn elite series (Norr, Syd, Väst, Öst; U18 Nationell starts in January) | stats.swehockey.se | the four regions read as one league; series (Topp 6, fortsättning...) in `stage` |
| `u18-elit`, `u21-elit` | Switzerland U18-Elit (U17-Elit until 2024-25), U21-Elit (U20-Elit) | data.sihf.ch | U18-Elit from 2016-17; goalies without saves, SV% or W-L (SIHF doesn't publish them for youth leagues); no standings |
| `norway-u18`, `norway-u20` | Norway U18 Elite, U20 Elite | the federation's results API (behind live.hockey.no) | from 2012-13; rows keep their tournament in `stage` (U20: opening round, Elite A/B); playoffs = the NM tournaments (quarterfinals, Final 4...); standings in Norway's 3-2-1 points |
| `nl`, `sl`, `myhl`, `swhl` | Switzerland | data.sihf.ch | `swhl` is the PostFinance Women's League (goalies without SV% or W-L: SIHF doesn't publish them); no standings (the API's table is incomplete for recent seasons) |
| `del`, `del2` | Germany | penny-del.org, del-2.org | |
| `extraliga`, `maxa-liga`, `czech-2-liga` | Czechia | ceskyhokej.cz (the federation) | from 2020-21; 2022-23 has standings but no player stats on the site; every row keeps its season part in `stage` (base round, groups, placement/relegation rounds; playoffs = preliminary round + title series); teams get their full names (the site's 3-letter code is kept in `team_code`) |
| `czech-u20`, `czech-u18`, `czech-u16`, `extraliga-zen` | Czech juniors (Extraliga juniorů), older dorost U18 (Extraliga staršího dorostu), younger dorost U16, women | ceskyhokej.cz | same as above; `czech-u16` from 2026-27 (the competition is new) |
| `khl`, `mhl` | KHL, MHL (Russian juniors) | the KHL's app feed (khl.api.webcaster.pro) | KHL from 2008-09, MHL from 2016-17; ~60 requests (a few minutes) a season, shared by skaters and goalies; skaters get TOI, shifts, faceoffs, top speed and distance; standings rebuilt from game results (W/OTW/SOW/L/OTL/SOL) |
| `vhl` | VHL | hockeydb.com | skaters only (goalies appear with `position` G and skater lines); one request per team, 3 s apart |
| `icehl` | ICE Hockey League | ice.hockey data files | skaters back to 2012-13; goalies and standings from 2025-26 (earlier files are partial) |
| `metal-ligaen` | Denmark | statistik.metalligaen.dk | standings verified; the stats host stopped responding mid-testing, so skaters/goalies are checked by hand only |
| `eihl` | UK Elite League | eliteleague.co.uk | |
| `iihf-wm`, `iihf-ww`, `iihf-wm20`, `iihf-wm18`, `iihf-ww18` | IIHF World Championships: men, women, U20, U18 men, U18 women | stats.iihf.com | top division only (`ps.iihf` has every division); season 2024-25 is the 2025 tournament; phase `tournament` |

European U18 leagues: `u18-nationell` and `u18-regional` (Sweden), `u18-sm-sarja` (Finland), `czech-u18`, `u18-elit` (Switzerland), `norway-u18`. Not wired: Slovakia (Cloudflare challenge), Germany's U17 DNL (deb-online.live loads its stats from a third-party API with the site's key, so it isn't wired), Denmark (the federation's hosts don't answer).

Women's leagues: `pwhl`, `ncaa-w`, `sdhl`, `auroraliiga`, `naisten-mestis`, `swhl`, `extraliga-zen`, plus `iihf-ww` and `iihf-ww18`.

khl.ru, mhl.khl.ru and vhlru.ru drop connections from many networks (from here, every Russian
site did), so the KHL and MHL come from the KHL's own app feed, which is served from a different
host, and the VHL from HockeyDB. The women's ZhHL has no app feed any more. hokej.cz now sits behind
a Cloudflare challenge, so the Czech leagues come from the federation's site, which also has the
youth and women's leagues.

Not covered: Slovakia (behind a Cloudflare challenge), France (stats host unreachable), and the Alps League, Norway, Poland,
Hungary, Italy, the GTHL (no public stats pages) and the PJHL (an old Ramp
frameset site), which aren't wired yet. The NAHL's stats widget needs a
CSRF session cookie, so it isn't wired either. Germany's DFEL isn't wired either. `ps.eliteprospects` covers most of these.

## IIHF tournaments (`ps.iihf`)

Every IIHF championship, men's and women's, senior, U20 and U18, every division and group, plus
Olympic qualification and other IIHF events, from the IIHF's own stats archive (stats.iihf.com/Hydra).

```python
ps.iihf.events(year=2025, gender="women")         # the catalog: event_id, title, tournament, division, teams
ps.iihf.skaters("ww", 2025)                       # Women's Worlds 2025, top division
ps.iihf.goalies("wm20", 2026)                     # World Juniors 2026 (played Dec 2025 - Jan 2026)
ps.iihf.skaters("ww18", 2025, division="all")     # every division
ps.iihf.skaters("wm", 2025, division="Div I Group A")
ps.iihf.skaters(510)                              # any event by id; or a list, or a frame from events()
ps.iihf.standings("wm", 2025)                     # group standings
ps.iihf.final_ranking("wm", 2025)
```

Tournament codes: `wm` (men's Worlds), `ww` (women's), `wm20` (U20), `wm18`, `ww18`, `olyq-m`, `olyq-w`
(Olympic qualification), `oly-m`, `oly-w` (Olympic tournaments: only 2014 has stats in the archive; 2018
isn't there, 2022's team reports are linked but gone, and 2026 has only its schedule). Years are the year a
tournament is named for. `wm20` 2022 is the August 2022 replay; the abandoned December 2021 tournament is
division `"Top (abandoned Dec 2021)"`. Covered: every championship from 2008 (some events back to 1990),
through the 2026 tournaments. Rows start with the event (`event_id, event, year, gender, tournament,
division`), then `player, team, team_code, position, gp, g, a, pts, pim, plus_minus` and whatever else
the report has (GWG, PPG, SHG, shots, SG%, and in the top divisions ice time and shifts). Goalies get
`gp, w, l, ga, saves, sv_pct, gaa, so, toi` (minutes). Player names are written "Hilary Knight"; the IIHF's
own spelling is kept in `first_name` / `last_name` ("KNIGHT").

An event is one request for its index page plus one per team (about 11 for a 10-team event).
The archive has no list of events, so the catalog ships with puckscrape (`src/puckscrape/data/iihf_events.csv`);
`ps.iihf.scan_events()` rebuilds it (about 1,100 requests). The archive's newest top-division events may
lag iihf.com, which sits behind a Cloudflare challenge and isn't used.

The IIHF's PDFs have no readable text layer: their subset fonts carry no character map. puckscrape
identifies each glyph by a hash of its outline, matched against Arial's (`data/arial_glyphs.json`,
built by `scripts/build_arial_glyphs.py`; it holds hashes, not the font).

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

## NHL draft rankings (`ps.eliteprospects`, `ps.tsn`)

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

TSN publishes each ranking (Craig Button's "Craig's List", TSN's scouting-survey ranking) as a table
in a tsn.ca article, so `tsn.draft_ranking` takes article URLs, old or new URL style. It returns the
table as printed (rank, team, league, position, height, weight, stats; goalies get `gaa` and `sv_pct`)
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
- IIHF statistics are the IIHF's, read from the public report PDFs at stats.iihf.com. Keep it to
  personal use and the default rate limit, and credit the IIHF if you publish with them.
- ESPN data comes from the undocumented JSON endpoints behind espn.com. They're unofficial and
  unsupported, can change without notice, and ESPN's terms of use apply: keep it to personal use.
- TSN draft rankings are Craig Button's and TSN's work, read from public tsn.ca articles. TSN's
  terms of use apply: keep it to personal use, and credit TSN if you publish with them.
- Licenses for code adapted from other projects are in [THIRD_PARTY_NOTICES](THIRD_PARTY_NOTICES).

## Tests

```
uv run pytest -m "not live"   # offline parser tests
uv run pytest -m live         # hits the real sites
```
