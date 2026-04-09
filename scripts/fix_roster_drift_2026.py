#!/usr/bin/env python3
"""
fix_roster_drift_2026.py — surgical roster drift fixes for the 2026 season.

Cross-references PGMRoster_2026_Final.json against the latest nflverse pull
and applies only the unambiguous fixes (Option C from the project review):

  1. Dedupe 4 confirmed (forename, surname, position) duplicates
  2. Re-derive ages from nflverse birth_date for matched players (>1yr drift)
  3. Move Marte Mapu from NE to HOU (confirmed trade per nflverse ACT)
  4. Move Philip Rivers from IND to Free Agent (retired since 2020)
  5. Generate reference/roster_drift_report.csv with every action

Deliberately does NOT do (per Option C):
  - Move the 499 FA-pool players to teams (preserves trimming work)
  - Auto-handle UFA/RFA drift (nflverse can lag re-signings; flagged for review)
  - Remove the other 8 "missing from nflverse" players (likely name normalization)

Run:  python scripts/fix_roster_drift_2026.py [--dry-run]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = ROOT / "PGMRoster_2026_Final.json"
NFLVERSE_PATH = ROOT / "reference" / "nflverse_rosters_2026.csv"
REPORT_PATH = ROOT / "reference" / "roster_drift_report.csv"

# Reference date for age calculation (matches CLAUDE.md "today's date" convention).
REFERENCE_DATE = date(2026, 4, 9)

PGM_TEAM_IDS = {
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
}
NFLVERSE_TEAM_ALIAS = {"LA": "LAR"}

# Map nflverse position codes to PGM3 valid positions for fuzzy match scoring.
NV_POS_TO_PGM = {
    "QB": "QB", "RB": "RB", "FB": "RB", "WR": "WR", "TE": "TE",
    "T": "OT", "OT": "OT", "G": "OG", "OG": "OG", "C": "C", "OL": "OL",
    "DE": "DE", "DT": "DT", "NT": "DT", "DL": "DL",
    "LB": "LB", "OLB": "OLB", "MLB": "MLB", "ILB": "MLB",
    "CB": "CB", "DB": "DB", "S": "S", "FS": "S", "SS": "S", "SAF": "S",
    "K": "K", "P": "P", "LS": "LS",
}


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/punct, drop generational suffixes (jr/sr/ii/iii/iv/v)."""
    if not isinstance(name, str):
        return ""
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\s+(jr|sr|ii|iii|iv|v)$", "", name).strip()
    return name


def age_from_birth_date(bd: str) -> int | None:
    if not isinstance(bd, str) or not bd:
        return None
    try:
        y, m, d = map(int, bd.split("-"))
    except ValueError:
        return None
    return REFERENCE_DATE.year - y - ((REFERENCE_DATE.month, REFERENCE_DATE.day) < (m, d))


def normalize_fa_contract(player: dict) -> None:
    """Per CLAUDE.md FA convention: salary/eSalary/guarantee/eGuarantee/length/eLength all 0."""
    for field in ("salary", "eSalary", "guarantee", "eGuarantee", "length", "eLength"):
        player[field] = 0


def load_nflverse_index(path: Path) -> dict:
    """
    Build dict: normalized_name -> list of nflverse rows.
    Each row keeps only the columns we need.
    """
    df = pd.read_csv(path, low_memory=False)
    df["_key"] = df["full_name"].apply(normalize_name)
    df = df[df["_key"] != ""]
    index: dict[str, list[dict]] = defaultdict(list)
    for _, row in df.iterrows():
        nv_team = NFLVERSE_TEAM_ALIAS.get(row.get("team"), row.get("team"))
        nv_pos_raw = row.get("depth_chart_position") or row.get("position")
        nv_pos_pgm = NV_POS_TO_PGM.get(str(nv_pos_raw).strip(), str(nv_pos_raw).strip()) if pd.notna(nv_pos_raw) else None
        index[row["_key"]].append({
            "full_name": row.get("full_name"),
            "team": nv_team,
            "status": row.get("status"),
            "position": nv_pos_raw,
            "pgm_pos": nv_pos_pgm,
            "birth_date": row.get("birth_date"),
            "years_exp": row.get("years_exp"),
        })
    return index


def resolve_nflverse_match(name_key: str, pgm_pos: str, index: dict) -> dict | None:
    """Pick the best nflverse row for a PGM player. Prefer position match, then ACT > UFA/RFA."""
    rows = index.get(name_key, [])
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    pos_matches = [r for r in rows if r["pgm_pos"] == pgm_pos]
    if len(pos_matches) == 1:
        return pos_matches[0]
    if pos_matches:
        rows = pos_matches
    act = [r for r in rows if r["status"] == "ACT"]
    if len(act) == 1:
        return act[0]
    return rows[0]


# ---------- Action handlers ---------- #

def dedup_players(roster: list, report_rows: list) -> int:
    """
    Remove (forename, surname, position) duplicates by priority:
      team-assigned > FA > Rookie, then higher rating, then lower index.
    Skips Jaylon Jones (legitimate namesakes, ages 27 and 22).
    """
    buckets: dict[tuple, list[tuple[int, dict]]] = defaultdict(list)
    for i, p in enumerate(roster):
        key = (
            p.get("forename", "").lower().strip(),
            p.get("surname", "").lower().strip(),
            p.get("position", ""),
        )
        buckets[key].append((i, p))

    NAMESAKE_KEYS = {("jaylon", "jones", "CB")}
    indexes_to_drop: set[int] = set()

    for key, items in buckets.items():
        if len(items) <= 1:
            continue
        if key in NAMESAKE_KEYS:
            continue

        # Detect true namesakes by age gap >= 4 (different real-world players).
        ages = [p.get("age") or 0 for _, p in items]
        if max(ages) - min(ages) >= 4:
            continue

        def keep_score(item):
            _, p = item
            team = p.get("teamID", "")
            team_priority = 0 if team in PGM_TEAM_IDS else (1 if team == "Free Agent" else 2)
            return (team_priority, -(p.get("rating") or 0))

        sorted_items = sorted(items, key=keep_score)
        keeper_idx, keeper = sorted_items[0]
        for drop_idx, drop_player in sorted_items[1:]:
            indexes_to_drop.add(drop_idx)
            report_rows.append({
                "action": "dedup_dropped",
                "name": f"{drop_player.get('forename','')} {drop_player.get('surname','')}",
                "position": drop_player.get("position", ""),
                "old_value": f"team={drop_player.get('teamID')} rating={drop_player.get('rating')} idx={drop_idx}",
                "new_value": f"kept idx={keeper_idx} (rating={keeper.get('rating')})",
                "source": "dedup",
                "notes": f"key={key}",
            })

    if indexes_to_drop:
        kept = [p for i, p in enumerate(roster) if i not in indexes_to_drop]
        roster.clear()
        roster.extend(kept)

    return len(indexes_to_drop)


def update_ages(roster: list, nv_index: dict, report_rows: list) -> int:
    """Re-derive age from nflverse birth_date when matched and drift >= 1yr."""
    updated = 0
    for p in roster:
        name_key = normalize_name(f"{p.get('forename','')} {p.get('surname','')}")
        if not name_key:
            continue
        match = resolve_nflverse_match(name_key, p.get("position", ""), nv_index)
        if match is None:
            continue
        new_age = age_from_birth_date(match.get("birth_date"))
        old_age = p.get("age", 0)
        if new_age is None or not old_age:
            continue
        if abs(new_age - old_age) >= 1:
            report_rows.append({
                "action": "age_updated",
                "name": f"{p.get('forename','')} {p.get('surname','')}",
                "position": p.get("position", ""),
                "old_value": str(old_age),
                "new_value": str(new_age),
                "source": f"nflverse birth_date={match.get('birth_date')}",
                "notes": p.get("teamID", ""),
            })
            p["age"] = new_age
            updated += 1
    return updated


def fix_marte_mapu(roster: list, report_rows: list) -> int:
    fixed = 0
    for p in roster:
        if p.get("forename") == "Marte" and p.get("surname") == "Mapu":
            old_team = p.get("teamID")
            if old_team != "HOU":
                p["teamID"] = "HOU"
                report_rows.append({
                    "action": "team_changed",
                    "name": "Marte Mapu",
                    "position": p.get("position", ""),
                    "old_value": old_team,
                    "new_value": "HOU",
                    "source": "nflverse ACT",
                    "notes": "Confirmed trade",
                })
                fixed += 1
    return fixed


def fix_philip_rivers(roster: list, report_rows: list) -> int:
    fixed = 0
    for p in roster:
        if p.get("forename") == "Philip" and p.get("surname") == "Rivers":
            old_team = p.get("teamID")
            if old_team != "Free Agent":
                p["teamID"] = "Free Agent"
                normalize_fa_contract(p)
                report_rows.append({
                    "action": "moved_to_fa",
                    "name": "Philip Rivers",
                    "position": p.get("position", ""),
                    "old_value": old_team,
                    "new_value": "Free Agent",
                    "source": "manual (retired 2020)",
                    "notes": "Not in nflverse 2026; contract zeroed",
                })
                fixed += 1
    return fixed


def flag_remaining_drift(roster: list, nv_index: dict, report_rows: list) -> dict:
    """Add flagged_for_review rows for items deliberately not auto-fixed."""
    counts = {"fa_to_act": 0, "ufa_rfa_team": 0, "missing_from_nflverse": 0}

    for p in roster:
        name = f"{p.get('forename','')} {p.get('surname','')}"
        name_key = normalize_name(name)
        if not name_key:
            continue
        pgm_team = p.get("teamID", "")
        match = resolve_nflverse_match(name_key, p.get("position", ""), nv_index)

        if match is None:
            if pgm_team in PGM_TEAM_IDS:
                report_rows.append({
                    "action": "flagged_for_review",
                    "name": name,
                    "position": p.get("position", ""),
                    "old_value": pgm_team,
                    "new_value": "?",
                    "source": "missing_from_nflverse",
                    "notes": "Possible name normalization mismatch; investigate before removing",
                })
                counts["missing_from_nflverse"] += 1
            continue

        nv_status = match.get("status")
        nv_team = match.get("team")

        if nv_status == "ACT":
            if pgm_team == "Free Agent":
                report_rows.append({
                    "action": "flagged_for_review",
                    "name": name,
                    "position": p.get("position", ""),
                    "old_value": "Free Agent",
                    "new_value": nv_team,
                    "source": "nflverse ACT",
                    "notes": f"Option C: not auto-promoted (rating={p.get('rating')})",
                })
                counts["fa_to_act"] += 1
        elif nv_status in ("UFA", "RFA"):
            if pgm_team in PGM_TEAM_IDS:
                report_rows.append({
                    "action": "flagged_for_review",
                    "name": name,
                    "position": p.get("position", ""),
                    "old_value": pgm_team,
                    "new_value": f"FA({nv_status})",
                    "source": "nflverse",
                    "notes": "nflverse can lag real-world re-signings (see McGovern); manual review",
                })
                counts["ufa_rfa_team"] += 1

    return counts


def write_report(report_rows: list, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["action", "name", "position", "old_value", "new_value", "source", "notes"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        # Sort: actions first (alphabetically), then flagged items.
        actions = [r for r in report_rows if r["action"] != "flagged_for_review"]
        flags = [r for r in report_rows if r["action"] == "flagged_for_review"]
        writer.writerows(sorted(actions, key=lambda r: (r["action"], r["name"])))
        writer.writerows(sorted(flags, key=lambda r: (r["source"], r["name"])))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing files")
    args = parser.parse_args()

    if not ROSTER_PATH.exists():
        print(f"[ERROR] Roster not found: {ROSTER_PATH}", file=sys.stderr)
        return 1
    if not NFLVERSE_PATH.exists():
        print(f"[ERROR] nflverse data not found: {NFLVERSE_PATH}", file=sys.stderr)
        print("        Run: python scripts/pull_nflverse_rosters.py", file=sys.stderr)
        return 1

    print(f"Loading roster: {ROSTER_PATH}")
    with ROSTER_PATH.open() as f:
        roster = json.load(f)
    print(f"  {len(roster)} players")

    print(f"Loading nflverse: {NFLVERSE_PATH}")
    nv_index = load_nflverse_index(NFLVERSE_PATH)
    print(f"  {sum(len(v) for v in nv_index.values())} rows, {len(nv_index)} unique names")

    report_rows: list = []

    print("\n[1/4] Deduping confirmed duplicates...")
    n_dedup = dedup_players(roster, report_rows)
    print(f"  Dropped {n_dedup} duplicate entries")

    print("[2/4] Re-deriving ages from nflverse birth_date...")
    n_ages = update_ages(roster, nv_index, report_rows)
    print(f"  Updated {n_ages} player ages")

    print("[3/4] Applying confirmed team fixes (Mapu, Rivers)...")
    n_mapu = fix_marte_mapu(roster, report_rows)
    n_rivers = fix_philip_rivers(roster, report_rows)
    print(f"  Mapu: {n_mapu} change(s), Rivers: {n_rivers} change(s)")

    print("[4/4] Flagging remaining drift for manual review...")
    flag_counts = flag_remaining_drift(roster, nv_index, report_rows)
    print(f"  FA-but-ACT: {flag_counts['fa_to_act']}")
    print(f"  UFA/RFA on team: {flag_counts['ufa_rfa_team']}")
    print(f"  Missing from nflverse: {flag_counts['missing_from_nflverse']}")

    print(f"\nReport: {len(report_rows)} total rows")
    if args.dry_run:
        print("\n[DRY RUN] Skipping writes.")
        return 0

    print(f"Writing roster: {ROSTER_PATH}")
    with ROSTER_PATH.open("w") as f:
        json.dump(roster, f, indent=2)

    print(f"Writing report: {REPORT_PATH}")
    write_report(report_rows, REPORT_PATH)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
