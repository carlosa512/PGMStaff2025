#!/usr/bin/env python3
"""
update_roster_2026.py
Apply 2026 NFL offseason moves (trades, FA signings, cuts) to PGMRoster_2026_Final.json.
Only updates teamID; teamNum (jersey number) is preserved.

Sources: NFL.com, ESPN, CBS Sports, PFF offseason trackers (March 2026)
"""

import json

INPUT_FILE  = "../PGMRoster_2026_Final.json"
OUTPUT_FILE = "../PGMRoster_2026_Final.json"

# ---------------------------------------------------------------------------
# MOVES: (forename, surname) -> new teamID
# Only teamID is changed; teamNum (jersey #) stays the same.
# ---------------------------------------------------------------------------
MOVES = {
    # ── TRADES ────────────────────────────────────────────────────────────
    # Trent McDuffie: KC → LAR (for 2026 1st + picks)
    ("Trent",    "McDuffie"):          "LAR",
    # Jaylen Waddle: MIA → DEN (for 2026 1st + 3rd + 4th)
    ("Jaylen",   "Waddle"):            "DEN",
    # Minkah Fitzpatrick: PIT → NYJ (for 2026 7th)
    ("Minkah",   "Fitzpatrick"):       "NYJ",
    # Geno Smith: LV → NYJ (6th for Smith + 7th)
    ("Geno",     "Smith"):             "NYJ",
    # David Montgomery: DET → HOU (for C Juice Scruggs + picks)
    ("David",    "Montgomery"):        "HOU",
    # Michael Pittman Jr.: IND → PIT (signed 3yr/$59M extension)
    ("Michael",  "Pittman Jr."):       "PIT",
    # Osa Odighizuwa: DAL → SF (for 2026 3rd)
    ("Osa",      "Odighizuwa"):        "SF",
    # Solomon Thomas: DAL → TEN (late-round swap)
    ("Solomon",  "Thomas"):            "TEN",
    # Colby Wooden: GB → IND (+ Zaire Franklin swap)
    ("Colby",    "Wooden"):            "IND",
    # Zaire Franklin: IND → GB (comes back in Wooden trade)
    ("Zaire",    "Franklin"):          "GB",

    # ── FREE AGENT SIGNINGS ───────────────────────────────────────────────
    # Kyler Murray: ARI released → signed MIN (1yr)
    ("Kyler",    "Murray"):            "MIN",
    # Tua Tagovailoa: MIA released → signed ATL (1yr/$1.3M)
    ("Tua",      "Tagovailoa"):        "ATL",
    # Malik Willis: signed MIA (3yr/$67.5M)
    ("Malik",    "Willis"):            "MIA",
    # Tyler Linderbaum: BAL → signed LV (3yr/$81M)
    ("Tyler",    "Linderbaum"):        "LV",
    # Travis Etienne Jr.: JAX → signed NO (4yr/$52M)
    ("Travis",   "Etienne Jr."):       "NO",
    # John Franklin-Myers: signed TEN (3yr/$63M)
    ("John",     "Franklin-Myers"):    "TEN",
    # Mike Evans: TB → signed SF
    ("Mike",     "Evans"):             "SF",
    # Kenneth Walker III: SEA → signed KC
    ("Kenneth",  "Walker III"):        "KC",
    # Devin Lloyd: JAX → signed CAR (3yr/$45M)
    ("Devin",    "Lloyd"):             "CAR",
    # Odafe Oweh: BAL → signed WAS (4yr/$100M)
    ("Odafe",    "Oweh"):              "WAS",
    # Rachaad White: TB → signed WAS (1yr/$2M)
    ("Rachaad",  "White"):             "WAS",
    # Trey Hendrickson: CIN → signed BAL (4yr/$112M)
    ("Trey",     "Hendrickson"):       "BAL",
    # Carson Wentz: returning to MIN (1yr)
    ("Carson",   "Wentz"):             "MIN",
    # Cade York: FA → signed NYJ
    ("Cade",     "York"):              "NYJ",

    # ── CUTS / RELEASES → FREE AGENT ─────────────────────────────────────
    # Josh Paschal: DET cut (missed 2025 after back surgery)
    ("Josh",     "Paschal"):           "Free Agent",
}

# ---------------------------------------------------------------------------

def main():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Build lookup: (forename, surname) -> index
    lookup = {}
    for i, player in enumerate(data):
        key = (player["forename"], player["surname"])
        if key in lookup:
            lookup[key].append(i)
        else:
            lookup[key] = [i]

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

    # Write output (minified, no indent)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"), ensure_ascii=False)

    print(f"\n=== update_roster_2026.py results ===")
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
