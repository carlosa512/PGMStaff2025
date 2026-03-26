#!/usr/bin/env python3
"""Fix contract field mismatches that cause PGM3 to auto-release players.

PGM3 requires salary == eSalary, guarantee == eGuarantee, length == eLength
for all players. When these diverge (e.g. after exporting a played season),
the game releases affected players to Free Agency on load.

Reference: https://github.com/AaronsAron/PGM3FootballRosters — all 3826 players
have perfectly matching contract fields.
"""

import json

ROSTER_PATH = "PGMRoster_2026_Final.json"

with open(ROSTER_PATH) as f:
    roster = json.load(f)

fixed = 0
for p in roster:
    changed = False
    if p.get("salary", 0) != p.get("eSalary", 0):
        p["salary"] = p["eSalary"]
        changed = True
    if p.get("guarantee", 0) != p.get("eGuarantee", 0):
        p["guarantee"] = p["eGuarantee"]
        changed = True
    if p.get("length", 0) != p.get("eLength", 0):
        p["length"] = p["eLength"]
        changed = True
    if changed:
        fixed += 1

with open(ROSTER_PATH, "w") as f:
    json.dump(roster, f)

print(f"Fixed {fixed} players with contract mismatches (out of {len(roster)} total)")

# Verify
mismatched = sum(1 for p in roster if
    p.get("salary", 0) != p.get("eSalary", 0) or
    p.get("guarantee", 0) != p.get("eGuarantee", 0) or
    p.get("length", 0) != p.get("eLength", 0))
print(f"Remaining mismatches: {mismatched}")
