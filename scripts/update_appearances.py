#!/usr/bin/env python3
"""Round 3: Correct appearance arrays for all 17 new staff entries."""
import json

FILE = "../PGMStaff_2026_Final.json"

# Corrected appearances keyed by (forename, surname)
APPEARANCES = {
    ("Pete",      "Carmichael Jr."): ["Head2d","Eyes1c","Hair4c","Beard4c","Eyebrows4b","Nose2c","Mouth2b","Glasses1e","Clothes1"],
    ("Jim",       "Leonhard"):       ["Head1a","Eyes1b","Hair1g","Beard1f1","Eyebrows1a","Nose1c","Mouth1b","Glasses1e","Clothes1"],
    ("Travis",    "Switzer"):        ["Head1c","Eyes1c","Hair2e","Beard2f1","Eyebrows2a","Nose1c","Mouth1b","Glasses1e","Clothes2"],
    ("Mike",      "Rutenberg"):      ["Head2b","Eyes1d","Hair3c","Beard3d","Eyebrows3a","Nose2c","Mouth2b","Glasses1e","Clothes1"],
    ("Andrew",    "Janocko"):        ["Head2a","Eyes1b","Hair3a","Beard3d","Eyebrows3a","Nose2a","Mouth2b","Glasses1e","Clothes2"],
    ("Rob",       "Leonard"):        ["Head2b","Eyes1c","Hair3c","Beard3g","Eyebrows3b","Nose2b","Mouth2b","Glasses1e","Clothes1"],
    ("Brian",     "Fleury"):         ["Head2a","Eyes1d","Hair2a","Beard2f1","Eyebrows2a","Nose2c","Mouth2b","Glasses1e","Clothes2"],
    ("Chris",     "O'Leary"):        ["Head2c","Eyes1b","Hair3a","Beard3g","Eyebrows3b","Nose2d","Mouth2a","Glasses1e","Clothes1"],
    ("Tommy",     "Rees"):           ["Head1b","Eyes1c","Hair2e","Beard2f1","Eyebrows2a","Nose1b","Mouth1b","Glasses1e","Clothes1"],
    ("Sean",      "Duggan"):         ["Head2a","Eyes1d","Hair2a","Beard2d","Eyebrows2b","Nose2a","Mouth2b","Glasses1e","Clothes2"],
    ("Eric",      "Bieniemy"):       ["Head5b","Eyes1c","Hair1j","Beard1e","Eyebrows1a","Nose5b","Mouth5a","Glasses1e","Clothes1"],
    ("Sean",      "Mannion"):        ["Head1b","Eyes1a","Hair2c","Beard2f1","Eyebrows2a","Nose1a","Mouth1b","Glasses1e","Clothes2"],
    ("Daronte",   "Jones"):          ["Head5b","Eyes1b","Hair1j","Beard1f2","Eyebrows1a","Nose5a","Mouth5b","Glasses1e","Clothes1"],
    ("Christian", "Parker"):         ["Head1a","Eyes1d","Hair3a","Beard3f1","Eyebrows3a","Nose1b","Mouth1a","Glasses1e","Clothes2"],
    ("Nick",      "Caley"):          ["Head2b","Eyes1c","Hair3a","Beard3d","Eyebrows3a","Nose2c","Mouth2b","Glasses1e","Clothes1"],
    ("Brian",     "Angelichio"):     ["Head2c","Eyes1b","Hair3g","Beard3d","Eyebrows3b","Nose2b","Mouth2a","Glasses1e","Clothes1"],
    ("Nathan",    "Scheelhaase"):    ["Head1d","Eyes1c","Hair2e","Beard2f1","Eyebrows2a","Nose1d","Mouth1b","Glasses1e","Clothes2"],
}

with open(FILE) as f:
    data = json.load(f)

updated = 0
for s in data:
    key = (s.get('forename','').strip(), s.get('surname','').strip())
    if key in APPEARANCES:
        old = s['appearance']
        s['appearance'] = APPEARANCES[key]
        print(f"  Updated: {key[0]} {key[1]}")
        print(f"    Before: {old}")
        print(f"    After:  {s['appearance']}")
        updated += 1

print(f"\nUpdated {updated}/{len(APPEARANCES)} entries.")

with open(FILE, 'w') as f:
    json.dump(data, f, separators=(',', ':'))
print("Saved.")
