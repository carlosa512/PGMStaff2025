"""
Update Contracts from OverTheCap Data
======================================
Applies real NFL contract data (from nflverse/OverTheCap) to PGMRoster_2026_Final.json.

Reads ./reference/nflverse_contracts.parquet (current data through 2026) and matches
players by name to update:
  - salary / eSalary       (from average remaining base_salary or APY fallback)
  - guarantee / eGuarantee (from remaining guaranteed money)
  - length / eLength       (remaining years on contract)

Values in the parquet are in MILLIONS and are converted to whole dollars for PGM3.

Run AFTER trim_rosters.py so we only process players who survived roster cuts.

Usage:
    python scripts/update_contracts.py
    python scripts/update_contracts.py --report-path reference/contract_update_report.csv

Prerequisites:
    Run `python scripts/pull_nflverse_rosters.py` first to download nflverse_contracts.parquet
    Requires: pip install pandas pyarrow
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict

import pandas as pd

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
CONTRACTS_PARQUET = os.path.join(REPO_ROOT, "reference", "nflverse_contracts.parquet")
DEFAULT_REPORT_PATH = os.path.join(REPO_ROOT, "reference", "contract_update_report.csv")
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet"

# Current game season year
CURRENT_YEAR = 2026

# Roster team IDs that should be treated as teamless for matching.
TEAMLESS_TEAM_IDS = {"", "FA", "Free Agent", "Rookie"}

# Known roster aliases to normalize misspellings/nicknames to the contract dataset spelling.
ALIAS_NAME_MAP = {
    "micah parson": "micah parsons",
    "riq woolen": "tariq woolen",
}

STATUS_MATCHED_TEAM = "matched_team"
STATUS_MATCHED_NAME_ONLY = "matched_name_only"
STATUS_SKIPPED_NO_MATCH = "skipped_no_match"
STATUS_SKIPPED_TEAM_MISMATCH = "skipped_team_mismatch"
STATUS_SKIPPED_AMBIGUOUS = "skipped_ambiguous"

ALL_STATUSES = (
    STATUS_MATCHED_TEAM,
    STATUS_MATCHED_NAME_ONLY,
    STATUS_SKIPPED_NO_MATCH,
    STATUS_SKIPPED_TEAM_MISMATCH,
    STATUS_SKIPPED_AMBIGUOUS,
)

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


def apply_alias(normalized_name):
    """Apply known name aliases. Returns (canonical_name, alias_description)."""
    canonical_name = ALIAS_NAME_MAP.get(normalized_name, normalized_name)
    if canonical_name != normalized_name:
        return canonical_name, f"{normalized_name} -> {canonical_name}"
    return canonical_name, ""


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


def parse_int(value, default):
    """Parse an integer from contract fields, with a safe default."""
    if value is None or pd.isna(value):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
    future_years.sort(key=lambda x: x["year"])
    return future_years


def calculate_remaining_years(row):
    """Calculate remaining years using contract metadata (source of truth)."""
    years = parse_int(row.get("years"), 1)
    year_signed = parse_int(row.get("year_signed"), CURRENT_YEAR)
    remaining_years = max(1, year_signed + years - CURRENT_YEAR)
    return remaining_years, year_signed


def extract_contract_data(row):
    """
    Extract normalized contract payload for lookup.

    Salary uses average base_salary across remaining year rows when available.
    Falls back to APY when base_salary entries are missing.
    """
    year_data = extract_year_data(row.get("cols"))
    remaining_years, year_signed = calculate_remaining_years(row)

    base_salary_values = [entry["base_salary"] for entry in year_data if entry["base_salary"] > 0]
    if base_salary_values:
        avg_base_salary = sum(base_salary_values) / len(base_salary_values)
        salary = millions_to_dollars(avg_base_salary)
        salary_source = "avg_base_salary_remaining_years"
    else:
        salary = millions_to_dollars(row.get("apy"))
        salary_source = "apy_fallback"

    guaranteed_values = [entry["guaranteed_salary"] for entry in year_data if entry["guaranteed_salary"] > 0]
    if guaranteed_values:
        guarantee = sum(millions_to_dollars(value) for value in guaranteed_values)
    else:
        guarantee = millions_to_dollars(row.get("guaranteed"))

    return {
        "salary": salary,
        "guarantee": guarantee,
        "length": remaining_years,
        "team": resolve_team(row.get("team")),
        "original_name": str(row.get("player", "")),
        "year_signed": year_signed,
        "salary_source": salary_source,
        "has_year_data": len(year_data) > 0,
    }


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
    Build active-contract lookup tables:
      - by team key: (canonical_name, team_id) -> contract
      - by canonical name: canonical_name -> list[contract]
    """
    active_df = df[df["is_active"] == True].sort_values("year_signed", ascending=False)
    print(f"Active player contracts: {len(active_df)}")

    lookup_by_team = {}
    lookup_by_name = defaultdict(list)

    for _, row in active_df.iterrows():
        raw_name = str(row.get("player", ""))
        normalized_name = normalize_name(raw_name)
        canonical_name, _ = apply_alias(normalized_name)

        contract = extract_contract_data(row)
        contract["canonical_name"] = canonical_name

        key = (canonical_name, contract["team"])
        if key in lookup_by_team:
            continue
        lookup_by_team[key] = contract

    for (canonical_name, _team), contract in lookup_by_team.items():
        lookup_by_name[canonical_name].append(contract)

    with_year_data = sum(1 for v in lookup_by_team.values() if v["has_year_data"])
    print(f"Players with per-year breakdown: {with_year_data}")
    print(f"Unique active name+team lookup keys: {len(lookup_by_team)}")
    print(f"Unique active names in lookup: {len(lookup_by_name)}")

    return lookup_by_team, dict(lookup_by_name)


def select_contract_for_player(canonical_name, team_id, lookup_by_team, lookup_by_name):
    """Select the best contract for a roster player following safety rules."""
    candidates = lookup_by_name.get(canonical_name, [])
    if not candidates:
        return None, STATUS_SKIPPED_NO_MATCH, "no_active_contract_name_match"

    if team_id not in TEAMLESS_TEAM_IDS:
        contract = lookup_by_team.get((canonical_name, team_id))
        if contract:
            return contract, STATUS_MATCHED_TEAM, "team_confirmed"
        return None, STATUS_SKIPPED_TEAM_MISMATCH, "team_mismatch_for_name_match"

    if len(candidates) == 1:
        return candidates[0], STATUS_MATCHED_NAME_ONLY, "teamless_player_unique_name_match"

    return None, STATUS_SKIPPED_AMBIGUOUS, f"teamless_player_has_{len(candidates)}_candidates"


def write_report(report_path, rows):
    """Write CSV report for contract update outcomes."""
    report_dir = os.path.dirname(report_path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)

    fieldnames = [
        "roster_name",
        "roster_team",
        "normalized_name",
        "alias_used",
        "matched_contract_name",
        "matched_contract_team",
        "match_status",
        "salary_source",
        "reason",
    ]

    with open(report_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def apply_contracts(roster_file, lookup_by_team, lookup_by_name, report_path):
    """Match roster players to contracts, apply updates, and emit an audit report."""
    with open(roster_file, "r") as f:
        data = json.load(f)

    players = data if isinstance(data, list) else data.get("players", data.get("roster", []))

    status_counts = {status: 0 for status in ALL_STATUSES}
    report_rows = []

    for player in players:
        forename = player.get("forename", "")
        surname = player.get("surname", "")
        full_name = f"{forename} {surname}".strip()
        normalized_name = normalize_name(full_name)
        canonical_name, alias_used = apply_alias(normalized_name)
        team_id = (player.get("teamID", "") or "").strip()

        contract, status, reason = select_contract_for_player(
            canonical_name,
            team_id,
            lookup_by_team,
            lookup_by_name,
        )
        status_counts[status] += 1

        report_row = {
            "roster_name": full_name,
            "roster_team": team_id,
            "normalized_name": canonical_name,
            "alias_used": alias_used,
            "matched_contract_name": "",
            "matched_contract_team": "",
            "match_status": status,
            "salary_source": "",
            "reason": reason,
        }
        if not contract:
            candidates = lookup_by_name.get(canonical_name, [])
            if candidates and status in (STATUS_SKIPPED_TEAM_MISMATCH, STATUS_SKIPPED_AMBIGUOUS):
                candidate_names = sorted({candidate["original_name"] for candidate in candidates if candidate["original_name"]})
                candidate_teams = sorted({candidate["team"] or "UNKNOWN" for candidate in candidates})
                report_row["matched_contract_name"] = " | ".join(candidate_names)
                report_row["matched_contract_team"] = " | ".join(candidate_teams)
                report_row["reason"] = f"{reason};candidate_teams={report_row['matched_contract_team']}"
            report_rows.append(report_row)
            continue

        # Apply contract data (always keep pairs matched)
        player["salary"] = contract["salary"]
        player["eSalary"] = contract["salary"]
        player["guarantee"] = contract["guarantee"]
        player["eGuarantee"] = contract["guarantee"]
        player["length"] = contract["length"]
        player["eLength"] = contract["length"]

        report_row["matched_contract_name"] = contract["original_name"]
        report_row["matched_contract_team"] = contract["team"] or ""
        report_row["salary_source"] = contract["salary_source"]
        report_rows.append(report_row)

    write_report(report_path, report_rows)

    # Save
    with open(roster_file, "w") as f:
        json.dump(data, f, indent=2)

    return status_counts, len(players)


def main():
    parser = argparse.ArgumentParser(description="Update PGM3 roster contracts from nflverse parquet data.")
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help=f"Path to CSV audit report (default: {DEFAULT_REPORT_PATH})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Update Contracts from OverTheCap Data (Parquet)")
    print("=" * 60)

    df = load_contracts()
    lookup_by_team, lookup_by_name = build_contract_lookup(df)

    print(f"\nApplying contracts to: {ROSTER_FILE}")
    status_counts, total = apply_contracts(
        ROSTER_FILE,
        lookup_by_team,
        lookup_by_name,
        args.report_path,
    )

    matched = status_counts[STATUS_MATCHED_TEAM] + status_counts[STATUS_MATCHED_NAME_ONLY]
    skipped = (
        status_counts[STATUS_SKIPPED_NO_MATCH]
        + status_counts[STATUS_SKIPPED_TEAM_MISMATCH]
        + status_counts[STATUS_SKIPPED_AMBIGUOUS]
    )
    pct = (matched / total * 100) if total > 0 else 0

    print(f"\n{'=' * 60}")
    print(f"  RESULTS")
    print(f"{'=' * 60}")
    print(f"Total roster players:    {total}")
    print(f"Matched with contracts:  {matched} ({pct:.1f}%)")
    print(f"  - {STATUS_MATCHED_TEAM}: {status_counts[STATUS_MATCHED_TEAM]}")
    print(f"  - {STATUS_MATCHED_NAME_ONLY}: {status_counts[STATUS_MATCHED_NAME_ONLY]}")
    print(f"  - {STATUS_SKIPPED_NO_MATCH}: {status_counts[STATUS_SKIPPED_NO_MATCH]}")
    print(f"  - {STATUS_SKIPPED_TEAM_MISMATCH}: {status_counts[STATUS_SKIPPED_TEAM_MISMATCH]}")
    print(f"  - {STATUS_SKIPPED_AMBIGUOUS}: {status_counts[STATUS_SKIPPED_AMBIGUOUS]}")
    print(f"Skipped total:           {skipped}")
    print(f"Report written to:       {args.report_path}")
    print(f"\nAll updated players have salary==eSalary, guarantee==eGuarantee, length==eLength.")


if __name__ == "__main__":
    main()
