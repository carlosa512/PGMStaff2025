#!/usr/bin/env python3
"""
PGMStaff2025 — 2026 Season Cleanup Script
Updates staff file to reflect post-2025 NFL coaching changes.
"""

import json
import uuid
import random
import copy

INPUT_FILE = "../archive/staff/PGMStaff2025.json"
OUTPUT_FILE = "../PGMStaff_2026_Final.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def new_uuid():
    return str(uuid.uuid4()).upper()

def rand_appearance():
    """Generate a random appearance array matching the game's schema."""
    heads  = ['Head1a','Head1b','Head1c','Head1d','Head2a','Head2b','Head2c','Head2d',
               'Head3a','Head3b','Head3c','Head3d','Head4b','Head4c','Head4d','Head5a','Head5b','Head5d']
    eyes   = ['Eyes1a','Eyes1b','Eyes1c','Eyes1d','Eyes1e']
    hairs  = ['Hair1a','Hair1b','Hair1c','Hair1d','Hair1e','Hair2a','Hair2c','Hair2d',
               'Hair3a','Hair3b','Hair3c','Hair3d','Hair4a','Hair4b','Hair5a','Hair5b',
               'Hair6a','Hair6b','Hair6c','Hair6d']
    beards = ['Beard1a','Beard1b','Beard1c','Beard1d','Beard1e','Beard2a','Beard2b',
               'Beard3a','Beard3b','Beard4a','Beard5a','Beard6a']
    brows  = ['Eyebrows1a','Eyebrows1b','Eyebrows2a','Eyebrows2b','Eyebrows3a','Eyebrows3b',
               'Eyebrows4a','Eyebrows4b','Eyebrows5a','Eyebrows5b','Eyebrows6a','Eyebrows6b']
    noses  = ['Nose1a','Nose1b','Nose1c','Nose1d','Nose2a','Nose2b','Nose2c','Nose2d',
               'Nose3a','Nose3c','Nose4a','Nose4b','Nose4c','Nose4d','Nose5a','Nose5b']
    mouths = ['Mouth1a','Mouth1b','Mouth2a','Mouth2b','Mouth3a','Mouth3b',
               'Mouth4a','Mouth4b','Mouth5a','Mouth5b']
    glasses= ['Glasses1a','Glasses1b','Glasses1c','Glasses1d','Glasses1e']
    clothes= ['Clothes1','Clothes2']
    return [
        random.choice(heads),
        random.choice(eyes),
        random.choice(hairs),
        random.choice(beards),
        random.choice(brows),
        random.choice(noses),
        random.choice(mouths),
        random.choice(glasses),
        random.choice(clothes),
    ]

def growth_type_for_age(age):
    """Generate a growthType array (51 values) appropriate for a coach's age."""
    g = [0] * 51
    # Coaches start declining in their late 50s / early 60s in-game
    decline_start = max(0, age - 38)  # roughly how far into array declines begin
    if decline_start < 51:
        for i in range(decline_start, 51):
            years_in = i - decline_start
            if years_in < 5:
                g[i] = -random.randint(100, 400)
            elif years_in < 15:
                g[i] = -random.randint(500, 1200)
            else:
                g[i] = -random.randint(1000, 2000)
    return g

def find(data, forename, surname):
    """Find a staff entry by name, return index."""
    for i, s in enumerate(data):
        if s.get('forename','').strip() == forename.strip() and s.get('surname','').strip() == surname.strip():
            return i
    raise ValueError(f"Staff not found: {forename} {surname}")

def find_by_uuid(data, iden):
    for i, s in enumerate(data):
        if s.get('iden') == iden:
            return i
    raise ValueError(f"UUID not found: {iden}")

def promote_to_hc(entry, new_team):
    """Convert an OC or DC entry to a HC entry (keep rating, redistribute stats)."""
    r = entry['rating']
    entry['role'] = 'Head Coach'
    entry['teamID'] = new_team
    entry['HCcoach'] = r
    entry['HCcoachDev'] = r - 2
    entry['HCcoachMatch'] = r - 3
    # Carry over management/motivation/discipline if they're reasonable, else set
    if entry.get('management', 0) < 50:
        entry['management'] = r - 2
    if entry.get('motivation', 0) < 50:
        entry['motivation'] = r - 4
    if entry.get('discipline', 0) < 50:
        entry['discipline'] = r - 5
    # Keep playcalling and style fields as-is
    return entry

def demote_to_oc(entry, new_team):
    """Convert an HC entry to an OC entry."""
    r = entry['rating']
    entry['role'] = 'Off Co-ord'
    entry['teamID'] = new_team
    entry['OCcoach'] = r
    entry['OCcoachDev'] = r - 2
    entry['OCcoachMatch'] = r - 3
    # HC stats can stay (the game uses role to determine which stats matter)
    return entry

def demote_to_dc(entry, new_team):
    """Convert an HC entry to a DC entry."""
    r = entry['rating']
    entry['role'] = 'Def Co-ord'
    entry['teamID'] = new_team
    entry['DCcoach'] = r
    entry['DCcoachDev'] = r - 2
    entry['DCcoachMatch'] = r - 3
    return entry

def base_entry(forename, surname, role, team, age, rating,
               off_style='Pro Style', def_style='4-3 Zone', blitz='Medium',
               fourth='Balanced', rb_style='Lead Back',
               phys_type='Balanced', phys_boost='Hamstring Strain',
               scout_type='Balanced', scout_boost='QB',
               salary=None, start_season=None):
    """Create a complete new staff entry with sensible defaults."""
    r = rating
    random.seed(forename + surname)  # deterministic appearance per person

    if salary is None:
        salary_map = {
            'Head Coach': 1200000, 'Off Co-ord': 600000, 'Def Co-ord': 600000,
            'Special Teams': 200000, 'Head Scout': 400000, 'Off Scout': 200000,
            'Def Scout': 200000, 'Head Physio': 300000, 'Assistant Physio': 200000
        }
        salary = salary_map.get(role, 400000)

    if start_season is None:
        # Estimate start season from age (assume started coaching around 30)
        start_season = max(1990, 2025 - (age - 30))

    # Coordinator-specific stats
    hc_coach = r - 5 if role == 'Head Coach' else r - 8
    oc_coach = r - 5 if role == 'Off Co-ord' else r - 10
    dc_coach = r - 5 if role == 'Def Co-ord' else r - 10
    st_coach = r - 12

    if role == 'Head Coach':
        hc_coach = r
    elif role == 'Off Co-ord':
        oc_coach = r
    elif role == 'Def Co-ord':
        dc_coach = r

    return {
        "AphysioPrev": 0,
        "STcoachMatch": r - 10 if role == 'Special Teams' else 0,
        "fourthStyle": fourth,
        "OCcoachDev": (r - 2) if role == 'Off Co-ord' else 0,
        "Oscout": 0,
        "HscoutEval": 0,
        "Hscout": 0,
        "length": 0,
        "age": age,
        "DCcoachMatch": (r - 3) if role == 'Def Co-ord' else 0,
        "eGuarantee": salary // 4,
        "physBoost": phys_boost,
        "Dscout": 0,
        "OscoutEval": 0,
        "playDesign": max(60, r + random.randint(-8, 8)),
        "blocking": max(55, r + random.randint(-15, 15)),
        "DCcoachDev": (r - 2) if role == 'Def Co-ord' else 0,
        "rehabBone": 0,
        "passRush": max(55, r + random.randint(-12, 12)),
        "growthType": growth_type_for_age(age),
        "OscoutDiamond": 0,
        "rehabMuscle": 0,
        "rbStyle": rb_style,
        "greed": random.randint(10, 60),
        "guarantee": 0,
        "DCcoach": max(50, dc_coach),
        "HphysioPrev": 0,
        "scoutType": scout_type,
        "OCcoach": max(50, oc_coach),
        "HphysioRehab": 0,
        "management": max(60, r + random.randint(-8, 6)),
        "rushing": max(55, r + random.randint(-15, 15)),
        "STcoachDev": 0,
        "Aphysio": 0,
        "salary": salary,
        "HCcoachMatch": (r - 3) if role == 'Head Coach' else 0,
        "motivation": max(60, r + random.randint(-10, 10)),
        "HscoutDiamond": 0,
        "blitzStyle": blitz,
        "scoutBoost": scout_boost,
        "physType": phys_type,
        "STcoach": max(50, st_coach),
        "coverage": max(55, r + random.randint(-12, 12)),
        "DscoutEval": 0,
        "kicking": max(50, r + random.randint(-15, 10)),
        "offStyle": off_style,
        "HCcoachDev": (r - 2) if role == 'Head Coach' else 0,
        "HCcoach": max(50, hc_coach),
        "potential": r * 3,
        "teamID": team,
        "discipline": max(60, r + random.randint(-8, 8)),
        "AphysioRehab": 0,
        "iden": new_uuid(),
        "ambition": random.randint(20, 75),
        "appearance": rand_appearance(),
        "rating": r,
        "receivers": max(55, r + random.randint(-15, 15)),
        "eSalary": salary,
        "forename": forename,
        "injPrevent": 0,
        "surname": surname,
        "Hphysio": 0,
        "reInjuryRisk": 0,
        "eLength": 1,
        "startSeason": start_season,
        "loyalty": random.randint(20, 70),
        "quarterbacks": max(55, r + random.randint(-15, 15)),
        "defStyle": def_style,
        "OCcoachMatch": (r - 3) if role == 'Off Co-ord' else 0,
        "role": role,
        "DscoutDiamond": 0,
        "playcalling": max(60, r + random.randint(-8, 8)),
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

with open(INPUT_FILE) as f:
    data = json.load(f)

print(f"Loaded {len(data)} staff entries.")

# ---------------------------------------------------------------------------
# STEP 1: DELETIONS
# ---------------------------------------------------------------------------

# Delete Bill Belichick (coaching at UNC, not in NFL)
idx = find_by_uuid(data, "A9FA680D-37CF-4AAA-BB15-E339320C03DE")
data.pop(idx)
print("Deleted: Bill Belichick")

# Delete duplicate Pete Carroll (Free Agent, age 65) — keep LV version (age 70)
idx = find_by_uuid(data, "B4BEF313-AACC-4A9F-892E-3F77B5461309")
data.pop(idx)
print("Deleted: Pete Carroll (duplicate Free Agent, age 65)")

# ---------------------------------------------------------------------------
# STEP 2: FIRED HCs → Free Agent (teamID change only, role stays Head Coach)
# ---------------------------------------------------------------------------

fired_hcs = [
    ("Jonathan", "Gannon"),   # ARI
    ("Raheem",   "Morris"),   # ATL
    ("John",     "Harbaugh"), # BAL
    ("Sean",     "McDermott"),# BUF
    ("Kevin",    "Stefanski"),# CLE
    ("Mike",     "McDaniel"), # MIA
    ("Brian",    "Daboll"),   # NYG
    ("Mike",     "Tomlin"),   # PIT
    ("Brian",    "Callahan"), # TEN
    ("Pete",     "Carroll"),  # LV (surviving duplicate, age 70)
]

for forename, surname in fired_hcs:
    idx = find(data, forename, surname)
    data[idx]['teamID'] = 'Free Agent'
    data[idx]['salary'] = 0
    data[idx]['guarantee'] = 0
    data[idx]['length'] = 0
    print(f"Moved to Free Agent: {forename} {surname} (was HC)")

# ---------------------------------------------------------------------------
# STEP 3: COORDINATORS PROMOTED TO HEAD COACH
# (role changed to Head Coach, new team, stats redistributed)
# ---------------------------------------------------------------------------

promotions = [
    # (forename, surname, new_team)
    ("Joe",   "Brady",   "BUF"),   # BUF OC → BUF HC
    ("Todd",  "Monken",  "CLE"),   # BAL OC → CLE HC
    ("Jesse", "Minter",  "BAL"),   # LAC DC → BAL HC
    ("Klint", "Kubiak",  "LV"),    # SEA OC → LV HC
    ("Mike",  "LaFleur", "ARI"),   # LAR OC → ARI HC
    ("Robert","Saleh",   "TEN"),   # SF DC → TEN HC
]

for forename, surname, new_team in promotions:
    idx = find(data, forename, surname)
    promote_to_hc(data[idx], new_team)
    data[idx]['salary'] = 0
    data[idx]['guarantee'] = 0
    data[idx]['length'] = 0
    print(f"Promoted to HC: {forename} {surname} → {new_team}")

# ---------------------------------------------------------------------------
# STEP 4: FREE AGENT HCs ASSIGNED TO TEAMS
# ---------------------------------------------------------------------------

fa_to_team = [
    ("Mike",  "McCarthy", "PIT", "Head Coach"),  # PIT HC
    ("John",  "Harbaugh", "NYG", "Head Coach"),  # NYG HC (freed in step 2)
    ("Kevin", "Stefanski","ATL", "Head Coach"),  # ATL HC (freed in step 2)
]

for forename, surname, new_team, role in fa_to_team:
    idx = find(data, forename, surname)
    data[idx]['teamID'] = new_team
    data[idx]['role'] = role
    print(f"Assigned to {new_team}: {forename} {surname} as {role}")

# ---------------------------------------------------------------------------
# STEP 5: COORDINATOR REASSIGNMENTS — same role, different team
# ---------------------------------------------------------------------------

coord_moves = [
    # (forename, surname, new_team)
    ("Declan",     "Doyle",   "BAL"),  # CHI OC → BAL OC
    ("Nathaniel",  "Hackett", "ARI"),  # Free Agent OC → ARI OC
    ("Matt",       "Nagy",    "NYG"),  # KC OC → NYG OC
    ("Dennard",    "Wilson",  "NYG"),  # TEN DC → NYG DC
    ("Patrick",    "Graham",  "PIT"),  # LV DC → PIT DC
    ("Anthony",    "Weaver",  "BAL"),  # MIA DC → BAL DC
]

for forename, surname, new_team in coord_moves:
    idx = find(data, forename, surname)
    data[idx]['teamID'] = new_team
    print(f"Moved coordinator: {forename} {surname} → {new_team}")

# ---------------------------------------------------------------------------
# STEP 6: FORMER HCs → COORDINATOR ROLES (role + team change)
# ---------------------------------------------------------------------------

# Raheem Morris: HC → LAR Def Co-ord
idx = find(data, "Raheem", "Morris")
demote_to_dc(data[idx], "LAR")
print("Role change: Raheem Morris → LAR Def Co-ord")

# Jonathan Gannon: HC → GB Def Co-ord
idx = find(data, "Jonathan", "Gannon")
demote_to_dc(data[idx], "GB")
print("Role change: Jonathan Gannon → GB Def Co-ord")

# Mike McDaniel: HC → LAC Off Co-ord
idx = find(data, "Mike", "McDaniel")
demote_to_oc(data[idx], "LAC")
print("Role change: Mike McDaniel → LAC Off Co-ord")

# Brian Daboll: HC → TEN Off Co-ord
idx = find(data, "Brian", "Daboll")
demote_to_oc(data[idx], "TEN")
print("Role change: Brian Daboll → TEN Off Co-ord")

# ---------------------------------------------------------------------------
# STEP 7: DISPLACED COORDINATORS → Free Agent
# ---------------------------------------------------------------------------

displaced = [
    ("Jim",   "Schwartz"), # CLE DC resigned
    ("Zach",  "Orr"),      # BAL DC replaced by Weaver
    ("Chris", "Shula"),    # LAR DC replaced by Morris
    ("Jeff",  "Hafley"),   # GB DC replaced by Gannon
]

for forename, surname in displaced:
    idx = find(data, forename, surname)
    data[idx]['teamID'] = 'Free Agent'
    data[idx]['salary'] = 0
    data[idx]['guarantee'] = 0
    data[idx]['length'] = 0
    print(f"Displaced to Free Agent: {forename} {surname}")

# ---------------------------------------------------------------------------
# STEP 8: NEW ENTRIES
# ---------------------------------------------------------------------------

new_staff = [
    # Pete Carmichael Jr. — BUF Off Co-ord
    # Longtime Saints OC, Pro Style, experienced
    base_entry("Pete", "Carmichael Jr.", "Off Co-ord", "BUF", 54, 77,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Hamstring Strain", scout_boost="QB",
               salary=700000, start_season=2006),

    # Jim Leonhard — BUF Def Co-ord
    # Former Bills safety, defensive coaching background
    base_entry("Jim", "Leonhard", "Def Co-ord", "BUF", 43, 72,
               off_style="Spread", def_style="4-2 Zone", blitz="High",
               fourth="Aggressive", rb_style="Backfield Committee",
               phys_boost="Knee Sprain", scout_boost="S",
               salary=600000, start_season=2016),

    # Travis Switzer — CLE Off Co-ord
    # Young coordinator in Monken's system
    base_entry("Travis", "Switzer", "Off Co-ord", "CLE", 37, 70,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Ankle Sprain", scout_boost="WR",
               salary=500000, start_season=2018),

    # Mike Rutenberg — CLE Def Co-ord
    # Replacing Schwartz, 4-3 base
    base_entry("Mike", "Rutenberg", "Def Co-ord", "CLE", 44, 70,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Torn Hamstring", scout_boost="DE",
               salary=550000, start_season=2015),

    # Andrew Janocko — LV Off Co-ord
    # Former Seahawks QB coach under Kubiak
    base_entry("Andrew", "Janocko", "Off Co-ord", "LV", 40, 69,
               off_style="Pro Style", def_style="3-4 Zone", blitz="Low",
               fourth="Cautious", rb_style="Lead Back",
               phys_boost="Shoulder Sprain", scout_boost="QB",
               salary=450000, start_season=2019),

    # Rob Leonard — LV Def Co-ord
    # Internal Raiders promotion
    base_entry("Rob", "Leonard", "Def Co-ord", "LV", 45, 68,
               off_style="Spread", def_style="3-4 Man", blitz="Medium",
               fourth="Balanced", rb_style="Bellcow",
               phys_boost="Calf Strain", scout_boost="OLB",
               salary=400000, start_season=2017),

    # Brian Fleury — SEA Off Co-ord
    # Replacing Kubiak in Seattle
    base_entry("Brian", "Fleury", "Off Co-ord", "SEA", 38, 70,
               off_style="Air Raid", def_style="4-3 Zone", blitz="Medium",
               fourth="Aggressive", rb_style="Backfield Committee",
               phys_boost="Foot Sprain", scout_boost="WR",
               salary=500000, start_season=2018),

    # Chris O'Leary — LAC Def Co-ord
    # Replacing Minter in LA
    base_entry("Chris", "O'Leary", "Def Co-ord", "LAC", 44, 71,
               off_style="West Coast", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="High Ankle Sprain", scout_boost="CB",
               salary=550000, start_season=2016),

    # Tommy Rees — ATL Off Co-ord
    # Former Notre Dame OC, passing game specialist
    base_entry("Tommy", "Rees", "Off Co-ord", "ATL", 36, 75,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Torn Shoulder", scout_boost="QB",
               salary=600000, start_season=2020),
]

data.extend(new_staff)
print(f"Added {len(new_staff)} new staff entries.")

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

with open(OUTPUT_FILE, 'w') as f:
    json.dump(data, f, separators=(',', ':'))

print(f"\nDone. Output written to {OUTPUT_FILE}")
print(f"Total staff entries: {len(data)}")
