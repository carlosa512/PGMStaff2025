#!/usr/bin/env python3
"""
Fix Stat Pattern — Restore PGM3 Game Engine Stat Rules
=======================================================
Fixes two critical bugs caused by previous fix scripts setting ALL stats to
60+ baselines:

1. 40 OVR BUG: The game engine only counts non-zero stats in its OVR formula.
   Setting off-position stats to 60+ diluted mid-tier players' OVR to 40.

2. AUTO-RELEASE BUG: Players with broken OVR get immediately released to
   Free Agency on roster load.

ROOT CAUSE: The PGM3 engine expects specific stats to be EXACTLY 0 per
position. This was verified by analyzing the original game save data, where
every position has a defined set of "always zero" stats.

FIX APPROACH:
- Restore the game's per-position zero-stat pattern
- For non-zero stats, ensure values follow the game's stat-to-rating
  relationship (higher-rated players have stats closer to rating; lower-rated
  players have stats well above rating as a floor)
- Preserve appearance fixes (they are separate and correct)
- Preserve rating floor (55+) and potential >= rating

Usage:
    python scripts/fix_stat_pattern.py

Output:
    Modifies PGMRoster_2026_Final.json in place
"""

import json
import random
import re

REPO_ROOT = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
ROSTER_FILE = f"{REPO_ROOT}/PGMRoster_2026_Final.json"

NFL_TEAMS = {
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
}

# ---------------------------------------------------------------------------
# Per-position "always zero" stats — derived from the user's actual PGM3 game
# save (commit 1f8af15). Every team player in the save has these stats at 0.
# Setting them to non-zero breaks the engine's OVR calculation.
# ---------------------------------------------------------------------------

ZERO_STATS = {
    "QB":  ["passBlock", "routeRun", "manCover", "tackle", "zoneCover",
            "blockShedding", "catching", "ballStrip", "kickAccuracy", "releaseLine"],

    "RB":  ["throwOnRun", "sPassAcc", "manCover", "dPassAcc", "tackle",
            "zoneCover", "blockShedding", "mPassAcc", "ballStrip", "kickAccuracy"],

    "WR":  ["throwOnRun", "sPassAcc", "manCover", "dPassAcc", "tackle",
            "zoneCover", "blockShedding", "mPassAcc", "ballStrip", "kickAccuracy"],

    "TE":  ["throwOnRun", "sPassAcc", "manCover", "dPassAcc", "tackle",
            "zoneCover", "blockShedding", "mPassAcc", "ballStrip", "kickAccuracy"],

    "OT":  ["throwOnRun", "routeRun", "ballSecurity", "trucking", "sPassAcc",
            "manCover", "elusiveness", "dPassAcc", "tackle", "zoneCover",
            "blockShedding", "mPassAcc", "catching", "skillMove", "ballStrip", "kickAccuracy"],

    "OG":  ["throwOnRun", "routeRun", "ballSecurity", "trucking", "sPassAcc",
            "manCover", "elusiveness", "dPassAcc", "tackle", "zoneCover",
            "blockShedding", "mPassAcc", "catching", "skillMove", "ballStrip", "kickAccuracy"],

    "C":   ["throwOnRun", "routeRun", "ballSecurity", "trucking", "sPassAcc",
            "manCover", "elusiveness", "dPassAcc", "tackle", "zoneCover",
            "blockShedding", "mPassAcc", "catching", "skillMove", "ballStrip", "kickAccuracy"],

    "DE":  ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "manCover", "elusiveness", "dPassAcc",
            "zoneCover", "mPassAcc", "catching", "kickAccuracy"],

    "DT":  ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "manCover", "elusiveness", "dPassAcc",
            "zoneCover", "mPassAcc", "catching", "kickAccuracy"],

    "OLB": ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "elusiveness", "dPassAcc", "mPassAcc",
            "catching", "kickAccuracy"],

    "MLB": ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "elusiveness", "dPassAcc", "mPassAcc",
            "catching", "kickAccuracy"],

    "CB":  ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "elusiveness", "dPassAcc", "mPassAcc",
            "catching", "kickAccuracy"],

    "S":   ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "elusiveness", "dPassAcc", "mPassAcc",
            "catching", "kickAccuracy"],

    "K":   ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "manCover", "elusiveness", "dPassAcc",
            "tackle", "zoneCover", "blockShedding", "mPassAcc", "catching",
            "skillMove", "ballStrip", "releaseLine"],

    "P":   ["passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity",
            "trucking", "sPassAcc", "manCover", "elusiveness", "dPassAcc",
            "tackle", "zoneCover", "blockShedding", "mPassAcc", "catching",
            "skillMove", "ballStrip", "releaseLine"],
}

# All gameplay stats (the superset)
ALL_GAMEPLAY_STATS = [
    "passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity", "trucking",
    "burst", "sPassAcc", "manCover", "elusiveness", "intelligence", "discipline",
    "stamina", "dPassAcc", "tackle", "zoneCover", "vision", "blockShedding",
    "power", "speed", "jumping", "decisions", "mPassAcc", "catching", "agility",
    "skillMove", "ballStrip", "kickAccuracy", "releaseLine",
]

# ---------------------------------------------------------------------------
# Game-accurate stat value formula
# ---------------------------------------------------------------------------
# From the game save, the relationship between rating and stat values is:
#   Low-tier  (rating 40-55): stats ~60-70  (floor of 60, big offset)
#   Mid-tier  (rating 55-75): stats ~rating + 10-15
#   High-tier (rating 75-99): stats ~rating + 0-8, capped at 99


def game_stat_value(rating, name, stat):
    """Calculate a stat value matching the PGM3 game engine's observed pattern."""
    random.seed(name + stat + "gamestat")
    if rating >= 90:
        return max(85, min(99, rating + random.randint(-5, 0)))
    elif rating >= 75:
        return max(75, min(99, rating + random.randint(0, 8)))
    elif rating >= 60:
        return max(65, min(95, rating + random.randint(8, 14)))
    else:
        return max(60, min(80, 60 + random.randint(0, 10)))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading roster...")
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    zeroed_out = 0       # stats we set from non-zero back to 0
    stats_raised = 0     # non-zero stats we raised to match game pattern
    players_fixed = 0
    details = []

    for p in pgm:
        name = f"{p['forename']} {p['surname']}"
        pos = p.get("position", "WR")
        rating = p.get("rating", 60)

        zero_set = set(ZERO_STATS.get(pos, ZERO_STATS["WR"]))
        nonzero_set = set(ALL_GAMEPLAY_STATS) - zero_set

        player_changes = []

        # --- Step 1: Zero out stats that should always be 0 for this position ---
        for stat in zero_set:
            current = p.get(stat, 0)
            if current != 0:
                p[stat] = 0
                zeroed_out += 1
                player_changes.append(f"{stat}: {current}→0")

        # --- Step 2: Ensure non-zero stats have game-appropriate values ---
        # The game expects non-zero stats to follow a rating-dependent pattern:
        #   rating 40-55 → stats ~60-70 (delta +15-20)
        #   rating 55-65 → stats ~70-80 (delta +15)
        #   rating 65-75 → stats ~75-85 (delta +10)
        #   rating 75-85 → stats ~80-92 (delta +5)
        #   rating 85+   → stats ~85-99 (delta ~0)
        # Stats well below this floor get raised to match the game pattern.
        for stat in nonzero_set:
            current = p.get(stat, 0)
            expected = game_stat_value(rating, name, stat)

            if current == 0:
                # Stat should be non-zero but is 0 — set to game pattern value
                p[stat] = expected
                stats_raised += 1
                player_changes.append(f"{stat}: 0→{expected}")
            elif stat != "stamina" and current < expected - 5:
                # Stat is too low vs game pattern — raise it. The -5 tolerance
                # allows some natural variation from game evolution.
                p[stat] = expected
                stats_raised += 1
                player_changes.append(f"{stat}: {current}→{expected}")

        # --- Step 3: Ensure stamina is at least 75 (game save shows 75-85) ---
        if p.get("stamina", 0) < 75:
            old_stam = p.get("stamina", 0)
            p["stamina"] = 85
            player_changes.append(f"stamina: {old_stam}→85")

        # --- Step 4: Rating floor + potential ---
        if p.get("teamID") in NFL_TEAMS and rating < 55:
            old_r = rating
            p["rating"] = 55
            rating = 55
            player_changes.append(f"rating: {old_r}→55")

        pot = p.get("potential", 0)
        if rating > 0 and pot < rating:
            p["potential"] = rating
            player_changes.append(f"potential: {pot}→{rating}")

        if player_changes:
            players_fixed += 1
            if len(details) < 40:
                details.append(f"  {p.get('teamID','??'):12} {pos:4} "
                              f"{name:30} {', '.join(player_changes[:5])}"
                              + (f" (+{len(player_changes)-5} more)" if len(player_changes) > 5 else ""))

    # --- Print results ---
    print(f"\n{'='*60}")
    print(f"STAT PATTERN FIX RESULTS")
    print(f"{'='*60}")
    print(f"Players modified:       {players_fixed}")
    print(f"Stats zeroed out:       {zeroed_out}")
    print(f"Stats raised (0→value): {stats_raised}")
    print(f"\nSample changes:")
    for line in details:
        print(line)
    if players_fixed > 40:
        print(f"  ... and {players_fixed - 40} more players")

    # --- Verification ---
    print(f"\n--- POST-FIX VERIFICATION ---")

    # Check that zero stats are actually zero
    violations = 0
    for p in pgm:
        pos = p.get("position", "WR")
        for stat in ZERO_STATS.get(pos, []):
            if p.get(stat, 0) != 0:
                violations += 1
    print(f"Zero-stat violations remaining: {violations}")

    # Check that non-zero stats are actually non-zero (for team players)
    missing_nonzero = 0
    for p in pgm:
        if p.get("teamID") not in NFL_TEAMS:
            continue
        pos = p.get("position", "WR")
        zero_set = set(ZERO_STATS.get(pos, []))
        for stat in ALL_GAMEPLAY_STATS:
            if stat not in zero_set and p.get(stat, 0) == 0:
                missing_nonzero += 1
    print(f"Missing non-zero stats (team players): {missing_nonzero}")

    # Rating distribution
    team_players = [p for p in pgm if p.get("teamID") in NFL_TEAMS]
    buckets = {}
    for p in team_players:
        b = (p["rating"] // 5) * 5
        buckets[b] = buckets.get(b, 0) + 1
    print(f"\nRating distribution (team players):")
    for k in sorted(buckets):
        bar = "#" * (buckets[k] // 5)
        print(f"  {k:3}-{k+4}: {buckets[k]:4}  {bar}")

    # Average stat delta for sample positions
    for pos in ["QB", "RB", "WR", "DE", "CB"]:
        team_pos = [p for p in team_players if p.get("position") == pos]
        if not team_pos:
            continue
        zero_set = set(ZERO_STATS.get(pos, []))
        nonzero_stats = [s for s in ALL_GAMEPLAY_STATS if s not in zero_set]
        deltas = []
        for p in team_pos:
            avg_stat = sum(p.get(s, 0) for s in nonzero_stats) / len(nonzero_stats)
            deltas.append(avg_stat - p["rating"])
        avg_delta = sum(deltas) / len(deltas)
        print(f"  {pos:4} avg(stats - rating) = {avg_delta:+.1f}")

    # Save
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    print(f"\nDone. Saved {len(pgm)} players to {ROSTER_FILE}")


if __name__ == "__main__":
    main()
