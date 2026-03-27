"""
Player Data Audit Fix - 2026
==============================
Performs targeted fixes and a nflverse-backed sweep for stale/wrong-team players.

Targeted fixes:
  1. Delete fake white "Joe Milton III" duplicate (ID: FC174C35)
  2. Rename real Black "Joe Milton" surname → "Milton III" (ID: 6BE81FCB)
  3. Move Latavius Murray to Free Agent + lower rating/stats (ID: 5F1D5493)
  4. Delete Marshawn Kneeland (deceased) (ID: 301A9E0D)

Broader sweep via nflverse_rosters_2026.csv:
  - For each PGM team player matched in nflverse:
    - If nflverse status is UFA/RFA → move to FA in PGM, zero contract
    - If nflverse shows a different team (ACT) → move to FA in PGM, zero contract
    - If nflverse shows same team ACT → no change
  - Unmatched players (generated/fictional) → skipped

Age corrections via nflverse_players.csv:
  - Compute age as of 2026-03-26 from birth_date for matched players
  - Update age in PGM where it differs

Usage:
    python scripts/fix_player_audit_2026.py
"""

import json
import os
import re
import unicodedata
from datetime import date

import pandas as pd

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
ROSTERS_CSV = os.path.join(REPO_ROOT, "reference", "nflverse_rosters_2026.csv")

AGE_DATE = date(2026, 3, 26)

# nflverse team code → PGM teamID
TEAM_MAP = {
    "LA": "LAR",
}

# PGM teamID → nflverse team code (reverse, plus identity)
PGM_TO_NFL = {v: k for k, v in TEAM_MAP.items()}

# Targeted fix IDs
ID_FAKE_MILTON_III = "FC174C35-2FA9-4CD1-8C7B-1102A7149AC7"
ID_REAL_MILTON = "6BE81FCB-DCC6-4485-8E4B-3D15E925D7EB"
ID_MURRAY = "5F1D5493-2E63-40B4-8BB4-1FE2DDE7E602"
ID_KNEELAND = "301A9E0D-5F8A-409F-935B-208D37B4E7C9"

TEAMLESS = {"Free Agent", "Rookie", "", None}

# RB stats that should be reduced for Murray (active skill stats, not pure athletic)
MURRAY_SKILL_STATS = [
    "passBlock", "rushBlock", "routeRun", "ballSecurity", "trucking",
    "elusiveness", "intelligence", "discipline", "vision", "decisions",
    "catching", "skillMove", "releaseLine",
]
MURRAY_NEW_RATING = 68
MURRAY_NEW_SKILL_STAT = 75  # down from 86


def normalize_name(name: str) -> str:
    """Lowercase, remove punctuation/accents, collapse whitespace."""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


def strip_suffix(name: str) -> str:
    """Remove trailing generational suffixes (jr, sr, ii, iii, iv, v)."""
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)\s*$", "", name).strip()


def build_nflverse_lookup(rosters_df: pd.DataFrame) -> dict:
    """
    Returns dict: normalized_full_name → (nfl_team, status)
    For duplicate names, keeps ACT over UFA/RFA.
    """
    lookup = {}
    status_priority = {"ACT": 0, "RFA": 1, "UFA": 2}

    for _, row in rosters_df.iterrows():
        full = normalize_name(str(row["full_name"]))
        nfl_team = str(row["team"])
        status = str(row["status"])
        pgm_team = TEAM_MAP.get(nfl_team, nfl_team)

        if full not in lookup:
            lookup[full] = (pgm_team, status)
        else:
            existing_status = lookup[full][1]
            if status_priority.get(status, 9) < status_priority.get(existing_status, 9):
                lookup[full] = (pgm_team, status)

    return lookup


def build_birthdate_lookup(rosters_df: pd.DataFrame) -> dict:
    """
    Returns dict: normalized_full_name → birth_date (date object).
    Sourced ONLY from nflverse_rosters_2026 (current season active/UFA players),
    NOT the full historical players DB — avoids false matches on common names.
    """
    lookup = {}
    for _, row in rosters_df.iterrows():
        full = str(row.get("full_name", "") or "")
        bd = row.get("birth_date", "")
        if not full or not bd or pd.isna(bd):
            continue
        try:
            bd_date = date.fromisoformat(str(bd)[:10])
        except ValueError:
            continue
        norm = normalize_name(full)
        if norm not in lookup:
            lookup[norm] = bd_date
    return lookup


def compute_age(birth: date, as_of: date) -> int:
    years = as_of.year - birth.year
    if (as_of.month, as_of.day) < (birth.month, birth.day):
        years -= 1
    return years


def zero_contract(player: dict) -> None:
    for field in ("salary", "eSalary", "guarantee", "eGuarantee", "length", "eLength"):
        player[field] = 0


def main():
    # Load roster
    with open(ROSTER_FILE, encoding="utf-8") as f:
        roster = json.load(f)
    print(f"Loaded {len(roster)} players from {ROSTER_FILE}")

    # Load nflverse data
    rosters_df = pd.read_csv(ROSTERS_CSV)
    nfl_lookup = build_nflverse_lookup(rosters_df)
    # Birth dates sourced only from 2026 roster CSV to avoid false matches
    # on common names against the full historical player database
    bd_lookup = build_birthdate_lookup(rosters_df)

    # -----------------------------------------------------------------------
    # TARGETED FIXES
    # -----------------------------------------------------------------------
    new_roster = []
    targeted_log = []

    for player in roster:
        pid = player.get("iden", "")

        # 1. Delete fake Joe Milton III (white)
        if pid == ID_FAKE_MILTON_III:
            targeted_log.append(f"  [DELETE] Fake Joe Milton III (Head1a/white, ID {pid})")
            continue  # skip → effectively deletes

        # 2. Rename real Joe Milton → Joe Milton III
        if pid == ID_REAL_MILTON:
            old_surname = player.get("surname", "")
            player["surname"] = "Milton III"
            targeted_log.append(
                f"  [RENAME] Joe '{old_surname}' → surname='Milton III' (ID {pid})"
            )

        # 3. Latavius Murray → FA + lower stats
        if pid == ID_MURRAY:
            player["teamID"] = "Free Agent"
            zero_contract(player)
            player["rating"] = MURRAY_NEW_RATING
            player["potential"] = MURRAY_NEW_RATING
            for stat in MURRAY_SKILL_STATS:
                if player.get(stat, 0) > 0:
                    player[stat] = MURRAY_NEW_SKILL_STAT
            targeted_log.append(
                f"  [FA+LOWER] Latavius Murray → Free Agent, rating={MURRAY_NEW_RATING}, "
                f"skill stats={MURRAY_NEW_SKILL_STAT} (ID {pid})"
            )

        # 4. Delete Marshawn Kneeland
        if pid == ID_KNEELAND:
            targeted_log.append(f"  [DELETE] Marshawn Kneeland (deceased, ID {pid})")
            continue  # skip → effectively deletes

        new_roster.append(player)

    print("\n--- TARGETED FIXES ---")
    for line in targeted_log:
        print(line)
    print(f"  Players before: {len(roster)}, after targeted fixes: {len(new_roster)}")

    # -----------------------------------------------------------------------
    # BROADER SWEEP: wrong-team / FA status players
    # -----------------------------------------------------------------------
    sweep_moved = []
    sweep_skipped_no_match = 0

    for player in new_roster:
        team = player.get("teamID", "")
        if team in TEAMLESS:
            continue  # skip FA/Rookie/blank

        full_name = f"{player.get('forename', '')} {player.get('surname', '')}".strip()
        norm = normalize_name(full_name)
        norm_no_suffix = strip_suffix(norm)

        # Try exact match, then suffix-stripped match
        nfl_entry = nfl_lookup.get(norm) or nfl_lookup.get(norm_no_suffix)

        if nfl_entry is None:
            sweep_skipped_no_match += 1
            continue

        nfl_team, nfl_status = nfl_entry

        if nfl_status in ("UFA", "RFA"):
            # Player is a free agent in nflverse → move to FA in PGM
            player["teamID"] = "Free Agent"
            zero_contract(player)
            sweep_moved.append(
                f"  [FA-{nfl_status}] {full_name} was {team} → Free Agent "
                f"(nflverse: {nfl_status})"
            )
        elif nfl_status == "ACT" and nfl_team != team:
            # Player is active but on a different team → they've been traded/released
            player["teamID"] = "Free Agent"
            zero_contract(player)
            sweep_moved.append(
                f"  [WRONG-TEAM] {full_name}: PGM={team} but nflverse={nfl_team} (ACT) → Free Agent"
            )
        # else: same team ACT → no change

    print(f"\n--- NFLVERSE SWEEP: MOVED TO FA ({len(sweep_moved)}) ---")
    for line in sweep_moved:
        print(line)
    print(f"  Players not in nflverse (skipped): {sweep_skipped_no_match}")

    # -----------------------------------------------------------------------
    # AGE CORRECTIONS
    # Only applied when the player's PGM team matches the nflverse team, or
    # when the player is FA in both PGM and nflverse (UFA/RFA).
    # This prevents fictional/generated players sharing a common name from
    # getting their age clobbered.
    # -----------------------------------------------------------------------
    age_corrections = []

    for player in new_roster:
        full_name = f"{player.get('forename', '')} {player.get('surname', '')}".strip()
        norm = normalize_name(full_name)
        norm_no_suffix = strip_suffix(norm)

        birth = bd_lookup.get(norm) or bd_lookup.get(norm_no_suffix)
        if birth is None:
            continue

        nfl_entry = nfl_lookup.get(norm) or nfl_lookup.get(norm_no_suffix)
        if nfl_entry is None:
            continue

        nfl_team, nfl_status = nfl_entry
        pgm_team = player.get("teamID", "")

        # Only correct age when we can confidently identify this as the same player:
        # 1. Active players: PGM team matches nflverse team
        # 2. Free agents: player is FA in PGM and nflverse shows UFA/RFA
        is_fa_in_pgm = pgm_team in TEAMLESS
        is_fa_in_nfl = nfl_status in ("UFA", "RFA")

        team_match = (pgm_team == nfl_team) and nfl_status == "ACT"
        fa_match = is_fa_in_pgm and is_fa_in_nfl

        if not (team_match or fa_match):
            continue

        correct_age = compute_age(birth, AGE_DATE)
        current_age = player.get("age")

        if current_age != correct_age:
            age_corrections.append(
                f"  [AGE] {full_name}: {current_age} → {correct_age} "
                f"(born {birth}, team={pgm_team})"
            )
            player["age"] = correct_age

    print(f"\n--- AGE CORRECTIONS ({len(age_corrections)}) ---")
    for line in age_corrections:
        print(line)

    # -----------------------------------------------------------------------
    # SAVE
    # -----------------------------------------------------------------------
    with open(ROSTER_FILE, "w", encoding="utf-8") as f:
        json.dump(new_roster, f, indent=2, ensure_ascii=False)

    total_removed = len(roster) - len(new_roster)
    print(f"\n--- SUMMARY ---")
    print(f"  Targeted deletions : {total_removed} (Kneeland + fake Milton III)")
    print(f"  Players moved to FA: {len(sweep_moved)} (sweep) + 1 (Murray)")
    print(f"  Age corrections    : {len(age_corrections)}")
    print(f"  Final roster size  : {len(new_roster)}")
    print(f"\nSaved → {ROSTER_FILE}")


if __name__ == "__main__":
    main()
