#!/usr/bin/env python3
"""
Fix Mental Stats — Position-Aware Profiles + Notable Player Overrides
======================================================================
Replaces the flat "rating - 2 ± 3" formula with position-specific target ranges
for intelligence, vision, decisions, and discipline. Adds a curated override table
for marquee players with well-known football IQ reputations.

Also handles personality stat overrides (ambition, greed, loyalty) for notable
players, light formula nudges for 80+ OVR elite players, player removals, and
adding missing players.

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
import uuid

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
# Personality + character overrides (ambition, greed, loyalty, discipline, etc.)
# Can also include mental stats — merged with MENTAL_OVERRIDES at runtime.
# ---------------------------------------------------------------------------

PERSONALITY_OVERRIDES = {
    # ---- Off-field issues: lower intelligence/discipline/decisions ----
    ("Tyreek", "Hill"):       {"discipline": 62, "intelligence": 70, "decisions": 72},
    ("Deshaun", "Watson"):    {"discipline": 55, "decisions": 60, "intelligence": 65},
    ("Puka", "Nacua"):        {"discipline": 72, "intelligence": 78},
    ("Rasheed", "Walker"):    {"discipline": 60, "intelligence": 65},
    ("Rashee", "Rice"):       {"discipline": 58, "intelligence": 65},
    ("Jalen", "Carter"):      {"discipline": 68, "intelligence": 72},
    ("George", "Pickens"):    {"discipline": 60, "intelligence": 70},
    ("Chris", "Olave"):       {"discipline": 55, "intelligence": 65},

    # ---- Holdout/volatile: high greed, low loyalty ----
    ("Brandon", "Aiyuk"):     {"greed": 80, "loyalty": 20, "ambition": 85},
    ("Stefon", "Diggs"):      {"greed": 75, "loyalty": 15, "discipline": 65},
    ("Tariq", "Woolen"):      {"greed": 65, "loyalty": 25, "discipline": 68},
    ("Micah", "Parson"):      {"ambition": 90},  # greed/loyalty already realistic
    ("CeeDee", "Lamb"):       {"greed": 65, "loyalty": 40, "ambition": 85},
    ("Ja'Marr", "Chase"):     {"greed": 60, "loyalty": 35, "ambition": 85},
    ("Jaylen", "Waddle"):     {"greed": 50, "loyalty": 50},
    ("Jalen", "Ramsey"):      {"greed": 70, "loyalty": 10, "ambition": 90},

    # ---- Team-first / high-character: high loyalty, low greed ----
    ("Cameron", "Heyward"):   {"greed": 15, "loyalty": 90},
    ("Travis", "Kelce"):      {"greed": 25, "loyalty": 85},
    ("T.J.", "Watt"):         {"greed": 20, "loyalty": 80, "ambition": 85},
    ("Derrick", "Henry"):     {"greed": 20, "loyalty": 85},
    ("Bobby", "Wagner"):      {"greed": 15, "loyalty": 65, "ambition": 70},
    ("Kyle", "Hamilton"):     {"ambition": 75, "greed": 15, "loyalty": 80},
    ("Calais", "Campbell"):   {"greed": 15, "loyalty": 80, "ambition": 60},
    ("Joel", "Bitonio"):      {"greed": 15, "loyalty": 90},
    ("Quenton", "Nelson"):    {"greed": 20, "loyalty": 85},
    ("Penei", "Sewell"):      {"greed": 20, "loyalty": 80, "ambition": 75},
    ("Saquon", "Barkley"):    {"greed": 15, "loyalty": 70, "ambition": 80},
    ("Brock", "Bowers"):      {"ambition": 65},
    ("Aidan", "Hutchinson"):  {"greed": 10, "loyalty": 80, "ambition": 80},
    ("Christian", "McCaffrey"):{"greed": 15, "loyalty": 75},
    ("Tua", "Tagovailoa"):    {"greed": 15, "loyalty": 80},
    ("Mike", "Evans"):        {"loyalty": 90},
    ("Patrick", "Mahomes"):   {"greed": 25, "loyalty": 90},
    ("Josh", "Allen"):        {"greed": 20, "loyalty": 90},
}

PERSONALITY_STATS = ["ambition", "greed", "loyalty"]

# ---------------------------------------------------------------------------
# Players to remove from roster
# ---------------------------------------------------------------------------

REMOVE_PLAYERS = [
    ("James", "Pearce Jr."),  # OLB, ATL — off-field legal issues
]

# ---------------------------------------------------------------------------
# Players to add to roster (not found in current data)
# Format: (forename, surname, position, team, age, draft_season, draft_pick,
#          rating, personality_overrides)
# ---------------------------------------------------------------------------

ADD_PLAYERS = [
    {
        "forename": "Beanie", "surname": "Bishop Jr.", "position": "CB",
        "teamID": "NO", "age": 25, "draftSeason": 2024, "draftNum": 0,
        "rating": 65, "teamNum": 31,
        "personality": {"discipline": 60, "intelligence": 65},
    },
    {
        "forename": "Haason", "surname": "Reddick", "position": "OLB",
        "teamID": "Free Agent", "age": 30, "draftSeason": 2017, "draftNum": 13,
        "rating": 78, "teamNum": 0,
        "personality": {"greed": 85, "loyalty": 10, "ambition": 90},
    },
]

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


def get_merged_overrides(forename, surname):
    """Merge MENTAL_OVERRIDES and PERSONALITY_OVERRIDES for a player."""
    key = (forename, surname)
    merged = {}
    if key in MENTAL_OVERRIDES:
        merged.update(MENTAL_OVERRIDES[key])
    if key in PERSONALITY_OVERRIDES:
        merged.update(PERSONALITY_OVERRIDES[key])
    return merged


def compute_elite_personality_nudge(p, stat, name):
    """
    Light formula for 80+ OVR players WITHOUT explicit personality overrides.
    Returns a nudged value or None if no change needed.
    """
    rating = p.get("rating", 60)
    if rating < 80:
        return None

    pos = p.get("position", "WR")
    current = p.get(stat, 50)

    random.seed(name + stat + "elite_pers_v1")
    jitter = random.randint(-5, 5)

    # Cap extreme greed for OL — team-first position
    if stat == "greed" and pos in ("OT", "OG", "C") and current > 70:
        return min(current, 55 + jitter)

    # Long-career vets shouldn't have rock-bottom loyalty
    draft_season = p.get("draftSeason", 2024)
    years_exp = max(0, 2026 - draft_season)
    if stat == "loyalty" and years_exp >= 7 and current < 25:
        return max(current, 30 + jitter)

    # Young stars should be hungry
    if stat == "ambition" and years_exp <= 2 and current < 30:
        return max(current, 40 + jitter)

    return None


def process_player(p):
    """
    Compute all mental + personality stat changes for one player.
    Returns list of (stat, old_val, new_val, source) tuples.
    """
    name = f"{p['forename']} {p['surname']}"
    pos = p.get("position", "WR")
    rating = p.get("rating", 60)
    is_team_player = p.get("teamID") in NFL_TEAMS
    overrides = get_merged_overrides(p["forename"], p["surname"])

    changes = []

    # --- Mental stats (formula + overrides) ---
    for stat in MENTAL_STATS:
        old_val = p.get(stat, 0)

        if stat in overrides:
            new_val = overrides[stat]
            source = "override"
        else:
            target = compute_target(rating, stat, pos, name, is_team_player)
            if target is None:
                continue
            if old_val > target + 3:
                continue
            new_val = target
            source = "formula"

        if new_val != old_val:
            changes.append((stat, old_val, new_val, source))

    # --- Personality stats (override-only, then elite nudge) ---
    for stat in PERSONALITY_STATS:
        old_val = p.get(stat, 50)

        if stat in overrides:
            new_val = overrides[stat]
            source = "override"
        else:
            nudge = compute_elite_personality_nudge(p, stat, name)
            if nudge is None:
                continue
            new_val = nudge
            source = "elite_nudge"

        if new_val != old_val:
            changes.append((stat, old_val, new_val, source))

    return changes


# ---------------------------------------------------------------------------
# Player creation helpers (mirrors add_missing_players.py)
# ---------------------------------------------------------------------------

# Which stats are non-zero for each position
POS_ACTIVE_STATS = {
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

HEADS  = ["Head1a","Head1b","Head1c","Head1d","Head2a","Head2b","Head2c","Head2d",
           "Head3a","Head3b","Head3c","Head3d","Head4b","Head4c","Head4d","Head5a","Head5b","Head5d"]
EYES   = ["Eyes1a","Eyes1b","Eyes1c","Eyes1d","Eyes1e"]
HAIRS  = ["Hair1a","Hair1b","Hair1c","Hair1d","Hair1e","Hair2a","Hair2c","Hair2d",
           "Hair3a","Hair3b","Hair3c","Hair3d","Hair4a","Hair4b","Hair5a","Hair5b",
           "Hair6a","Hair6b","Hair6c","Hair6d"]
BROWS  = ["Eyebrows1a", "Eyebrows1b"]
NOSE_BY_GROUP = {
    1: ["Nose1a","Nose1b","Nose1c","Nose1d"], 2: ["Nose2a","Nose2b","Nose2c","Nose2d"],
    3: ["Nose3a","Nose3c"], 4: ["Nose4a","Nose4b","Nose4c","Nose4d"], 5: ["Nose5a","Nose5b"],
}
MOUTH_BY_GROUP = {
    1: ["Mouth1a","Mouth1b"], 2: ["Mouth2a","Mouth2b"], 3: ["Mouth3a","Mouth3b"],
    4: ["Mouth4a","Mouth4b"], 5: ["Mouth5a","Mouth5b"],
}
BEARD_BY_GROUP = {
    1: ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e","Beard2a","Beard2b","Beard3a","Beard3b"],
    2: ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e","Beard2a","Beard2b","Beard3a","Beard3b"],
    3: ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e","Beard2a","Beard2b","Beard3a","Beard3b"],
    4: ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e"],
    5: ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e"],
}


def rand_appearance(forename, surname):
    random.seed(forename + surname)
    head = random.choice(HEADS)
    tone_group = int(re.search(r'(\d)', head).group(1))
    return [
        head, random.choice(EYES), random.choice(HAIRS),
        random.choice(BEARD_BY_GROUP[tone_group]), random.choice(BROWS),
        random.choice(NOSE_BY_GROUP[tone_group]), random.choice(MOUTH_BY_GROUP[tone_group]),
        "Glasses1e", random.choice(["Clothes1", "Clothes2"]),
    ]


def growth_type_for_age(age):
    g = [0] * 31
    decline_start = max(0, 30 - age)
    for i in range(decline_start, 31):
        years_in = i - decline_start
        if years_in < 3:
            g[i] = -100
        elif years_in < 7:
            g[i] = random.randint(-500, -300)
        elif years_in < 12:
            g[i] = random.randint(-1200, -700)
        else:
            g[i] = random.randint(-2000, -1000)
    return g


def create_player(spec):
    """Create a full PGM player entry from an ADD_PLAYERS spec dict."""
    fn = spec["forename"]
    sn = spec["surname"]
    pos = spec["position"]
    rating = spec["rating"]
    age = spec["age"]

    random.seed(fn + sn + "growth")
    gt = growth_type_for_age(age)

    years_exp = max(0, 2026 - spec.get("draftSeason", 2024))
    potential = min(99, rating + random.randint(3, 10)) if years_exp <= 2 else rating

    # Personality defaults (overridden by spec["personality"] later)
    random.seed(fn + sn + "pers")
    greed = random.randint(15, 60)
    ambition = random.randint(20, 70)
    loyalty = random.randint(20, 65)

    # Stats — zero all, fill position-relevant
    stat_fields = {s: 0 for s in [
        "passBlock","rushBlock","throwOnRun","routeRun","ballSecurity","trucking",
        "burst","sPassAcc","manCover","elusiveness","intelligence","discipline",
        "dPassAcc","tackle","zoneCover","vision","blockShedding","power","speed",
        "jumping","releaseLine","decisions","mPassAcc","catching","agility",
        "skillMove","ballStrip","kickAccuracy","stamina",
    ]}
    active = POS_ACTIVE_STATS.get(pos, POS_ACTIVE_STATS["WR"])
    random.seed(fn + sn + "stats")
    for stat in active:
        if stat in stat_fields:
            stat_fields[stat] = max(60, min(99, rating + random.randint(-3, 3)))

    entry = {
        "passBlock": stat_fields["passBlock"], "rushBlock": stat_fields["rushBlock"],
        "throwOnRun": stat_fields["throwOnRun"], "injuryProne": 20,
        "potential": potential, "forename": fn,
        "routeRun": stat_fields["routeRun"], "ballSecurity": stat_fields["ballSecurity"],
        "trucking": stat_fields["trucking"], "burst": stat_fields["burst"],
        "sPassAcc": stat_fields["sPassAcc"], "loyalty": loyalty,
        "manCover": stat_fields["manCover"], "teamNum": spec.get("teamNum", 0),
        "elusiveness": stat_fields["elusiveness"],
        "intelligence": stat_fields["intelligence"], "discipline": stat_fields["discipline"],
        "draftSeason": spec.get("draftSeason", 2024),
        "appearance": rand_appearance(fn, sn), "stamina": stat_fields["stamina"],
        "eSalary": 0, "dPassAcc": stat_fields["dPassAcc"],
        "tackle": stat_fields["tackle"], "growthType": gt, "age": age,
        "zoneCover": stat_fields["zoneCover"], "vision": stat_fields["vision"],
        "blockShedding": stat_fields["blockShedding"], "power": stat_fields["power"],
        "eGuarantee": 0, "iden": str(uuid.uuid4()).upper(),
        "speed": stat_fields["speed"], "position": pos,
        "draftNum": spec.get("draftNum", 224), "jumping": stat_fields["jumping"],
        "greed": greed, "releaseLine": 0, "eLength": 1 if spec["teamID"] != "Free Agent" else 0,
        "ambition": ambition, "decisions": stat_fields["decisions"],
        "mPassAcc": stat_fields["mPassAcc"], "catching": stat_fields["catching"],
        "agility": stat_fields["agility"], "skillMove": stat_fields["skillMove"],
        "length": 1 if spec["teamID"] != "Free Agent" else 0,
        "guarantee": 0, "rating": rating, "teamID": spec["teamID"],
        "ballStrip": stat_fields["ballStrip"], "salary": 0,
        "kickAccuracy": stat_fields["kickAccuracy"], "surname": sn,
    }

    # Apply personality overrides from spec
    for stat, val in spec.get("personality", {}).items():
        entry[stat] = val

    # Zero contract for free agents
    if spec["teamID"] == "Free Agent":
        for f in ("salary", "eSalary", "guarantee", "eGuarantee", "length", "eLength"):
            entry[f] = 0

    return entry


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

    original_count = len(pgm)

    # --- Step 0: Fix whitespace in forenames (e.g., "Stefon  Diggs") ---
    forename_fixes = 0
    for p in pgm:
        cleaned = " ".join(p["forename"].split())
        if cleaned != p["forename"]:
            if not dry_run:
                p["forename"] = cleaned
            forename_fixes += 1
            print(f"  Fixed forename whitespace: '{p['forename']}' → '{cleaned}' ({p['surname']})")

    # --- Step 1: Remove players ---
    remove_set = {(fn, sn) for fn, sn in REMOVE_PLAYERS}
    removed = []
    if remove_set:
        new_pgm = []
        for p in pgm:
            key = (p["forename"], p["surname"])
            if key in remove_set:
                removed.append(f"{p['forename']} {p['surname']} ({p.get('position','?')}, {p.get('teamID','?')})")
                print(f"  REMOVE: {removed[-1]}")
            else:
                new_pgm.append(p)
        if not dry_run:
            pgm = new_pgm
        else:
            # Still use new_pgm for stat processing in dry-run
            pgm = new_pgm

    # --- Step 2: Add missing players ---
    added = []
    existing_names = {f"{p['forename']} {p['surname']}" for p in pgm}
    for spec in ADD_PLAYERS:
        name = f"{spec['forename']} {spec['surname']}"
        if name in existing_names:
            print(f"  SKIP ADD (already exists): {name}")
            continue
        entry = create_player(spec)
        added.append(f"{name} ({spec['position']}, {spec['teamID']})")
        print(f"  ADD: {added[-1]}")
        if not dry_run:
            pgm.append(entry)
        else:
            pgm.append(entry)  # Add for stat processing even in dry-run

    # --- Step 3: Process mental + personality stats ---
    all_changes = []
    players_changed = 0
    all_stat_names = MENTAL_STATS + PERSONALITY_STATS
    stat_counts = {s: 0 for s in all_stat_names}
    override_count = 0
    nudge_count = 0

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
                elif source == "elite_nudge":
                    nudge_count += 1
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
    print(f"MENTAL + PERSONALITY STATS FIX RESULTS")
    print(f"{'='*60}")
    print(f"  Forename whitespace fixes: {forename_fixes}")
    print(f"  Players removed:        {len(removed)}")
    print(f"  Players added:          {len(added)}")
    print(f"  Players with changes:   {players_changed}")
    print(f"  Total stat changes:     {len(all_changes)}")
    print(f"  Override applications:  {override_count}")
    print(f"  Elite nudges:           {nudge_count}")
    print(f"\n  By stat:")
    for stat in all_stat_names:
        if stat_counts[stat] > 0:
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

    # Sample elite nudges
    nudge_rows = [c for c in all_changes if c["source"] == "elite_nudge"]
    if nudge_rows:
        print(f"\n  Elite personality nudges (sample):")
        seen = set()
        for c in nudge_rows[:20]:
            key = (c["name"], c["stat"])
            if key not in seen:
                seen.add(key)
                print(f"    {c['name']:<30} {c['pos']:<5} {c['stat']:<14} "
                      f"{c['old_val']:>3} → {c['new_val']:>3} ({c['delta']:+d})")

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

    # --- Write report ---
    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "team", "pos", "stat", "old_val", "new_val", "delta", "source"
        ])
        writer.writeheader()

        # Add removal rows
        for r in removed:
            writer.writerow({"name": r, "team": "", "pos": "", "stat": "",
                             "old_val": "", "new_val": "", "delta": "", "source": "removed"})
        # Add addition rows
        for a in added:
            writer.writerow({"name": a, "team": "", "pos": "", "stat": "",
                             "old_val": "", "new_val": "", "delta": "", "source": "added"})

        writer.writerows(all_changes)
    print(f"\nReport written to: {args.report_path}")

    # --- Save roster ---
    if not dry_run:
        with open(ROSTER_FILE, "w", encoding="utf-8") as f:
            json.dump(pgm, f, separators=(",", ":"))
        print(f"\nSaved {len(pgm)} players to {ROSTER_FILE} (was {original_count})")
    else:
        print(f"\nDry-run complete. Roster would go from {original_count} to {len(pgm)} players.")
        print("Run with --apply to commit changes.")


if __name__ == "__main__":
    main()
