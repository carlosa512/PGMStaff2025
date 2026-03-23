# NFL Reference Data for PGM3

**Last pulled:** 2026-03-23 13:47:30
**Source:** nflverse (https://github.com/nflverse/nflverse-data)
**Data updates daily at 7AM UTC** (including offseason free agency/trades)

## Files

### nflverse_rosters_2026.csv
Season-level roster for 2026. One row per player per team.
Key columns: player_id, player_name, position, team, jersey_number, height, weight,
birth_date, college, status, years_exp, draft_number, draft_round, draft_club

### nflverse_rosters_weekly_2026.csv
Weekly roster snapshots. Shows when players moved teams during the season/offseason.
Same columns as above but with a `week` column. Most recent week = current roster state.

### nflverse_players.csv
Master player database across all seasons. Best for ID lookups and cross-referencing.
Includes gsis_id, espn_id, yahoo_id, rotowire_id, pff_id, pfr_id, fantasy_data_id.

### nflverse_draft_picks.csv
Historical draft picks. Filter by season=2026 for current year's rookie class.
Key columns: season, round, pick, team, player_name, position, college

### nflverse_transactions.csv
Trade data. Useful for tracking player movement between teams.

## How to refresh
Run: `python scripts/pull_nflverse_rosters.py`
Do this after major free agency waves, trades, or the NFL Draft.

## Claude Code usage
Point Claude Code to these files instead of web searching for roster data.
See CLAUDE.md for full instructions.
