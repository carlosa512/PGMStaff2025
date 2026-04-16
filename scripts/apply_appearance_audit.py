#!/usr/bin/env python3
"""Apply reviewed appearance changes from reference/appearance_audit.csv to the roster.

Only rows with status == "confirmed" are applied. Rows with status in
{needs_review, no_change, manual_override} are skipped.

When proposed_head is set and differs from current, Nose and Mouth are
auto-derived to match the new tone group (per CLAUDE.md: Head group must
equal Nose group and Mouth group). Beards are tone-validated for Head4/5.
Extended variants (Hair1s, Beard1f1, Beard1g, etc.) are preserved when
already tone-compatible; hair is not tone-constrained.

Outputs a per-player apply report at reference/appearance_audit_apply_report.csv.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ROSTER = REPO_ROOT / "PGMRoster_2026_Final.json"
DEFAULT_CSV = REPO_ROOT / "reference" / "appearance_audit.csv"
DEFAULT_REPORT = REPO_ROOT / "reference" / "appearance_audit_apply_report.csv"

# Tone-grouped pools (mirrors scripts/fix_appearances_and_ratings.py:142-174).
NOSE_BY_GROUP = {
    1: ["Nose1a", "Nose1b", "Nose1c", "Nose1d"],
    2: ["Nose2a", "Nose2b", "Nose2c", "Nose2d"],
    3: ["Nose3a", "Nose3c"],
    4: ["Nose4a", "Nose4b", "Nose4c", "Nose4d"],
    5: ["Nose5a", "Nose5b", "Nose5c", "Nose5d"],  # real roster uses 5c/5d too
}
MOUTH_BY_GROUP = {
    1: ["Mouth1a", "Mouth1b"],
    2: ["Mouth2a", "Mouth2b"],
    3: ["Mouth3a", "Mouth3b"],
    4: ["Mouth4a", "Mouth4b"],
    5: ["Mouth5a", "Mouth5b"],
}
SAFE_EYEBROWS = {"Eyebrows1a", "Eyebrows1b"}
# Valid beards per head group. Head4-5 require Beard1* (standard or extended).
TONE_SAFE_BEARD_PREFIX = {
    1: ("Beard1", "Beard2", "Beard3", "Beard4", "Beard5", "Beard6"),
    2: ("Beard1", "Beard2", "Beard3", "Beard4", "Beard5", "Beard6"),
    3: ("Beard1", "Beard2", "Beard3"),
    4: ("Beard1",),
    5: ("Beard1",),
}

APPEARANCE_IDX = {
    "head": 0, "eyes": 1, "hair": 2, "beard": 3,
    "eyebrows": 4, "nose": 5, "mouth": 6, "glasses": 7, "clothes": 8,
}


def head_group(head_value: str) -> int | None:
    m = re.match(r"Head(\d)", head_value or "")
    return int(m.group(1)) if m else None


def derive_nose(current_nose: str, new_group: int) -> str:
    """Preserve the letter suffix within the new tone group; fall back to first variant."""
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


def beard_tone_compatible(beard: str, group: int) -> bool:
    allowed = TONE_SAFE_BEARD_PREFIX.get(group, ())
    return any(beard.startswith(p) for p in allowed)


def resolve_beard(current_beard: str, proposed_beard: str, new_group: int) -> tuple[str, str]:
    """Return (final_beard, decision_note)."""
    if proposed_beard:
        if not beard_tone_compatible(proposed_beard, new_group):
            return proposed_beard, f"WARNING: proposed beard {proposed_beard} not tone-safe for Head{new_group}"
        return proposed_beard, "applied proposed beard"
    # No proposal — keep current if tone-compatible.
    if beard_tone_compatible(current_beard, new_group):
        return current_beard, "preserved current beard (tone-compatible)"
    # Force to Beard1a for tone safety.
    return "Beard1a", f"swapped beard {current_beard} -> Beard1a for Head{new_group} tone-safety"


def load_roster(path: Path) -> list[dict]:
    with open(path, "r") as f:
        return json.load(f)


def save_roster(path: Path, data: list[dict]) -> None:
    with open(path, "w") as f:
        json.dump(data, f, separators=(",", ":"))


def find_player(roster: list[dict], name: str, team: str) -> dict | None:
    """Match by full name + team. Returns first match or None."""
    name_norm = name.strip()
    matches = []
    for p in roster:
        fn = p.get("forename", "").strip()
        sn = p.get("surname", "").strip()
        full = f"{fn} {sn}"
        if full == name_norm and p.get("teamID", "") == team:
            matches.append(p)
    if not matches:
        return None
    if len(matches) > 1:
        # Name+team collision is unexpected; return first but flag.
        return matches[0]
    return matches[0]


def apply_row(player: dict, row: dict) -> dict:
    """Apply a single confirmed CSV row to the player dict.

    Returns a dict of changes made for the report.
    """
    app = list(player.get("appearance", [""] * 9))
    if len(app) != 9:
        # Pad defensively.
        app = (app + [""] * 9)[:9]

    changes: dict[str, str] = {}
    decision_notes: list[str] = []

    proposed_head = row.get("proposed_head", "").strip()
    proposed_hair = row.get("proposed_hair", "").strip()
    proposed_beard = row.get("proposed_beard", "").strip()

    current_head = app[APPEARANCE_IDX["head"]]
    current_nose = app[APPEARANCE_IDX["nose"]]
    current_mouth = app[APPEARANCE_IDX["mouth"]]
    current_beard = app[APPEARANCE_IDX["beard"]]

    # Determine effective head (proposed or current).
    effective_head = proposed_head or current_head
    new_group = head_group(effective_head)
    old_group = head_group(current_head)

    # Head change
    if proposed_head and proposed_head != current_head:
        app[APPEARANCE_IDX["head"]] = proposed_head
        changes["head"] = f"{current_head} -> {proposed_head}"
        if new_group is None:
            decision_notes.append(f"WARNING: could not parse group from {proposed_head}")

    # Hair change (no tone constraint)
    if proposed_hair:
        if proposed_hair != app[APPEARANCE_IDX["hair"]]:
            changes["hair"] = f"{app[APPEARANCE_IDX['hair']]} -> {proposed_hair}"
        app[APPEARANCE_IDX["hair"]] = proposed_hair

    # Nose / Mouth sync when head group changed
    if new_group is not None and new_group != old_group:
        new_nose = derive_nose(current_nose, new_group)
        new_mouth = derive_mouth(current_mouth, new_group)
        if new_nose != current_nose:
            app[APPEARANCE_IDX["nose"]] = new_nose
            changes["nose"] = f"{current_nose} -> {new_nose} (auto-derived from Head group)"
        if new_mouth != current_mouth:
            app[APPEARANCE_IDX["mouth"]] = new_mouth
            changes["mouth"] = f"{current_mouth} -> {new_mouth} (auto-derived from Head group)"

    # Beard handling
    if new_group is not None:
        resolved_beard, beard_note = resolve_beard(current_beard, proposed_beard, new_group)
        if resolved_beard != current_beard:
            app[APPEARANCE_IDX["beard"]] = resolved_beard
            changes["beard"] = f"{current_beard} -> {resolved_beard}"
        if proposed_beard or beard_note != "preserved current beard (tone-compatible)":
            decision_notes.append(beard_note)

    # Eyebrow safety: force group 1 if it somehow drifted.
    current_eyebrows = app[APPEARANCE_IDX["eyebrows"]]
    if current_eyebrows not in SAFE_EYEBROWS:
        app[APPEARANCE_IDX["eyebrows"]] = "Eyebrows1a"
        changes["eyebrows"] = f"{current_eyebrows} -> Eyebrows1a (safety enforcement)"

    player["appearance"] = app
    return {
        "changes": changes,
        "decision_notes": decision_notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv-path", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--roster-path", type=Path, default=DEFAULT_ROSTER)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--dry-run", action="store_true",
                        help="Do not write roster; only produce report.")
    args = parser.parse_args()

    if not args.csv_path.exists():
        print(f"ERROR: CSV not found: {args.csv_path}", file=sys.stderr)
        return 1
    if not args.roster_path.exists():
        print(f"ERROR: Roster not found: {args.roster_path}", file=sys.stderr)
        return 1

    roster = load_roster(args.roster_path)

    with open(args.csv_path, "r") as f:
        csv_rows = list(csv.DictReader(f))

    report_rows = []
    stats = {"applied": 0, "skipped_status": 0, "not_found": 0, "errors": 0}

    for row in csv_rows:
        status = row.get("status", "").strip()
        name = row.get("name", "").strip()
        team = row.get("team", "").strip()

        if status != "confirmed":
            stats["skipped_status"] += 1
            report_rows.append({
                "name": name, "team": team, "outcome": f"skipped (status={status})",
                "changes": "", "decision_notes": "",
            })
            continue

        player = find_player(roster, name, team)
        if player is None:
            stats["not_found"] += 1
            report_rows.append({
                "name": name, "team": team, "outcome": "not_found",
                "changes": "", "decision_notes": "player not found by name+team",
            })
            continue

        try:
            result = apply_row(player, row)
            stats["applied"] += 1
            report_rows.append({
                "name": name, "team": team, "outcome": "applied",
                "changes": "; ".join(f"{k}: {v}" for k, v in result["changes"].items()) or "(no-op)",
                "decision_notes": "; ".join(result["decision_notes"]),
            })
        except Exception as e:  # pragma: no cover — defensive
            stats["errors"] += 1
            report_rows.append({
                "name": name, "team": team, "outcome": "error",
                "changes": "", "decision_notes": f"{type(e).__name__}: {e}",
            })

    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(args.report_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "team", "outcome", "changes", "decision_notes"])
        w.writeheader()
        w.writerows(report_rows)

    if not args.dry_run and stats["applied"] > 0:
        save_roster(args.roster_path, roster)

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"[{mode}] applied={stats['applied']} skipped={stats['skipped_status']} "
          f"not_found={stats['not_found']} errors={stats['errors']}")
    print(f"Report: {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
