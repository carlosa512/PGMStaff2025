"""
Update Contracts from OverTheCap Data
======================================
Applies real NFL contract data (from nflverse/OverTheCap) to PGMRoster_2026_Final.json.

Reads ./reference/nflverse_contracts.parquet (current data through 2026) and matches
players by name to update:
  - salary / eSalary       (from per-year cap_number or APY)
  - guarantee / eGuarantee (from remaining guaranteed money)
  - length / eLength       (remaining years on contract)

Values in the parquet are in MILLIONS and are converted to whole dollars for PGM3.

Run AFTER trim_rosters.py so we only process players who survived roster cuts.

Usage:
    python scripts/update_contracts.py

Prerequisites:
    Run `python scripts/pull_nflverse_rosters.py` first to download nflverse_contracts.parquet
    Requires: pip install pandas pyarrow
"""

import json
import os
import re

import pandas as pd

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
CONTRACTS_PARQUET = os.path.join(REPO_ROOT, "reference", "nflverse_contracts.parquet")
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet"

# Current game season year
CURRENT_YEAR = 2026

# Map OverTheCap team names to PGM3 team IDs
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


def millions_to_dollars(val):
    """Convert a value in millions to whole dollars. Returns 0 if invalid."""
    if val is None or pd.isna(val):
        return 0
    return int(round(float(val) * 1_000_000))


def normalize_name(name):
    """Normalize a player name for matching: lowercase, strip suffixes, punctuation."""
    name = name.strip().lower()
    # Remove common suffixes
    name = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)$', '', name)
    # Remove periods and apostrophes
    name = name.replace(".", "").replace("'", "").replace("\u2019", "")
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    return name


def resolve_team(otc_team):
    """Convert OverTheCap team name to PGM3 team ID."""
    if not otc_team or pd.isna(otc_team):
        return None
    otc_team = str(otc_team).strip()

    if otc_team in TEAM_NAME_TO_ID:
        return TEAM_NAME_TO_ID[otc_team]

    # Multi-team format like "DEN/SEA" - first team is current
    if "/" in otc_team:
        first_team = otc_team.split("/")[0].strip()
        if first_team in ABBREV_TO_ID:
            return ABBREV_TO_ID[first_team]
        if first_team in TEAM_NAME_TO_ID:
            return TEAM_NAME_TO_ID[first_team]

    if otc_team in ABBREV_TO_ID:
        return ABBREV_TO_ID[otc_team]

    return None


def extract_year_data(cols):
    """
    Extract per-year contract breakdown from the 'cols' array.
    Returns list of year entries (excluding 'Total' row) for years >= CURRENT_YEAR.
    Each entry has: year, cap_number, base_salary, guaranteed_salary (all in millions).
    """
    if cols is None:
        return []

    # cols can be a numpy array or list of dicts
    entries = list(cols) if hasattr(cols, '__iter__') else []
    future_years = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        year_str = str(entry.get("year", ""))
        if year_str == "Total" or not year_str.isdigit():
            continue
        year_int = int(year_str)
        if year_int >= CURRENT_YEAR:
            cap = entry.get("cap_number", 0) or 0
            # Skip void years (zero cap hit)
            if float(cap) > 0:
                future_years.append({
                    "year": year_int,
                    "cap_number": float(cap),
                    "base_salary": float(entry.get("base_salary", 0) or 0),
                    "guaranteed_salary": float(entry.get("guaranteed_salary", 0) or 0),
                })
    return future_years


def load_contracts():
    """Load contract data from local parquet or download from nflverse."""
    if os.path.exists(CONTRACTS_PARQUET):
        print(f"Loading contracts from: {CONTRACTS_PARQUET}")
        df = pd.read_parquet(CONTRACTS_PARQUET)
    else:
        print(f"Local contracts file not found. Downloading from nflverse...")
        df = pd.read_parquet(CONTRACTS_URL)
        os.makedirs(os.path.dirname(CONTRACTS_PARQUET), exist_ok=True)
        df.to_parquet(CONTRACTS_PARQUET, index=False)
        print(f"Saved to: {CONTRACTS_PARQUET}")

    print(f"Total contract records: {len(df)}")
    print(f"Max year_signed: {df['year_signed'].max()}")
    return df


def build_contract_lookup(df):
    """
    Build a lookup dict: normalized_name -> contract info.
    Uses per-year breakdowns from 'cols' for accurate 2026 salary/guarantee data.
    Prefers active contracts; uses inactive as fallback.
    """
    df_sorted = df.sort_values("year_signed", ascending=False)

    active_count = int(df["is_active"].sum())
    print(f"Active player contracts: {active_count}")

    def _extract(row):
        """Extract contract data using per-year breakdowns when available."""
        year_data = extract_year_data(row.get("cols"))

        if year_data:
            # Use the current year's cap_number as salary
            current_year_entry = next((y for y in year_data if y["year"] == CURRENT_YEAR), year_data[0])
            salary = millions_to_dollars(current_year_entry["cap_number"])

            # Remaining guaranteed = sum of guaranteed_salary for all future years
            guarantee = sum(millions_to_dollars(y["guaranteed_salary"]) for y in year_data)

            # Remaining years = count of future year entries with non-zero cap
            length = len(year_data)
        else:
            # Fallback to top-level APY and guaranteed fields (in millions)
            salary = millions_to_dollars(row.get("apy"))
            guarantee = millions_to_dollars(row.get("guaranteed"))

            # Calculate remaining years from year_signed + years
            years = int(row["years"]) if pd.notna(row.get("years")) else 1
            year_signed = int(row["year_signed"]) if pd.notna(row.get("year_signed")) else CURRENT_YEAR
            length = max(1, year_signed + years - CURRENT_YEAR)

        length = max(1, length)

        return {
            "salary": salary,
            "guarantee": guarantee,
            "length": length,
            "team": resolve_team(row.get("team")),
            "original_name": row["player"],
            "year_signed": int(row["year_signed"]) if pd.notna(row.get("year_signed")) else CURRENT_YEAR,
            "has_year_data": len(year_data) > 0,
        }

    # First pass: active contracts only
    lookup = {}
    for _, row in df_sorted[df_sorted["is_active"] == True].iterrows():
        norm_name = normalize_name(str(row["player"]))
        if norm_name not in lookup:
            lookup[norm_name] = _extract(row)

    active_unique = len(lookup)

    # Second pass: inactive contracts as fallback
    inactive_added = 0
    for _, row in df_sorted[df_sorted["is_active"] != True].iterrows():
        norm_name = normalize_name(str(row["player"]))
        if norm_name not in lookup:
            lookup[norm_name] = _extract(row)
            inactive_added += 1

    print(f"Unique players in lookup: {len(lookup)} ({active_unique} active, {inactive_added} inactive fallback)")

    # Count how many have per-year data
    with_year_data = sum(1 for v in lookup.values() if v["has_year_data"])
    print(f"Players with per-year breakdown: {with_year_data}")

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

        if contract["team"] and team_id not in ("Free Agent", "Rookie", ""):
            if contract["team"] == team_id:
                team_confirmed += 1
            else:
                name_only_match += 1
        else:
            name_only_match += 1

        # Apply contract data (always keep pairs matched)
        if contract["salary"]:
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
    print("Update Contracts from OverTheCap Data (Parquet)")
    print("=" * 60)

    df = load_contracts()
    lookup = build_contract_lookup(df)

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
