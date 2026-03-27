"""
Stale Veterans & Non-Roster Player Sweep — 2026
=================================================
Ensures that no player on a real NFL team roster in PGM is either:
  1. A real veteran who is no longer active in the 2026 NFL season
  2. A generated/fictional player (no made-up players on real rosters)

Logic:
  For each PGM player on an NFL team, check nflverse_rosters_2026:
    - Name found as ACT/RFA on the SAME team  → keep (confirmed active, correct team)
    - Name found but UFA / different team ACT  → skip (already handled by prior sweep)
    - Name NOT found in nflverse 2026 at all   → move to FA, zero contract
        → if also in nflverse_players historical DB: real retired/cut veteran → lower rating
        → if not in historical DB either: fictional/generated → FA only, no rating change

Hardcoded normalization misses (players in nflverse 2026 under a different spelling
that were missed by the prior sweep's name matching):
  - Kamren Curl    (PGM: LAR) → Kam Curl    in nflverse: UFA → FA
  - Chigoziem Okonkwo (PGM: TEN) → Chig Okonkwo in nflverse: ACT on WAS → FA

Usage:
    python scripts/fix_stale_veterans_2026.py
"""

import json
import os
import re
import unicodedata

import pandas as pd

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
ROSTERS_CSV = os.path.join(REPO_ROOT, "reference", "nflverse_rosters_2026.csv")
PLAYERS_CSV = os.path.join(REPO_ROOT, "reference", "nflverse_players.csv")

# nflverse team → PGM team
TEAM_MAP = {"LA": "LAR"}

NFL_TEAMS = {
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
}

# Players whose name spelling in PGM differs from nflverse but refer to the same person.
# Format: (pgm_forename, pgm_surname, pgm_team) — all moved to FA unconditionally.
NORMALIZATION_MISS_OVERRIDES = [
    ("Kamren", "Curl", "LAR"),
    ("Chigoziem", "Okonkwo", "TEN"),
]

# Jaire Alexander gets a heavier reduction per user request ("a ton")
JAIRE_REDUCTION = 15
DEFAULT_VETERAN_REDUCTION = 8
RATING_FLOOR = 60


def normalize(name: str) -> str:
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z\s]", "", name)
    return re.sub(r"\s+", " ", name).strip()


def strip_suffix(name: str) -> str:
    return re.sub(r"\s+(jr|sr|ii|iii|iv|v)\s*$", "", name).strip()


def zero_contract(p: dict) -> None:
    for f in ("salary", "eSalary", "guarantee", "eGuarantee", "length", "eLength"):
        p[f] = 0


def build_active_set(rosters_df: pd.DataFrame):
    """
    Returns a set of (norm_name, pgm_team) for all ACT/RFA players in nflverse 2026.
    Also a plain norm_name set for 'player exists in nflverse 2026 at all'.
    """
    active_pairs = set()
    in_nflverse_2026 = set()
    for _, row in rosters_df.iterrows():
        full = normalize(str(row["full_name"]))
        nfl_team = TEAM_MAP.get(str(row["team"]), str(row["team"]))
        status = str(row["status"])
        in_nflverse_2026.add(full)
        in_nflverse_2026.add(strip_suffix(full))
        if status in ("ACT", "RFA"):
            active_pairs.add((full, nfl_team))
            active_pairs.add((strip_suffix(full), nfl_team))
    return active_pairs, in_nflverse_2026


def build_historical_set(players_df: pd.DataFrame):
    """Returns a set of normalized names from the full historical nflverse_players DB."""
    names = set()
    for _, row in players_df.iterrows():
        display = str(row.get("display_name", "") or "")
        if display and display != "nan":
            n = normalize(display)
            names.add(n)
            names.add(strip_suffix(n))
    return names


def main():
    with open(ROSTER_FILE, encoding="utf-8") as f:
        roster = json.load(f)
    print(f"Loaded {len(roster)} players")

    rosters_df = pd.read_csv(ROSTERS_CSV)
    players_df = pd.read_csv(PLAYERS_CSV)

    active_pairs, in_nfl_2026 = build_active_set(rosters_df)
    historical_names = build_historical_set(players_df)

    # --- Step 1: Hardcoded normalization misses ---
    override_keys = {(fn, sn, team) for fn, sn, team in NORMALIZATION_MISS_OVERRIDES}
    override_log = []

    # --- Step 2: Full sweep ---
    fa_real = []    # real veterans moved to FA
    fa_fictional = []  # generated/fictional moved to FA
    kept = []       # confirmed active, no change

    for p in roster:
        team = p.get("teamID", "")
        if team not in NFL_TEAMS:
            continue  # FA, Rookie, blank — untouched

        fn, sn = p.get("forename", ""), p.get("surname", "")
        full_name = f"{fn} {sn}".strip()

        # Hardcoded overrides
        if (fn, sn, team) in override_keys:
            p["teamID"] = "Free Agent"
            zero_contract(p)
            override_log.append(f"  [NORM-MISS] {full_name} ({team}) → Free Agent")
            continue

        norm = normalize(full_name)
        norm_ns = strip_suffix(norm)

        # Check if confirmed active on this exact team
        if (norm, team) in active_pairs or (norm_ns, team) in active_pairs:
            kept.append(full_name)
            continue  # ✓ confirmed active on correct team

        # Not confirmed active on this team — move to FA
        zero_contract(p)
        p["teamID"] = "Free Agent"

        is_real = norm in historical_names or norm_ns in historical_names

        if is_real:
            # Real veteran: apply rating reduction
            if fn == "Jaire" and sn == "Alexander":
                reduction = JAIRE_REDUCTION
            else:
                reduction = DEFAULT_VETERAN_REDUCTION

            old_rating = p["rating"]
            new_rating = max(RATING_FLOOR, old_rating - reduction)
            p["rating"] = new_rating
            if "potential" in p:
                p["potential"] = max(RATING_FLOOR, p["potential"] - reduction)

            fa_real.append(
                f"  [VETERAN] {full_name} ({team}, {p['position']}, "
                f"rating {old_rating}→{new_rating})"
            )
        else:
            fa_fictional.append(
                f"  [FICTIONAL] {full_name} ({team}, {p['position']}, "
                f"rating {p['rating']})"
            )

    # --- Output ---
    print(f"\n--- NORMALIZATION MISSES ({len(override_log)}) ---")
    for line in override_log:
        print(line)

    print(f"\n--- REAL VETERANS MOVED TO FA ({len(fa_real)}) ---")
    for line in fa_real:
        print(line)

    print(f"\n--- FICTIONAL/GENERATED MOVED TO FA ({len(fa_fictional)}) ---")
    for line in fa_fictional:
        print(line)

    # --- Save ---
    with open(ROSTER_FILE, "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)

    print(f"\n--- SUMMARY ---")
    print(f"  Normalization misses fixed : {len(override_log)}")
    print(f"  Real veterans → FA         : {len(fa_real)}")
    print(f"  Fictional players → FA     : {len(fa_fictional)}")
    print(f"  Confirmed active (kept)    : {len(kept)}")
    print(f"\nSaved → {ROSTER_FILE}")


if __name__ == "__main__":
    main()
