# PGM3 NFL Roster & Staff Manager

Tools and data for managing NFL rosters and coaching staff in Pro GM 3 (PGM3).

## Data Files

| File | Description |
|------|-------------|
| `PGMRoster_2026_Final.json` | Main roster (~4,216 players) |
| `PGMStaff_2026_Final.json` | Coaching staff (~447 entries) |
| `reference/` | NFL reference data pulled from nflverse |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pull_nflverse_rosters.py` | Pull fresh reference data from nflverse |
| `scripts/add_missing_players.py` | Add NFL players missing from roster |
| `scripts/fix_ratings.py` | Fix player ratings below minimum threshold |
| `scripts/fix_appearances_and_ratings.py` | Fix appearance rendering issues and boost stats |
| `scripts/trim_rosters.py` | Enforce 53-man roster limits |
| `scripts/update_roster_2026.py` | Apply offseason moves (trades, FA, cuts) |
| `scripts/update_appearances.py` | Manual appearance corrections |
| `scripts/update_staff_2026.py` | Update coaching staff |

## Quick Start

```bash
# Pull fresh NFL data
pip install pandas
python scripts/pull_nflverse_rosters.py

# Add missing players and fix issues
python scripts/add_missing_players.py
python scripts/fix_appearances_and_ratings.py
python scripts/trim_rosters.py
```

## Details

See [CLAUDE.md](CLAUDE.md) for full documentation on the appearance system, rating formulas, and position stats.
