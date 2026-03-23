"""
Trim Team Rosters to 53-Man Limit
==================================
Converts the lowest-rated players on each NFL team to Free Agents until
every team has exactly 53 players (or fewer if they started with fewer).

Selection uses a two-phase approach:
  Phase 1: Guarantee positional minimums (e.g., at least 2 QBs, 3 WRs, etc.)
  Phase 2: Fill remaining slots up to 53 by rating descending

Free Agents and Rookies are untouched.

Usage:
    python scripts/trim_rosters.py

Output:
    Modifies PGMRoster_2026_Final.json in place
    Prints a per-team summary of changes
"""

import json

ROSTER_FILE = __import__("os").path.join(
    __import__("os").path.dirname(__file__), "..", "PGMRoster_2026_Final.json"
)

ROSTER_LIMIT = 53

# Minimum players to guarantee per position before any ratings-based cuts
POS_MINIMUMS = {
    "QB":  2,
    "RB":  2,
    "WR":  3,
    "TE":  2,
    "OT":  2,
    "OG":  2,
    "C":   1,
    "DE":  2,
    "DT":  2,
    "OLB": 2,
    "MLB": 1,
    "CB":  3,
    "S":   2,
    "K":   1,
    "P":   1,
}

NFL_TEAMS = {
    "ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN",
    "DET","GB","HOU","IND","JAX","KC","LAC","LAR","LV","MIA",
    "MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS",
}


def select_keepers(players):
    """
    Given a list of players on one team, return the set of idens to keep (≤ 53).
    Uses two-phase selection: positional minimums first, then top by rating.
    """
    kept_idens = set()

    # Phase 1: Positional minimums — for each position, keep the top N by rating
    by_pos = {}
    for p in players:
        pos = p["position"]
        by_pos.setdefault(pos, []).append(p)

    for pos, min_count in POS_MINIMUMS.items():
        candidates = sorted(by_pos.get(pos, []), key=lambda p: p["rating"], reverse=True)
        for p in candidates[:min_count]:
            kept_idens.add(p["iden"])

    # Phase 2: Fill remaining slots by rating until we hit 53
    remaining_slots = ROSTER_LIMIT - len(kept_idens)
    if remaining_slots > 0:
        not_yet_kept = [p for p in players if p["iden"] not in kept_idens]
        by_rating = sorted(not_yet_kept, key=lambda p: p["rating"], reverse=True)
        for p in by_rating[:remaining_slots]:
            kept_idens.add(p["iden"])

    return kept_idens


def main():
    with open(ROSTER_FILE) as f:
        pgm = json.load(f)

    total_before = len(pgm)
    fa_conversions = 0

    # Group active team players by team
    team_players = {t: [] for t in NFL_TEAMS}
    others = []

    for p in pgm:
        tid = p["teamID"]
        if tid in NFL_TEAMS:
            team_players[tid].append(p)
        else:
            others.append(p)

    # Determine keepers per team and convert the rest to FA
    print(f"{'Team':<6} {'Before':>6} {'Kept':>6} {'Cut→FA':>8}  {'Cut threshold':>14}")
    print("-" * 50)

    kept_idens = set()
    for team in sorted(NFL_TEAMS):
        players = team_players[team]
        team_kept = select_keepers(players)
        kept_idens.update(team_kept)

        cut = len(players) - len(team_kept)
        fa_conversions += cut

        # Find cut threshold rating (lowest kept rating)
        kept_ratings = sorted(
            [p["rating"] for p in players if p["iden"] in team_kept]
        )
        threshold = kept_ratings[0] if kept_ratings else "n/a"

        print(f"{team:<6} {len(players):>6} {len(team_kept):>6} {cut:>8}  rating≥{threshold:>6}")

    # Apply: convert non-kept team players to Free Agent
    for p in pgm:
        if p["teamID"] in NFL_TEAMS and p["iden"] not in kept_idens:
            p["teamID"] = "Free Agent"

    # Save
    with open(ROSTER_FILE, "w") as f:
        json.dump(pgm, f, separators=(",", ":"))

    total_after = len(pgm)
    print(f"\nTotal players: {total_before} → {total_after} (unchanged)")
    print(f"Players converted to Free Agent: {fa_conversions}")

    # Verify
    team_counts = {}
    for p in pgm:
        if p["teamID"] in NFL_TEAMS:
            team_counts[p["teamID"]] = team_counts.get(p["teamID"], 0) + 1

    over_limit = {t: c for t, c in team_counts.items() if c > ROSTER_LIMIT}
    if over_limit:
        print(f"\nWARNING: Teams still over {ROSTER_LIMIT}: {over_limit}")
    else:
        print(f"\nAll 32 teams at or under {ROSTER_LIMIT} players. ✓")


if __name__ == "__main__":
    main()
