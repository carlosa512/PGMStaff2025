#!/usr/bin/env python3
"""
Apply PFF-Style Ratings to PGM3 Roster
=======================================
Replicates AaronsAron's rating model: a recency-weighted, snap-count-weighted blend
of per-season performance scores, with a playing-time threshold and a draft-position
fallback for recent draftees. Approximates PFF grades using nflverse season stats.

Two modes:
  1. Formula synthesis (default): Uses nflverse player_stats (offense + defense)
     to compute per-position performance scores. No PFF subscription needed.
  2. CSV import: If reference/pff_grades_2025.csv exists, uses those grades directly
     (community Kaggle datasets, manual exports, etc.) instead of formula synthesis.

Usage:
    python scripts/apply_pff_ratings.py            # dry-run, shows changes only
    python scripts/apply_pff_ratings.py --apply    # writes changes to roster JSON
    python scripts/apply_pff_ratings.py --apply --report-path reference/pff_rating_report.csv

Output:
    Dry-run: prints table of proposed rating changes
    --apply: modifies PGMRoster_2026_Final.json in place
    reference/pff_rating_report.csv: full audit trail (always written)
"""

import argparse
import csv
import json
import os
import random
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")
OFF_STATS_FILE = os.path.join(REPO_ROOT, "reference", "nflverse_player_stats_offense.csv")
DEF_STATS_FILE = os.path.join(REPO_ROOT, "reference", "nflverse_player_stats_defense.csv")
PLAYERS_FILE = os.path.join(REPO_ROOT, "reference", "nflverse_players.csv")
DRAFT_FILE = os.path.join(REPO_ROOT, "reference", "nflverse_draft_picks.csv")
PFF_CSV_FILE = os.path.join(REPO_ROOT, "reference", "pff_grades_2025.csv")

CURRENT_YEAR = 2026  # in-game start year

NFL_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

# Recency weights per season offset from current (0 = most recent played season = 2025)
RECENCY_WEIGHTS = {0: 1.0, 1: 0.60, 2: 0.35, 3: 0.15}

# Snap threshold per season for full trust; below this, performance score is discounted
SNAP_THRESHOLD = 500

# Total snap-weight needed (across all seasons) before a player is "fully" performance-rated
FULL_TRUST_SNAP_WEIGHT = 3.0

# Off-roster baseline for players with very little playing time
OFF_ROSTER_BASELINE = 57

# Seasons to consider (most recent first)
STAT_SEASONS = [2025, 2024, 2023, 2022]

# Recent draft threshold: players drafted within this many years get draft-position blending
RECENT_DRAFT_YEARS = 4

# Snap threshold (career) before draft position no longer matters for draftees
DRAFTEE_SNAP_THRESHOLD = 700

# Name normalization aliases (mirrors update_contracts.py)
NAME_ALIASES = {
    "micah parson": "micah parsons",
    "riq woolen": "tariq woolen",
    "ken walker": "kenneth walker",
    "gabriel davis": "gabe davis",
    "josh palmer": "joshua palmer",
    "isaiah likely": "isaiah likely",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name):
    """Lowercase, strip punctuation, collapse spaces."""
    n = name.lower().strip()
    n = re.sub(r"[''`.]", "", n)
    n = re.sub(r"\s+", " ", n)
    return NAME_ALIASES.get(n, n)


def safe_float(val, default=0.0):
    try:
        return float(val) if val not in (None, "", "NA", "nan") else default
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    try:
        return int(float(val)) if val not in (None, "", "NA", "nan") else default
    except (ValueError, TypeError):
        return default


def percentile_rank(value, all_values):
    """Return 0-100 percentile rank of value within all_values list."""
    if not all_values or len(all_values) < 2:
        return 50.0
    below = sum(1 for v in all_values if v < value)
    return 100.0 * below / len(all_values)


# ---------------------------------------------------------------------------
# Per-season performance score computation
# ---------------------------------------------------------------------------

def compute_offense_scores(off_rows):
    """
    Compute per-player per-season performance scores (0-100) from offensive stats.
    Returns: dict[(norm_name, season)] -> {"score": float, "snaps": int, "pos": str}
    """
    # Group by (name, season, position)
    by_player = defaultdict(lambda: defaultdict(float))
    by_player_pos = {}
    by_player_snaps = defaultdict(int)

    for row in off_rows:
        name = normalize_name(row.get("player_name", row.get("player_display_name", "")))
        if not name:
            continue
        season = safe_int(row.get("season", 0))
        if season not in STAT_SEASONS:
            continue
        pos = (row.get("position") or "").upper()
        key = (name, season)

        # Accumulate stats (players can have multiple rows if they changed teams mid-season)
        by_player[key]["completions"] += safe_float(row.get("completions"))
        by_player[key]["attempts"] += safe_float(row.get("attempts"))
        by_player[key]["passing_yards"] += safe_float(row.get("passing_yards"))
        by_player[key]["passing_tds"] += safe_float(row.get("passing_tds"))
        by_player[key]["interceptions"] += safe_float(row.get("interceptions"))
        by_player[key]["rushing_yards"] += safe_float(row.get("rushing_yards"))
        by_player[key]["carries"] += safe_float(row.get("carries"))
        by_player[key]["receiving_yards"] += safe_float(row.get("receiving_yards"))
        by_player[key]["targets"] += safe_float(row.get("targets"))
        by_player[key]["receptions"] += safe_float(row.get("receptions"))
        # Snap counts — try several column name variants
        snaps = safe_int(row.get("offense_snaps") or row.get("snap_counts_offense")
                         or row.get("snaps_played_offense") or row.get("games") or 0)
        by_player_snaps[key] += snaps
        if pos:
            by_player_pos[key] = pos

    # Compute raw metrics per player-season
    raw_metrics = {}
    for (name, season), stats in by_player.items():
        pos = by_player_pos.get((name, season), "")
        snaps = by_player_snaps.get((name, season), 0)
        s = stats

        if pos == "QB":
            att = s["attempts"]
            cmp_pct = s["completions"] / att if att > 0 else 0
            ypa = s["passing_yards"] / att if att > 0 else 0
            td_int = (s["passing_tds"] + 1) / (s["interceptions"] + 1)
            rush_threat = s["rushing_yards"] / max(1, snaps if snaps > 0 else 1)
            metric = 0.35 * cmp_pct * 100 + 0.35 * min(ypa * 10, 100) + \
                     0.20 * min(td_int * 25, 100) + 0.10 * min(rush_threat * 50, 100)

        elif pos == "RB":
            carries = s["carries"]
            ypc = s["rushing_yards"] / carries if carries > 0 else 0
            scrimmage_per_snap = (s["rushing_yards"] + s["receiving_yards"]) / max(1, snaps) if snaps > 0 else 0
            metric = 0.40 * min(ypc * 12, 100) + 0.35 * min(scrimmage_per_snap * 80, 100) + \
                     0.25 * min(s["receiving_yards"] / 80, 100)

        elif pos in ("WR", "TE"):
            tgt = s["targets"]
            ypt = s["receiving_yards"] / tgt if tgt > 0 else 0
            catch_pct = s["receptions"] / tgt if tgt > 0 else 0
            yps = s["receiving_yards"] / max(1, snaps) if snaps > 0 else 0
            if pos == "WR":
                metric = 0.40 * min(ypt * 10, 100) + 0.35 * catch_pct * 100 + \
                         0.25 * min(yps * 80, 100)
            else:  # TE
                metric = 0.35 * min(ypt * 10, 100) + 0.30 * catch_pct * 100 + \
                         0.35 * min(yps * 80, 100)
        else:
            metric = None

        if metric is not None:
            raw_metrics[(name, season, pos)] = {"metric": metric, "snaps": snaps}

    # Percentile rank within position group per season
    scores = {}
    pos_season_metrics = defaultdict(list)
    for (name, season, pos), data in raw_metrics.items():
        pos_season_metrics[(pos, season)].append(data["metric"])

    for (name, season, pos), data in raw_metrics.items():
        all_m = pos_season_metrics[(pos, season)]
        score = percentile_rank(data["metric"], all_m)
        scores[(name, season)] = {"score": score, "snaps": data["snaps"], "pos": pos}

    return scores


def compute_defense_scores(def_rows):
    """
    Compute per-player per-season performance scores from defensive stats.
    Returns: dict[(norm_name, season)] -> {"score": float, "snaps": int, "pos": str}
    """
    by_player = defaultdict(lambda: defaultdict(float))
    by_player_pos = {}
    by_player_snaps = defaultdict(int)

    for row in def_rows:
        name = normalize_name(row.get("player_name", row.get("player_display_name", "")))
        if not name:
            continue
        season = safe_int(row.get("season", 0))
        if season not in STAT_SEASONS:
            continue
        pos = (row.get("position") or "").upper()
        key = (name, season)

        by_player[key]["tackles"] += safe_float(row.get("tackles") or row.get("tackles_solo", 0))
        by_player[key]["sacks"] += safe_float(row.get("sacks"))
        by_player[key]["tfl"] += safe_float(row.get("tackles_for_loss") or row.get("tfl", 0))
        by_player[key]["interceptions"] += safe_float(row.get("interceptions"))
        by_player[key]["pbu"] += safe_float(row.get("pass_breakups") or row.get("passes_defended", 0))
        by_player[key]["fumbles"] += safe_float(row.get("fumbles_forced", 0))
        snaps = safe_int(row.get("defense_snaps") or row.get("snap_counts_defense")
                         or row.get("snaps_played_defense") or row.get("games") or 0)
        by_player_snaps[key] += snaps
        if pos:
            by_player_pos[key] = pos

    raw_metrics = {}
    for (name, season), stats in by_player.items():
        pos = by_player_pos.get((name, season), "")
        snaps = by_player_snaps.get((name, season), 0)
        s = stats
        snaps_safe = max(1, snaps)

        if pos in ("DE", "OLB"):
            # Pass rush focus
            metric = 0.50 * min(s["sacks"] / snaps_safe * 1000, 100) + \
                     0.50 * min(s["tfl"] / snaps_safe * 800, 100)

        elif pos == "DT":
            metric = 0.50 * min(s["tfl"] / snaps_safe * 800, 100) + \
                     0.30 * min(s["sacks"] / snaps_safe * 800, 100) + \
                     0.20 * min(s["tackles"] / snaps_safe * 300, 100)

        elif pos == "MLB":
            metric = 0.40 * min(s["tackles"] / snaps_safe * 300, 100) + \
                     0.30 * min(s["tfl"] / snaps_safe * 600, 100) + \
                     0.30 * min((s["interceptions"] + s["pbu"]) / snaps_safe * 800, 100)

        elif pos == "CB":
            # Lower targets allowed = better; reward PBUs and INTs
            metric = 0.40 * min((s["pbu"] + s["interceptions"] * 2) / snaps_safe * 600, 100) + \
                     0.30 * min(s["interceptions"] / snaps_safe * 1500, 100) + \
                     0.30 * min(s["tackles"] / snaps_safe * 200, 100)

        elif pos == "S":
            metric = 0.35 * min(s["tackles"] / snaps_safe * 250, 100) + \
                     0.35 * min((s["pbu"] + s["interceptions"] * 2) / snaps_safe * 600, 100) + \
                     0.30 * min(s["interceptions"] / snaps_safe * 1500, 100)

        else:
            metric = None

        if metric is not None:
            raw_metrics[(name, season, pos)] = {"metric": metric, "snaps": snaps}

    scores = {}
    pos_season_metrics = defaultdict(list)
    for (name, season, pos), data in raw_metrics.items():
        pos_season_metrics[(pos, season)].append(data["metric"])

    for (name, season, pos), data in raw_metrics.items():
        all_m = pos_season_metrics[(pos, season)]
        score = percentile_rank(data["metric"], all_m)
        scores[(name, season)] = {"score": score, "snaps": data["snaps"], "pos": pos}

    return scores


# ---------------------------------------------------------------------------
# Weighted rating derivation
# ---------------------------------------------------------------------------

def derive_rating_from_scores(norm_name, season_scores):
    """
    Apply AaronsAron's recency + snap-count weighting model.

    season_scores: list of {"season": int, "score": float, "snaps": int}
    Returns: (final_score, total_snap_weight, seasons_used)
    """
    weighted_sum = 0.0
    weight_sum = 0.0
    total_snap_weight = 0.0

    for entry in season_scores:
        season = entry["season"]
        score = entry["score"]
        snaps = entry["snaps"]
        offset = (STAT_SEASONS[0]) - season  # 0 = most recent
        recency_w = RECENCY_WEIGHTS.get(offset, 0.0)
        if recency_w == 0.0:
            continue
        snap_w = min(1.0, snaps / SNAP_THRESHOLD) if snaps > 0 else 0.0
        combined_w = recency_w * snap_w
        weighted_sum += score * combined_w
        weight_sum += combined_w
        total_snap_weight += snap_w

    if weight_sum == 0:
        return None, total_snap_weight, 0

    weighted_score = weighted_sum / weight_sum
    seasons_used = len([e for e in season_scores if e["snaps"] > 0])
    return weighted_score, total_snap_weight, seasons_used


def apply_playing_time_threshold(weighted_score, total_snap_weight):
    """Blend performance score with off-roster baseline based on playing time."""
    pff_weight = min(1.0, total_snap_weight / FULL_TRUST_SNAP_WEIGHT)
    return pff_weight * weighted_score + (1 - pff_weight) * OFF_ROSTER_BASELINE


def draft_position_rating(overall_pick):
    """Draft-position-based rating (same formula as add_missing_players.py)."""
    return max(58, min(85, 85 - int(overall_pick / 8)))


def apply_draftee_blending(perf_score, career_snaps, draft_rating):
    """Blend performance score with draft rating based on accumulated career snaps."""
    snap_weight = min(1.0, career_snaps / DRAFTEE_SNAP_THRESHOLD)
    return snap_weight * perf_score + (1 - snap_weight) * draft_rating


def perf_score_to_pgm3_rating(score):
    """
    Map 0-100 performance percentile to PGM3 rating (55-95).
    Calibrated so ~50th percentile starter ≈ 72, top 5% ≈ 90+, elite ≈ 95.
    """
    if score >= 90:
        return min(95, int(85 + (score - 90) * 1.0))
    elif score >= 75:
        return int(76 + (score - 75) * 0.6)
    elif score >= 50:
        return int(65 + (score - 50) * 0.44)
    else:
        return max(55, int(55 + score * 0.2))


def blend_with_current(perf_derived, current_rating):
    """Blend 70/30 toward perf-derived to avoid wild swings from noisy data."""
    blended = int(0.70 * perf_derived + 0.30 * current_rating)
    return max(55, min(95, blended))


# ---------------------------------------------------------------------------
# PFF CSV import mode
# ---------------------------------------------------------------------------

def load_pff_csv(path):
    """
    Load user-provided PFF grades CSV. Returns dict[norm_name] -> {"grade": float, "pos": str}.
    Auto-detects common column names.
    """
    result = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.lower().strip() for h in reader.fieldnames or []]

        # Find name column
        name_col = next((h for h in reader.fieldnames
                         if h.lower() in ("player", "player_name", "name", "full_name")), None)
        # Find grade column
        grade_col = next((h for h in reader.fieldnames
                          if h.lower() in ("grade", "overall_grade", "pff_grade",
                                           "grades_offense", "grades_defense", "grades_overall")), None)
        pos_col = next((h for h in reader.fieldnames
                        if h.lower() in ("position", "pos")), None)

        if not name_col or not grade_col:
            print(f"[WARN] PFF CSV: could not find name/grade columns in {headers}")
            return result

        f.seek(0)
        next(reader)  # skip header
        for row in reader:
            name = normalize_name(row.get(name_col, ""))
            grade = safe_float(row.get(grade_col))
            pos = (row.get(pos_col, "") or "").upper() if pos_col else ""
            if name and grade > 0:
                result[name] = {"grade": grade, "pos": pos}

    return result


def pff_grade_to_pgm3_rating(grade):
    """Map PFF 0-100 grade to PGM3 rating. Calibrated to PFF tier labels."""
    # PFF tiers: 90-100=elite, 85-89=pro bowler, 70-84=starter, 60-69=backup, <60=replaceable
    if grade >= 90:
        return min(95, int(85 + (grade - 90) * 1.0))
    elif grade >= 80:
        return int(79 + (grade - 80) * 0.6)
    elif grade >= 70:
        return int(72 + (grade - 70) * 0.7)
    elif grade >= 60:
        return int(65 + (grade - 60) * 0.7)
    else:
        return max(55, int(55 + grade * 0.17))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_draft_data():
    """Load draft picks to get overall pick number by player name."""
    if not os.path.exists(DRAFT_FILE):
        return {}
    result = {}
    with open(DRAFT_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = normalize_name(row.get("player_name", ""))
            season = safe_int(row.get("season", 0))
            pick = safe_int(row.get("pick", 0))
            if name and season and pick:
                result[name] = {"season": season, "pick": pick}
    return result


def load_players_data():
    """Load nflverse_players.csv for gsis_id and basic info."""
    if not os.path.exists(PLAYERS_FILE):
        return {}
    result = {}
    with open(PLAYERS_FILE, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = normalize_name(row.get("display_name", "") or row.get("full_name", ""))
            if not name:
                continue
            result[name] = {
                "gsis_id": row.get("gsis_id", ""),
                "draft_round": safe_int(row.get("draft_round")),
                "draft_pick": safe_int(row.get("draft_number") or row.get("draft_pick")),
                "years_exp": safe_int(row.get("years_of_experience")),
            }
    return result


def load_stat_rows(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Apply PFF-style ratings to PGM3 roster")
    parser.add_argument("--apply", action="store_true",
                        help="Write changes to roster JSON (default: dry-run only)")
    parser.add_argument("--report-path", default=os.path.join(REPO_ROOT, "reference",
                                                               "pff_rating_report.csv"),
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

    # Detect PFF CSV mode
    use_pff_csv = os.path.exists(PFF_CSV_FILE)
    if use_pff_csv:
        print(f"\n[CSV mode] Found {PFF_CSV_FILE} — using PFF grades directly.")
        pff_data = load_pff_csv(PFF_CSV_FILE)
        print(f"  Loaded {len(pff_data)} player grades from CSV.")
    else:
        print(f"\n[Formula mode] No pff_grades_2025.csv found — using nflverse stat synthesis.")
        off_rows = load_stat_rows(OFF_STATS_FILE)
        def_rows = load_stat_rows(DEF_STATS_FILE)
        if not off_rows and not def_rows:
            print("[ERROR] No stat files found. Run pull_nflverse_rosters.py first.")
            sys.exit(1)
        print(f"  Offense stat rows: {len(off_rows)}")
        print(f"  Defense stat rows: {len(def_rows)}")
        print("  Computing performance scores...")
        off_scores = compute_offense_scores(off_rows)
        def_scores = compute_defense_scores(def_rows)
        all_scores = {**off_scores, **def_scores}
        print(f"  Scored {len(all_scores)} player-season entries.")

    draft_data = load_draft_data()
    players_data = load_players_data()

    print(f"\nProcessing {len(pgm)} roster players...")

    changes = []
    unchanged = 0
    unmatched = 0

    OFFENSIVE_POSITIONS = {"QB", "RB", "WR", "TE", "OT", "OG", "C"}
    DEFENSIVE_POSITIONS = {"DE", "DT", "OLB", "MLB", "CB", "S"}

    for p in pgm:
        name_raw = f"{p['forename']} {p['surname']}"
        norm = normalize_name(name_raw)
        pos = p.get("position", "")
        team = p.get("teamID", "")
        old_rating = p.get("rating", 60)
        is_team_player = team in NFL_TEAMS

        new_rating = None
        source = "unchanged"
        snap_seasons = 0
        snap_weight_total = 0.0
        score_used = None

        # --- CSV mode ---
        if use_pff_csv:
            entry = pff_data.get(norm)
            if entry:
                pff_derived = pff_grade_to_pgm3_rating(entry["grade"])
                new_rating = blend_with_current(pff_derived, old_rating)
                source = "pff_csv"
                score_used = entry["grade"]
            else:
                unmatched += 1

        # --- Formula mode ---
        else:
            # Collect season scores for this player
            season_entries = []
            for season in STAT_SEASONS:
                key = (norm, season)
                if key in all_scores:
                    entry = all_scores[key]
                    season_entries.append({
                        "season": season,
                        "score": entry["score"],
                        "snaps": entry["snaps"],
                    })

            if not season_entries:
                unmatched += 1
            else:
                weighted_score, total_snap_weight, seas_used = derive_rating_from_scores(
                    norm, season_entries
                )
                snap_seasons = seas_used
                snap_weight_total = total_snap_weight

                if weighted_score is None:
                    unmatched += 1
                else:
                    # Apply playing-time threshold blending
                    perf_score = apply_playing_time_threshold(weighted_score, total_snap_weight)

                    # Apply draftee blending if recently drafted
                    draft_info = draft_data.get(norm) or players_data.get(norm, {})
                    draft_season = draft_info.get("season") or p.get("draftSeason", 0)
                    overall_pick = draft_info.get("pick") or p.get("draftNum", 0)

                    if (draft_season and overall_pick and
                            CURRENT_YEAR - draft_season <= RECENT_DRAFT_YEARS):
                        career_snaps = sum(e["snaps"] for e in season_entries)
                        draft_r = draft_position_rating(overall_pick)
                        perf_score = apply_draftee_blending(perf_score, career_snaps, draft_r)
                        source = "formula+draft"
                    else:
                        source = "formula"

                    score_used = round(perf_score, 1)
                    perf_derived = perf_score_to_pgm3_rating(perf_score)
                    new_rating = blend_with_current(perf_derived, old_rating)

        # Record change
        if new_rating is not None and new_rating != old_rating:
            changes.append({
                "name": name_raw,
                "team": team,
                "pos": pos,
                "old_rating": old_rating,
                "new_rating": new_rating,
                "delta": new_rating - old_rating,
                "snap_seasons": snap_seasons,
                "snap_weight": round(snap_weight_total, 2),
                "score": score_used,
                "source": source,
                "is_team_player": is_team_player,
            })
            if not dry_run:
                p["rating"] = new_rating
                if p.get("potential", 0) < new_rating:
                    p["potential"] = new_rating
        else:
            unchanged += 1

    # --- Print results ---
    changes.sort(key=lambda x: abs(x["delta"]), reverse=True)

    print(f"\n{'='*70}")
    print(f"RATING SYNTHESIS RESULTS")
    print(f"{'='*70}")
    print(f"  Players matched + changed:  {len(changes)}")
    print(f"  Players unchanged:          {unchanged}")
    print(f"  Players unmatched:          {unmatched}")
    print(f"  Mode:                       {'PFF CSV' if use_pff_csv else 'Formula synthesis'}")

    # Print top changes
    print(f"\n{'Name':<30} {'Team':<5} {'Pos':<5} {'Old':>4} {'New':>4} {'Δ':>5}  {'Source':<14}  Score/Snaps")
    print("-" * 80)
    for c in changes[:50]:
        snaps_str = f"{c['snap_weight']:.1f}sw/{c['snap_seasons']}s" if c["snap_seasons"] else ""
        score_str = f"{c['score']}" if c["score"] is not None else ""
        print(f"{c['name']:<30} {c['team']:<5} {c['pos']:<5} {c['old_rating']:>4} "
              f"{c['new_rating']:>4} {c['delta']:>+5}  {c['source']:<14}  {score_str} {snaps_str}")
    if len(changes) > 50:
        print(f"  ... and {len(changes) - 50} more changes")

    # Rating distribution preview
    if not dry_run:
        team_players = [p for p in pgm if p.get("teamID") in NFL_TEAMS]
        buckets = {}
        for p in team_players:
            b = (p["rating"] // 5) * 5
            buckets[b] = buckets.get(b, 0) + 1
        print(f"\nNew rating distribution (team players):")
        for k in sorted(buckets):
            bar = "#" * (buckets[k] // 5)
            print(f"  {k:3}-{k+4}: {buckets[k]:4}  {bar}")

    # --- Write report ---
    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "team", "pos", "old_rating", "new_rating", "delta",
            "source", "score", "snap_weight", "snap_seasons", "is_team_player"
        ])
        writer.writeheader()
        # Include unchanged unmatched players too for full audit
        writer.writerows(changes)
    print(f"\nReport written to: {args.report_path}")

    # --- Save roster ---
    if not dry_run:
        with open(ROSTER_FILE, "w", encoding="utf-8") as f:
            json.dump(pgm, f, separators=(",", ":"))
        print(f"\nSaved {len(pgm)} players to {ROSTER_FILE}")
        print("Next step: run fix_stat_pattern.py to sync individual stats to new ratings.")
    else:
        print("\nDry-run complete. Run with --apply to commit changes.")


if __name__ == "__main__":
    main()
