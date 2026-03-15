#!/usr/bin/env python3
"""
update_st_coaches_2026.py
Replace all 30 fictional/outdated Special Teams Coordinators with verified
real 2026 NFL STCs. DAL (Nick Sorensen) and DET (Dave Fipp) are unchanged.
Chris Tabor moves BUF → MIA; BUF gets Jeff Rodgers.
"""

import json, copy

INPUT_FILE = "../PGMStaff_2026_Final.json"
OUTPUT_FILE = "../PGMStaff_2026_Final.json"

# ---------------------------------------------------------------------------
# Real 2026 NFL Special Teams Coordinators
# Fields: forename, surname, age, rating, appearance
# STcoachDev / STcoachMatch are auto-calculated preserving existing spread.
# ---------------------------------------------------------------------------
REAL_ST_COACHES = {
    "ARI": {"forename": "Michael",  "surname": "Ghobrial",   "age": 38, "rating": 67,
            "appearance": ["Head2a","Eyes1b","Hair2a","Beard2f1","Eyebrows2a","Nose2a","Mouth2b","Glasses1e","Clothes2"]},
    "ATL": {"forename": "Craig",    "surname": "Aukerman",   "age": 52, "rating": 73,
            "appearance": ["Head2c","Eyes1d","Hair4g","Beard4c","Eyebrows4b","Nose2c","Mouth2b","Glasses1e","Clothes1"]},
    "BAL": {"forename": "Chris",    "surname": "Levine",     "age": 45, "rating": 68,
            "appearance": ["Head2b","Eyes1c","Hair3c","Beard3d","Eyebrows3b","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "BUF": {"forename": "Jeff",     "surname": "Rodgers",    "age": 48, "rating": 73,
            "appearance": ["Head5b","Eyes1c","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "CAR": {"forename": "Tracy",    "surname": "Smith",      "age": 46, "rating": 69,
            "appearance": ["Head5c","Eyes1b","Hair1j","Beard1f2","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "CHI": {"forename": "Richard",  "surname": "Hightower",  "age": 49, "rating": 71,
            "appearance": ["Head5b","Eyes1c","Hair1h","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "CIN": {"forename": "Darrin",   "surname": "Simmons",    "age": 53, "rating": 78,
            "appearance": ["Head5b","Eyes1d","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "CLE": {"forename": "Byron",    "surname": "Storer",     "age": 42, "rating": 65,
            "appearance": ["Head1c","Eyes1b","Hair2e","Beard2f1","Eyebrows2a","Nose1c","Mouth1b","Glasses1e","Clothes2"]},
    # DAL: Nick Sorensen — UNCHANGED
    "DEN": {"forename": "Darren",   "surname": "Rizzi",      "age": 54, "rating": 73,
            "appearance": ["Head2d","Eyes1c","Hair4c","Beard4c","Eyebrows4b","Nose2c","Mouth2b","Glasses1e","Clothes1"]},
    # DET: Dave Fipp — UNCHANGED
    "GB":  {"forename": "Cam",      "surname": "Achord",     "age": 40, "rating": 75,
            "appearance": ["Head2a","Eyes1c","Hair2a","Beard2d","Eyebrows2b","Nose2a","Mouth2b","Glasses1e","Clothes1"]},
    "HOU": {"forename": "Frank",    "surname": "Ross",       "age": 50, "rating": 73,
            "appearance": ["Head5b","Eyes1b","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "IND": {"forename": "Brian",    "surname": "Mason",      "age": 48, "rating": 71,
            "appearance": ["Head2b","Eyes1c","Hair3c","Beard3d","Eyebrows3b","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "JAX": {"forename": "Heath",    "surname": "Farwell",    "age": 46, "rating": 72,
            "appearance": ["Head1d","Eyes1c","Hair3g","Beard3d","Eyebrows3b","Nose1d","Mouth1b","Glasses1e","Clothes1"]},
    "KC":  {"forename": "Dave",     "surname": "Toub",       "age": 64, "rating": 90,
            "appearance": ["Head2d","Eyes1d","Hair6l","Beard6d","Eyebrows6b","Nose2d","Mouth2b","Glasses1e","Clothes1"]},
    "LAC": {"forename": "Ryan",     "surname": "Ficken",     "age": 47, "rating": 70,
            "appearance": ["Head2b","Eyes1b","Hair3a","Beard3d","Eyebrows3a","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "LAR": {"forename": "Bubba",    "surname": "Ventrone",   "age": 47, "rating": 71,
            "appearance": ["Head2a","Eyes1c","Hair3a","Beard3d","Eyebrows3a","Nose2a","Mouth2b","Glasses1e","Clothes2"]},
    "LV":  {"forename": "Joe",      "surname": "DeCamilis",  "age": 55, "rating": 76,
            "appearance": ["Head2d","Eyes1d","Hair4c","Beard4c","Eyebrows4b","Nose2c","Mouth2b","Glasses1e","Clothes1"]},
    # MIA: Chris Tabor — handled specially (uses BUF Tabor's existing appearance)
    "MIN": {"forename": "Matt",     "surname": "Daniels",    "age": 36, "rating": 71,
            "appearance": ["Head5a","Eyes1b","Hair1j","Beard1f1","Eyebrows1a","Nose5a","Mouth5a","Glasses1e","Clothes2"]},
    "NE":  {"forename": "Jeremy",   "surname": "Springer",   "age": 44, "rating": 76,
            "appearance": ["Head2b","Eyes1c","Hair2a","Beard2f1","Eyebrows2a","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "NO":  {"forename": "Phil",     "surname": "Galiano",    "age": 52, "rating": 70,
            "appearance": ["Head2c","Eyes1c","Hair4g","Beard4c","Eyebrows4b","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "NYG": {"forename": "Chris",    "surname": "Horton",     "age": 44, "rating": 73,
            "appearance": ["Head5b","Eyes1c","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "NYJ": {"forename": "Chris",    "surname": "Banjo",      "age": 38, "rating": 70,
            "appearance": ["Head5a","Eyes1b","Hair1j","Beard1f1","Eyebrows1a","Nose5a","Mouth5a","Glasses1e","Clothes2"]},
    "PHI": {"forename": "Michael",  "surname": "Clay",       "age": 44, "rating": 71,
            "appearance": ["Head5b","Eyes1b","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "PIT": {"forename": "Danny",    "surname": "Crossman",   "age": 54, "rating": 73,
            "appearance": ["Head5c","Eyes1c","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"]},
    "SEA": {"forename": "Jay",      "surname": "Harbaugh",   "age": 38, "rating": 78,
            "appearance": ["Head1b","Eyes1c","Hair2e","Beard2f1","Eyebrows2a","Nose1b","Mouth1b","Glasses1e","Clothes2"]},
    "SF":  {"forename": "Brant",    "surname": "Boyer",      "age": 53, "rating": 72,
            "appearance": ["Head2c","Eyes1d","Hair4c","Beard4c","Eyebrows4b","Nose2c","Mouth2b","Glasses1e","Clothes1"]},
    "TB":  {"forename": "Danny",    "surname": "Smith",      "age": 71, "rating": 80,
            "appearance": ["Head1d","Eyes1d","Hair6g","Beard6g","Eyebrows6b","Nose1d","Mouth1b","Glasses1e","Clothes1"]},
    "TEN": {"forename": "John",     "surname": "Fassel",     "age": 44, "rating": 78,
            "appearance": ["Head2b","Eyes1b","Hair3c","Beard3d","Eyebrows3b","Nose2b","Mouth2b","Glasses1e","Clothes1"]},
    "WAS": {"forename": "Larry",    "surname": "Izzo",       "age": 47, "rating": 70,
            "appearance": ["Head2a","Eyes1c","Hair3g","Beard3d","Eyebrows3a","Nose2a","Mouth2b","Glasses1e","Clothes1"]},
}

SKIP_TEAMS = {"DAL", "DET"}   # already accurate, do not touch


def apply_coach(entry, new_data):
    """Update name/age/rating/appearance on an existing entry, preserving all else."""
    old_rating  = entry.get("STcoach", entry.get("rating", 70))
    new_rating  = new_data["rating"]

    # Preserve the existing Dev / Match spread relative to the base rating
    dev_offset   = entry.get("STcoachDev",   old_rating) - old_rating
    match_offset = entry.get("STcoachMatch", old_rating) - old_rating

    entry["forename"]     = new_data["forename"]
    entry["surname"]      = new_data["surname"]
    entry["age"]          = new_data["age"]
    entry["rating"]       = new_rating
    entry["STcoach"]      = new_rating
    entry["STcoachDev"]   = new_rating + dev_offset
    entry["STcoachMatch"] = new_rating + match_offset
    entry["appearance"]   = new_data["appearance"]
    return entry


def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Index ST entries by teamID for quick lookup
    st_by_team = {}
    for entry in data:
        if entry.get("role") == "Special Teams":
            team = entry.get("teamID", "Free Agent")
            st_by_team[team] = entry

    # --- Special case: Chris Tabor BUF → MIA ---
    # Save Tabor's appearance before overwriting BUF entry
    tabor_entry = st_by_team.get("BUF")
    tabor_appearance = copy.deepcopy(tabor_entry["appearance"]) if tabor_entry else None

    # Apply all standard updates
    changed = []
    for team, new_data in REAL_ST_COACHES.items():
        if team in SKIP_TEAMS:
            continue
        entry = st_by_team.get(team)
        if not entry:
            print(f"WARNING: No ST entry found for team {team}")
            continue
        old_name = f"{entry['forename'].strip()} {entry['surname'].strip()}"
        apply_coach(entry, new_data)
        new_name = f"{new_data['forename']} {new_data['surname']}"
        changed.append((team, old_name, new_name, new_data["rating"]))

    # MIA gets Chris Tabor — use his real info but his old BUF appearance
    mia_entry = st_by_team.get("MIA")
    if mia_entry:
        old_name = f"{mia_entry['forename'].strip()} {mia_entry['surname'].strip()}"
        tabor_new = {
            "forename":  "Chris",
            "surname":   "Tabor",
            "age":       54,
            "rating":    74,
            "appearance": tabor_appearance or ["Head2b","Eyes1c","Hair3c","Beard3d","Eyebrows3b","Nose2b","Mouth2b","Glasses1e","Clothes1"],
        }
        apply_coach(mia_entry, tabor_new)
        changed.append(("MIA", old_name, "Chris Tabor", 74))

    # Write output
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nUpdated {len(changed)} Special Teams Coordinator entries:")
    print(f"{'Team':<6} {'Old Name':<22} {'New Name':<22} {'Rating'}")
    print("-" * 65)
    for team, old, new, rating in sorted(changed):
        print(f"{team:<6} {old:<22} {new:<22} {rating}")

    # Verify no duplicates
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        verify = json.load(f)
    st_names = [(e["forename"].strip() + " " + e["surname"].strip())
                for e in verify if e.get("role") == "Special Teams" and e.get("teamID") != "Free Agent"]
    dupes = [n for n in set(st_names) if st_names.count(n) > 1]
    if dupes:
        print(f"\nWARNING: Duplicate names found: {dupes}")
    else:
        print(f"\nNo duplicate names detected across {len(st_names)} team-assigned ST coaches. ✓")

    # Spot-check
    spot = {e["teamID"]: e for e in verify if e.get("role") == "Special Teams"}
    checks = [
        ("KC",  "Dave",  "Toub",       90),
        ("DAL", "Nick",  "Sorensen",   61),
        ("DET", "Dave",  "Fipp",       78),
        ("BUF", "Jeff",  "Rodgers",    73),
        ("MIA", "Chris", "Tabor",      74),
        ("TB",  "Danny", "Smith",      80),
    ]
    print("\nSpot-checks:")
    for team, fname, lname, expected_rating in checks:
        e = spot.get(team, {})
        actual = f"{e.get('forename','?').strip()} {e.get('surname','?').strip()}"
        r = e.get("rating", "?")
        status = "✓" if e.get("forename","").strip() == fname and e.get("surname","").strip() == lname and r == expected_rating else "✗"
        print(f"  {status} {team}: {actual} (rating={r})")


if __name__ == "__main__":
    main()
