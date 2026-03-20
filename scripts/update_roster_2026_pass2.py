#!/usr/bin/env python3
"""
update_roster_2026_pass2.py
Comprehensive division-by-division pass to fix all missed 2026 NFL offseason moves.
Sources: NFL.com, ESPN, CBS Sports, PFF, Yahoo Sports (March 2026 confirmed transactions)

This is the second-pass script. Pass 1 (update_roster_2026.py) applied 25 moves;
this script applies the additional 67 moves found in the full division-by-division review.
"""

import json

INPUT_FILE  = "../PGMRoster_2026_Final.json"
OUTPUT_FILE = "../PGMRoster_2026_Final.json"

# ---------------------------------------------------------------------------
# MOVES: (forename, surname) -> new teamID
# Only teamID is changed; teamNum (jersey #) stays the same.
# ---------------------------------------------------------------------------
MOVES = {
    # ── AFC EAST ──────────────────────────────────────────────────────────
    # BUF signed Bradley Chubb (released by MIA), 3yr/$43.5M
    ("Bradley",   "Chubb"):              "BUF",
    # BUF: signed Isiah Pacheco (from KC), filled void at RB
    ("Isiah",     "Pacheco"):            "BUF",
    # BUF: signed CJ Gardner-Johnson (from HOU), 1yr/$6M
    ("C.J.",      "Gardner-Johnson"):    "BUF",
    # BUF → TEN: Mitchell Trubisky agreed to terms with Titans
    ("Mitch",     "Trubisky"):           "TEN",
    # BUF → LV: Taron Johnson traded to Raiders (nickel CB swap)
    ("Taron",     "Johnson"):            "LV",
    # MIA → BAL: Tyler Huntley re-signed with Ravens
    ("Tyler",     "Huntley"):            "BAL",
    # NYJ → KC: Justin Fields traded for 2027 6th round pick
    ("Justin",    "Fields"):             "KC",
    # NYJ ← DAL: Mazi Smith traded to Jets
    ("Mazi",      "Smith"):              "NYJ",
    # NYJ ← NO: Demario Davis signed with Jets
    ("Demario",   "Davis"):              "NYJ",

    # ── AFC NORTH ─────────────────────────────────────────────────────────
    # BAL ← DEN: P.J. Locke signed with Ravens, 1yr/$5M
    ("P.J.",      "Locke"):              "BAL",
    # BAL ← MIA: Tyler Huntley re-signs (already above)
    # BAL → NYG: Isaiah Likely signed with Giants
    ("Isaiah",    "Likely"):             "NYG",
    # BAL → NYG: Jordan Stout signed with Giants (P)
    ("Jordan",    "Stout"):              "NYG",
    # CIN ← SEA: Boye Mafe signed with Bengals (pass rusher)
    ("Boye",      "Mafe"):               "CIN",
    # CLE ← HOU: Tytus Howard traded to Browns for 2026 5th
    ("Tytus",     "Howard"):             "CLE",
    # CLE ← BUF: A.J. Epenesa signed with Browns
    ("A.J.",      "Epenesa"):            "CLE",
    # CLE ← LAC: Zion Johnson signed with Browns, 3yr/$50M
    ("Zion",      "Johnson"):            "CLE",
    # CLE ← CLE: Jerome Ford re-signed... actually Ford → WAS (below)
    # DET ← HOU: Juice Scruggs traded to Lions (part of Montgomery deal)
    ("Juice",     "Scruggs"):            "DET",
    # PIT ← CAR: Rico Dowdle signed, 2yr/$12.25M
    ("Rico",      "Dowdle"):             "PIT",
    # PIT ← TB: Jamel Dean signed, 3yr/$36.75M
    ("Jamel",     "Dean"):               "PIT",
    # PIT ← CHI: Jaquan Brisker signed, 1yr/$5.5M
    ("Jaquan",    "Brisker"):            "PIT",
    # PIT ← TEN: Sebastian Joseph-Day signed, 2yr/$11M
    ("Sebastian", "Joseph-Day"):         "PIT",

    # ── AFC SOUTH ─────────────────────────────────────────────────────────
    # IND ← CHI: Jonathan Owens signed, 1yr
    ("Jonathan",  "Owens"):              "IND",
    # IND ← NYJ: Micheal Clemons signed with Colts
    ("Micheal",   "Clemons"):            "IND",

    # ── AFC WEST ──────────────────────────────────────────────────────────
    # DEN ← LAC: J.K. Dobbins re-signed with Broncos, 2yr/$16M
    ("J.K.",      "Dobbins"):            "DEN",
    # LV ← PHI: Nakobe Dean signed with Raiders, 3yr/$36M
    ("Nakobe",    "Dean"):               "LV",
    # LV ← GB: Quay Walker signed with Raiders
    ("Quay",      "Walker"):             "LV",

    # ── NFC EAST ──────────────────────────────────────────────────────────
    # DAL ← GB: Rashan Gary traded to Cowboys for 2027 4th
    ("Rashan",    "Gary"):               "DAL",
    # DAL ← SEA: Sam Howell signed with Cowboys, 1yr/$2.5M
    ("Sam",       "Howell"):             "DAL",
    # DAL → CHI: Jack Sanborn signed with Bears (March 18)
    ("Jack",      "Sanborn"):            "CHI",
    # DAL → DET: Damone Clark signed with Lions (March 18)
    ("Damone",    "Clark"):              "DET",
    # NYG ← BAL: Isaiah Likely signed (already above)
    # NYG ← BAL: Jordan Stout signed (already above)
    # NYG → TEN: Wan'Dale Robinson signed, 4yr/$78M
    ("Wan'Dale",  "Robinson"):           "TEN",
    # PHI ← CAR: Andy Dalton traded to Eagles for 2027 7th
    ("Andy",      "Dalton"):             "PHI",
    # PHI ← KC: Marquise Brown signed, 1yr/$6.5M
    ("Marquise",  "Brown"):              "PHI",
    # PHI ← ATL: Arnold Ebiketie signed with Eagles
    ("Arnold",    "Ebiketie"):           "PHI",
    # PHI ← SEA: Tariq Woolen signed with Eagles
    ("Tariq",     "Woolen"):             "PHI",
    # PHI → CAR: AJ Dillon signed with Panthers (March 19)
    ("AJ",        "Dillon"):             "CAR",
    # PHI → TB: Kenneth Gainwell signed with Buccaneers, 2yr/$14M
    ("Kenneth",   "Gainwell"):           "TB",
    # PHI → LV: Nakobe Dean (already above)
    # WAS ← KC: Leo Chenal signed with Commanders
    ("Leo",       "Chenal"):             "WAS",
    # WAS ← CLE: Jerome Ford signed with Commanders
    ("Jerome",    "Ford"):               "WAS",
    # WAS ← DET: Amik Robertson signed, 2yr/$16M
    ("Amik",      "Robertson"):          "WAS",

    # ── NFC NORTH ─────────────────────────────────────────────────────────
    # CHI ← MIN: Garrett Bradbury acquired (MIN→NE→CHI)
    ("Garrett",   "Bradbury"):           "CHI",
    # CHI ← DET: Kalif Raymond signed, 1yr
    ("Kalif",     "Raymond"):            "CHI",
    # CHI ← TEN: James Lynch signed (March 18)
    ("James",     "Lynch"):              "CHI",
    # CHI → ARI: Matt Pryor signed with Cardinals, 1yr
    ("Matt",      "Pryor"):              "ARI",
    # DET ← MIN: Javon Hargrave signed with Lions
    ("Javon",     "Hargrave"):           "DET",
    # DET ← WAS: Benjamin St-Juste signed with Lions
    ("Benjamin",  "St-Juste"):           "DET",
    # DET ← FA: Skyy Moore signed with Lions
    ("Skyy",      "Moore"):              "DET",
    # DET ← CAR: D.J. Wonnum signed with Lions (March 18)
    ("D.J.",      "Wonnum"):             "DET",
    # DET ← ARI: Greg Dortch signed with Lions (March 19)
    ("Greg",      "Dortch"):             "DET",
    # GB → LV: Quay Walker (already above)
    # GB → DAL: Rashan Gary (already above)
    # GB → NE: Romeo Doubs signed with Patriots, 4yr/$70M
    ("Romeo",     "Doubs"):              "NE",
    # GB → CAR: Rasheed Walker signed with Panthers, 1yr
    ("Rasheed",   "Walker"):             "CAR",
    # NE ← DEN→SEA: Dre'Mont Jones signed with Patriots, 3yr/$39.5M
    ("Dre'Mont",  "Jones"):              "NE",
    # NE ← GB: Romeo Doubs (already above)
    # NE → ATL: Austin Hooper signed with Falcons, 1yr/$3.25M
    ("Austin",    "Hooper"):             "ATL",
    # NE → ARI: Kendrick Bourne signed with Cardinals, 2yr
    ("Kendrick",  "Bourne"):             "ARI",
    # MIN → CHI: Garrett Bradbury (already above)
    # MIN → DET: Javon Hargrave (already above)
    # MIN → NO: Ty Chandler signed with Saints
    ("Ty",        "Chandler"):           "NO",

    # ── NFC SOUTH ─────────────────────────────────────────────────────────
    # ATL → NO: Kaden Elliss signed with Saints, 3yr/$33M
    ("Kaden",     "Elliss"):             "NO",
    # ATL → PHI: Arnold Ebiketie (already above)
    # ATL → MIA: Bradley Pinion signed with Dolphins (P)
    ("Bradley",   "Pinion"):             "MIA",
    # ATL → ARI: Tyler Allgeier signed with Cardinals, 2yr/$12.25M
    ("Tyler",     "Allgeier"):           "ARI",
    # ATL ← IND: Samson Ebukam signed with Falcons
    ("Samson",    "Ebukam"):             "ATL",
    # ATL ← NE: Austin Hooper (already above)
    # ATL ← TEN: Nick Folk signed with Falcons (K), 2yr
    ("Nick",      "Folk"):               "ATL",
    # CAR ← MIA: Jaelan Phillips signed, 4yr/$120M
    ("Jaelan",    "Phillips"):           "CAR",
    # CAR ← GB: Rasheed Walker (already above)
    # CAR ← PHI: AJ Dillon (already above)
    # CAR → PIT: Rico Dowdle (already above)
    # CAR → DET: D.J. Wonnum (already above)
    # CAR → PHI: Andy Dalton (already above)
    # NO ← ATL: Kaden Elliss (already above)
    # NO ← MIN: Ty Chandler (already above)
    # NO ← BUF: David Edwards signed with Saints, 4yr/$61M
    ("David",     "Edwards"):            "NO",
    # NO → NYJ: Demario Davis (already above)
    # NO → SEA: Rashid Shaheed signed with Seahawks, 3yr/$51M
    ("Rashid",    "Shaheed"):            "SEA",
    # TB ← DET: Alex Anzalone signed, 2yr/$17M
    ("Alex",      "Anzalone"):           "TB",
    # TB ← PHI: Kenneth Gainwell (already above)
    # TB → PIT: Jamel Dean (already above)

    # ── NFC WEST ──────────────────────────────────────────────────────────
    # ARI ← ATL: Tyler Allgeier (already above)
    # ARI ← NE: Kendrick Bourne (already above)
    # ARI ← PIT: Isaac Seumalo signed, 3yr/$31.5M
    ("Isaac",     "Seumalo"):            "ARI",
    # ARI ← CHI: Matt Pryor (already above)
    # ARI ← KC: Gardner Minshew signed with Cardinals
    ("Gardner",   "Minshew"):            "ARI",
    # ARI → DET: Greg Dortch (already above)
    # LAR ← KC: Jaylen Watson signed, 3yr/$51M
    ("Jaylen",    "Watson"):             "LAR",
    # SEA → CIN: Boye Mafe (already above)
    # SEA → PHI: Tariq Woolen (already above)
    # SEA → NE: Dre'Mont Jones (already above)
    # SEA → DAL: Sam Howell (already above)
}

# ---------------------------------------------------------------------------

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build lookup: (forename, surname) -> [indices]
    lookup = {}
    for i, player in enumerate(data):
        key = (player["forename"], player["surname"])
        lookup.setdefault(key, []).append(i)

    moved = []
    already_correct = []
    not_found = []

    for (fn, sn), new_team in MOVES.items():
        key = (fn, sn)
        if key not in lookup:
            not_found.append(f"{fn} {sn} → {new_team}")
            continue
        indices = lookup[key]
        if len(indices) > 1:
            print(f"  WARN: multiple entries for {fn} {sn} — updating all {len(indices)}")
        for idx in indices:
            old_team = data[idx]["teamID"]
            if old_team == new_team:
                already_correct.append(f"{fn} {sn} ({new_team})")
            else:
                data[idx]["teamID"] = new_team
                moved.append(f"{fn} {sn}: {old_team} → {new_team}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    print(f"\n=== update_roster_2026_pass2.py results ===")
    print(f"  Moved:           {len(moved)}")
    print(f"  Already correct: {len(already_correct)}")
    print(f"  Not found:       {len(not_found)}")
    print()
    for m in moved:
        print(f"  ✓ {m}")
    if already_correct:
        print()
        for a in already_correct:
            print(f"  = {a}")
    if not_found:
        print()
        for nf in not_found:
            print(f"  ✗ NOT FOUND: {nf}")
    print()
    print(f"Written to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
