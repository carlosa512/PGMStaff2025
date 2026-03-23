"""
Fix Player Ratings
==================
One-time repair script that addresses two artifacts:

1. BUMP: Active team players with rating < 55 → raised to 55 (keeps them playable)
2. RE-RATE: Team players stuck at exactly 68 from the old max(68,...) floor →
   re-derived using the w_av formula (PFR career value + pick bonus + calibrated base)
   Individual active stats are also updated to stay consistent with the new rating.

Uses the same rating formula as the updated add_missing_players.py.

Usage:
    python scripts/fix_ratings.py

Output:
    Modifies PGMRoster_2026_Final.json in place
    Prints a summary of all changes
"""

import csv
import json
import random
from datetime import date

REPO_ROOT = __import__("os").path.join(__import__("os").path.dirname(__file__), "..")
ROSTER_FILE = f"{REPO_ROOT}/PGMRoster_2026_Final.json"
NF_PLAYERS  = f"{REPO_ROOT}/reference/nflverse_players.csv"
NF_ROSTERS  = f"{REPO_ROOT}/reference/nflverse_rosters_2026.csv"
NF_DRAFT    = f"{REPO_ROOT}/reference/nflverse_draft_picks.csv"

TODAY = date(2026, 3, 23)

NFL_TEAMS = {
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
}

POS_BUCKET = {
    "QB": "QB",
    "RB": "skill", "WR": "skill", "TE": "skill",
    "OT": "OL",    "OG": "OL",    "C":  "OL",
    "DE": "DL",    "DT": "DL",
    "OLB": "LB",   "MLB": "LB",
    "CB": "DB",    "S":  "DB",
    "K":  "spec",  "P":  "spec",
}

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


def exp_bucket(y):
    if y <= 1:  return "0-1"
    if y <= 3:  return "2-3"
    if y <= 6:  return "4-6"
    return "7+"



# Fixed base by experience — not calibration table (which skews high from elite manual players)
EXP_BASE = {"0-1": 61, "2-3": 63, "4-6": 65, "7+": 67}

# w_av: normalize to 90 (realistic ceiling for active roster veterans).
# HOF-level careers hit 100+, but active players rarely exceed 90 of accrued value.
WAV_SCALE = 90.0
WAV_MAX_BONUS = 20


def compute_rating(pos, yexp, w_av, draft_pick, draft_round, name):
    """New formula: fixed exp base + w_av quality signal + granular pick bonus."""
    eb   = exp_bucket(yexp)
    base = EXP_BASE.get(eb, 65)

    # w_av bonus: 0-20 scaled against 90-career ceiling
    wav_bonus = min(WAV_MAX_BONUS, int(w_av * WAV_MAX_BONUS / WAV_SCALE)) if w_av and w_av > 0 else 0

    # Pick bonus: overall pick 1 → +10, pick 260 → +0; fall back to round if no pick
    if draft_pick and draft_pick > 0:
        pick_bonus = max(0, 10 - int(draft_pick / 26))
    elif draft_round:
        pick_bonus = 6 if draft_round == 1 else (3 if draft_round == 2 else 0)
    else:
        pick_bonus = 0

    random.seed(name)
    jitter = random.randint(-2, 2)
    return max(60, min(92, base + wav_bonus + pick_bonus + jitter))


def update_stats(p, new_rating):
    """Re-derive active stats to be consistent with new_rating."""
    pos = p.get("position", "WR")
    active_stats = POS_STATS.get(pos, POS_STATS["WR"])
    name = f"{p['forename']} {p['surname']}"
    random.seed(name + "stats")
    for stat in active_stats:
        if stat in p:
            p[stat] = max(60, min(99, new_rating + random.randint(-3, 3)))


def main():
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    # Load years_exp by name from nflverse rosters
    nf_exp_by_name = {}
    with open(NF_ROSTERS) as f:
        for row in csv.DictReader(f):
            nf_exp_by_name[row["full_name"].strip()] = row.get("years_exp", "4")

    # Load w_av lookup keyed by gsis_id
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

    # Build player data lookup: name → {w_av, draft_round, draft_pick, yexp}
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

    bumped = []
    rerated = []

    for p in pgm:
        if p["teamID"] not in NFL_TEAMS:
            continue

        name = f"{p['forename']} {p['surname']}"
        old_rating = p["rating"]

        # Pass 1: bump below-55 to 55
        if old_rating < 55:
            p["rating"] = 55
            p["potential"] = max(55, p.get("potential", 55))
            update_stats(p, 55)
            bumped.append(f"  {p['teamID']:4} {p['position']:4} {name} {old_rating} → 55")
            continue

        # Pass 2: re-rate 68-floor artifacts
        if old_rating != 68:
            continue

        d = player_data.get(name, {})
        yexp = d.get("yexp", 4)
        w_av = d.get("w_av", 0.0)
        dr   = d.get("draft_round")
        dp   = d.get("draft_pick", 0)

        new_rating = compute_rating(p["position"], yexp, w_av, dp, dr, name)

        if new_rating == old_rating:
            continue  # no change needed

        p["rating"] = new_rating
        p["potential"] = max(new_rating, p.get("potential", new_rating))
        update_stats(p, new_rating)
        rerated.append((name, p["position"], p["teamID"], old_rating, new_rating,
                        f"w_av={w_av:.0f} pick={dp} yexp={yexp}"))

    # Print results
    print(f"\n=== BUMPED to 55 ({len(bumped)}) ===")
    for line in bumped:
        print(line)

    print(f"\n=== RE-RATED from 68 ({len(rerated)}) ===")
    up   = [(n, pos, t, o, nw, info) for n, pos, t, o, nw, info in rerated if nw > o]
    down = [(n, pos, t, o, nw, info) for n, pos, t, o, nw, info in rerated if nw < o]
    print(f"  Up:   {len(up)}, Down: {len(down)}")
    print("\n  Notable increases (w_av suggests quality):")
    for row in sorted(up, key=lambda x: x[4], reverse=True)[:20]:
        n, pos, t, o, nw, info = row
        print(f"    {t:4} {pos:4} {n:30} {o} → {nw}  ({info})")
    print("\n  Notable decreases (UDFA/low-career):")
    for row in sorted(down, key=lambda x: x[4])[:20]:
        n, pos, t, o, nw, info = row
        print(f"    {t:4} {pos:4} {n:30} {o} → {nw}  ({info})")

    # Save
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    print(f"\nDone. Bumped {len(bumped)}, re-rated {len(rerated)} of {sum(1 for p in pgm if p['teamID'] in NFL_TEAMS and p.get('rating') == 68)} floor players.")

    # Print new distribution
    team_players = [p for p in pgm if p["teamID"] in NFL_TEAMS]
    buckets = {}
    for p in team_players:
        b = (p["rating"] // 5) * 5
        buckets[b] = buckets.get(b, 0) + 1
    print("\nNew rating distribution:")
    for k in sorted(buckets):
        bar = "#" * (buckets[k] // 5)
        print(f"  {k:3}-{k+4}: {buckets[k]:4}  {bar}")


if __name__ == "__main__":
    main()
