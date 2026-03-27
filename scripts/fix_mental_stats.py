#!/usr/bin/env python3
"""
Fix Mental Stats — Position-Aware Profiles + Notable Player Overrides
======================================================================
Replaces the flat "rating - 2 ± 3" formula with position-specific target ranges
for intelligence, vision, decisions, and discipline. Adds a curated override table
for marquee players with well-known football IQ reputations.

Key rules:
  - "Primary" mental stats (already in POS_STATS for the position) are never lowered.
  - ZERO_STATS per position are never touched.
  - Stats already above the computed target are never lowered for elite players.
  - Overrides are applied last and always take precedence.
  - Name-seeded jitter for determinism. New seed suffix ("mental_v2") avoids
    collision with the existing fix_appearances_and_ratings.py seeds.

Usage:
    python scripts/fix_mental_stats.py            # dry-run, shows changes only
    python scripts/fix_mental_stats.py --apply    # writes changes to roster JSON
    python scripts/fix_mental_stats.py --apply --report-path reference/mental_stats_report.csv
"""

import argparse
import csv
import json
import os
import random
import re

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")

NFL_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

# ---------------------------------------------------------------------------
# Position stats (mirrors fix_appearances_and_ratings.py) — DO NOT modify
# ---------------------------------------------------------------------------

# Mental stats that are primary active stats per position (already handled upstream)
POS_PRIMARY_MENTAL = {
    "QB":  {"intelligence", "vision", "decisions"},  # discipline is secondary
    "OT":  {"intelligence", "discipline"},
    "OG":  {"intelligence", "discipline"},
    "C":   {"intelligence", "discipline"},
    "DE":  {"intelligence"},
    "DT":  {"intelligence"},
    "OLB": {"intelligence"},
    "MLB": {"intelligence"},
    "CB":  {"intelligence"},
    "S":   {"intelligence"},
    # RB, WR, TE, K, P — none of the 4 mental stats are primary
}

# Per-position ZERO_STATS — mental stats are not in any ZERO_STATS list,
# but keep this for safety in case the game evolves.
MENTAL_ZERO_STATS = {
    # (none currently — all 4 mental stats are allowed to be non-zero for all positions)
}

MENTAL_STATS = ["intelligence", "vision", "decisions", "discipline"]

# ---------------------------------------------------------------------------
# Position-specific mental stat target offsets from player rating
# Format: (min_offset, max_offset) — negative = below rating, positive = above rating
# "primary" positions use whatever fix_stat_pattern.py already set — we skip those.
# ---------------------------------------------------------------------------

# (min_delta, max_delta) from rating. Applied to secondary/non-primary mental stats only.
POS_MENTAL_PROFILE = {
    #          intelligence   vision        decisions     discipline
    "QB":  {   "intelligence": None,           # primary — skip
               "vision":       None,           # primary — skip
               "decisions":    None,           # primary — skip
               "discipline":   (-3, -12) },

    "OT":  {   "intelligence": None,           # primary — skip
               "vision":       (-5, -15),
               "decisions":    (-5, -15),
               "discipline":   None },         # primary — skip

    "OG":  {   "intelligence": None,
               "vision":       (-5, -15),
               "decisions":    (-5, -15),
               "discipline":   None },

    "C":   {   "intelligence": None,
               "vision":       (-5, -15),
               "decisions":    (-5, -15),
               "discipline":   None },

    "MLB": {   "intelligence": None,           # primary (already non-trivial value)
               "vision":       (+2, -5),       # safeties of the LB corps — high vision
               "decisions":    (-2, -10),
               "discipline":   (-2, -10) },

    "OLB": {   "intelligence": None,
               "vision":       (-2, -8),
               "decisions":    (-5, -12),
               "discipline":   (-5, -12) },

    "S":   {   "intelligence": None,
               "vision":       (+2, -5),       # centerfielder — best vision of secondary
               "decisions":    (-2, -10),
               "discipline":   (-5, -12) },

    "CB":  {   "intelligence": None,
               "vision":       (-2, -8),
               "decisions":    (-5, -12),
               "discipline":   (0, -8) },      # technique/footwork — higher discipline

    "DE":  {   "intelligence": None,
               "vision":       (-8, -16),
               "decisions":    (-8, -16),
               "discipline":   (-2, -10) },

    "DT":  {   "intelligence": None,
               "vision":       (-8, -16),
               "decisions":    (-8, -16),
               "discipline":   (-2, -10) },

    "TE":  {   "intelligence": (-5, -12),
               "vision":       (-8, -15),
               "decisions":    (-8, -15),
               "discipline":   (-5, -12) },

    "RB":  {   "intelligence": (-8, -15),
               "vision":       (-10, -18),
               "decisions":    (-8, -15),
               "discipline":   (-8, -15) },

    "WR":  {   "intelligence": (-8, -15),
               "vision":       (-10, -18),
               "decisions":    (-10, -18),
               "discipline":   (-8, -15) },

    "K":   {   "intelligence": (-5, -12),
               "vision":       (-8, -15),
               "decisions":    (-8, -15),
               "discipline":   (-2, -8) },

    "P":   {   "intelligence": (-5, -12),
               "vision":       (-8, -15),
               "decisions":    (-8, -15),
               "discipline":   (-2, -8) },
}

# Default fallback for unrecognized positions
DEFAULT_MENTAL_PROFILE = {
    "intelligence": (-5, -12),
    "vision":       (-8, -15),
    "decisions":    (-8, -15),
    "discipline":   (-5, -12),
}

# ---------------------------------------------------------------------------
# Notable player overrides
# Keys: (forename, surname) — must match PGM3 roster exactly.
# Only set the stats you want to override; others follow the position formula.
# Add more entries freely — they take full precedence over the formula.
# ---------------------------------------------------------------------------

MENTAL_OVERRIDES = {
    # ---- Elite football IQ / field generals ----
    ("Patrick", "Mahomes"):   {"intelligence": 97, "vision": 97, "decisions": 96},
    ("Joe", "Burrow"):        {"intelligence": 95, "vision": 94, "decisions": 95},
    ("Lamar", "Jackson"):     {"intelligence": 93, "vision": 94, "decisions": 92},
    ("C.J.", "Stroud"):       {"intelligence": 91, "vision": 92, "decisions": 90},
    ("Jalen", "Hurts"):       {"intelligence": 90, "vision": 90, "decisions": 89},
    ("Dak", "Prescott"):      {"intelligence": 89, "vision": 89, "decisions": 88},
    ("Matthew", "Stafford"):  {"intelligence": 90, "vision": 90, "decisions": 90},
    ("Kirk", "Cousins"):      {"intelligence": 89, "vision": 88, "decisions": 88},
    ("Derek", "Carr"):        {"intelligence": 88, "vision": 87, "decisions": 87},
    ("Aaron", "Rodgers"):     {"intelligence": 95, "vision": 95, "decisions": 94},
    ("Tom", "Brady"):         {"intelligence": 99, "vision": 99, "decisions": 99},

    # ---- Gunnslinger / risky tendencies (lower decisions) ----
    ("Josh", "Allen"):        {"decisions": 82, "intelligence": 90, "vision": 89},
    ("Justin", "Fields"):     {"decisions": 76, "intelligence": 81, "vision": 80},
    ("Will", "Levis"):        {"decisions": 74, "intelligence": 79, "vision": 77},
    ("Sam", "Darnold"):       {"decisions": 77, "intelligence": 80, "vision": 80},
    ("Mitchell", "Trubisky"): {"decisions": 75, "intelligence": 79, "vision": 78},

    # ---- Elite LB/DB football IQ ----
    ("Micah", "Parsons"):     {"intelligence": 93},
    ("Fred", "Warner"):       {"intelligence": 94, "vision": 93},
    ("Tyrann", "Mathieu"):    {"intelligence": 93, "vision": 94},
    ("Kyle", "Hamilton"):     {"intelligence": 91, "vision": 92},
    ("Demario", "Davis"):     {"intelligence": 92, "vision": 91},
    ("Roquan", "Smith"):      {"intelligence": 91, "vision": 90},
    ("Bobby", "Wagner"):      {"intelligence": 93, "vision": 92},
    ("Patrick", "Queen"):     {"intelligence": 86, "vision": 85},

    # ---- Elite OL football IQ ----
    ("Zack", "Martin"):       {"discipline": 97, "intelligence": 93},
    ("Travis", "Kelce"):      {"intelligence": 91, "vision": 90},
    ("Jason", "Kelce"):       {"intelligence": 96, "discipline": 95},
    ("Penei", "Sewell"):      {"intelligence": 90, "discipline": 91},
    ("Rashawn", "Slater"):    {"intelligence": 90, "discipline": 92},
    ("Quenton", "Nelson"):    {"intelligence": 89, "discipline": 91},

    # ---- Elite WR route IQ ----
    ("Davante", "Adams"):     {"intelligence": 87, "decisions": 85},
    ("Stefon", "Diggs"):      {"intelligence": 86, "decisions": 85},
    ("DeAndre", "Hopkins"):   {"intelligence": 87, "decisions": 86},
    ("Amari", "Cooper"):      {"intelligence": 85, "decisions": 84},
}

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def compute_target(rating, stat, pos, name, is_team_player):
    """
    Compute target value for a mental stat given position profile.
    Returns None if the stat should be skipped (primary or zero stat for this position).
    """
    profile = POS_MENTAL_PROFILE.get(pos, DEFAULT_MENTAL_PROFILE)
    offset_range = profile.get(stat)

    if offset_range is None:
        # Primary stat for this position — skip
        return None

    min_off, max_off = offset_range  # e.g. (-3, -12) or (+2, -5)
    lo = min(min_off, max_off)
    hi = max(min_off, max_off)

    random.seed(name + stat + "mental_v2")
    jitter = random.randint(lo, hi)
    target = rating + jitter

    # Clamp
    floor = 55 if is_team_player else 50
    target = max(floor, min(97, target))
    return target


def process_player(p):
    """
    Compute all mental stat changes for one player.
    Returns list of (stat, old_val, new_val, source) tuples.
    """
    name = f"{p['forename']} {p['surname']}"
    pos = p.get("position", "WR")
    rating = p.get("rating", 60)
    is_team_player = p.get("teamID") in NFL_TEAMS
    override_key = (p["forename"], p["surname"])
    overrides = MENTAL_OVERRIDES.get(override_key, {})

    changes = []

    for stat in MENTAL_STATS:
        old_val = p.get(stat, 0)

        # Check if override exists for this stat
        if stat in overrides:
            new_val = overrides[stat]
            source = "override"
        else:
            target = compute_target(rating, stat, pos, name, is_team_player)
            if target is None:
                continue  # primary stat — handled by fix_stat_pattern.py, skip

            # Never lower a stat that's already comfortably above our computed target
            # (respects manually set or previously boosted values)
            if old_val > target + 3:
                continue  # already better than our formula would set

            new_val = target
            source = "formula"

        if new_val != old_val:
            changes.append((stat, old_val, new_val, source))

    return changes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fix mental stats with position-aware profiles")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes to roster JSON (default: dry-run only)")
    parser.add_argument("--report-path",
                        default=os.path.join(REPO_ROOT, "reference", "mental_stats_report.csv"),
                        help="Path for audit CSV report")
    args = parser.parse_args()

    dry_run = not args.apply
    if dry_run:
        print("DRY-RUN mode — no changes will be written. Use --apply to commit.")
    else:
        print("APPLY mode — roster will be modified.")

    print("\nLoading roster...")
    with open(ROSTER_FILE, encoding="utf-8") as f:
        pgm = json.load(f)

    all_changes = []
    players_changed = 0
    stat_counts = {s: 0 for s in MENTAL_STATS}
    override_count = 0

    for p in pgm:
        name = f"{p['forename']} {p['surname']}"
        pos = p.get("position", "WR")
        team = p.get("teamID", "")

        player_changes = process_player(p)

        if player_changes:
            players_changed += 1
            for (stat, old_val, new_val, source) in player_changes:
                stat_counts[stat] += 1
                if source == "override":
                    override_count += 1
                all_changes.append({
                    "name": name,
                    "team": team,
                    "pos": pos,
                    "stat": stat,
                    "old_val": old_val,
                    "new_val": new_val,
                    "delta": new_val - old_val,
                    "source": source,
                })
                if not dry_run:
                    p[stat] = new_val

    # --- Print summary ---
    print(f"\n{'='*60}")
    print(f"MENTAL STATS FIX RESULTS")
    print(f"{'='*60}")
    print(f"  Players with changes:   {players_changed}")
    print(f"  Total stat changes:     {len(all_changes)}")
    print(f"  Override applications:  {override_count}")
    print(f"\n  By stat:")
    for stat in MENTAL_STATS:
        print(f"    {stat:<15}: {stat_counts[stat]} changes")

    # Sample overrides applied
    override_rows = [c for c in all_changes if c["source"] == "override"]
    if override_rows:
        print(f"\n  Notable override changes:")
        seen = set()
        for c in override_rows:
            key = c["name"]
            if key not in seen:
                seen.add(key)
                player_overrides = [r for r in override_rows if r["name"] == key]
                stats_str = ", ".join(
                    f"{r['stat']}:{r['old_val']}→{r['new_val']}" for r in player_overrides
                )
                print(f"    {key:<30} {c['pos']:<5} {stats_str}")

    # Sample formula changes (largest deltas)
    formula_rows = sorted(
        [c for c in all_changes if c["source"] == "formula"],
        key=lambda x: abs(x["delta"]), reverse=True
    )
    if formula_rows:
        print(f"\n  Largest formula adjustments (sample):")
        seen = set()
        for c in formula_rows[:20]:
            key = (c["name"], c["stat"])
            if key not in seen:
                seen.add(key)
                print(f"    {c['name']:<30} {c['pos']:<5} {c['stat']:<14} "
                      f"{c['old_val']:>3} → {c['new_val']:>3} ({c['delta']:+d})")

    # Position average mental stats (for verification)
    if not dry_run:
        print(f"\n  Average mental stats by position (team players, after fix):")
        pos_stats = {}
        for p in pgm:
            if p.get("teamID") not in NFL_TEAMS:
                continue
            pos = p.get("position", "?")
            if pos not in pos_stats:
                pos_stats[pos] = {s: [] for s in MENTAL_STATS}
            for s in MENTAL_STATS:
                val = p.get(s, 0)
                if val > 0:
                    pos_stats[pos][s].append(val)
        for pos in sorted(pos_stats):
            avgs = []
            for s in MENTAL_STATS:
                vals = pos_stats[pos][s]
                avg = sum(vals) / len(vals) if vals else 0
                avgs.append(f"{s[:3]}={avg:.0f}")
            print(f"    {pos:<5} " + "  ".join(avgs))

    # --- Write report ---
    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "team", "pos", "stat", "old_val", "new_val", "delta", "source"
        ])
        writer.writeheader()
        writer.writerows(all_changes)
    print(f"\nReport written to: {args.report_path}")

    # --- Save roster ---
    if not dry_run:
        with open(ROSTER_FILE, "w", encoding="utf-8") as f:
            json.dump(pgm, f, separators=(",", ":"))
        print(f"\nSaved {len(pgm)} players to {ROSTER_FILE}")
    else:
        print("\nDry-run complete. Run with --apply to commit changes.")


if __name__ == "__main__":
    main()
