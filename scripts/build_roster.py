"""
Build Roster Pipeline
=====================
Runs all roster fix/update scripts in the correct order to produce a
clean PGMRoster_2026_Final.json.

Pipeline order:
  1. add_missing_players.py        - Add NFL players missing from roster
  2. update_roster_2026.py         - Apply trades, FA signings, cuts
  3. fix_ratings.py                - Re-rate players using w_av formula
  4. fix_appearances_and_ratings.py - Fix appearance clipping + stat baselines
  5. fix_stat_pattern.py           - Enforce per-position zero-stat pattern
  6. fix_contracts.py              - Sync salary/eSalary contract fields
  7. trim_rosters.py               - Enforce 53-man limits, prune low FAs

Usage:
    python scripts/build_roster.py              # Run full pipeline
    python scripts/build_roster.py --fixes-only # Only run fix scripts (steps 3-7)
    python scripts/build_roster.py --skip add_missing_players update_roster_2026

Output:
    Modifies PGMRoster_2026_Final.json in place
"""

import argparse
import json
import os
import subprocess
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(SCRIPTS_DIR, "..")
ROSTER_FILE = os.path.join(REPO_ROOT, "PGMRoster_2026_Final.json")

# Pipeline steps in execution order
PIPELINE = [
    ("add_missing_players",        "Add missing players from nflverse"),
    ("update_roster_2026",         "Apply roster moves (trades, FA, cuts)"),
    ("fix_ratings",                "Re-rate players (w_av formula)"),
    ("fix_appearances_and_ratings", "Fix appearances + stat baselines"),
    ("fix_stat_pattern",           "Enforce per-position zero-stat pattern"),
    ("fix_contracts",              "Sync contract fields (salary == eSalary)"),
    ("trim_rosters",               "Enforce 53-man limits"),
]

FIX_ONLY_STEPS = {
    "fix_ratings",
    "fix_appearances_and_ratings",
    "fix_stat_pattern",
    "fix_contracts",
    "trim_rosters",
}


def count_players(roster_file):
    """Return total players and team player count."""
    with open(roster_file, "r") as f:
        data = json.load(f)
    players = data if isinstance(data, list) else data.get("players", data.get("roster", []))
    team_players = sum(1 for p in players if p.get("teamID", "FA") not in ("FA", ""))
    return len(players), team_players


def run_step(script_name, description):
    """Run a single pipeline script. Returns True on success."""
    script_path = os.path.join(SCRIPTS_DIR, f"{script_name}.py")
    if not os.path.exists(script_path):
        print(f"  SKIP (not found): {script_path}")
        return True

    print(f"\n{'='*60}")
    print(f"  STEP: {description}")
    print(f"  Script: {script_name}.py")
    print(f"{'='*60}")

    start = time.time()
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=REPO_ROOT,
    )
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n  FAILED ({elapsed:.1f}s) — exit code {result.returncode}")
        return False

    print(f"\n  Done ({elapsed:.1f}s)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Run the PGM3 roster build pipeline")
    parser.add_argument("--fixes-only", action="store_true",
                        help="Only run fix scripts (skip add/update steps)")
    parser.add_argument("--skip", nargs="+", default=[],
                        help="Script names to skip (without .py)")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="Stop pipeline on first error (default: continue)")
    args = parser.parse_args()

    skip_set = set(args.skip)
    if args.fixes_only:
        skip_set.update(name for name, _ in PIPELINE if name not in FIX_ONLY_STEPS)

    # Pre-flight check
    if not os.path.exists(ROSTER_FILE):
        print(f"ERROR: Roster file not found: {ROSTER_FILE}")
        sys.exit(1)

    total, on_team = count_players(ROSTER_FILE)
    print(f"PGM3 Roster Build Pipeline")
    print(f"{'='*60}")
    print(f"Roster: {ROSTER_FILE}")
    print(f"Players before: {total} total, {on_team} on teams")

    steps_to_run = [(n, d) for n, d in PIPELINE if n not in skip_set]
    if not steps_to_run:
        print("Nothing to run (all steps skipped).")
        return

    print(f"Steps: {len(steps_to_run)} of {len(PIPELINE)}")
    if skip_set:
        print(f"Skipping: {', '.join(sorted(skip_set))}")

    failed = []
    for name, desc in steps_to_run:
        ok = run_step(name, desc)
        if not ok:
            failed.append(name)
            if args.stop_on_error:
                print(f"\nStopping pipeline due to error in {name}")
                break

    # Summary
    total_after, on_team_after = count_players(ROSTER_FILE)
    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"Players after: {total_after} total, {on_team_after} on teams")
    print(f"Delta: {total_after - total:+d} total, {on_team_after - on_team:+d} on teams")

    if failed:
        print(f"\nFailed steps: {', '.join(failed)}")
        sys.exit(1)
    else:
        print(f"\nAll {len(steps_to_run)} steps completed successfully.")


if __name__ == "__main__":
    main()
