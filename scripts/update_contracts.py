"""
Update Contracts from OverTheCap Data
======================================
Applies real NFL contract data (from nflverse/OverTheCap) to PGMRoster_2026_Final.json.

Reads ./reference/nflverse_contracts.parquet (current data through 2026) and matches
players by name to update:
  - salary / eSalary       (from remaining-year base salary average or APY fallback)
  - guarantee / eGuarantee (from current-year bonus components)
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
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet"

DEFAULT_REPORT_PATH = os.path.join(REPO_ROOT, "reference", "contract_update_report.csv")
DEFAULT_TEAM_CAP_REPORT_PATH = os.path.join(REPO_ROOT, "reference", "team_cap_report.csv")
DEFAULT_RELEASE_OVERRIDES_PATH = os.path.join(REPO_ROOT, "reference", "release_overrides_2026.csv")

# Current game season year
CURRENT_YEAR = 2026

# PGM in-game budget shown for the season cap screen.
TEAM_SEASON_BUDGET = 279_200_000

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
STATUS_RELEASE_OVERRIDE = "release_override"
STATUS_FA_NORMALIZED = "fa_normalized"

ALL_STATUSES = (
    STATUS_MATCHED_TEAM,
    STATUS_MATCHED_NAME_ONLY,
    STATUS_SKIPPED_NO_MATCH,
    STATUS_SKIPPED_TEAM_MISMATCH,
    STATUS_SKIPPED_AMBIGUOUS,
    STATUS_RELEASE_OVERRIDE,
    STATUS_FA_NORMALIZED,
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
    name = re.sub(r'\s+(jr\.?|sr\.?|ii|iii|iv|v)$', '', name)
    name = name.replace(".", "").replace("'", "").replace("\u2019", "")
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


def parse_float(value, default=0.0):
    """Parse a float from contract fields, with a safe default."""
    if value is None or pd.isna(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def extract_year_data(cols):
    """
    Extract valid future/current contract rows from 'cols'.
    Returns rows for years >= CURRENT_YEAR with cap_number > 0, sorted by year.
    """
    if cols is None:
        return []

    entries = list(cols) if hasattr(cols, "__iter__") else []
    rows = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue

        year_str = str(entry.get("year", ""))
        if year_str == "Total" or not year_str.isdigit():
            continue

        year_int = int(year_str)
        if year_int < CURRENT_YEAR:
            continue

        cap_number = parse_float(entry.get("cap_number", 0), 0.0)
        if cap_number <= 0:
            continue

        rows.append(
            {
                "year": year_int,
                "cap_number": cap_number,
                "base_salary": parse_float(entry.get("base_salary", 0), 0.0),
                "guaranteed_salary": parse_float(entry.get("guaranteed_salary", 0), 0.0),
                "prorated_bonus": parse_float(entry.get("prorated_bonus", 0), 0.0),
                "roster_bonus": parse_float(entry.get("roster_bonus", 0), 0.0),
                "option_bonus": parse_float(entry.get("option_bonus", 0), 0.0),
                "other_bonus": parse_float(entry.get("other_bonus", 0), 0.0),
                "per_game_roster_bonus": parse_float(entry.get("per_game_roster_bonus", 0), 0.0),
                "workout_bonus": parse_float(entry.get("workout_bonus", 0), 0.0),
            }
        )

    rows.sort(key=lambda x: x["year"])
    return rows


def calculate_remaining_years(row):
    """Calculate remaining years using contract metadata (source of truth)."""
    years = parse_int(row.get("years"), 1)
    year_signed = parse_int(row.get("year_signed"), CURRENT_YEAR)
    remaining_years = max(1, year_signed + years - CURRENT_YEAR)
    return remaining_years, year_signed


def get_current_year_entry(year_data):
    """Return current year entry if present, else None."""
    for entry in year_data:
        if entry["year"] == CURRENT_YEAR:
            return entry
    return None


def extract_contract_data(row):
    """
    Extract normalized contract payload for lookup.

    Salary: average base salary over first N valid rows where N=remaining years (fallback APY).
    Guarantee: current-year bonus components fallback to current-year guaranteed_salary else zero.
    Length: remaining years from metadata.
    """
    year_data = extract_year_data(row.get("cols"))
    remaining_years, year_signed = calculate_remaining_years(row)

    # Salary should only consider the first remaining contract years, not arbitrary
    # later seasons that can inflate present-day values.
    salary_window = year_data[:remaining_years]
    base_salary_values = [entry["base_salary"] for entry in salary_window if entry["base_salary"] > 0]

    if base_salary_values:
        salary = millions_to_dollars(sum(base_salary_values) / len(base_salary_values))
        salary_source = "avg_base_salary_remaining_years_limited"
    else:
        salary = millions_to_dollars(row.get("apy"))
        salary_source = "apy_fallback"

    current_year_entry = get_current_year_entry(year_data)
    guarantee = 0
    guarantee_source = "zero_no_current_year_data"

    if current_year_entry:
        bonus_millions = (
            current_year_entry["prorated_bonus"]
            + current_year_entry["roster_bonus"]
            + current_year_entry["option_bonus"]
            + current_year_entry["other_bonus"]
            + current_year_entry["per_game_roster_bonus"]
            + current_year_entry["workout_bonus"]
        )
        if bonus_millions > 0:
            guarantee = millions_to_dollars(bonus_millions)
            guarantee_source = "current_year_bonus_components"
        elif current_year_entry["guaranteed_salary"] > 0:
            guarantee = millions_to_dollars(current_year_entry["guaranteed_salary"])
            guarantee_source = "current_year_guaranteed_salary_fallback"
        else:
            guarantee_source = "zero_no_current_year_bonus_or_guaranteed"

    return {
        "salary": salary,
        "guarantee": guarantee,
        "length": remaining_years,
        "team": resolve_team(row.get("team")),
        "original_name": str(row.get("player", "")),
        "year_signed": year_signed,
        "salary_source": salary_source,
        "guarantee_source": guarantee_source,
        "has_year_data": len(year_data) > 0,
    }


def load_contracts():
    """Load contract data from local parquet or download from nflverse."""
    if os.path.exists(CONTRACTS_PARQUET):
        print(f"Loading contracts from: {CONTRACTS_PARQUET}")
        df = pd.read_parquet(CONTRACTS_PARQUET)
    else:
        print("Local contracts file not found. Downloading from nflverse...")
        df = pd.read_parquet(CONTRACTS_URL)
        os.makedirs(os.path.dirname(CONTRACTS_PARQUET), exist_ok=True)
        df.to_parquet(CONTRACTS_PARQUET, index=False)
        print(f"Saved to: {CONTRACTS_PARQUET}")

    print(f"Total contract records: {len(df)}")
    print(f"Max year_signed: {df['year_signed'].max()}")
    return df


def load_release_overrides(path):
    """Load explicit release overrides by canonical player name from CSV."""
    overrides = {}
    if not os.path.exists(path):
        print(f"Release overrides file not found: {path} (continuing without overrides)")
        return overrides

    with open(path, "r", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            forename = str(row.get("forename", "")).strip()
            surname = str(row.get("surname", "")).strip()
            if not forename or not surname:
                continue
            canonical_name, _ = apply_alias(normalize_name(f"{forename} {surname}"))
            reason = str(row.get("reason", "")).strip() or "release_override"
            overrides[canonical_name] = reason

    print(f"Loaded release overrides: {len(overrides)}")
    return overrides


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

    with_year_data = sum(1 for value in lookup_by_team.values() if value["has_year_data"])
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


def ensure_pair_fields(player):
    """Ensure display and engine contract fields are paired."""
    player["salary"] = int(player.get("salary", 0) or 0)
    player["eSalary"] = player["salary"]
    player["guarantee"] = int(player.get("guarantee", 0) or 0)
    player["eGuarantee"] = player["guarantee"]
    player["length"] = int(player.get("length", 0) or 0)
    player["eLength"] = player["length"]


def zero_contract_fields(player, free_agent_length=0):
    """Zero all contract fields (used for Free Agent normalization)."""
    changed = (
        int(player.get("salary", 0) or 0) != 0
        or int(player.get("guarantee", 0) or 0) != 0
        or int(player.get("length", 0) or 0) != free_agent_length
        or int(player.get("eSalary", 0) or 0) != 0
        or int(player.get("eGuarantee", 0) or 0) != 0
        or int(player.get("eLength", 0) or 0) != free_agent_length
    )
    player["salary"] = 0
    player["eSalary"] = 0
    player["guarantee"] = 0
    player["eGuarantee"] = 0
    player["length"] = free_agent_length
    player["eLength"] = free_agent_length
    return changed


def write_player_report(report_path, rows):
    """Write player-level CSV report for contract update outcomes."""
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
        "guarantee_source",
        "reason",
    ]

    with open(report_path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_team_cap_report(report_path, players):
    """Write team-level cap report using salary + guarantee as cap hit proxy."""
    report_dir = os.path.dirname(report_path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)

    team_ids = sorted(set(ABBREV_TO_ID.values()))
    team_totals = {team: {"salary": 0, "bonus": 0} for team in team_ids}

    for player in players:
        team_id = str(player.get("teamID", "") or "").strip()
        if team_id not in team_totals:
            continue
        team_totals[team_id]["salary"] += int(player.get("salary", 0) or 0)
        team_totals[team_id]["bonus"] += int(player.get("guarantee", 0) or 0)

    with open(report_path, "w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["team", "salary_total", "bonus_total", "cap_hit_total", "budget", "remaining_space"],
        )
        writer.writeheader()
        for team in team_ids:
            salary_total = team_totals[team]["salary"]
            bonus_total = team_totals[team]["bonus"]
            cap_hit_total = salary_total + bonus_total
            remaining_space = TEAM_SEASON_BUDGET - cap_hit_total
            writer.writerow(
                {
                    "team": team,
                    "salary_total": salary_total,
                    "bonus_total": bonus_total,
                    "cap_hit_total": cap_hit_total,
                    "budget": TEAM_SEASON_BUDGET,
                    "remaining_space": remaining_space,
                }
            )


def apply_contracts(
    roster_file,
    lookup_by_team,
    lookup_by_name,
    release_overrides,
    player_report_path,
    team_cap_report_path,
):
    """Match roster players to contracts, apply updates, and emit reports."""
    with open(roster_file, "r") as handle:
        data = json.load(handle)

    players = data if isinstance(data, list) else data.get("players", data.get("roster", []))

    status_counts = {status: 0 for status in ALL_STATUSES}
    report_rows = []

    for player in players:
        forename = player.get("forename", "")
        surname = player.get("surname", "")
        full_name = f"{forename} {surname}".strip()
        normalized_name = normalize_name(full_name)
        canonical_name, alias_used = apply_alias(normalized_name)
        team_id = str(player.get("teamID", "") or "").strip()

        if canonical_name in release_overrides and team_id not in TEAMLESS_TEAM_IDS:
            player["teamID"] = "Free Agent"
            changed = zero_contract_fields(player, free_agent_length=0)
            status_counts[STATUS_RELEASE_OVERRIDE] += 1
            report_rows.append(
                {
                    "roster_name": full_name,
                    "roster_team": team_id,
                    "normalized_name": canonical_name,
                    "alias_used": alias_used,
                    "matched_contract_name": "",
                    "matched_contract_team": "",
                    "match_status": STATUS_RELEASE_OVERRIDE,
                    "salary_source": "",
                    "guarantee_source": "",
                    "reason": f"override_to_free_agent:{release_overrides[canonical_name]};contract_zeroed={changed}",
                }
            )
            continue

        if team_id in {"", "FA", "Free Agent"}:
            changed = zero_contract_fields(player, free_agent_length=0)
            status_counts[STATUS_FA_NORMALIZED] += 1
            report_rows.append(
                {
                    "roster_name": full_name,
                    "roster_team": team_id,
                    "normalized_name": canonical_name,
                    "alias_used": alias_used,
                    "matched_contract_name": "",
                    "matched_contract_team": "",
                    "match_status": STATUS_FA_NORMALIZED,
                    "salary_source": "",
                    "guarantee_source": "",
                    "reason": "free_agent_contract_zeroed" if changed else "free_agent_contract_already_zero",
                }
            )
            continue

        if team_id == "Rookie":
            ensure_pair_fields(player)
            status_counts[STATUS_SKIPPED_NO_MATCH] += 1
            report_rows.append(
                {
                    "roster_name": full_name,
                    "roster_team": team_id,
                    "normalized_name": canonical_name,
                    "alias_used": alias_used,
                    "matched_contract_name": "",
                    "matched_contract_team": "",
                    "match_status": STATUS_SKIPPED_NO_MATCH,
                    "salary_source": "",
                    "guarantee_source": "",
                    "reason": "rookie_contract_not_managed_by_update_contracts",
                }
            )
            continue

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
            "guarantee_source": "",
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

        player["salary"] = contract["salary"]
        player["eSalary"] = contract["salary"]
        player["guarantee"] = contract["guarantee"]
        player["eGuarantee"] = contract["guarantee"]
        player["length"] = contract["length"]
        player["eLength"] = contract["length"]

        report_row["matched_contract_name"] = contract["original_name"]
        report_row["matched_contract_team"] = contract["team"] or ""
        report_row["salary_source"] = contract["salary_source"]
        report_row["guarantee_source"] = contract["guarantee_source"]
        report_rows.append(report_row)

    write_player_report(player_report_path, report_rows)
    write_team_cap_report(team_cap_report_path, players)

    with open(roster_file, "w") as handle:
        json.dump(data, handle, indent=2)

    return status_counts, len(players)


def main():
    parser = argparse.ArgumentParser(description="Update PGM3 roster contracts from nflverse parquet data.")
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help=f"Path to player-level CSV audit report (default: {DEFAULT_REPORT_PATH})",
    )
    parser.add_argument(
        "--team-cap-report-path",
        default=DEFAULT_TEAM_CAP_REPORT_PATH,
        help=f"Path to team-level cap CSV report (default: {DEFAULT_TEAM_CAP_REPORT_PATH})",
    )
    parser.add_argument(
        "--release-overrides-path",
        default=DEFAULT_RELEASE_OVERRIDES_PATH,
        help=f"Path to release override CSV (default: {DEFAULT_RELEASE_OVERRIDES_PATH})",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Update Contracts from OverTheCap Data (Parquet)")
    print("=" * 60)

    df = load_contracts()
    release_overrides = load_release_overrides(args.release_overrides_path)
    lookup_by_team, lookup_by_name = build_contract_lookup(df)

    print(f"\nApplying contracts to: {ROSTER_FILE}")
    status_counts, total = apply_contracts(
        ROSTER_FILE,
        lookup_by_team,
        lookup_by_name,
        release_overrides,
        args.report_path,
        args.team_cap_report_path,
    )

    matched = status_counts[STATUS_MATCHED_TEAM] + status_counts[STATUS_MATCHED_NAME_ONLY]
    skipped = (
        status_counts[STATUS_SKIPPED_NO_MATCH]
        + status_counts[STATUS_SKIPPED_TEAM_MISMATCH]
        + status_counts[STATUS_SKIPPED_AMBIGUOUS]
    )
    pct = (matched / total * 100) if total > 0 else 0

    print(f"\n{'=' * 60}")
    print("  RESULTS")
    print(f"{'=' * 60}")
    print(f"Total roster players:    {total}")
    print(f"Matched with contracts:  {matched} ({pct:.1f}%)")
    print(f"  - {STATUS_MATCHED_TEAM}: {status_counts[STATUS_MATCHED_TEAM]}")
    print(f"  - {STATUS_MATCHED_NAME_ONLY}: {status_counts[STATUS_MATCHED_NAME_ONLY]}")
    print(f"  - {STATUS_SKIPPED_NO_MATCH}: {status_counts[STATUS_SKIPPED_NO_MATCH]}")
    print(f"  - {STATUS_SKIPPED_TEAM_MISMATCH}: {status_counts[STATUS_SKIPPED_TEAM_MISMATCH]}")
    print(f"  - {STATUS_SKIPPED_AMBIGUOUS}: {status_counts[STATUS_SKIPPED_AMBIGUOUS]}")
    print(f"  - {STATUS_RELEASE_OVERRIDE}: {status_counts[STATUS_RELEASE_OVERRIDE]}")
    print(f"  - {STATUS_FA_NORMALIZED}: {status_counts[STATUS_FA_NORMALIZED]}")
    print(f"Skipped total:           {skipped}")
    print(f"Player report written:   {args.report_path}")
    print(f"Team cap report written: {args.team_cap_report_path}")
    print("\nAll updated players have salary==eSalary, guarantee==eGuarantee, length==eLength.")


if __name__ == "__main__":
    main()
