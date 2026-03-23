# CLAUDE.md - NFL Roster Data Instructions

## Local Reference Data (USE FIRST)

This repo contains pre-pulled NFL roster data in `./reference/`. **Always check these files before searching the web for any player, roster, or team data.** This saves tokens and is more accurate than web searches.

### Available data files:

- `./reference/nflverse_rosters_2026.csv` - Current season rosters with positions, teams, jersey numbers, draft info
- `./reference/nflverse_rosters_weekly_2026.csv` - Weekly roster snapshots (latest week = current state)
- `./reference/nflverse_players.csv` - Master player database with all IDs (gsis, espn, pfr, pff, etc.)
- `./reference/nflverse_draft_picks.csv` - Draft picks by season (filter season=2026 for rookies)
- `./reference/nflverse_transactions.csv` - Trade history

### Workflow for roster edits:

1. Read the relevant CSV file(s) from `./reference/` to get accurate player data
2. Cross-reference player names, positions, and teams against the CSV before making changes
3. Use `nflverse_players.csv` for full name spellings and position verification
4. Use `nflverse_draft_picks.csv` (filtered to season=2026) for rookie class data
5. Only search the web if a player is not found in the local files (e.g., UDFA signings, very recent moves)

### Important reminders (from existing PGM3 conventions):

- Verify player presence in the roster file before creating new entries
- Never assign players to teams they are not actually on
- Use only valid PGM3 positions (never "EDGE" or invented positions)
- Free agents must always be preserved
- Appearance values should reflect real-life racial likeness
- Draft years for non-current-year rookies should be rolled back by one relative to in-game start year

### Refreshing the data:

If the data seems stale, run: `python scripts/pull_nflverse_rosters.py`

This pulls fresh data from nflverse (updates daily at 7AM UTC, including offseason).
