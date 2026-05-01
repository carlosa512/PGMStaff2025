"""Cherry-pick manual in-game edits from PGMRoster2026-manually_edited.txt
into PGMRoster_2026_Final.json, writing PGMRoster_2026_test.json.

Rules (see CLAUDE.md and conversation):
- 2026 rookies, draftNum 1..138 (rounds 1-4): adopt full edited record.
- 2026 rookies, draftNum >138 or <=0 (round 5-7 + UDFA): apply appearance
  changes from edited; apply teamID changes ONLY when both old and new
  team are real (team->team), since FA->team / team->FA moves are game-
  engine UDFA signings/cuts, not user fixes.
- Veterans (draftSeason != 2026): if appearance differs in edited, adopt
  full edited record; otherwise leave _Final.json record untouched.
- New-in-edited rookies are NOT added (observed phantom from engine).
- Players only in _Final (not in edited) are kept as-is.
- After merge: sync contract display fields to engine fields per CLAUDE.md
  (salary==eSalary, guarantee==eGuarantee, length==eLength). Free Agents
  zeroed out.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "PGMRoster_2026_Final.json"
EDITED = ROOT / "PGMRoster2026-manually_edited.txt"
OUT = ROOT / "PGMRoster_2026_test.json"

ROUND_4_LAST_PICK = 138


def norm_name(forename: str, surname: str) -> str:
    """Normalize for matching across name-format quirks."""
    f = re.sub(r"[.\s]+", " ", (forename or "")).strip().lower()
    s = re.sub(r"[.\s]+", " ", (surname or "")).strip().lower()
    return f"{f}|{s}"


def player_key(p: dict) -> tuple:
    return (norm_name(p["forename"], p["surname"]), p.get("draftSeason"))


def is_2026_rookie(p: dict) -> bool:
    return p.get("draftSeason") == 2026


def is_round_1_to_4(p: dict) -> bool:
    dn = p.get("draftNum") or 0
    return 1 <= dn <= ROUND_4_LAST_PICK


def sync_contracts(p: dict) -> None:
    """Make display fields match engine fields; zero FAs."""
    if p.get("teamID") == "Free Agent":
        for fld in ("salary", "eSalary", "guarantee", "eGuarantee", "length", "eLength"):
            p[fld] = 0
        return
    # Engine fields are the source of truth post-play; if engine is 0 but
    # display has a value, fall back to display (covers freshly-imported records).
    for disp, eng in (("salary", "eSalary"), ("guarantee", "eGuarantee"), ("length", "eLength")):
        e_val = p.get(eng, 0) or 0
        d_val = p.get(disp, 0) or 0
        if e_val:
            p[disp] = e_val
        elif d_val:
            p[eng] = d_val
        else:
            p[disp] = 0
            p[eng] = 0


def main():
    final = json.loads(FINAL.read_text())
    edited = json.loads(EDITED.read_text())

    emap = {player_key(p): p for p in edited}
    fmap = {player_key(p): p for p in final}

    out = []
    counts = {
        "rookie_full_replace": 0,
        "rookie_late_partial": 0,
        "vet_appearance_replace": 0,
        "vet_unchanged": 0,
        "no_match_kept": 0,
        "team_change_applied": 0,
        "appearance_change_applied": 0,
    }

    for f in final:
        k = player_key(f)
        e = emap.get(k)
        if e is None:
            out.append(f)
            counts["no_match_kept"] += 1
            continue

        is_real_team_move = (
            e["teamID"] != f["teamID"]
            and f["teamID"] != "Free Agent"
            and e["teamID"] != "Free Agent"
        )
        if is_2026_rookie(f) and is_round_1_to_4(f):
            merged = dict(e)
            # Preserve canonical name spelling/punctuation from _Final
            merged["forename"] = f["forename"]
            merged["surname"] = f["surname"]
            # Reject engine-driven FA<->team moves; only honor team->team fixes
            if e["teamID"] != f["teamID"] and not is_real_team_move:
                merged["teamID"] = f["teamID"]
                merged["teamNum"] = f.get("teamNum", e.get("teamNum"))
                counts["engine_move_rejected"] = counts.get("engine_move_rejected", 0) + 1
            elif is_real_team_move:
                counts["team_change_applied"] += 1
            out.append(merged)
            counts["rookie_full_replace"] += 1
            if e["appearance"] != f["appearance"]:
                counts["appearance_change_applied"] += 1
        elif is_2026_rookie(f):
            merged = dict(f)
            if e["appearance"] != f["appearance"]:
                merged["appearance"] = e["appearance"]
                counts["appearance_change_applied"] += 1
            if is_real_team_move:
                merged["teamID"] = e["teamID"]
                merged["teamNum"] = e.get("teamNum", f.get("teamNum"))
                counts["team_change_applied"] += 1
            elif e["teamID"] != f["teamID"]:
                counts["engine_move_rejected"] = counts.get("engine_move_rejected", 0) + 1
            out.append(merged)
            counts["rookie_late_partial"] += 1
        else:
            # Veteran
            if e["appearance"] != f["appearance"]:
                merged = dict(e)
                merged["forename"] = f["forename"]
                merged["surname"] = f["surname"]
                # Don't carry over team changes for vets (per user)
                merged["teamID"] = f["teamID"]
                merged["teamNum"] = f.get("teamNum", e.get("teamNum"))
                out.append(merged)
                counts["vet_appearance_replace"] += 1
                counts["appearance_change_applied"] += 1
            else:
                out.append(f)
                counts["vet_unchanged"] += 1

    # Do NOT add new-in-edited rookies — observed engine-fabricated phantom
    # (Christopher Hill, draftNum 82 already used by another player).
    counts["new_rookies_skipped"] = sum(
        1 for k, e in emap.items() if k not in fmap and is_2026_rookie(e)
    )

    # Contract sync pass
    for p in out:
        sync_contracts(p)

    OUT.write_text(json.dumps(out, indent=2))
    print(f"Wrote {OUT} ({len(out)} players)")
    for k, v in counts.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
