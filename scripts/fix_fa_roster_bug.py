"""
Fix FA Roster Bug — Name-Mismatch Players
==========================================
Five players were incorrectly swept to Free Agency by fix_player_audit_2026.py
and fix_stale_veterans_2026.py because their PGM name spelling didn't match
their nflverse name exactly.

Fixes:
  1. Micah Parson → Parsons, restore to GB with contract
  2. Foyesade Oluokun → restore to JAX with contract
  3. Joshua Palmer → restore to BUF with contract
  4. Dax Hill → restore to CIN with contract
  5. Delete duplicate Tariq Woolen (Riq Woolen already on PHI)

Usage:
    python scripts/fix_fa_roster_bug.py
"""

import json
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")

# Player fixes keyed by iden prefix
FIXES = {
    "A7501C69": {
        "name": "Micah Parson → Parsons",
        "surname": "Parsons",
        "teamID": "GB",
        "rating": 98,
        "salary": 2387000,
        "eSalary": 2387000,
        "guarantee": 16850000,
        "eGuarantee": 16850000,
        "length": 3,
        "eLength": 3,
    },
    "CFA5CC0E": {
        "name": "Foyesade Oluokun",
        "teamID": "JAX",
        "salary": 9000000,
        "eSalary": 9000000,
        "guarantee": 8108500,
        "eGuarantee": 8108500,
        "length": 1,
        "eLength": 1,
    },
    "13DAC203": {
        "name": "Joshua Palmer",
        "teamID": "BUF",
        "salary": 3300000,
        "eSalary": 3300000,
        "guarantee": 0,
        "eGuarantee": 0,
        "length": 1,
        "eLength": 1,
    },
    "8D0BF729": {
        "name": "Dax Hill",
        "teamID": "CIN",
        "salary": 600000,
        "eSalary": 600000,
        "guarantee": 0,
        "eGuarantee": 0,
        "length": 1,
        "eLength": 1,
    },
}

# Duplicate to remove (old Tariq Woolen; Riq Woolen already on PHI)
DELETE_IDEN_PREFIX = "C973F19C"


def main():
    with open(ROSTER_FILE, encoding="utf-8") as f:
        roster = json.load(f)
    print(f"Loaded {len(roster)} players")

    fixed = []
    deleted = False
    new_roster = []

    for player in roster:
        iden = player.get("iden", "")
        prefix = iden.split("-")[0] if "-" in iden else iden[:8]

        # Delete duplicate Tariq Woolen
        if prefix == DELETE_IDEN_PREFIX:
            fn = player.get("forename", "")
            sn = player.get("surname", "")
            print(f"  [DELETE] {fn} {sn} (duplicate, Riq Woolen already on PHI)")
            deleted = True
            continue

        # Apply fixes
        if prefix in FIXES:
            fix = FIXES[prefix]
            fn = player.get("forename", "")
            sn = player.get("surname", "")
            old_team = player.get("teamID", "")

            for key, value in fix.items():
                if key == "name":
                    continue
                player[key] = value

            new_team = player["teamID"]
            new_sn = player.get("surname", sn)
            fixed.append(
                f"  [FIX] {fn} {sn} → {fn} {new_sn}: "
                f"{old_team} → {new_team}, "
                f"salary={player['salary']}, guarantee={player['guarantee']}, "
                f"length={player['length']}"
            )

        new_roster.append(player)

    print(f"\n--- FIXES APPLIED ({len(fixed)}) ---")
    for line in fixed:
        print(line)

    if deleted:
        print(f"\n--- DUPLICATE REMOVED ---")
        print(f"  Tariq Woolen (iden {DELETE_IDEN_PREFIX}...) removed")

    with open(ROSTER_FILE, "w", encoding="utf-8") as f:
        json.dump(new_roster, f, indent=2, ensure_ascii=False)

    print(f"\nFinal roster size: {len(new_roster)}")
    print(f"Saved → {ROSTER_FILE}")


if __name__ == "__main__":
    main()
