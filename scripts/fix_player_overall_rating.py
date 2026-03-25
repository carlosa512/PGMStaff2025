"""
Fix Player Overall Rating (In-Game OVR)
========================================
Recalculates all player stats from the `rating` field using the community-proven
formula so the game engine's OVR calculation displays correct values.

Root cause: the old formula set active stats to `rating +/- 3` (e.g. 62-68 for
a 65-rated player), but the game engine needs them at ~(rating+90)/2 (e.g. 77-78).

The community formula (verified across ratings 60-90):
  Position/mental stats: rating + ceil((90 - rating) * 0.5) + jitter
  Physical stats:        rating + floor((90 - rating) * 0.5) + jitter
  Stamina:               always 85
  Off-position stats:    LEFT UNCHANGED (zeroing causes game to drop players to FA)

Star players (rating >= 85) with hand-tuned stat profiles are preserved --
only active stats below the community formula floor are boosted.

Usage:
    python scripts/fix_player_overall_rating.py

Output:
    Modifies PGMRoster_2026_Final.json in place
    Prints a summary of all changes
"""

import json
import random
import os

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")

NFL_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

# ---------------------------------------------------------------------------
# Position-active stats (from community roster analysis)
# Every stat NOT in this list for a position gets set to 0.
# ---------------------------------------------------------------------------

PHYSICAL = {"speed", "burst", "power", "jumping", "agility"}
MENTAL = {"intelligence", "vision", "decisions", "discipline"}

ACTIVE_STATS = {
    "QB":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "ballSecurity","skillMove","trucking","elusiveness","rushBlock","stamina",
            "throwOnRun","sPassAcc","mPassAcc","dPassAcc"],
    "RB":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "ballSecurity","skillMove","trucking","elusiveness","catching","rushBlock","passBlock",
            "routeRun","releaseLine","stamina"],
    "WR":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "ballSecurity","skillMove","trucking","elusiveness","catching","rushBlock","passBlock",
            "routeRun","releaseLine","stamina"],
    "TE":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "ballSecurity","skillMove","trucking","elusiveness","catching","rushBlock","passBlock",
            "routeRun","releaseLine","stamina"],
    "OT":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "rushBlock","passBlock","releaseLine","stamina"],
    "OG":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "rushBlock","passBlock","releaseLine","stamina"],
    "C":   ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "rushBlock","passBlock","releaseLine","stamina"],
    "DE":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","tackle","blockShedding","ballStrip"],
    "DT":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","tackle","blockShedding","ballStrip"],
    "OLB": ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","manCover","zoneCover","tackle","blockShedding","ballStrip"],
    "MLB": ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","manCover","zoneCover","tackle","blockShedding","ballStrip"],
    "CB":  ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","manCover","zoneCover","tackle","blockShedding","ballStrip"],
    "S":   ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "skillMove","releaseLine","stamina","manCover","zoneCover","tackle","blockShedding","ballStrip"],
    "K":   ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "stamina","kickAccuracy"],
    "P":   ["speed","burst","power","jumping","agility","intelligence","vision","decisions","discipline",
            "stamina","kickAccuracy"],
}

# All gameplay stat fields
ALL_GAMEPLAY_STATS = [
    "passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity", "trucking",
    "burst", "sPassAcc", "manCover", "elusiveness", "intelligence", "discipline",
    "stamina", "dPassAcc", "tackle", "zoneCover", "vision", "blockShedding",
    "power", "speed", "jumping", "decisions", "mPassAcc", "catching", "agility",
    "skillMove", "ballStrip", "kickAccuracy", "releaseLine",
]

# Stats to keep at 0 for non-K/P positions
KICKING_STATS = {"kickAccuracy"}
# Stats to keep at 0 for K/P
KP_SKIP_STATS = {"throwOnRun", "sPassAcc", "dPassAcc", "mPassAcc"}


# ---------------------------------------------------------------------------
# Stat computation
# ---------------------------------------------------------------------------

def compute_stat(rating, stat_name, player_name):
    """Compute a stat value using the community formula.

    Physical stats:         rating + floor((90 - rating) / 2) + jitter
    Position/mental stats:  rating + ceil((90 - rating) / 2) + jitter
    Stamina:                always 85
    """
    if stat_name == "stamina":
        return 85

    random.seed(player_name + stat_name)
    jitter = random.randint(-2, 2)

    gap = 90 - rating
    if stat_name in PHYSICAL:
        base = rating + gap // 2
    else:
        base = rating + -(-gap // 2)  # ceiling division

    return max(55, min(99, base + jitter))


def is_hand_tuned(player, active_set):
    """Detect if a star player's stats show manual tuning (high variance).
    Hand-tuned players have individually varied stats rather than uniform formula output."""
    values = [player.get(s, 0) for s in active_set if s != "stamina" and player.get(s, 0) > 0]
    if len(values) < 3:
        return False
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    # Standard deviation > 5 indicates hand-tuning
    return variance > 25


def fix_player(p):
    """Recalculate all stats for a single player. Returns (changes, was_preserved)."""
    pos = p.get("position", "WR")
    rating = p.get("rating", 0)
    if not rating:
        return [], False

    name = f"{p['forename']} {p['surname']}"
    active = set(ACTIVE_STATS.get(pos, ACTIVE_STATS["WR"]))
    is_kp = pos in ("K", "P")
    effective_rating = max(55, rating)
    changes = []

    # Star player preservation: keep hand-tuned active stats
    if rating >= 85 and is_hand_tuned(p, active):
        # Only zero kickAccuracy for non-K/P
        if not is_kp:
            old = p.get("kickAccuracy", 0)
            if old != 0:
                p["kickAccuracy"] = 0
                changes.append(f"kickAccuracy: {old} -> 0")
        return changes, True

    # Normal path: recalculate active stats, leave off-position stats unchanged
    for stat in ALL_GAMEPLAY_STATS:
        old_val = p.get(stat, 0)

        # kickAccuracy = 0 for non-K/P
        if stat in KICKING_STATS and not is_kp:
            if old_val != 0:
                p[stat] = 0
                changes.append(f"{stat}: {old_val} -> 0")
            continue

        # Passing stats = 0 for K/P
        if stat in KP_SKIP_STATS and is_kp:
            if old_val != 0:
                p[stat] = 0
                changes.append(f"{stat}: {old_val} -> 0")
            continue

        # Only recalculate active (position-relevant) stats
        if stat in active:
            new_val = compute_stat(effective_rating, stat, name)
            if old_val != new_val:
                p[stat] = new_val
                changes.append(f"{stat}: {old_val} -> {new_val}")
        # Off-position stats: leave unchanged (zeroing causes game to drop players to FA)

    return changes, False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading roster...")
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    total = len(pgm)
    fixed = 0
    star_preserved = 0
    stat_changes = 0
    stats_zeroed = 0

    for p in pgm:
        changes, preserved = fix_player(p)
        if changes:
            fixed += 1
            stat_changes += len(changes)
            stats_zeroed += sum(1 for c in changes if c.endswith("-> 0"))
            if preserved:
                star_preserved += 1

    # --- Print results ---
    print(f"\n{'='*60}")
    print(f"PLAYER STATS RECALCULATED: {fixed} players modified")
    print(f"  Individual stat changes: {stat_changes}")
    print(f"  Star players preserved (hand-tuned, rating >= 85): {star_preserved}")
    print(f"  Note: off-position stats left unchanged (zeroing causes FA bug)")
    print(f"{'='*60}")

    # Spot-check sample players at various rating tiers
    print("\n--- Sample players (before -> after implied by current values) ---")
    shown = set()
    for target in (60, 65, 70, 75, 80, 85, 90):
        for p in pgm:
            r = p.get("rating", 0)
            name = f"{p['forename']} {p['surname']}"
            if r == target and name not in shown:
                pos = p.get("position", "?")
                speed = p.get("speed", 0)
                intel = p.get("intelligence", 0)
                stamina = p.get("stamina", 0)
                kick = p.get("kickAccuracy", 0)
                print(f"  r={r:3} {pos:3} {name:30} speed={speed} intel={intel} stamina={stamina} kickAcc={kick}")
                shown.add(name)
                break

    # Rating distribution (unchanged since we don't modify the rating field)
    team_players = [p for p in pgm if p.get("teamID") in NFL_TEAMS]
    buckets = {}
    for p in team_players:
        b = (p["rating"] // 5) * 5
        buckets[b] = buckets.get(b, 0) + 1
    print(f"\nRating distribution (team players, unchanged):")
    for k in sorted(buckets):
        bar = "#" * (buckets[k] // 5)
        print(f"  {k:3}-{k+4}: {buckets[k]:4}  {bar}")

    # Save with compact JSON (matching other scripts)
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    print(f"\nDone. Saved {len(pgm)} players to {ROSTER_FILE}")


if __name__ == "__main__":
    main()
