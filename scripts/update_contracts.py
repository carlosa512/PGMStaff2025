"""
Update Contracts from OverTheCap Data
======================================
Applies real NFL contract data (from nflverse/OverTheCap) to PGMRoster_2026_Final.json.

Reads ./reference/nflverse_contracts.csv and matches players by name to update:
  - salary / eSalary     (from APY - average per year)
  - guarantee / eGuarantee (from total guaranteed money)
  - length / eLength     (remaining years on contract)

Run AFTER trim_rosters.py so we only process players who survived roster cuts.

Usage:
    python scripts/update_contracts.py

Prerequisites:
    Run `python scripts/pull_nflverse_rosters.py` first to download nflverse_contracts.csv
"""

import json
import os
import re
import sys

import pandas as pd

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
CONTRACTS_FILE = os.path.join(REPO_ROOT, "reference", "nflverse_contracts.csv")
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.csv.gz"

# Current game season year
CURRENT_YEAR = 2026

# Map OverTheCap team names to PGM3 team IDs
# Multi-team entries like "DEN/SEA" use the first team (current team)
TEAM_NAME_TO_ID = {
    "49ers": "SF", "Bears": "CHI", "Bengals": "CIN", "Bills": "BUF",
    "Broncos": "DEN", "Browns": "CLE", "Buccaneers": "TB", "Cardinals": "ARI",
    "Chargers": "LAC", "Chiefs": "KC", "Colts": "IND", "Commanders": "WAS",
    "Cowboys": "DAL", "Dolphins": "MIA", "Eagles": "PHI", "Falcons": "ATL",
    "Giants": "NYG", "Jaguars": "JAX", "Jets": "NYJ", "Lions": "DET",
    "Packers": "GB", "Panthers": "CAR", "Patriots": "NE", "Raiders": "LV",
    "Rams": "LAR", "Ravens": "BAL", "Saints": "NO", "Seahawks": "SEA",
    "Steelers": "PIT", "Texans": "HOU", "Titans": "TEN", "Vikings": "MIN",
}

# Abbreviation map for multi-team entries like "DEN/SEA", "IND/ATL"
ABBREV_TO_ID = {
    "ARI": "ARI", "ATL": "ATL", "BAL": "BAL", "BUF": "BUF",
    "CAR": "CAR", "CHI": "CHI", "CIN": "CIN", "CLE": "CLE",
    "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GB": "GB",
    "HOU": "HOU", "IND": "IND", "JAX": "JAX", "KC": "KC",
    "LAC": "LAC", "LAR": "LAR", "LV": "LV", "MIA": "MIA",
    "MIN": "MIN", "NE": "NE", "NO": "NO", "NYG": "NYG",
    "NYJ": "NYJ", "PHI": "PHI", "PIT": "PIT", "SEA": "SEA",
    "SF": "SF", "TB": "TB", "TEN": "TEN", "WAS": "WAS",
}


def normalize_name(name):
    """Normalize a player name for matching: lowercase, strip suffixes, punctuation."""
    name = name.strip().lower()
    # Remove common suffixes
    name = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)$', '', name)
    # Remove periods and apostrophes
    name = name.replace(".", "").replace("'", "").replace("'", "")
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name


def resolve_team(otc_team):
    """Convert OverTheCap team name to PGM3 team ID."""
    if not otc_team or pd.isna(otc_team):
        return None
    otc_team = str(otc_team).strip()

    # Direct match (e.g., "Chiefs" -> "KC")
    if otc_team in TEAM_NAME_TO_ID:
        return TEAM_NAME_TO_ID[otc_team]

    # Multi-team format like "DEN/SEA" - first team is current
    if "/" in otc_team:
        first_team = otc_team.split("/")[0].strip()
        if first_team in ABBREV_TO_ID:
            return ABBREV_TO_ID[first_team]
        if first_team in TEAM_NAME_TO_ID:
            return TEAM_NAME_TO_ID[first_team]

    # Direct abbreviation
    if otc_team in ABBREV_TO_ID:
        return ABBREV_TO_ID[otc_team]

    return None


def load_contracts():
    """Load contract data from local CSV or download from nflverse."""
    if os.path.exists(CONTRACTS_FILE):
        print(f"Loading contracts from: {CONTRACTS_FILE}")
        df = pd.read_csv(CONTRACTS_FILE, low_memory=False)
    else:
        print(f"Local contracts file not found. Downloading from nflverse...")
        df = pd.read_csv(CONTRACTS_URL, low_memory=False)
        # Save for future use
        os.makedirs(os.path.dirname(CONTRACTS_FILE), exist_ok=True)
        df.to_csv(CONTRACTS_FILE, index=False)
        print(f"Saved to: {CONTRACTS_FILE}")

    print(f"Total contract records: {len(df)}")
    return df


def build_contract_lookup(df):
    """
    Build a lookup dict: normalized_name -> contract info.
    For players with multiple contracts, keep the most recent one.
    Prefers active contracts; uses inactive as fallback for players not in active set.
    """
    # Sort by year_signed descending so most recent contract comes first
    df_sorted = df.sort_values("year_signed", ascending=False)

    active_count = int(df["is_active"].sum())
    print(f"Active player contracts: {active_count}")

    def _extract(row):
        apy = row["apy"]
        guaranteed = row["guaranteed"]
        years = int(row["years"]) if pd.notna(row["years"]) else 1
        year_signed = int(row["year_signed"]) if pd.notna(row["year_signed"]) else CURRENT_YEAR

        remaining = year_signed + years - CURRENT_YEAR
        remaining = max(1, remaining)

        return {
            "salary": int(apy) if pd.notna(apy) else None,
            "guarantee": int(guaranteed) if pd.notna(guaranteed) else None,
            "length": remaining,
            "team": resolve_team(row.get("team")),
            "original_name": row["player"],
            "year_signed": year_signed,
        }

    # First pass: active contracts only
    lookup = {}
    for _, row in df_sorted[df_sorted["is_active"] == True].iterrows():
        norm_name = normalize_name(str(row["player"]))
        if norm_name not in lookup:
            lookup[norm_name] = _extract(row)

    active_unique = len(lookup)

    # Second pass: inactive contracts as fallback (most recent contract for unmatched names)
    inactive_added = 0
    for _, row in df_sorted[df_sorted["is_active"] != True].iterrows():
        norm_name = normalize_name(str(row["player"]))
        if norm_name not in lookup:
            lookup[norm_name] = _extract(row)
            inactive_added += 1

    print(f"Unique players in lookup: {len(lookup)} ({active_unique} active, {inactive_added} inactive fallback)")
    return lookup


def apply_contracts(roster_file, lookup):
    """Match roster players to contract data and update fields."""
    with open(roster_file, "r") as f:
        data = json.load(f)

    players = data if isinstance(data, list) else data.get("players", data.get("roster", []))

    matched = 0
    skipped = 0
    name_only_match = 0
    team_confirmed = 0

    for player in players:
        forename = player.get("forename", "")
        surname = player.get("surname", "")
        full_name = f"{forename} {surname}"
        norm_name = normalize_name(full_name)
        team_id = player.get("teamID", "")

        contract = lookup.get(norm_name)
        if not contract:
            skipped += 1
            continue

        # Verify: if contract has a team and player has a team, prefer team match
        # But still apply if name matches (player may have been traded)
        if contract["team"] and team_id not in ("Free Agent", "Rookie", ""):
            if contract["team"] == team_id:
                team_confirmed += 1
            else:
                name_only_match += 1
        else:
            name_only_match += 1

        # Apply contract data (always keep pairs matched)
        if contract["salary"] is not None:
            player["salary"] = contract["salary"]
            player["eSalary"] = contract["salary"]

        if contract["guarantee"] is not None:
            player["guarantee"] = contract["guarantee"]
            player["eGuarantee"] = contract["guarantee"]

        player["length"] = contract["length"]
        player["eLength"] = contract["length"]

        matched += 1

    # Save
    with open(roster_file, "w") as f:
        json.dump(data, f, indent=2)

    return matched, skipped, team_confirmed, name_only_match


def main():
    print("=" * 60)
    print("Update Contracts from OverTheCap Data")
    print("=" * 60)

    # Load contract data
    df = load_contracts()

    # Build lookup
    lookup = build_contract_lookup(df)

    # Apply to roster
    print(f"\nApplying contracts to: {ROSTER_FILE}")
    matched, skipped, team_confirmed, name_only = apply_contracts(ROSTER_FILE, lookup)

    total = matched + skipped
    pct = (matched / total * 100) if total > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"Total roster players:    {total}")
    print(f"Matched with contracts:  {matched} ({pct:.1f}%)")
    print(f"  - Team confirmed:      {team_confirmed}")
    print(f"  - Name-only match:     {name_only}")
    print(f"Skipped (no match):      {skipped}")
    print(f"\nAll updated players have salary==eSalary, guarantee==eGuarantee, length==eLength.")


if __name__ == "__main__":
    main()
