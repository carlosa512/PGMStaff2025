#!/usr/bin/env python3
"""
Generate 2026 NFL Draft Rookies (All 7 Rounds)
==============================================
Adds the 2026 NFL Draft class to PGMRoster_2026_Final.json.

Reads picks from `reference/draft_2026_picks.csv` (manually compiled — nflverse
has not ingested 2026 yet) and applies overrides from
`reference/draft_2026_overrides.csv` (curated R1 + select R2-R3 + late notables).

The user's intent: R1 maximally accurate (rating + likeness), R2-R3 nice-to-have
accuracy, R4-R7 trust the formula. Conservative ratings — "down draft year" —
no rookies above OVR 79; only overrides may exceed the formula cap of 76.

De-duplication: if a pick name matches an existing entry whose draftNum<=0
(typical of UDFA placeholder), update in place (preserve iden). Otherwise append.

Usage:
    python scripts/generate_draft_2026.py [--dry-run] [--strict]
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

# Reuse the existing player-build pipeline from add_missing_players.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
import add_missing_players as amp
# fix_stat_pattern.ZERO_STATS is authoritative for the game engine.
import fix_stat_pattern as fsp

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTER_FILE = REPO_ROOT / "PGMRoster_2026_Final.json"
PICKS_CSV = REPO_ROOT / "reference" / "draft_2026_picks.csv"
OVERRIDES_CSV = REPO_ROOT / "reference" / "draft_2026_overrides.csv"
SIGNED_ROSTER_CSV = REPO_ROOT / "reference" / "nflverse_rosters_2026.csv"
REPORT_CSV = REPO_ROOT / "reference" / "draft_2026_apply_report.csv"

# Down-year rating limits — calibrated so stored rating ≈ in-game OVR display.
# Engine OVR drops ~5-6 below stored for picks rated >=75 (verified from
# screenshots: Caleb Downs stored 79 -> in-game 73). Lowering both caps by 5-6
# brings editor display within ±3 of the engine's OVR for the whole class.
DOWN_YEAR_FORMULA_CAP = 70   # formula-only generation max
ABSOLUTE_RATING_CAP = 74     # overrides may not exceed this

# Defaults for unsigned rookies
TODAY = date(2026, 4, 26)
ROOKIE_DEFAULT_BIRTH = "2003-09-01"  # gives age 22 with TODAY

# nflverse uses some position labels add_missing_players.POS_MAP doesn't cover,
# and PGM-style abbrevs in our manual picks CSV (OG/MLB) need explicit mapping.
EXTRA_POS_MAP = {
    "EDGE": "DE",
    "IOL": "OG",
    # PGM-style abbreviations (in case picks CSV uses them directly):
    "OG": "G",   # POS_MAP has G->OG
    "OLB": "LB", # POS_MAP has LB->OLB
    "MLB": "ILB",  # POS_MAP has ILB->MLB
}

NFL_TEAMS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
    "DET", "GB", "HOU", "IND", "JAX", "KC", "LAC", "LAR", "LV", "MIA",
    "MIN", "NE", "NO", "NYG", "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
}

# Tone-grouped pools (mirrors apply_appearance_audit.py)
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
APPEARANCE_IDX = {
    "head": 0, "eyes": 1, "hair": 2, "beard": 3,
    "eyebrows": 4, "nose": 5, "mouth": 6, "glasses": 7, "clothes": 8,
}


def head_group(head_value: str) -> int | None:
    m = re.match(r"Head(\d)", head_value or "")
    return int(m.group(1)) if m else None


def derive_nose(current_nose: str, new_group: int) -> str:
    pool = NOSE_BY_GROUP[new_group]
    m = re.match(r"Nose\d([a-z])", current_nose or "")
    if m:
        candidate = f"Nose{new_group}{m.group(1)}"
        if candidate in pool:
            return candidate
    return pool[0]


def derive_mouth(current_mouth: str, new_group: int) -> str:
    pool = MOUTH_BY_GROUP[new_group]
    m = re.match(r"Mouth\d([a-z])", current_mouth or "")
    if m:
        candidate = f"Mouth{new_group}{m.group(1)}"
        if candidate in pool:
            return candidate
    return pool[0]


# Normalise position via amp.POS_MAP plus extras; fall back to original
def normalize_position(raw_pos: str) -> str:
    raw = (raw_pos or "").strip().upper()
    if raw in EXTRA_POS_MAP:
        raw = EXTRA_POS_MAP[raw]
    return amp.POS_MAP.get(raw, raw if raw in amp.POS_STATS else "WR")


def load_signed_rookies() -> dict[str, dict]:
    """Map (forename, surname) -> nflverse roster row for 2026 rookies who have signed."""
    out = {}
    if not SIGNED_ROSTER_CSV.exists():
        return out
    with open(SIGNED_ROSTER_CSV) as f:
        for row in csv.DictReader(f):
            full = (row.get("full_name") or "").strip()
            if not full:
                continue
            parts = full.split(" ", 1)
            key = (parts[0].lower(), (parts[1] if len(parts) > 1 else "").lower())
            out[key] = row
    return out


def synthesize_row(pick: dict, signed: dict | None) -> dict:
    """Build the dict shape add_missing_players.build_player() expects."""
    name = pick["player_name"].strip()
    team = pick["team"].strip()
    pos_raw = (pick["position"] or "").strip().upper()
    # build_player calls amp.POS_MAP.get(dcp, "WR"); POS_MAP keys are nflverse-
    # style (G, LB, ILB), so translate PGM-style and EDGE to a POS_MAP-friendly key.
    pos_dcp = EXTRA_POS_MAP.get(pos_raw, pos_raw)

    if signed:
        birth_date = signed.get("birth_date") or ROOKIE_DEFAULT_BIRTH
        jersey = signed.get("jersey_number") or "0"
    else:
        birth_date = ROOKIE_DEFAULT_BIRTH
        jersey = "0"

    return {
        "full_name": name,
        "team": team,
        "depth_chart_position": pos_dcp,
        "birth_date": birth_date,
        "jersey_number": jersey,
        "status": "ACT",
        "years_exp": "0",
        "rookie_year": "2026",
    }


def load_overrides() -> dict[int, dict]:
    """Key by overall pick number."""
    out = {}
    if not OVERRIDES_CSV.exists():
        return out
    with open(OVERRIDES_CSV) as f:
        for row in csv.DictReader(f):
            try:
                pick = int(row["pick"])
            except (ValueError, KeyError, TypeError):
                continue
            if pick in out:
                print(f"  [warn] duplicate override for pick {pick}; keeping first")
                continue
            out[pick] = row
    return out


def rebuild_active_stats(entry: dict, pos: str, rating: int, name_seed: str) -> None:
    """Re-derive active position stats to track a new rating value.
    Respects ZERO_STATS — never sets a value on a stat the engine requires to be 0.
    """
    rng = random.Random(name_seed + "stats_rebuild")
    zero = set(fsp.ZERO_STATS.get(pos, []))
    for stat in amp.POS_STATS.get(pos, amp.POS_STATS["WR"]):
        if stat in entry and stat not in zero:
            entry[stat] = max(60, min(99, rating + rng.randint(-3, 3)))


def enforce_zero_stats(entry: dict) -> None:
    """Zero out any stat that the engine requires to be 0 for this position."""
    pos = entry.get("position", "")
    for stat in fsp.ZERO_STATS.get(pos, []):
        if stat in entry:
            entry[stat] = 0


def apply_overrides(entry: dict, ov: dict, name_seed: str) -> list[str]:
    """Apply override fields to entry; return list of changes."""
    changes = []

    rating_str = (ov.get("override_rating") or "").strip()
    if rating_str:
        try:
            new_rating = int(rating_str)
        except ValueError:
            changes.append(f"WARN bad override_rating={rating_str!r}; skipped")
        else:
            new_rating = max(55, min(ABSOLUTE_RATING_CAP, new_rating))
            entry["rating"] = new_rating
            rebuild_active_stats(entry, entry["position"], new_rating, name_seed)
            changes.append(f"rating->{new_rating}")

    pot_str = (ov.get("override_potential") or "").strip()
    if pot_str:
        try:
            new_pot = int(pot_str)
        except ValueError:
            changes.append(f"WARN bad override_potential={pot_str!r}; skipped")
        else:
            entry["potential"] = max(entry["rating"], min(99, new_pot))
            changes.append(f"potential->{entry['potential']}")

    appearance = list(entry.get("appearance", []))
    if len(appearance) != 9:
        changes.append("WARN appearance not 9-element; skipping appearance overrides")
        return changes

    head_override = (ov.get("override_head") or "").strip()
    if head_override:
        new_group = head_group(head_override)
        if new_group is None:
            changes.append(f"WARN bad override_head={head_override!r}; skipped")
        else:
            old_group = head_group(appearance[APPEARANCE_IDX["head"]])
            appearance[APPEARANCE_IDX["head"]] = head_override
            # Auto-derive Nose/Mouth to match new tone group (unless overridden below)
            nose_override = (ov.get("override_nose") or "").strip()
            mouth_override = (ov.get("override_mouth") or "").strip()
            if not nose_override:
                appearance[APPEARANCE_IDX["nose"]] = derive_nose(appearance[APPEARANCE_IDX["nose"]], new_group)
            if not mouth_override:
                appearance[APPEARANCE_IDX["mouth"]] = derive_mouth(appearance[APPEARANCE_IDX["mouth"]], new_group)
            changes.append(f"head->{head_override} (group {old_group}->{new_group})")

    for slot in ("hair", "beard", "eyebrows", "nose", "mouth", "clothes", "glasses", "eyes"):
        val = (ov.get(f"override_{slot}") or "").strip()
        if val:
            appearance[APPEARANCE_IDX[slot]] = val
            changes.append(f"{slot}->{val}")

    entry["appearance"] = appearance
    return changes


def cap_formula_rating(entry: dict, name_seed: str) -> bool:
    """If no override raised the rating above DOWN_YEAR_FORMULA_CAP, clamp it."""
    if entry["rating"] > DOWN_YEAR_FORMULA_CAP:
        entry["rating"] = DOWN_YEAR_FORMULA_CAP
        rebuild_active_stats(entry, entry["position"], DOWN_YEAR_FORMULA_CAP, name_seed)
        # Potential should still reflect rookie growth headroom
        if entry.get("potential", 0) < entry["rating"]:
            entry["potential"] = entry["rating"]
        return True
    return False


def validate_entry(entry: dict, existing_idens: set[str]) -> list[str]:
    """Return list of issue strings; empty = OK."""
    issues = []

    pos = entry.get("position", "")
    # Must be a known PGM position
    if pos not in amp.POS_STATS:
        issues.append(f"unknown position {pos!r}")
        return issues

    # Per-position ZERO_STATS must be exactly 0
    try:
        from fix_stat_pattern import ZERO_STATS
    except ImportError:
        ZERO_STATS = {}
    for stat in ZERO_STATS.get(pos, []):
        if entry.get(stat, 0) != 0:
            issues.append(f"{stat} must be 0 for {pos} (got {entry[stat]})")

    # Contract field sync
    if entry.get("salary") != entry.get("eSalary"):
        issues.append(f"salary {entry.get('salary')} != eSalary {entry.get('eSalary')}")
    if entry.get("guarantee") != entry.get("eGuarantee"):
        issues.append(f"guarantee != eGuarantee")
    if entry.get("length") != entry.get("eLength"):
        issues.append(f"length != eLength")

    # Team must be valid
    team = entry.get("teamID")
    if team not in NFL_TEAMS and team not in {"Free Agent", "Rookie"}:
        issues.append(f"invalid teamID {team!r}")

    # Appearance tone consistency
    app = entry.get("appearance", [])
    if len(app) == 9:
        hg = head_group(app[0])
        ng = head_group(app[5].replace("Nose", "Head") if app[5] else "")
        mg = head_group(app[6].replace("Mouth", "Head") if app[6] else "")
        if hg and ng and hg != ng:
            issues.append(f"head group {hg} != nose group {ng}")
        if hg and mg and hg != mg:
            issues.append(f"head group {hg} != mouth group {mg}")
        if app[4] not in {"Eyebrows1a", "Eyebrows1b"}:
            issues.append(f"unsafe eyebrows {app[4]} (must be Eyebrows1a/1b)")

    # Rating bounds
    if entry["rating"] < 55 or entry["rating"] > 99:
        issues.append(f"rating {entry['rating']} out of [55,99]")
    if entry["potential"] < entry["rating"]:
        issues.append(f"potential {entry['potential']} < rating {entry['rating']}")

    if entry["iden"] in existing_idens:
        issues.append(f"iden collision {entry['iden']}")

    return issues


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report only; don't save roster")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on any validation issue")
    parser.add_argument("--picks-path", default=str(PICKS_CSV))
    parser.add_argument("--overrides-path", default=str(OVERRIDES_CSV))
    parser.add_argument("--report-path", default=str(REPORT_CSV))
    args = parser.parse_args()

    # Monkey-patch TODAY in add_missing_players so age math uses today's date
    amp.TODAY = TODAY

    print("=" * 70)
    print("Generate 2026 NFL Draft Rookies")
    print(f"  picks:     {args.picks_path}")
    print(f"  overrides: {args.overrides_path}")
    print(f"  roster:    {ROSTER_FILE}")
    print(f"  dry-run:   {args.dry_run}")
    print("=" * 70)

    # Load roster
    with open(ROSTER_FILE) as f:
        roster = json.load(f)
    print(f"Loaded roster: {len(roster)} players")

    # Index existing 2026 entries for reconcile
    existing_2026 = {}
    for p in roster:
        if p.get("draftSeason") == 2026:
            key = (p["forename"].lower().strip(), p["surname"].lower().strip())
            existing_2026.setdefault(key, []).append(p)
    print(f"Existing draftSeason=2026 entries: {sum(len(v) for v in existing_2026.values())}")

    # Build rating table from existing roster
    pgm_with_exp = []
    nf_exp_by_name = {}
    if SIGNED_ROSTER_CSV.exists():
        with open(SIGNED_ROSTER_CSV) as f:
            for row in csv.DictReader(f):
                full = (row.get("full_name") or "").strip()
                if full:
                    nf_exp_by_name[full] = row.get("years_exp", "0")
    for p in roster:
        name = f"{p['forename']} {p['surname']}"
        p2 = dict(p)
        p2["years_exp"] = nf_exp_by_name.get(name, "4")
        pgm_with_exp.append(p2)
    rating_table = amp.build_rating_table(pgm_with_exp)
    print(f"Rating calibration table: {len(rating_table)} buckets")

    # Load picks & overrides & signed lookups
    with open(args.picks_path) as f:
        picks = list(csv.DictReader(f))
    print(f"Loaded picks CSV: {len(picks)} 2026 picks")
    overrides = load_overrides()
    print(f"Loaded overrides: {len(overrides)} pick-keyed overrides")
    signed = load_signed_rookies()
    print(f"Signed-rookie lookup: {len(signed)} 2026 active roster names")

    existing_idens = {p["iden"] for p in roster}
    new_entries = []
    inplace_updates = []
    overrides_applied = []
    overrides_unmatched = set(overrides.keys())
    validation_issues = []
    rating_buckets_r1 = Counter()
    rating_buckets_all = Counter()

    report_rows = []

    for pick in picks:
        try:
            pick_num = int(pick["pick"])
            round_num = int(pick["round"])
        except (ValueError, KeyError):
            print(f"  [warn] bad pick row, skipping: {pick}")
            continue

        name = pick["player_name"].strip()
        parts = name.split(" ", 1)
        forename = parts[0]
        surname = parts[1] if len(parts) > 1 else ""
        signed_row = signed.get((forename.lower(), surname.lower()))

        # Build the synthetic row & call build_player
        row = synthesize_row(pick, signed_row)
        draft_info = {
            "draft_round": round_num,
            "draft_pick": pick_num,
            "w_av": 0.0,
        }
        entry = amp.build_player(row, draft_info, rating_table)

        # Force the values we care about
        entry["draftSeason"] = 2026
        entry["draftNum"] = pick_num

        # add_missing_players.POS_STATS includes some stats that fix_stat_pattern
        # demands be zero (e.g. elusiveness for CB/S). Zero them BEFORE applying
        # overrides so override-driven stat rebuilds also respect the constraint.
        enforce_zero_stats(entry)

        # Apply override
        ov = overrides.get(pick_num)
        had_rating_override = False
        ov_changes = []
        if ov:
            ov_changes = apply_overrides(entry, ov, forename + surname)
            had_rating_override = any(c.startswith("rating->") for c in ov_changes)
            overrides_applied.append((pick_num, name, ov_changes))
            overrides_unmatched.discard(pick_num)

        # Cap formula-generated ratings
        if not had_rating_override:
            cap_formula_rating(entry, forename + surname)

        # Validate
        issues = validate_entry(entry, existing_idens - {entry["iden"]})
        if issues:
            validation_issues.append((pick_num, name, issues))

        # Reconcile vs existing 2026 entries.
        # Rule: if an existing draftSeason=2026 entry has the same name, update
        # in place (preserve iden). Prefer matches with draftNum<=0 (UDFA
        # placeholders); fall back to any existing 2026 entry — these were
        # added by a prior run of this script and should be refreshed with
        # the latest data (positions, ratings, overrides).
        key = (forename.lower(), surname.lower())
        existing_matches = existing_2026.get(key, [])
        target = None
        for em in existing_matches:
            if em.get("draftNum", 0) <= 0:
                target = em
                break
        if target is None and existing_matches:
            target = existing_matches[0]
        if target is not None:
            preserved_iden = target["iden"]
            target.clear()
            target.update(entry)
            target["iden"] = preserved_iden
            inplace_updates.append((pick_num, name, target["teamID"]))
            existing_idens.add(preserved_iden)
            final_iden = preserved_iden
        else:
            new_entries.append(entry)
            existing_idens.add(entry["iden"])
            final_iden = entry["iden"]

        # Histograms
        if round_num == 1:
            rating_buckets_r1[(entry["rating"] // 5) * 5] += 1
        rating_buckets_all[(entry["rating"] // 5) * 5] += 1

        report_rows.append({
            "pick": pick_num,
            "round": round_num,
            "team": entry["teamID"],
            "player": name,
            "position": entry["position"],
            "rating": entry["rating"],
            "potential": entry["potential"],
            "head": entry["appearance"][0] if len(entry["appearance"]) >= 1 else "",
            "override_applied": "yes" if ov_changes else "no",
            "override_changes": ";".join(ov_changes),
            "reconcile": "inplace" if target is not None else "appended",
            "iden": final_iden,
            "issues": ";".join(":".join(str(x) for x in i) for i in issues) if issues else "",
        })

    # Append new entries
    if not args.dry_run:
        roster.extend(new_entries)

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print(f"  Picks processed:       {len(picks)}")
    print(f"  Appended (new):        {len(new_entries)}")
    print(f"  Updated in place:      {len(inplace_updates)}")
    print(f"  Override applied:      {len(overrides_applied)}")
    print(f"  Overrides unmatched:   {len(overrides_unmatched)} {sorted(overrides_unmatched) if overrides_unmatched else ''}")
    print(f"  Validation issues:     {len(validation_issues)}")
    print()
    print("Round 1 rating histogram:")
    for k in sorted(rating_buckets_r1):
        print(f"  {k}-{k+4}: {rating_buckets_r1[k]}")
    print()
    print("All-class rating histogram:")
    for k in sorted(rating_buckets_all):
        print(f"  {k}-{k+4}: {rating_buckets_all[k]}")
    print()
    if validation_issues:
        print("VALIDATION ISSUES (first 20):")
        for pn, nm, iss in validation_issues[:20]:
            print(f"  pick {pn} {nm}: {iss}")

    # Write per-pick report
    if report_rows:
        with open(args.report_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
            w.writeheader()
            w.writerows(report_rows)
        print(f"\nReport written: {args.report_path}")

    # Save roster
    if args.dry_run:
        print("\nDry-run: roster NOT saved.")
    else:
        with open(ROSTER_FILE, "w") as f:
            json.dump(roster, f, separators=(",", ":"))
        print(f"\nRoster saved: {ROSTER_FILE} ({len(roster)} players)")

    if args.strict and validation_issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
