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
    ./reference/nflverse_contracts.parquet       - Player contracts from OverTheCap (current data)
    ./reference/DATA_README.md                   - Description of each file
"""

import os
import sys
from datetime import datetime

SEASON = 2026
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "reference")

# nflverse GitHub release base URL
NFLVERSE_BASE = "https://github.com/nflverse/nflverse-data/releases/download"

# Seasons to pull for multi-season rating model (last 4 seasons)
STAT_SEASONS = [2022, 2023, 2024, 2025]

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

        # Contracts (from OverTheCap via nflverse) - parquet for current data
        print("  Pulling contracts (parquet)...")
        try:
            contracts = nfl.load_contracts()
            contracts_df = contracts.to_pandas() if hasattr(contracts, "to_pandas") else contracts
            contracts_path = os.path.join(OUTPUT_DIR, "nflverse_contracts.parquet")
            contracts_df.to_parquet(contracts_path, index=False)
            print(f"  Saved: {contracts_path} ({len(contracts_df)} rows)")
        except Exception as e:
            print(f"  [WARN] Failed to pull contracts via nflreadpy: {e}")
            print("  Trying direct parquet download...")
            _download_contracts_parquet()

        # Per-season player stats (offense + defense) for rating model
        _pull_player_stats_nflreadpy(nfl)

        return True

    except ImportError:
        print("[nflreadpy] Not installed. Falling back to direct CSV download.")
        return False
    except Exception as e:
        print(f"[nflreadpy] Error: {e}")
        print("Falling back to direct CSV download.")
        return False


def _pull_player_stats_nflreadpy(nfl):
    """Pull multi-season offense + defense player stats via nflreadpy."""
    import pandas as pd

    for stat_type, out_name in [
        ("offense", "nflverse_player_stats_offense.csv"),
        ("defense", "nflverse_player_stats_defense.csv"),
    ]:
        print(f"  Pulling {stat_type} player stats ({STAT_SEASONS[0]}-{STAT_SEASONS[-1]})...")
        out_path = os.path.join(OUTPUT_DIR, out_name)
        seasons_dfs = []
        for season in STAT_SEASONS:
            try:
                df = nfl.load_player_stats(stat_type=stat_type, seasons=[season])
                df = df.to_pandas() if hasattr(df, "to_pandas") else df
                df["season"] = season
                seasons_dfs.append(df)
            except Exception as e:
                # Try direct CSV fallback for this season
                base = "player_stats_def" if stat_type == "defense" else "player_stats"
                url = f"{NFLVERSE_BASE}/player_stats/{base}_{season}.csv"
                try:
                    df = pd.read_csv(url, low_memory=False)
                    df["season"] = season
                    seasons_dfs.append(df)
                except Exception as e2:
                    print(f"  [WARN] Could not pull {stat_type} stats for {season}: {e2}")
        if seasons_dfs:
            combined = pd.concat(seasons_dfs, ignore_index=True)
            combined.to_csv(out_path, index=False)
            print(f"  Saved: {out_path} ({len(combined)} rows across {len(seasons_dfs)} seasons)")
        else:
            print(f"  [WARN] No {stat_type} stats pulled.")


def _download_player_stats_direct():
    """Fallback: download per-season stats directly from nflverse GitHub releases."""
    import pandas as pd

    for stat_type, out_name in [
        ("player_stats", "nflverse_player_stats_offense.csv"),
        ("player_stats_def", "nflverse_player_stats_defense.csv"),
    ]:
        print(f"  Downloading {stat_type} ({STAT_SEASONS[0]}-{STAT_SEASONS[-1]})...")
        out_path = os.path.join(OUTPUT_DIR, out_name)
        seasons_dfs = []
        for season in STAT_SEASONS:
            url = f"{NFLVERSE_BASE}/player_stats/{stat_type}_{season}.csv"
            try:
                df = pd.read_csv(url, low_memory=False)
                df["season"] = season
                seasons_dfs.append(df)
                print(f"    {season}: {len(df)} rows")
            except Exception as e:
                print(f"    [WARN] {season}: {e}")
        if seasons_dfs:
            combined = pd.concat(seasons_dfs, ignore_index=True)
            combined.to_csv(out_path, index=False)
            print(f"  Saved: {out_path} ({len(combined)} rows)")
        else:
            print(f"  [WARN] No {stat_type} data downloaded.")


def _download_contracts_parquet():
    """Download contracts parquet directly from nflverse GitHub releases."""
    import pandas as pd
    contracts_url = f"{NFLVERSE_BASE}/contracts/historical_contracts.parquet"
    contracts_path = os.path.join(OUTPUT_DIR, "nflverse_contracts.parquet")
    try:
        df = pd.read_parquet(contracts_url)
        df.to_parquet(contracts_path, index=False)
        print(f"  Saved: {contracts_path} ({len(df)} rows)")
    except ImportError:
        print("  [ERROR] pyarrow is required for parquet. Install with: pip install pyarrow")
    except Exception as e:
        print(f"  [ERROR] Failed to download contracts parquet: {e}")


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

    # Download contracts parquet separately (CSV version is stale at 2022)
    print("  Downloading contracts (parquet - current data)...")
    _download_contracts_parquet()

    # Per-season player stats for rating model
    _download_player_stats_direct()

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

### nflverse_contracts.parquet
Historical player contracts from OverTheCap.com (parquet format for current data through {SEASON}).
~50,000 rows covering active and inactive players. Includes per-year breakdowns with
cap_number, base_salary, guaranteed_salary, roster_bonus, and prorated_bonus.
Key columns: player, position, team, year_signed, years, value, apy, guaranteed, gsis_id, cols.
Values are in millions. Filter `is_active == True` for current contracts.
Use with `scripts/update_contracts.py` to apply real contract data to the game roster.
Note: The CSV version is frozen at 2022 data - always use the parquet file.

### nflverse_player_stats_offense.csv
Per-player per-season offensive stats for {', '.join(str(s) for s in {STAT_SEASONS})}.
Key columns: player_id, player_name, season, completions, attempts, passing_yards, passing_tds,
interceptions, rushing_yards, carries, receiving_yards, targets, receptions, snap counts.
Used by `scripts/apply_pff_ratings.py` to compute performance-based ratings.

### nflverse_player_stats_defense.csv
Per-player per-season defensive stats for the same seasons.
Key columns: player_id, player_name, season, tackles, sacks, tackles_for_loss,
interceptions, pass_breakups, snap counts.
Used by `scripts/apply_pff_ratings.py` for defensive player rating synthesis.

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
