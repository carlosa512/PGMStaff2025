"""
Fix Appearances, Ratings, and All Stats
========================================
Addresses four issues in PGMRoster_2026_Final.json:

1. APPEARANCE CLIPPING: Players with Head/Nose/Mouth/Eyebrows/Beard skin-tone group
   mismatches. Fixes by aligning Nose, Mouth, Eyebrows, and Beard to match Head group.
   Beards with extended variants (Beard2r, etc.) are left untouched.

2. LOW OVR: Active roster players below 55 are bumped to 55 with stats recalculated.
   Ensures potential >= rating for all players (fixes Future Growth = 0).

3. MENTAL STATS: Boosts intelligence, vision, decisions, discipline to
   rating-5 baseline (floor 40, cap 90). Overwrites if current value is below baseline.

4. SECONDARY STATS: The game engine uses ALL stats for OVR calculation.
   Sets every remaining gameplay stat to rating-5 baseline (floor 40, cap 90).
   Overwrites existing values if below the computed baseline.

Usage:
    python scripts/fix_appearances_and_ratings.py

Output:
    Modifies PGMRoster_2026_Final.json in place
    Prints a summary of all changes
"""

import csv
import json
import random
import re
from datetime import date

REPO_ROOT = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
ROSTER_FILE = f"{REPO_ROOT}/PGMRoster_2026_Final.json"
NF_PLAYERS  = f"{REPO_ROOT}/reference/nflverse_players.csv"
NF_ROSTERS  = f"{REPO_ROOT}/reference/nflverse_rosters_2026.csv"
NF_DRAFT    = f"{REPO_ROOT}/reference/nflverse_draft_picks.csv"

NFL_TEAMS = {
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
}

# Position stats that are the PRIMARY active stats (non-zero) for each position
POS_STATS = {
    "QB":  ["throwOnRun","sPassAcc","dPassAcc","mPassAcc","decisions","vision",
            "intelligence","burst","speed","agility","elusiveness","ballSecurity",
            "skillMove","stamina","jumping","power"],
    "RB":  ["trucking","ballSecurity","elusiveness","burst","speed","agility",
            "catching","skillMove","rushBlock","stamina","power","jumping"],
    "WR":  ["routeRun","catching","ballSecurity","burst","speed","agility",
            "elusiveness","skillMove","stamina","jumping"],
    "TE":  ["routeRun","catching","ballSecurity","burst","speed","agility",
            "elusiveness","skillMove","rushBlock","passBlock","stamina","jumping","power"],
    "OT":  ["passBlock","rushBlock","burst","power","speed","agility",
            "intelligence","discipline","stamina","jumping"],
    "OG":  ["passBlock","rushBlock","burst","power","speed","agility",
            "intelligence","discipline","stamina","jumping"],
    "C":   ["passBlock","rushBlock","burst","power","speed","agility",
            "intelligence","discipline","stamina","jumping"],
    "DE":  ["blockShedding","tackle","power","burst","speed","agility",
            "ballStrip","intelligence","stamina","jumping"],
    "DT":  ["blockShedding","tackle","power","burst","speed","agility",
            "ballStrip","intelligence","stamina","jumping"],
    "OLB": ["blockShedding","tackle","zoneCover","burst","speed","agility",
            "ballStrip","intelligence","stamina","jumping"],
    "MLB": ["blockShedding","tackle","zoneCover","burst","speed","agility",
            "ballStrip","intelligence","stamina","jumping"],
    "CB":  ["manCover","zoneCover","tackle","ballStrip","burst","speed",
            "agility","elusiveness","intelligence","stamina","jumping"],
    "S":   ["manCover","zoneCover","tackle","ballStrip","burst","speed",
            "agility","elusiveness","intelligence","stamina","jumping"],
    "K":   ["kickAccuracy","burst","stamina","jumping"],
    "P":   ["kickAccuracy","burst","stamina","jumping"],
}

# Mental stats that should be non-zero for ALL positions
MENTAL_STATS = ["intelligence", "vision", "decisions", "discipline"]

# ALL gameplay stat fields (used to ensure no stat is left at 0)
ALL_GAMEPLAY_STATS = [
    "passBlock", "rushBlock", "throwOnRun", "routeRun", "ballSecurity", "trucking",
    "burst", "sPassAcc", "manCover", "elusiveness", "intelligence", "discipline",
    "stamina", "dPassAcc", "tackle", "zoneCover", "vision", "blockShedding",
    "power", "speed", "jumping", "decisions", "mPassAcc", "catching", "agility",
    "skillMove", "ballStrip", "kickAccuracy", "releaseLine",
]

# ---------------------------------------------------------------------------
# Appearance fix: tone-grouped pools
# ---------------------------------------------------------------------------

NOSE_BY_GROUP = {
    1: ["Nose1a", "Nose1b", "Nose1c", "Nose1d"],
    2: ["Nose2a", "Nose2b", "Nose2c", "Nose2d"],
    3: ["Nose3a", "Nose3c"],
    4: ["Nose4a", "Nose4b", "Nose4c", "Nose4d"],
    5: ["Nose5a", "Nose5b"],
}

MOUTH_BY_GROUP = {
    1: ["Mouth1a", "Mouth1b"],
    2: ["Mouth2a", "Mouth2b"],
    3: ["Mouth3a", "Mouth3b"],
    4: ["Mouth4a", "Mouth4b"],
    5: ["Mouth5a", "Mouth5b"],
}

# Eyebrows are NOT tone-grouped — Eyebrows1a/1b render correctly on all skin tones.
# Reference: 03ka/10-25_final roster confirms Head5 players use Eyebrows1a/1b.
SAFE_EYEBROWS = ["Eyebrows1a", "Eyebrows1b"]

# Beard pools by head group — data shows Head groups 4-5 overwhelmingly use Beard1 (92-93%),
# while Head groups 1-3 use Beard1-3 (75-85%). Beard4-6 are rare and often cause visual
# skin-tone mismatches. Only fix standard pool beards (not extended variants like Beard2r).
BEARD_BY_GROUP = {
    1: ["Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e",
        "Beard2a", "Beard2b", "Beard3a", "Beard3b"],
    2: ["Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e",
        "Beard2a", "Beard2b", "Beard3a", "Beard3b"],
    3: ["Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e",
        "Beard2a", "Beard2b", "Beard3a", "Beard3b"],
    4: ["Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e"],
    5: ["Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e"],
}

# Standard pool beard values (only fix these, skip extended variants)
STANDARD_BEARDS = {
    "Beard1a", "Beard1b", "Beard1c", "Beard1d", "Beard1e",
    "Beard2a", "Beard2b", "Beard3a", "Beard3b",
    "Beard4a", "Beard5a", "Beard6a",
}

# Standard pool grey/white/auburn hair values that look unrealistic on young players.
# Hair3 = greying/auburn (appropriate for 30+ only), Hair5 = grey, Hair6 = white/silver.
# Only fix standard pool (not extended variants).
YOUNG_HAIR_FIX = {
    "Hair3a", "Hair3b", "Hair3c", "Hair3d",    # greying/auburn — wrong for under-30
    "Hair5a", "Hair5b",                        # grey
    "Hair6a", "Hair6b", "Hair6c", "Hair6d",    # white/silver
}
DARK_HAIRS = ["Hair1a", "Hair1b", "Hair1c", "Hair1d", "Hair1e"]
GREYING_HAIRS = ["Hair3a", "Hair3b", "Hair3c", "Hair3d"]


def get_tone_group(component_value):
    """Extract skin tone group number (1-5) from a component like 'Head5a' or 'Nose2b'."""
    m = re.search(r'(\d)', component_value)
    return int(m.group(1)) if m else None


def fix_component(current_value, group, pool_by_group, name_seed):
    """Replace a component with one from the correct tone group, deterministically."""
    current_group = get_tone_group(current_value)
    if current_group == group:
        return current_value, False  # already correct

    pool = pool_by_group.get(group)
    if not pool:
        return current_value, False

    random.seed(name_seed + current_value)
    new_value = random.choice(pool)
    return new_value, True


def fix_appearance(player):
    """Fix skin-tone mismatches in a player's appearance array.
    Returns (fixed_count, details) where details lists what was changed."""
    app = player.get("appearance", [])
    if len(app) < 9:
        return 0, []

    name = f"{player['forename']} {player['surname']}"
    changes = []

    # Replace invalid head models that cause engine-level eyebrow rendering bugs.
    # Head4a and Head5c are excluded from valid generation pools (CLAUDE.md, add_missing_players.py)
    # because the engine renders eyebrows with orange/peach discoloration on these models
    # regardless of which eyebrow variant is assigned.
    INVALID_HEAD_REPLACEMENTS = {
        "Head4a": ["Head4b", "Head4c", "Head4d"],
        "Head5c": ["Head5a", "Head5b", "Head5d"],
    }
    head_raw = app[0]
    if head_raw in INVALID_HEAD_REPLACEMENTS:
        random.seed(name + "headfix")
        new_head = random.choice(INVALID_HEAD_REPLACEMENTS[head_raw])
        changes.append(f"Head: {head_raw} → {new_head} (invalid model)")
        app[0] = new_head

    head = app[0]   # index 0
    nose = app[5]   # index 5
    mouth = app[6]  # index 6
    brows = app[4]  # index 4

    head_group = get_tone_group(head)
    if head_group is None:
        return 0, []

    # Fix Nose
    new_nose, changed = fix_component(nose, head_group, NOSE_BY_GROUP, name + "nose")
    if changed:
        changes.append(f"Nose: {nose} → {new_nose}")
        app[5] = new_nose

    # Fix Mouth
    new_mouth, changed = fix_component(mouth, head_group, MOUTH_BY_GROUP, name + "mouth")
    if changed:
        changes.append(f"Mouth: {mouth} → {new_mouth}")
        app[6] = new_mouth

    # Fix Eyebrows — only Eyebrows1a/1b render correctly across all skin tones.
    # Eyebrows2-6 cause rendering artifacts (orange/peach discoloration).
    if app[4] not in SAFE_EYEBROWS:
        random.seed(name + "browfix")
        new_brows = random.choice(SAFE_EYEBROWS)
        changes.append(f"Eyebrows: {app[4]} → {new_brows}")
        app[4] = new_brows

    # Fix Beard (only standard pool beards — skip extended variants like Beard2r)
    beard = app[3]   # index 3
    if beard in STANDARD_BEARDS:
        beard_pool = BEARD_BY_GROUP.get(head_group)
        if beard_pool and beard not in beard_pool:
            random.seed(name + "beard" + beard)
            new_beard = random.choice(beard_pool)
            changes.append(f"Beard: {beard} → {new_beard}")
            app[3] = new_beard

    # Fix unrealistic grey/white hair on players (white hair = coaches only)
    age = player.get("age", 25)
    hair = app[2]   # index 2
    if hair in YOUNG_HAIR_FIX:
        if age < 30:
            # Under 30: dark hair
            random.seed(name + "hairfix")
            new_hair = random.choice(DARK_HAIRS)
            changes.append(f"Hair: {hair} → {new_hair} (age {age})")
            app[2] = new_hair
        elif hair.startswith("Hair6"):
            # 30+: white hair → salt-and-pepper (Hair6 is for coaches, not players)
            random.seed(name + "hairfix")
            new_hair = random.choice(GREYING_HAIRS)
            changes.append(f"Hair: {hair} → {new_hair} (age {age})")
            app[2] = new_hair

    # Fix hair that visually clashes with dark eyebrows on darker skin tones.
    # Eyebrows are always Eyebrows1a/b (dark), so Hair3 (auburn/greying) and Hair4
    # (reddish) look very out of place on Head4-5 players. Replace with dark Hair1.
    hair = app[2]
    if head_group >= 4 and (hair.startswith("Hair3") or hair.startswith("Hair4")):
        random.seed(name + "hairtonefix")
        new_hair = random.choice(DARK_HAIRS)
        changes.append(f"Hair: {hair} → {new_hair} (tone {head_group} + light hair mismatch)")
        app[2] = new_hair

    return len(changes), changes


# ---------------------------------------------------------------------------
# Rating fix (reuses fix_ratings.py logic)
# ---------------------------------------------------------------------------

EXP_BASE = {"0-1": 61, "2-3": 63, "4-6": 65, "7+": 67}
WAV_SCALE = 90.0
WAV_MAX_BONUS = 20


def exp_bucket(y):
    if y <= 1:  return "0-1"
    if y <= 3:  return "2-3"
    if y <= 6:  return "4-6"
    return "7+"


def compute_rating(pos, yexp, w_av, draft_pick, draft_round, name):
    eb   = exp_bucket(yexp)
    base = EXP_BASE.get(eb, 65)
    wav_bonus = min(WAV_MAX_BONUS, int(w_av * WAV_MAX_BONUS / WAV_SCALE)) if w_av and w_av > 0 else 0
    if draft_pick and draft_pick > 0:
        pick_bonus = max(0, 10 - int(draft_pick / 26))
    elif draft_round:
        pick_bonus = 6 if draft_round == 1 else (3 if draft_round == 2 else 0)
    else:
        pick_bonus = 0
    random.seed(name)
    jitter = random.randint(-2, 2)
    return max(55, min(92, base + wav_bonus + pick_bonus + jitter))


def update_primary_stats(p, new_rating):
    """Re-derive active stats to be consistent with new_rating."""
    pos = p.get("position", "WR")
    active_stats = POS_STATS.get(pos, POS_STATS["WR"])
    name = f"{p['forename']} {p['surname']}"
    random.seed(name + "stats")
    for stat in active_stats:
        if stat in p:
            p[stat] = max(60, min(99, new_rating + random.randint(-3, 3)))


def add_mental_baselines(p):
    """Set mental stats to a strong baseline derived from the player's OVR.
    Overwrites if current value is below the computed baseline."""
    pos = p.get("position", "WR")
    active_stats = POS_STATS.get(pos, POS_STATS["WR"])
    rating = p.get("rating", 60)
    name = f"{p['forename']} {p['surname']}"

    changes = []
    for stat in MENTAL_STATS:
        # Skip if it's already a primary stat for this position (already set correctly)
        if stat in active_stats:
            continue
        current = p.get(stat, 0)

        # Baseline: rating - 2 with jitter, floor 60, ceiling 90
        random.seed(name + stat + "mental3")
        baseline = max(60, min(90, rating - 2 + random.randint(-3, 3)))

        if current < baseline:
            p[stat] = baseline
            changes.append(f"{stat}: {current} → {baseline}")

    return changes


def add_secondary_baselines(p):
    """Set ALL remaining gameplay stats to non-zero baselines.
    This prevents the game engine from dragging down OVR with zero-valued stats."""
    pos = p.get("position", "WR")
    active_stats = set(POS_STATS.get(pos, POS_STATS["WR"]))
    rating = p.get("rating", 60)
    name = f"{p['forename']} {p['surname']}"
    is_kp = pos in ("K", "P")

    changes = []
    for stat in ALL_GAMEPLAY_STATS:
        # Skip primary stats that already have values (only rescue 0-valued ones)
        if stat in active_stats and p.get(stat, 0) > 0:
            continue
        # Skip mental stats (handled by add_mental_baselines)
        if stat in MENTAL_STATS:
            continue
        current = p.get(stat, 0)

        # Secondary baseline: rating - 2 with jitter, floor 60, ceiling 90
        random.seed(name + stat + "secondary3")
        baseline = max(60, min(90, rating - 2 + random.randint(-3, 3)))

        if current < baseline:
            p[stat] = baseline
            changes.append(f"{stat}: {current} → {baseline}")

    return changes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Loading roster...")
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    # Load nflverse data for rating recalculation
    wav_by_gsis = {}
    with open(NF_DRAFT) as f:
        for row in csv.DictReader(f):
            gsis = row.get("gsis_id", "").strip()
            if not gsis:
                continue
            try:
                wav_by_gsis[gsis] = float(row["w_av"]) if row.get("w_av") else 0.0
            except (ValueError, TypeError):
                wav_by_gsis[gsis] = 0.0

    player_data = {}
    with open(NF_PLAYERS) as f:
        for row in csv.DictReader(f):
            name = (row.get("display_name") or "").strip()
            if not name:
                continue
            gsis = row.get("gsis_id", "").strip()
            w_av = wav_by_gsis.get(gsis, 0.0)
            try:
                dr = int(float(row["draft_round"])) if row.get("draft_round") else None
            except (ValueError, TypeError):
                dr = None
            try:
                dp = int(float(row["draft_pick"])) if row.get("draft_pick") else 0
            except (ValueError, TypeError):
                dp = 0
            try:
                yexp = int(float(row["years_of_experience"])) if row.get("years_of_experience") else 0
            except (ValueError, TypeError):
                yexp = 0
            player_data[name] = {"w_av": w_av, "draft_round": dr, "draft_pick": dp, "yexp": yexp}

    # Counters
    appearance_fixes = 0
    appearance_details = []
    rating_bumps = []
    potential_fixes = 0
    mental_stat_fixes = 0
    mental_details = []
    secondary_stat_fixes = 0
    secondary_details = []

    for p in pgm:
        name = f"{p['forename']} {p['surname']}"
        is_team_player = p.get("teamID") in NFL_TEAMS

        # --- Fix 1: Appearance clipping (all players, not just team players) ---
        fix_count, details = fix_appearance(p)
        if fix_count > 0:
            appearance_fixes += 1
            appearance_details.append(f"  {p.get('teamID','??'):4} {p.get('position','??'):4} "
                                      f"{name:30} {', '.join(details)}")

        # --- Fix 2: Rating floor (team players only) ---
        if is_team_player and p.get("rating", 0) < 55:
            old_rating = p["rating"]
            # Try to compute a proper rating from nflverse data
            d = player_data.get(name, {})
            yexp = d.get("yexp", p.get("years_exp", 4))
            w_av = d.get("w_av", 0.0)
            dr = d.get("draft_round")
            dp = d.get("draft_pick", 0)
            new_rating = compute_rating(p.get("position", "WR"), yexp, w_av, dp, dr, name)
            new_rating = max(55, new_rating)

            p["rating"] = new_rating
            update_primary_stats(p, new_rating)
            rating_bumps.append(f"  {p['teamID']:4} {p.get('position','??'):4} "
                                f"{name:30} {old_rating} → {new_rating}")

        # --- Fix 2b: Ensure potential >= rating ---
        rating = p.get("rating", 0)
        potential = p.get("potential", 0)
        if rating > 0 and potential < rating:
            p["potential"] = max(rating, potential)
            potential_fixes += 1

        # --- Fix 3: Baseline mental stats (all players, boosted formula) ---
        mental_changes = add_mental_baselines(p)
        if mental_changes:
            mental_stat_fixes += 1
            mental_details.append(f"  {p.get('teamID','??'):4} {p.get('position','??'):4} "
                                  f"{name:30} {', '.join(mental_changes)}")

        # --- Fix 4: Secondary stat baselines (all players, no stat left at 0) ---
        secondary_changes = add_secondary_baselines(p)
        if secondary_changes:
            secondary_stat_fixes += 1
            secondary_details.append(f"  {p.get('teamID','??'):4} {p.get('position','??'):4} "
                                     f"{name:30} {', '.join(secondary_changes)}")

    # --- Print results ---
    print(f"\n{'='*60}")
    print(f"APPEARANCE FIXES: {appearance_fixes} players")
    print(f"{'='*60}")
    for line in appearance_details[:30]:
        print(line)
    if len(appearance_details) > 30:
        print(f"  ... and {len(appearance_details) - 30} more")

    print(f"\n{'='*60}")
    print(f"RATING BUMPS: {len(rating_bumps)} players bumped to 55+")
    print(f"{'='*60}")
    for line in rating_bumps[:30]:
        print(line)
    if len(rating_bumps) > 30:
        print(f"  ... and {len(rating_bumps) - 30} more")

    print(f"\nPOTENTIAL FIXES: {potential_fixes} players (potential < rating)")

    print(f"\n{'='*60}")
    print(f"MENTAL STAT BASELINES BOOSTED: {mental_stat_fixes} players")
    print(f"{'='*60}")
    for line in mental_details[:30]:
        print(line)
    if len(mental_details) > 30:
        print(f"  ... and {len(mental_details) - 30} more")

    print(f"\n{'='*60}")
    print(f"SECONDARY STAT BASELINES BOOSTED: {secondary_stat_fixes} players")
    print(f"{'='*60}")
    for line in secondary_details[:30]:
        print(line)
    if len(secondary_details) > 30:
        print(f"  ... and {len(secondary_details) - 30} more")

    # Verify: count remaining issues
    remaining_low = sum(1 for p in pgm if p.get("teamID") in NFL_TEAMS and p.get("rating", 99) < 55)
    remaining_mismatch = 0
    for p in pgm:
        app = p.get("appearance", [])
        if len(app) >= 9:
            hg = get_tone_group(app[0])
            ng = get_tone_group(app[5])
            if hg and ng and hg != ng:
                remaining_mismatch += 1

    print(f"\n--- POST-FIX VERIFICATION ---")
    print(f"Remaining Head/Nose mismatches: {remaining_mismatch}")
    print(f"Remaining team players below 55 OVR: {remaining_low}")

    # Distribution
    team_players = [p for p in pgm if p.get("teamID") in NFL_TEAMS]
    buckets = {}
    for p in team_players:
        b = (p["rating"] // 5) * 5
        buckets[b] = buckets.get(b, 0) + 1
    print(f"\nRating distribution (team players):")
    for k in sorted(buckets):
        bar = "#" * (buckets[k] // 5)
        print(f"  {k:3}-{k+4}: {buckets[k]:4}  {bar}")

    # Save
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    print(f"\nDone. Saved {len(pgm)} players to {ROSTER_FILE}")


if __name__ == "__main__":
    main()
