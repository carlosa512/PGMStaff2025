"""
Add Missing Players to PGMRoster_2026_Final.py
===============================================
Identifies active NFL players in nflverse_rosters_2026.csv that are not
present in PGMRoster_2026_Final.json and generates complete PGM entries
for them using:
  - nflverse data for identity, team, age, draft info
  - Existing PGM player ratings as calibration baselines
  - Placeholder contracts (temporary, pending real contract data)
  - Seeded-random appearances (manual review recommended for accuracy)

Usage:
    python scripts/add_missing_players.py

Output:
    Appends new entries to PGMRoster_2026_Final.json
    Prints a summary of added players
"""

import csv
import json
import random
import uuid
from collections import defaultdict
from datetime import date
from difflib import get_close_matches

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

REPO_ROOT = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
ROSTER_FILE  = f"{REPO_ROOT}/PGMRoster_2026_Final.json"
NF_ROSTERS   = f"{REPO_ROOT}/reference/nflverse_rosters_2026.csv"
NF_PLAYERS   = f"{REPO_ROOT}/reference/nflverse_players.csv"
NF_DRAFT     = f"{REPO_ROOT}/reference/nflverse_draft_picks.csv"

TEAM_MAP  = {"LA": "LAR"}
SKIP_POS  = {"LS", "FB"}

POS_MAP = {
    "C": "C", "CB": "CB", "DB": "CB", "DE": "DE", "DL": "DT", "DT": "DT",
    "FS": "S", "G": "OG", "ILB": "MLB", "K": "K", "LB": "OLB",
    "MLB": "MLB", "NT": "DT", "OL": "OG", "OLB": "OLB", "OT": "OT",
    "P": "P", "QB": "QB", "RB": "RB", "S": "S", "SAF": "S",
    "TE": "TE", "WR": "WR",
}

# Which stats are non-zero for each position
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

# Group positions for calibration lookup
POS_BUCKET = {
    "QB": "QB",
    "RB": "skill", "WR": "skill", "TE": "skill",
    "OT": "OL", "OG": "OL", "C": "OL",
    "DE": "DL", "DT": "DL",
    "OLB": "LB", "MLB": "LB",
    "CB": "DB", "S": "DB",
    "K": "spec", "P": "spec",
}

ALL_STATS = [
    "passBlock","rushBlock","throwOnRun","injuryProne","routeRun","ballSecurity",
    "trucking","burst","sPassAcc","manCover","elusiveness","intelligence",
    "discipline","dPassAcc","tackle","growthType","zoneCover","vision",
    "blockShedding","power","speed","jumping","greed","releaseLine","ambition",
    "decisions","mPassAcc","catching","agility","skillMove","ballStrip",
    "kickAccuracy","stamina","loyalty","potential",
]

ZERO_STATS = {s for s in ALL_STATS if s not in
              {"injuryProne","growthType","greed","ambition","loyalty","potential","stamina"}}

TODAY = date(2026, 3, 23)

# ---------------------------------------------------------------------------
# Appearance pool (same as update_staff_2026.py)
# ---------------------------------------------------------------------------

HEADS  = ["Head1a","Head1b","Head1c","Head1d","Head2a","Head2b","Head2c","Head2d",
           "Head3a","Head3b","Head3c","Head3d","Head4b","Head4c","Head4d","Head5a","Head5b","Head5d"]
EYES   = ["Eyes1a","Eyes1b","Eyes1c","Eyes1d","Eyes1e"]
HAIRS  = ["Hair1a","Hair1b","Hair1c","Hair1d","Hair1e","Hair2a","Hair2c","Hair2d",
           "Hair3a","Hair3b","Hair3c","Hair3d","Hair4a","Hair4b","Hair5a","Hair5b",
           "Hair6a","Hair6b","Hair6c","Hair6d"]
BEARDS = ["Beard1a","Beard1b","Beard1c","Beard1d","Beard1e","Beard2a","Beard2b",
           "Beard3a","Beard3b","Beard4a","Beard5a","Beard6a"]
BROWS  = ["Eyebrows1a","Eyebrows1b","Eyebrows2a","Eyebrows2b","Eyebrows3a","Eyebrows3b",
           "Eyebrows4a","Eyebrows4b","Eyebrows5a","Eyebrows5b","Eyebrows6a","Eyebrows6b"]
NOSES  = ["Nose1a","Nose1b","Nose1c","Nose1d","Nose2a","Nose2b","Nose2c","Nose2d",
           "Nose3a","Nose3c","Nose4a","Nose4b","Nose4c","Nose4d","Nose5a","Nose5b"]
MOUTHS = ["Mouth1a","Mouth1b","Mouth2a","Mouth2b","Mouth3a","Mouth3b",
           "Mouth4a","Mouth4b","Mouth5a","Mouth5b"]

def rand_appearance(forename, surname):
    random.seed(forename + surname)
    return [
        random.choice(HEADS),
        random.choice(EYES),
        random.choice(HAIRS),
        random.choice(BEARDS),
        random.choice(BROWS),
        random.choice(NOSES),
        random.choice(MOUTHS),
        "Glasses1e",
        random.choice(["Clothes1", "Clothes2"]),
    ]

# ---------------------------------------------------------------------------
# growthType — 31-element player decline curve
# ---------------------------------------------------------------------------

def growth_type_for_age(age):
    """
    Returns a 31-element growthType array.
    Decline starts around age 30 for most positions.
    Younger players have more zeros; older players decline sooner/steeper.
    """
    g = [0] * 31
    decline_start = max(0, 30 - age)  # index where decline begins
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

# ---------------------------------------------------------------------------
# Rating calibration from existing PGM players
# ---------------------------------------------------------------------------

def exp_bucket(years_exp):
    try:
        y = int(float(years_exp))
    except (ValueError, TypeError):
        y = 0
    if y <= 1:   return "0-1"
    if y <= 3:   return "2-3"
    if y <= 6:   return "4-6"
    return "7+"

def build_rating_table(pgm_players):
    """Compute median rating per (pos_bucket, exp_bucket) from existing PGM data."""
    from statistics import median
    buckets = defaultdict(list)
    for p in pgm_players:
        pos = p.get("position", "")
        pb  = POS_BUCKET.get(pos)
        rating = p.get("rating")
        yexp = p.get("years_exp", 0)
        if pb and rating:
            buckets[(pb, exp_bucket(yexp))].append(rating)

    table = {}
    for key, vals in buckets.items():
        table[key] = int(median(vals))

    # Fallback overall medians per bucket
    overall = defaultdict(list)
    for (pb, _), vals in buckets.items():
        overall[pb].extend(vals)
    for pb, vals in overall.items():
        table[(pb, "fallback")] = int(median(vals))

    return table

def lookup_rating(table, pos, years_exp):
    pb  = POS_BUCKET.get(pos, "skill")
    eb  = exp_bucket(years_exp)
    return table.get((pb, eb)) or table.get((pb, "fallback")) or 76

# ---------------------------------------------------------------------------
# Salary placeholder
# ---------------------------------------------------------------------------

def placeholder_salary(years_exp, draft_round):
    yr = int(float(years_exp)) if years_exp else 0
    random.seed(yr * 13 + (draft_round or 7))
    yr = int(float(years_exp)) if years_exp else 0
    if yr <= 0:
        base = 870_000
    elif yr <= 3:
        base = random.randint(1_000_000, 3_000_000)
    elif yr <= 6:
        base = random.randint(2_000_000, 8_000_000)
    else:
        base = random.randint(4_000_000, 12_000_000)

    # Bump for high draft picks
    if draft_round == 1:
        base = int(base * 1.5)
    elif draft_round == 2:
        base = int(base * 1.2)

    return base

# ---------------------------------------------------------------------------
# Main player entry builder
# ---------------------------------------------------------------------------

def build_player(row, draft_info, rating_table):
    """Build a complete PGM player entry from nflverse row + lookup data."""
    # Use full_name (common name) not first/last (legal name) to match how
    # nflverse identifies players everywhere else (e.g., "DJ Moore" not "Denniston Moore")
    full = row["full_name"].strip()
    parts = full.split(" ", 1)
    forename = parts[0]
    surname  = parts[1] if len(parts) > 1 else ""

    # Seed all random calls for this player by name
    random.seed(forename + surname)

    team = TEAM_MAP.get(row["team"], row["team"])
    dcp  = row["depth_chart_position"].strip()
    pos  = POS_MAP.get(dcp, "WR")  # fallback to WR if unknown

    # Age from birth_date
    try:
        bd   = date.fromisoformat(row["birth_date"])
        age  = (TODAY - bd).days // 365
    except Exception:
        age  = 25

    # Jersey number
    try:
        jersey = int(float(row["jersey_number"])) if row["jersey_number"] else 0
    except Exception:
        jersey = 0

    # Draft info
    years_exp   = row.get("years_exp", "0") or "0"
    rookie_year = row.get("rookie_year", "")
    try:
        draft_season = int(float(rookie_year)) if rookie_year else 2025
    except Exception:
        draft_season = 2025

    draft_round = draft_info.get("draft_round")
    draft_pick  = draft_info.get("draft_pick", 0)
    w_av        = draft_info.get("w_av", 0.0)

    # Rating — w_av (PFR career value, 0-44) is the heavy primary signal for veterans.
    # Overall pick number gives more granular draft pedigree than round alone.
    base = lookup_rating(rating_table, pos, years_exp)
    jitter = random.randint(-3, 3)
    # w_av: scale 0-44 → 0-24 bonus (dominant signal for veterans)
    wav_bonus = min(24, int(w_av * 24 / 44)) if w_av and w_av > 0 else 0
    # Pick bonus: overall pick 1→+10, pick 260→+0 (replaces coarse round-only bonus)
    if draft_pick and draft_pick > 0:
        pick_bonus = max(0, 10 - int(draft_pick / 26))
    elif draft_round:
        pick_bonus = 6 if draft_round == 1 else (3 if draft_round == 2 else 0)
    else:
        pick_bonus = 0
    rating = max(60, min(95, base + wav_bonus + pick_bonus + jitter))

    # Potential: higher for young players
    yr_int = int(float(years_exp)) if years_exp else 0
    if yr_int <= 2:
        potential = min(99, rating + random.randint(3, 10))
    else:
        potential = rating

    # growthType (re-seed for consistency)
    random.seed(forename + surname + "growth")
    gt = growth_type_for_age(age)

    # Salary
    random.seed(forename + surname + "salary")
    salary = placeholder_salary(years_exp, draft_round)
    guarantee  = salary
    e_salary   = salary
    e_guarantee = guarantee // 2

    # Personality
    random.seed(forename + surname + "pers")
    greed   = random.randint(15, 60)
    ambition= random.randint(20, 70)
    loyalty = random.randint(20, 65)

    # Stats — start all at 0, fill in position-relevant stats
    stat_fields = {s: 0 for s in [
        "passBlock","rushBlock","throwOnRun","routeRun","ballSecurity","trucking",
        "burst","sPassAcc","manCover","elusiveness","intelligence","discipline",
        "dPassAcc","tackle","zoneCover","vision","blockShedding","power","speed",
        "jumping","releaseLine","decisions","mPassAcc","catching","agility",
        "skillMove","ballStrip","kickAccuracy","stamina",
    ]}

    active_stats = POS_STATS.get(pos, POS_STATS["WR"])
    random.seed(forename + surname + "stats")
    for stat in active_stats:
        if stat in stat_fields:
            stat_fields[stat] = max(60, min(99, rating + random.randint(-3, 3)))

    stat_fields["injuryProne"] = 20

    entry = {
        "passBlock":    stat_fields["passBlock"],
        "rushBlock":    stat_fields["rushBlock"],
        "throwOnRun":   stat_fields["throwOnRun"],
        "injuryProne":  20,
        "potential":    potential,
        "forename":     forename,
        "routeRun":     stat_fields["routeRun"],
        "ballSecurity": stat_fields["ballSecurity"],
        "trucking":     stat_fields["trucking"],
        "burst":        stat_fields["burst"],
        "sPassAcc":     stat_fields["sPassAcc"],
        "loyalty":      loyalty,
        "manCover":     stat_fields["manCover"],
        "teamNum":      jersey,
        "elusiveness":  stat_fields["elusiveness"],
        "intelligence": stat_fields["intelligence"],
        "discipline":   stat_fields["discipline"],
        "draftSeason":  draft_season,
        "appearance":   rand_appearance(forename, surname),
        "stamina":      stat_fields["stamina"],
        "eSalary":      e_salary,
        "dPassAcc":     stat_fields["dPassAcc"],
        "tackle":       stat_fields["tackle"],
        "growthType":   gt,
        "age":          age,
        "zoneCover":    stat_fields["zoneCover"],
        "vision":       stat_fields["vision"],
        "blockShedding":stat_fields["blockShedding"],
        "power":        stat_fields["power"],
        "eGuarantee":   e_guarantee,
        "iden":         str(uuid.uuid4()).upper(),
        "speed":        stat_fields["speed"],
        "position":     pos,
        "draftNum":     draft_pick,
        "jumping":      stat_fields["jumping"],
        "greed":        greed,
        "releaseLine":  0,
        "eLength":      1,
        "ambition":     ambition,
        "decisions":    stat_fields["decisions"],
        "mPassAcc":     stat_fields["mPassAcc"],
        "catching":     stat_fields["catching"],
        "agility":      stat_fields["agility"],
        "skillMove":    stat_fields["skillMove"],
        "length":       1,
        "guarantee":    guarantee,
        "rating":       rating,
        "teamID":       team,
        "ballStrip":    stat_fields["ballStrip"],
        "salary":       salary,
        "kickAccuracy": stat_fields["kickAccuracy"],
        "surname":      surname,
    }
    return entry

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # Load current PGM roster
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    pgm_names = {f"{p['forename']} {p['surname']}" for p in pgm}
    pgm_name_list = list(pgm_names)

    # Also store years_exp on existing players for calibration
    # (nflverse has years_exp, PGM doesn't store it — we'll use nflverse for calibration)
    # Build rating table using existing PGM players + nflverse years_exp joined by name
    nf_exp_by_name = {}
    with open(NF_ROSTERS) as f:
        for row in csv.DictReader(f):
            nf_exp_by_name[row["full_name"].strip()] = row.get("years_exp", "0")

    # Attach years_exp to pgm players for calibration
    pgm_with_exp = []
    for p in pgm:
        name = f"{p['forename']} {p['surname']}"
        p2 = dict(p)
        p2["years_exp"] = nf_exp_by_name.get(name, "4")  # default mid-career if unknown
        pgm_with_exp.append(p2)

    rating_table = build_rating_table(pgm_with_exp)
    print(f"Rating calibration table: {len(rating_table)} buckets")

    # Load w_av (PFR weighted career value) from draft picks — keyed by gsis_id
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

    # Load nflverse draft data for pick numbers + w_av via gsis_id join
    draft_by_name = {}
    with open(NF_PLAYERS) as f:
        for row in csv.DictReader(f):
            name = (row.get("display_name") or row.get("full_name", "")).strip()
            if not name:
                continue
            try:
                dr = int(float(row["draft_round"])) if row.get("draft_round") else None
                dp = int(float(row["draft_pick"]))  if row.get("draft_pick")  else 0
            except Exception:
                dr, dp = None, 0
            gsis = row.get("gsis_id", "").strip()
            w_av = wav_by_gsis.get(gsis, 0.0)
            draft_by_name[name] = {"draft_round": dr, "draft_pick": dp, "w_av": w_av}

    # Build per-team cut thresholds from current file (rating of 53rd player per team)
    # New players whose rating falls below this threshold go straight to Free Agent.
    NFL_TEAMS = {
        "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
        "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
        "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
    }
    ROSTER_LIMIT = 53
    team_ratings = {}
    for p in pgm:
        if p["teamID"] in NFL_TEAMS:
            team_ratings.setdefault(p["teamID"], []).append(p["rating"])
    # Threshold = rating of the lowest kept player (53rd slot)
    team_threshold = {}
    for team, ratings in team_ratings.items():
        ratings_sorted = sorted(ratings, reverse=True)
        if len(ratings_sorted) >= ROSTER_LIMIT:
            team_threshold[team] = ratings_sorted[ROSTER_LIMIT - 1]
        else:
            team_threshold[team] = 0  # team has room, no threshold

    # Load nflverse rosters and identify missing players
    new_entries = []
    skipped_pos = 0
    already_present = 0
    fuzzy_skipped = 0
    sent_to_fa = 0

    with open(NF_ROSTERS) as f:
        for row in csv.DictReader(f):
            name = row["full_name"].strip()
            dcp  = row["depth_chart_position"].strip()
            status = row["status"]

            if dcp in SKIP_POS:
                skipped_pos += 1
                continue
            if status != "ACT":
                continue  # only add active roster players
            if name in pgm_names:
                already_present += 1
                continue
            # Skip if a fuzzy match exists (already in PGM under slightly different name)
            close = get_close_matches(name, pgm_name_list, n=1, cutoff=0.85)
            if close:
                fuzzy_skipped += 1
                continue

            # Build entry
            draft_info = draft_by_name.get(name, {"draft_round": None, "draft_pick": 0})
            entry = build_player(row, draft_info, rating_table)

            # If the team is already at 53 and this player's rating is below the cut
            # threshold, add them as a Free Agent rather than bloating the roster.
            team = entry["teamID"]
            threshold = team_threshold.get(team, 0)
            if team in NFL_TEAMS and threshold > 0 and entry["rating"] < threshold:
                entry["teamID"] = "Free Agent"
                sent_to_fa += 1

            new_entries.append(entry)

    print(f"\nAlready in PGM:     {already_present}")
    print(f"Skipped (LS/FB):    {skipped_pos}")
    print(f"Fuzzy-matched:      {fuzzy_skipped}")
    print(f"New players to add: {len(new_entries)}")
    print(f"  → Added as FA (below cut threshold): {sent_to_fa}")

    # Verify no UUID collisions
    existing_idens = {p["iden"] for p in pgm}
    for e in new_entries:
        while e["iden"] in existing_idens:
            e["iden"] = str(uuid.uuid4()).upper()
        existing_idens.add(e["iden"])

    # Append and save
    pgm.extend(new_entries)
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    print(f"\nTotal players in file: {len(pgm)}")
    print(f"Saved to {ROSTER_FILE}")

    # Sample output for verification
    print("\n--- Sample of added players ---")
    for e in new_entries[:8]:
        print(f"  {e['forename']} {e['surname']} | {e['position']} | {e['teamID']} "
              f"#{e['teamNum']} | age {e['age']} | rating {e['rating']} | "
              f"salary ${e['salary']:,}")

if __name__ == "__main__":
    main()
