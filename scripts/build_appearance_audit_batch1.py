"""Build reference/appearance_audit.csv for Batch 1 (85+ OVR players).

One-shot generator. Captures my per-player proposals and writes the initial
audit CSV. The CSV becomes the authoritative artifact after generation — do
not re-run over a reviewed CSV (it would overwrite user edits).

Run from repo root: ``python3 scripts/build_appearance_audit_batch1.py``
"""
import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROSTER_PATH = REPO_ROOT / "PGMRoster_2026_Final.json"
OUT_PATH = REPO_ROOT / "reference" / "appearance_audit.csv"

# Curated players (gold standard; from screenshots/prior chat). For Batch 1 we
# include only those at 85+ OVR; rows get status=manual_override, empty proposals.
CURATED_NAMES = {
    ("Josh", "Allen"),
    ("Brock", "Purdy"),
    ("Patrick", "Mahomes"),
    ("Mike", "Evans"),
    ("Micah", "Parsons"),
    ("Myles", "Garrett"),
    ("Justin", "Jefferson"),
    ("Ja'Marr", "Chase"),
    ("Lamar", "Jackson"),
    ("CeeDee", "Lamb"),
    ("Jahmyr", "Gibbs"),
}

# Audit proposals keyed by (forename, surname).
# Fields: proposed_head, proposed_hair, proposed_beard, confidence, source, status, notes
# - Leave proposal fields empty string to "keep current".
# - status = "needs_review" (my proposal, awaiting user confirmation)
#          | "no_change" (current looks correct; no proposal)
#          | "manual_override" (already curated)
# - source = "knowledge" | "web_search"
# - confidence = "high" | "medium" | "low"
PROPOSALS = {
    # ----- ARI -----
    ("James", "Conner"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black RB, medium-dark complexion; Head4b fits well"),

    # ----- ATL -----
    ("Chris", "Lindstrom"): dict(status="needs_review", confidence="medium", source="web_search",
        proposed_head="Head1b",
        notes="White OG; Head2b is slightly tan. Pale complexion per headshot; Head1b more accurate"),
    ("Jessie", "Bates III"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black S, medium complexion; Head3c fits"),
    ("Bijan", "Robinson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black RB, medium-dark; Head4d fits"),
    ("Tua", "Tagovailoa"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head4b",
        notes="Samoan QB; Head4d (darkest of group 4) slightly too dark for his tone. Head4b closer to likeness"),

    # ----- BAL -----
    ("Kyle", "Hamilton"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Biracial S (Black father, Italian mother); Head3a fits biracial-lighter per calibration"),
    ("Lamar", "Jackson"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Trey", "Hendrickson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White DE with full beard; Head2b fits tanner complexion"),
    ("Derrick", "Henry"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black RB, darker-skinned; Head5a fits"),
    ("Mark", "Andrews"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White TE; Head1a correct"),

    # ----- BUF -----
    ("Josh", "Allen"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Greg", "Rousseau"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head4d",
        notes="Black OLB, Haitian heritage, medium-dark tone; Head5b slightly too dark, Head4d closer"),
    ("James", "Cook"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head4d",
        notes="Black RB, medium tone; Head5b slightly too dark, Head4d closer"),

    # ----- CHI -----
    ("Cairo", "Santos"): dict(status="needs_review", confidence="medium", source="web_search",
        notes="Brazilian K; light-medium Hispanic tone. Head1d acceptable but verify"),
    ("Joe", "Thuney"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White OG with beard; Head1d fits tanner complexion"),

    # ----- CIN -----
    ("Joe", "Burrow"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White QB; Head1a correct"),
    ("Ja'Marr", "Chase"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),

    # ----- CLE -----
    ("Myles", "Garrett"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Corey", "Bojorquez"): dict(status="needs_review", confidence="medium", source="web_search",
        notes="Hispanic P; Head2b plausible, verify tone"),
    ("Deshaun", "Watson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black QB, darker-skinned; Head5a fits"),

    # ----- DAL -----
    ("Brandon", "Aubrey"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White K, red-bearded; Head1a + Hair3g/Beard3g (red variants) correct"),
    ("Quinnen", "Williams"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DT, medium-dark; Head4b fits"),
    ("CeeDee", "Lamb"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),

    # ----- DEN -----
    ("Quinn", "Meinerz"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White OG with signature long beard; Head1b + Hair2j/Beard2j fits"),
    ("Jaylen", "Waddle"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black WR, medium-dark; Head5b fits"),
    ("Pat", "Surtain II"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black CB, medium-dark; Head4b fits"),
    ("Garett", "Bolles"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White OT with beard; Head1c fits"),
    ("Brandon", "Jones"): dict(status="needs_review", confidence="high", source="knowledge",
        proposed_head="Head4b",
        notes="MISMATCH: Black S currently at Head2a (white tone). Broncos S Brandon Jones is Black, medium-dark; Head4b correct"),

    # ----- DET -----
    ("Penei", "Sewell"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head4c",
        notes="Samoan OT, medium-dark Polynesian tone; Head4c slightly darker than current Head4b. Optional bump"),
    ("Amon-Ra", "St. Brown"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Biracial WR (Black father, German mother); Head3a fits per biracial-lighter calibration"),
    ("Brian", "Branch"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black S, medium-dark; Head4c fits"),
    ("Aidan", "Hutchinson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White DE; Head1b correct"),
    ("Jahmyr", "Gibbs"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Jared", "Goff"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White QB; Head1a correct"),

    # ----- GB -----
    ("Micah", "Parsons"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Zach", "Tom"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black OG, lighter-medium tone; Head3a fits"),
    ("Xavier", "McKinney"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black S, medium tone; Head3b fits"),

    # ----- HOU -----
    ("Will", "Anderson Jr."): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DE, medium-dark; Head5a fits"),
    ("Nico", "Collins"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black WR, medium-dark; Head5b fits"),
    ("Danielle", "Hunter"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DE (Jamaican heritage), medium tone; Head4b fits"),

    # ----- IND -----
    ("Bernhard", "Raimann"): dict(status="needs_review", confidence="medium", source="web_search",
        proposed_head="Head1b",
        notes="Austrian OT; very light complexion. Head1d is the darkest of Group 1 and too tan; Head1b better"),
    ("DeForest", "Buckner"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DT, medium-dark; Head4b fits"),
    ("Sauce", "Gardner"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black CB, medium-dark; Head5a fits"),

    # ----- JAX -----
    ("Josh", "Hines-Allen"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black OLB, darker-skinned; Head4d fits"),
    ("Logan", "Cooke"): dict(status="needs_review", confidence="low", source="web_search",
        notes="White P; verify tone. Head1d acceptable"),
    ("Cam", "Little"): dict(status="needs_review", confidence="low", source="web_search",
        notes="White K (young); verify tone. Head1c acceptable"),

    # ----- KC -----
    ("Creed", "Humphrey"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White C, blond; Head1a + Hair2b/Beard2b (blond) correct"),
    ("Chris", "Jones"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DE, darker-skinned; Head5b fits. Typically bald; Hair1h acceptable short variant"),
    ("Patrick", "Mahomes"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Harrison", "Butker"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K with beard; Head1d acceptable (tanner Group 1)"),

    # ----- LAC -----
    ("Rashawn", "Slater"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head3a",
        notes="Biracial OT (Black father, white mother); Head2b currently is slightly light. Head3a fits biracial calibration"),
    ("Cameron", "Dicker"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K; Head2a acceptable"),
    ("JK", "Scott"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White P; Head1d acceptable"),
    ("Justin", "Herbert"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White QB, tan California complexion; Head2a fits"),

    # ----- LAR -----
    ("Puka", "Nacua"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head3a",
        notes="Samoan WR; Head2b currently is slightly light. Head3a better for Polynesian medium-tan tone"),
    ("Ethan", "Evans"): dict(status="needs_review", confidence="low", source="web_search",
        notes="White P (rookie-era); verify tone. Head1a acceptable"),

    # ----- LV -----
    ("AJ", "Cole"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White P with long hair; Head2d acceptable (tannest Group 2)"),
    ("Maxx", "Crosby"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White DE with beard, tan complexion; Head2b fits"),
    ("Kolton", "Miller"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White OT; Head1c correct"),
    ("Tyler", "Linderbaum"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White C; Head2b acceptable"),

    # ----- MIA -----
    ("Bradley", "Pinion"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White P; Head1c acceptable"),

    # ----- MIN -----
    ("Justin", "Jefferson"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Christian", "Darrisaw"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black OT, darker-skinned; Head5b fits"),
    ("Carson", "Wentz"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head1b",
        notes="White QB; Head1d is the darkest/tannest Group 1. Wentz has a lighter complexion; Head1b closer"),
    ("Brian", "O'Neill"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White OT; Head2c acceptable"),
    ("Jonathan", "Greenard"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DE, darker-skinned; Head4d fits"),

    # ----- NYG -----
    ("Andrew", "Thomas"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black OT, darker-skinned; Head5b fits"),

    # ----- PHI -----
    ("Jordan", "Mailata"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head4b",
        notes="Samoan-Australian OT; Head3b currently is slightly light. Mailata is notably dark-brown Polynesian; Head4b closer"),
    ("Lane", "Johnson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White OT with beard, tan complexion; Head2d fits"),
    ("A.J.", "Brown"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black WR, darker-skinned; Head5b fits"),
    ("DeVonta", "Smith"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black WR, darker-skinned; Head4d fits"),
    ("Jalen", "Hurts"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black QB, medium-dark; Head4b fits"),

    # ----- PIT -----
    ("T.J.", "Watt"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White DE, redhead; Head1a + Hair3g/Beard3f1 (red variants) correct"),
    ("Chris", "Boswell"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K with beard; Head1d acceptable"),
    ("Cameron", "Heyward"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DT, medium-dark; Head4c fits"),
    ("Alex", "Highsmith"): dict(status="needs_review", confidence="high", source="knowledge",
        proposed_head="Head4c",
        notes="MISMATCH: Black OLB currently at Head2a (white tone). Highsmith is Black medium-dark; Head4c correct"),

    # ----- SEA -----
    ("Michael", "Dickson"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Australian P, white/light complexion; Head1b fits"),
    ("Leonard", "Williams"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DT, medium-dark; Head4c fits"),
    ("Jason", "Myers"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K; Head1c acceptable"),

    # ----- SF -----
    ("Trent", "Williams"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black OT, darker-skinned; Head5d (darkest Group 5) fits"),
    ("Nick", "Bosa"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White DE; Head1a correct"),
    ("George", "Kittle"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White TE with signature mustache/hair; Head1a + Hair4b/Beard4b fits"),
    ("Fred", "Warner"): dict(status="needs_review", confidence="medium", source="knowledge",
        proposed_head="Head3c",
        notes="Biracial MLB (white father, Mexican mother); lighter-medium tone. Head4c currently is slightly dark; Head3c closer to biracial calibration"),
    ("Christian", "McCaffrey"): dict(status="no_change", confidence="high", source="knowledge",
        notes="White RB; Head1b correct"),
    ("Brock", "Purdy"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),
    ("Mike", "Evans"): dict(status="manual_override", confidence="high", source="knowledge",
        notes="Curated gold standard"),

    # ----- TB -----
    ("Chase", "McLaughlin"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K; Head2a acceptable"),
    ("Tristan", "Wirfs"): dict(status="needs_review", confidence="high", source="knowledge",
        proposed_head="Head1a",
        notes="MISMATCH: White OT currently at Head3b (medium tone). Wirfs is a very light-complexioned white Iowan; Head1a correct"),
    ("Antoine", "Winfield Jr."): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black S, lighter-medium tone; Head3b fits"),

    # ----- TEN -----
    ("Jeffery", "Simmons"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DT, medium-dark; Head4b fits"),

    # ----- FREE AGENTS -----
    ("Bobby", "Wagner"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black MLB, darker-skinned; Head5d fits"),
    ("Matt", "Prater"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White K veteran; Head1d acceptable (tanner)"),
    ("Kevin", "Zeitler"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White OG veteran with beard; Head1d acceptable"),
    ("Taylor", "Decker"): dict(status="no_change", confidence="medium", source="web_search",
        notes="White OT veteran; Head1d acceptable"),
    ("Khalil", "Mack"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black DE, darker-skinned; Head5d fits"),
    ("Tyreek", "Hill"): dict(status="no_change", confidence="high", source="knowledge",
        notes="Black WR, medium-dark; Head5a fits"),
    ("Jason", "Sanders"): dict(status="needs_review", confidence="low", source="web_search",
        notes="K (Hispanic/white?); verify tone. Head1c acceptable pending confirmation"),
}


def main():
    with open(ROSTER_PATH, "r") as f:
        roster = json.load(f)

    targets = [
        p for p in roster
        if p.get("rating", 0) >= 85
        and p.get("position") != "Rookie"
        and p.get("teamID") != "Rookie"
    ]

    # Sort: teams A-Z (FAs last), within team by rating desc
    targets.sort(key=lambda p: (
        p.get("teamID") == "Free Agent",
        p.get("teamID", ""),
        -p.get("rating", 0),
    ))

    rows = []
    for p in targets:
        fn = p.get("forename", "").strip()
        sn = p.get("surname", "").strip()
        key = (fn, sn)
        app = p.get("appearance", [""] * 9)
        cur_head, cur_hair, cur_beard = app[0], app[2], app[3]

        prop = PROPOSALS.get(key, {})
        rows.append({
            "name": f"{fn} {sn}",
            "team": p.get("teamID", ""),
            "position": p.get("position", ""),
            "rating": p.get("rating", ""),
            "current_head": cur_head,
            "current_hair": cur_hair,
            "current_beard": cur_beard,
            "proposed_head": prop.get("proposed_head", ""),
            "proposed_hair": prop.get("proposed_hair", ""),
            "proposed_beard": prop.get("proposed_beard", ""),
            "confidence": prop.get("confidence", "low"),
            "source": prop.get("source", "web_search"),
            "status": prop.get("status", "needs_review"),
            "notes": prop.get("notes", "TODO: no proposal recorded"),
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name", "team", "position", "rating",
        "current_head", "current_hair", "current_beard",
        "proposed_head", "proposed_hair", "proposed_beard",
        "confidence", "source", "status", "notes",
    ]
    with open(OUT_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # Summary
    by_status = {}
    by_source = {}
    by_confidence = {}
    head_changes = 0
    missing = []
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        by_confidence[r["confidence"]] = by_confidence.get(r["confidence"], 0) + 1
        if r["proposed_head"]:
            head_changes += 1
        if r["notes"].startswith("TODO"):
            missing.append(r["name"])

    print(f"Total rows: {len(rows)}")
    print(f"By status: {by_status}")
    print(f"By source: {by_source}")
    print(f"By confidence: {by_confidence}")
    print(f"Head change proposals: {head_changes}")
    if missing:
        print(f"MISSING PROPOSALS ({len(missing)}):")
        for m in missing:
            print(f"  - {m}")
    else:
        print("All rows have proposals recorded.")


if __name__ == "__main__":
    main()
