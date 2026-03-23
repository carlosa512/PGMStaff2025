"""
NFL Roster Data Puller for PGM3
================================
Pulls current NFL roster data from nflverse for use with Claude Code
and Pocket GM 3 roster editing.

Tries nflreadpy first, falls back to direct CSV download from GitHub releases.
Run this script whenever you want fresh roster data (e.g., after major
free agency signings, trades, or the draft).

Usage:
    python scripts/pull_nflverse_rosters.py

Output:
    ./reference/nflverse_rosters_2026.csv        - Season-level roster
    ./reference/nflverse_rosters_weekly_2026.csv - Weekly roster (most current team assignment)
    ./reference/nflverse_players.csv             - Full player database with IDs
    ./reference/nflverse_draft_picks.csv         - Draft picks (useful for rookies)
    ./reference/nflverse_transactions.csv        - Trades data
    ./reference/DATA_README.md                   - Description of each file
"""

import os
import sys
from datetime import datetime

SEASON = 2026
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")

# nflverse GitHub release base URL
NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"

# Direct CSV URLs for each dataset
DATASETS = {
    "nflverse_rosters_{season}.csv": f"{NFLVERSE_BASE}/rosters/roster_{SEASON}.csv",
    "nflverse_rosters_weekly_{season}.csv": f"{NFLVERSE_BASE}/weekly_rosters/roster_weekly_{SEASON}.csv",
    "nflverse_players.csv": f"{NFLVERSE_BASE}/players/players.csv",
    "nflverse_draft_picks.csv": f"{NFLVERSE_BASE}/draft_picks/draft_picks.csv",
    "nflverse_transactions.csv": f"{NFLVERSE_BASE}/trades/trades.csv",
}


def ensure_output_dir():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"Output directory: {os.path.abspath(OUTPUT_DIR)}")


def try_nflreadpy():
    """Attempt to use nflreadpy (preferred method)."""
    try:
        import nflreadpy as nfl
        print("[nflreadpy] Package found. Pulling data...")

        # Season-level rosters
        print("  Pulling season rosters...")
        rosters = nfl.load_rosters([SEASON])
        rosters_df = rosters.to_pandas() if hasattr(rosters, "to_pandas") else rosters
        rosters_path = os.path.join(OUTPUT_DIR, f"nflverse_rosters_{SEASON}.csv")
        rosters_df.to_csv(rosters_path, index=False)
        print(f"  Saved: {rosters_path} ({len(rosters_df)} rows)")

        # Weekly rosters (most current assignments)
        print("  Pulling weekly rosters...")
        weekly = nfl.load_rosters_weekly([SEASON])
        weekly_df = weekly.to_pandas() if hasattr(weekly, "to_pandas") else weekly
        weekly_path = os.path.join(OUTPUT_DIR, f"nflverse_rosters_weekly_{SEASON}.csv")
        weekly_df.to_csv(weekly_path, index=False)
        print(f"  Saved: {weekly_path} ({len(weekly_df)} rows)")

        # Players database
        print("  Pulling players database...")
        players = nfl.load_players()
        players_df = players.to_pandas() if hasattr(players, "to_pandas") else players
        players_path = os.path.join(OUTPUT_DIR, "nflverse_players.csv")
        players_df.to_csv(players_path, index=False)
        print(f"  Saved: {players_path} ({len(players_df)} rows)")

        # Draft picks
        print("  Pulling draft picks...")
        drafts = nfl.load_draft_picks()
        drafts_df = drafts.to_pandas() if hasattr(drafts, "to_pandas") else drafts
        drafts_path = os.path.join(OUTPUT_DIR, "nflverse_draft_picks.csv")
        drafts_df.to_csv(drafts_path, index=False)
        print(f"  Saved: {drafts_path} ({len(drafts_df)} rows)")

        # Trades
        print("  Pulling trades...")
        trades = nfl.load_trades()
        trades_df = trades.to_pandas() if hasattr(trades, "to_pandas") else trades
        trades_path = os.path.join(OUTPUT_DIR, "nflverse_transactions.csv")
        trades_df.to_csv(trades_path, index=False)
        print(f"  Saved: {trades_path} ({len(trades_df)} rows)")

        return True

    except ImportError:
        print("[nflreadpy] Not installed. Falling back to direct CSV download.")
        return False
    except Exception as e:
        print(f"[nflreadpy] Error: {e}")
        print("Falling back to direct CSV download.")
        return False


def try_direct_csv():
    """Download CSVs directly from nflverse GitHub releases using pandas."""
    try:
        import pandas as pd
    except ImportError:
        print("[ERROR] pandas is required. Install with: pip install pandas")
        return False

    print("[direct CSV] Downloading from nflverse GitHub releases...")
    success_count = 0

    for filename_template, url in DATASETS.items():
        filename = filename_template.format(season=SEASON)
        filepath = os.path.join(OUTPUT_DIR, filename)

        try:
            print(f"  Downloading {filename}...")
            df = pd.read_csv(url, low_memory=False)
            df.to_csv(filepath, index=False)
            print(f"  Saved: {filepath} ({len(df)} rows)")
            success_count += 1
        except Exception as e:
            print(f"  [WARN] Failed to download {filename}: {e}")
            # If the 2026 file doesn't exist yet, try 2025 as fallback
            if str(SEASON) in url:
                fallback_url = url.replace(str(SEASON), str(SEASON - 1))
                fallback_filename = filename.replace(str(SEASON), str(SEASON - 1))
                try:
                    print(f"  Trying fallback: {fallback_filename}...")
                    df = pd.read_csv(fallback_url, low_memory=False)
                    fallback_path = os.path.join(OUTPUT_DIR, fallback_filename)
                    df.to_csv(fallback_path, index=False)
                    print(f"  Saved fallback: {fallback_path} ({len(df)} rows)")
                    success_count += 1
                except Exception as e2:
                    print(f"  [ERROR] Fallback also failed: {e2}")

    return success_count > 0


def write_data_readme():
    """Create a README describing the data files for Claude Code to reference."""
    readme_path = os.path.join(OUTPUT_DIR, "DATA_README.md")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    content = f"""# NFL Reference Data for PGM3

**Last pulled:** {timestamp}
**Source:** nflverse (https://github.com/nflverse/nflverse-data)
**Data updates daily at 7AM UTC** (including offseason free agency/trades)

## Files

### nflverse_rosters_{SEASON}.csv
Season-level roster for {SEASON}. One row per player per team.
Key columns: player_id, player_name, position, team, jersey_number, height, weight,
birth_date, college, status, years_exp, draft_number, draft_round, draft_club

### nflverse_rosters_weekly_{SEASON}.csv
Weekly roster snapshots. Shows when players moved teams during the season/offseason.
Same columns as above but with a `week` column. Most recent week = current roster state.

### nflverse_players.csv
Master player database across all seasons. Best for ID lookups and cross-referencing.
Includes gsis_id, espn_id, yahoo_id, rotowire_id, pff_id, pfr_id, fantasy_data_id.

### nflverse_draft_picks.csv
Historical draft picks. Filter by season={SEASON} for current year's rookie class.
Key columns: season, round, pick, team, player_name, position, college

### nflverse_transactions.csv
Trade data. Useful for tracking player movement between teams.

## How to refresh
Run: `python scripts/pull_nflverse_rosters.py`
Do this after major free agency waves, trades, or the NFL Draft.

## Claude Code usage
Point Claude Code to these files instead of web searching for roster data.
See CLAUDE.md for full instructions.
"""

    with open(readme_path, "w") as f:
        f.write(content)
    print(f"\nData README written to: {readme_path}")


def main():
    print("=" * 60)
    print(f"NFL Roster Data Puller for PGM3 (Season: {SEASON})")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 60)

    ensure_output_dir()

    # Try nflreadpy first, fall back to direct CSV
    if not try_nflreadpy():
        if not try_direct_csv():
            print("\n[ERROR] Could not pull data. Check your internet connection.")
            print("You may need to install dependencies:")
            print("  pip install pandas")
            print("  pip install nflreadpy@git+https://github.com/nflverse/nflreadpy")
            sys.exit(1)

    write_data_readme()

    print("\n" + "=" * 60)
    print("DONE. Files saved to ./reference/")
    print("=" * 60)


if __name__ == "__main__":
    main()
