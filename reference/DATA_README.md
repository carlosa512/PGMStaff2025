# NFL Reference Data for PGM3

**Last pulled:** 2026-03-27 00:33:29
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

### nflverse_contracts.parquet
Historical player contracts from OverTheCap.com (parquet format for current data through 2026).
~50,000 rows covering active and inactive players. Includes per-year breakdowns with
cap_number, base_salary, guaranteed_salary, roster_bonus, and prorated_bonus.
Key columns: player, position, team, year_signed, years, value, apy, guaranteed, gsis_id, cols.
Values are in millions. Filter `is_active == True` for current contracts.
Use with `scripts/update_contracts.py` to apply real contract data to the game roster.
Note: The CSV version is frozen at 2022 data - always use the parquet file.

## How to refresh
Run: `python scripts/pull_nflverse_rosters.py`
Do this after major free agency waves, trades, or the NFL Draft.

## Claude Code usage
Point Claude Code to these files instead of web searching for roster data.
See CLAUDE.md for full instructions.
