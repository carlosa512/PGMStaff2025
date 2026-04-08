#!/usr/bin/env python3
"""
Update coach appearances for 2026 — fix incorrect skin tones and add glasses
where needed, based on real-life appearance research for active team coaches.

Each appearance array follows: [Head, Eyes, Hair, Beard, Eyebrows, Nose, Mouth, Glasses, Clothes]
- Nose/Mouth groups always match Head group
- Eyebrows always group 1 (1a or 1b) to avoid rendering artifacts
- Beard1 variants for Head groups 4-5 (skin tone matching)
- Glasses1e = no glasses; Glasses1a-d = various glasses
"""
import json
from pathlib import Path

FILE = Path(__file__).parent.parent / "PGMStaff_2026_Final.json"

# Corrected appearances keyed by (forename, surname)
APPEARANCES = {
    # === MAJOR SKIN TONE MISMATCHES ===

    # Christian Parker (DAL DC) — Black, bald, goatee
    ("Christian", "Parker"):       ["Head5b", "Eyes1d", "Hair1j", "Beard1e", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1e", "Clothes2"],

    # Anthony Weaver (BAL DC) — Black, bald, beard
    ("Anthony", "Weaver"):         ["Head5a", "Eyes1e", "Hair1j", "Beard1d", "Eyebrows1a", "Nose5a", "Mouth5b", "Glasses1e", "Clothes2"],

    # Danny Crossman (PIT ST) — White, brown/graying short hair, clean-shaven
    ("Danny", "Crossman"):         ["Head1c", "Eyes1c", "Hair3a", "Beard1a", "Eyebrows1a", "Nose1c", "Mouth1a", "Glasses1e", "Clothes1"],

    # Darrin Simmons (CIN ST) — White, brown/graying short hair, clean-shaven
    ("Darrin", "Simmons"):         ["Head1c", "Eyes1d", "Hair3a", "Beard1a", "Eyebrows1a", "Nose1b", "Mouth1a", "Glasses1e", "Clothes1"],

    # Brian Mason (IND ST) — Black, bald, goatee
    ("Brian", "Mason"):            ["Head5b", "Eyes1c", "Hair1j", "Beard1e", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1e", "Clothes1"],

    # Jeremy Springer (NE ST) — Black, short hair, clean-shaven
    ("Jeremy", "Springer"):        ["Head5a", "Eyes1c", "Hair1n", "Beard1a", "Eyebrows1a", "Nose5a", "Mouth5b", "Glasses1e", "Clothes1"],

    # Aden Durde (SEA DC) — White (English), brown short hair, beard/stubble
    ("Aden", "Durde"):             ["Head1c", "Eyes1a", "Hair1d", "Beard1d", "Eyebrows1a", "Nose1c", "Mouth1a", "Glasses1e", "Clothes1"],

    # Brian Schottenheimer (DAL HC) — White, brown receding, clean-shaven
    ("Brian", "Schottenheimer"):   ["Head1b", "Eyes1e", "Hair2a", "Beard1a", "Eyebrows1a", "Nose1b", "Mouth1a", "Glasses1e", "Clothes2"],

    # John Harbaugh (NYG HC) — White, dark/graying short hair, clean-shaven
    ("John", "Harbaugh"):          ["Head1c", "Eyes1e", "Hair3c", "Beard1a", "Eyebrows1a", "Nose1c", "Mouth1a", "Glasses1e", "Clothes2"],

    # Steve Wilks (NYJ DC) — Black, bald, goatee/mustache
    ("Steve", "Wilks"):            ["Head5b", "Eyes1e", "Hair1j", "Beard1e", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1e", "Clothes1"],

    # Dave Canales (CAR HC) — Mexican-American, dark hair, short beard
    ("Dave", "Canales"):           ["Head3a", "Eyes1e", "Hair1a", "Beard3b", "Eyebrows1a", "Nose3a", "Mouth3b", "Glasses1e", "Clothes2"],

    # Mike McDaniel (LAC OC) — Biracial (Black/white), dark hair, stubble, glasses
    ("Mike", "McDaniel"):          ["Head3b", "Eyes1c", "Hair2c", "Beard3a", "Eyebrows1a", "Nose3a", "Mouth3b", "Glasses1c", "Clothes2"],

    # Michael Ghobrial (ARI ST) — Coptic Egyptian, dark hair, clean-shaven
    ("Michael", "Ghobrial"):       ["Head3a", "Eyes1b", "Hair2a", "Beard3a", "Eyebrows1a", "Nose3a", "Mouth3a", "Glasses1e", "Clothes2"],

    # === BORDERLINE / TONE-ACCURACY ADJUSTMENTS ===

    # DeMeco Ryans (HOU HC) — Black, short/buzzed, beard
    ("DeMeco", "Ryans"):           ["Head5a", "Eyes1c", "Hair1n", "Beard1d", "Eyebrows1a", "Nose5a", "Mouth5b", "Glasses1e", "Clothes1"],

    # Vance Joseph (DEN DC) — Black, bald/close-cropped, goatee/mustache
    ("Vance", "Joseph"):           ["Head5b", "Eyes1e", "Hair1j", "Beard1e", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1e", "Clothes2"],

    # Patrick Graham (PIT DC) — Black, bald, beard, glasses
    ("Patrick", "Graham"):         ["Head5b", "Eyes1a", "Hair1j", "Beard1d", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1c", "Clothes2"],

    # Kelvin Sheppard (DET DC) — Black, short hair, stubble
    ("Kelvin", "Sheppard"):        ["Head5a", "Eyes1b", "Hair1n", "Beard1a", "Eyebrows1a", "Nose5a", "Mouth5b", "Glasses1e", "Clothes1"],

    # Brian Flores (MIN DC) — Afro-Latino (Honduran), lighter, bald, goatee
    ("Brian", "Flores"):           ["Head4b", "Eyes1c", "Hair1j", "Beard1e", "Eyebrows1a", "Nose4a", "Mouth4b", "Glasses1e", "Clothes1"],

    # Daronte Jones (WAS DC) — Lighter-complexioned Black, bald, beard
    ("Daronte", "Jones"):          ["Head4c", "Eyes1b", "Hair1j", "Beard1d", "Eyebrows1a", "Nose4a", "Mouth4b", "Glasses1e", "Clothes1"],

    # Lou Anarumo (IND DC) — White (Italian heritage), dark/graying, clean-shaven
    ("Lou", "Anarumo"):            ["Head2c", "Eyes1e", "Hair3a", "Beard2a", "Eyebrows1a", "Nose2c", "Mouth2a", "Glasses1e", "Clothes1"],

    # Tracy Smith (CAR ST) — Black, bald, clean-shaven (Head5c is invalid value)
    ("Tracy", "Smith"):            ["Head5b", "Eyes1b", "Hair1j", "Beard1a", "Eyebrows1a", "Nose5b", "Mouth5a", "Glasses1e", "Clothes1"],

    # === INVALID VALUE FIX ===

    # Kacy Rodgers (TB DC) — Black, bald, mustache (Nose5c invalid → Nose5b)
    ("Kacy", "Rodgers"):           ["Head5b", "Eyes1a", "Hair1j", "Beard1a", "Eyebrows1a", "Nose5b", "Mouth5b", "Glasses1e", "Clothes1"],

    # === GLASSES ADDITIONS ===

    # Vic Fangio (PHI DC) — White (Italian), white/gray thinning, glasses
    ("Vic", "Fangio"):             ["Head2d", "Eyes1d", "Hair3g", "Beard1a", "Eyebrows1a", "Nose2c", "Mouth2b", "Glasses1c", "Clothes1"],

    # Chris Foerster (SF OC) — White, gray/balding, glasses
    ("Chris", "Foerster"):         ["Head2d", "Eyes1d", "Hair3g", "Beard1a", "Eyebrows1a", "Nose2a", "Mouth2b", "Glasses1c", "Clothes1"],
}


def main():
    with open(FILE) as f:
        data = json.load(f)

    updated = 0
    not_found = []
    for key in APPEARANCES:
        found = False
        for s in data:
            if (s.get("forename", "").strip(), s.get("surname", "").strip()) == key:
                old = s["appearance"]
                new = APPEARANCES[key]
                s["appearance"] = new
                print(f"  {key[0]} {key[1]} ({s.get('teamID','?')} {s.get('role','?')}):")
                print(f"    Before: {old}")
                print(f"    After:  {new}")
                updated += 1
                found = True
                break
        if not found:
            not_found.append(key)

    print(f"\nUpdated {updated}/{len(APPEARANCES)} entries.")
    if not_found:
        print(f"NOT FOUND: {not_found}")

    with open(FILE, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print("Saved.")


if __name__ == "__main__":
    main()
