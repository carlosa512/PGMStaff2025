#!/usr/bin/env python3
"""
PGMStaff2025 — Round 2 Corrections Script
Team-by-team audit fixes: removes duplicates, corrects placements,
fills vacancies, adds missing new hires.
"""

import json, uuid, random, copy

FILE = "PGMStaff_2025_Final.json"

def new_uuid():
    return str(uuid.uuid4()).upper()

def find(data, forename, surname):
    for i, s in enumerate(data):
        if s.get('forename','').strip() == forename.strip() and \
           s.get('surname','').strip() == surname.strip():
            return i
    raise ValueError(f"Not found: {forename} {surname}")

def rand_appearance():
    random.seed(None)
    heads  = ['Head1a','Head1b','Head1c','Head1d','Head2a','Head2b','Head2c','Head2d',
               'Head3a','Head3b','Head3c','Head3d','Head4b','Head4c','Head4d','Head5a','Head5b']
    eyes   = ['Eyes1a','Eyes1b','Eyes1c','Eyes1d','Eyes1e']
    hairs  = ['Hair1a','Hair1b','Hair1c','Hair1d','Hair2a','Hair2c','Hair3a','Hair3b',
               'Hair4a','Hair4b','Hair5a','Hair5b','Hair6a','Hair6b','Hair6c','Hair6d']
    beards = ['Beard1a','Beard1b','Beard1c','Beard2a','Beard2b','Beard3a','Beard4a','Beard5a']
    brows  = ['Eyebrows1a','Eyebrows1b','Eyebrows2a','Eyebrows2b','Eyebrows3a','Eyebrows3b',
               'Eyebrows4a','Eyebrows4b','Eyebrows5a','Eyebrows5b']
    noses  = ['Nose1a','Nose1b','Nose2a','Nose2b','Nose3a','Nose4a','Nose4b','Nose5a','Nose5b']
    mouths = ['Mouth1a','Mouth1b','Mouth2a','Mouth2b','Mouth3a','Mouth3b','Mouth4a','Mouth5a']
    glasses= ['Glasses1a','Glasses1b','Glasses1c','Glasses1d','Glasses1e']
    clothes= ['Clothes1','Clothes2']
    return [random.choice(heads), random.choice(eyes), random.choice(hairs),
            random.choice(beards), random.choice(brows), random.choice(noses),
            random.choice(mouths), random.choice(glasses), random.choice(clothes)]

def growth_type_for_age(age):
    g = [0] * 51
    decline_start = max(0, age - 38)
    for i in range(decline_start, 51):
        yrs = i - decline_start
        if yrs < 5:   g[i] = -random.randint(100, 400)
        elif yrs < 15: g[i] = -random.randint(500, 1200)
        else:          g[i] = -random.randint(1000, 2000)
    return g

def base_entry(forename, surname, role, team, age, rating,
               off_style='Pro Style', def_style='4-3 Zone', blitz='Medium',
               fourth='Balanced', rb_style='Lead Back',
               phys_boost='Hamstring Strain', scout_boost='QB',
               salary=None, start_season=None):
    random.seed(forename + surname)
    r = rating
    salary = salary or {'Head Coach':1200000,'Off Co-ord':600000,'Def Co-ord':600000}.get(role,400000)
    start_season = start_season or max(1990, 2025-(age-30))
    hc  = r if role=='Head Coach'  else r-8
    oc  = r if role=='Off Co-ord'  else r-10
    dc  = r if role=='Def Co-ord'  else r-10
    return {
        "AphysioPrev":0,"STcoachMatch":0,"fourthStyle":fourth,
        "OCcoachDev":(r-2) if role=='Off Co-ord' else 0,
        "Oscout":0,"HscoutEval":0,"Hscout":0,"length":0,"age":age,
        "DCcoachMatch":(r-3) if role=='Def Co-ord' else 0,
        "eGuarantee":salary//4,"physBoost":phys_boost,
        "Dscout":0,"OscoutEval":0,
        "playDesign":max(60,r+random.randint(-8,8)),
        "blocking":max(55,r+random.randint(-15,15)),
        "DCcoachDev":(r-2) if role=='Def Co-ord' else 0,
        "rehabBone":0,"passRush":max(55,r+random.randint(-12,12)),
        "growthType":growth_type_for_age(age),
        "OscoutDiamond":0,"rehabMuscle":0,"rbStyle":rb_style,
        "greed":random.randint(10,60),"guarantee":0,
        "DCcoach":max(50,dc),"HphysioPrev":0,"scoutType":"Balanced",
        "OCcoach":max(50,oc),"HphysioRehab":0,
        "management":max(60,r+random.randint(-8,6)),
        "rushing":max(55,r+random.randint(-15,15)),
        "STcoachDev":0,"Aphysio":0,"salary":salary,
        "HCcoachMatch":(r-3) if role=='Head Coach' else 0,
        "motivation":max(60,r+random.randint(-10,10)),
        "HscoutDiamond":0,"blitzStyle":blitz,"scoutBoost":scout_boost,
        "physType":"Balanced","STcoach":max(50,r-12),
        "coverage":max(55,r+random.randint(-12,12)),
        "DscoutEval":0,"kicking":max(50,r+random.randint(-15,10)),
        "offStyle":off_style,
        "HCcoachDev":(r-2) if role=='Head Coach' else 0,
        "HCcoach":max(50,hc),"potential":r*3,"teamID":team,
        "discipline":max(60,r+random.randint(-8,8)),
        "AphysioRehab":0,"iden":new_uuid(),
        "ambition":random.randint(20,75),"appearance":rand_appearance(),
        "rating":r,"receivers":max(55,r+random.randint(-15,15)),
        "eSalary":salary,"forename":forename,"injPrevent":0,"surname":surname,
        "Hphysio":0,"reInjuryRisk":0,"eLength":1,"startSeason":start_season,
        "loyalty":random.randint(20,70),
        "quarterbacks":max(55,r+random.randint(-15,15)),
        "defStyle":def_style,
        "OCcoachMatch":(r-3) if role=='Off Co-ord' else 0,
        "role":role,"DscoutDiamond":0,
        "playcalling":max(60,r+random.randint(-8,8)),
    }

# Load
with open(FILE) as f:
    data = json.load(f)
print(f"Loaded {len(data)} entries.")

# -----------------------------------------------------------------------
# STEP 1 — Displace to Free Agent
# -----------------------------------------------------------------------
displace = [
    ("Bobby",   "Babich"),     # BUF DC — replaced by Leonhard
    ("Ken",     "Dorsey"),     # CLE OC — replaced by Switzer
    ("Matt",    "Eberflus"),   # DAL DC — fired after 1 year
    ("John",    "Morton"),     # DET OC — replaced by Petzing
    ("Chip",    "Kelly"),      # LV OC  — replaced by Janocko
    ("Frank",   "Smith"),      # MIA OC — replaced by Slowik
    ("Mike",    "Kafka"),      # NYG OC — replaced by Nagy
    ("Shane",   "Bowen"),      # NYG DC — replaced by Wilson
    ("Tanner",  "Engstrand"),  # NYJ OC — replaced by Reich
    ("Arthur",  "Smith"),      # PIT OC — left for Ohio State
    ("Teeth",   "Austin"),     # PIT DC — replaced by Graham
    ("Josh",    "Grizzard"),   # TB OC  — replaced by Robinson
    ("Joe",     "Whitt Jr."),  # WAS DC — replaced by Jones
    ("Raheem",  "Morris"),     # LAR DC — was wrong placement; goes to SF
]

for fn, sn in displace:
    idx = find(data, fn, sn)
    data[idx]['teamID'] = 'Free Agent'
    data[idx]['salary'] = 0
    data[idx]['guarantee'] = 0
    data[idx]['length'] = 0
    print(f"  → FA: {fn} {sn}")

# -----------------------------------------------------------------------
# STEP 2 — Coordinator team moves (same role, different team)
# -----------------------------------------------------------------------
moves = [
    ("Drew",    "Petzing",  "DET"),   # ARI OC → DET OC
    ("Zac",     "Robinson", "TB"),    # ATL OC → TB OC
    ("Bobby",   "Slowik",   "MIA"),   # HOU OC → MIA OC
    ("Gus",     "Bradley",  "TEN"),   # FA DC  → TEN DC
    ("Press",   "Taylor",   "CHI"),   # FA OC  → CHI OC
    ("Raheem",  "Morris",   "SF"),    # FA DC  → SF DC (correction)
    ("Chris",   "Shula",    "LAR"),   # FA DC  → LAR DC (restore — displaced by error in Round 1)
]

for fn, sn, team in moves:
    idx = find(data, fn, sn)
    data[idx]['teamID'] = team
    print(f"  → {team}: {fn} {sn}")

# -----------------------------------------------------------------------
# STEP 3 — Role changes
# -----------------------------------------------------------------------

# Jeff Hafley: Free Agent Def Co-ord → MIA Head Coach
idx = find(data, "Jeff", "Hafley")
r = data[idx]['rating']
data[idx]['role'] = 'Head Coach'
data[idx]['teamID'] = 'MIA'
data[idx]['HCcoach'] = r
data[idx]['HCcoachDev'] = r - 2
data[idx]['HCcoachMatch'] = r - 3
if data[idx].get('management', 0) < 55: data[idx]['management'] = r - 2
if data[idx].get('motivation', 0) < 55: data[idx]['motivation'] = r - 4
if data[idx].get('discipline', 0) < 55: data[idx]['discipline'] = r - 5
data[idx]['salary'] = 0
print(f"  Promoted to HC: Jeff Hafley → MIA (rating:{r})")

# Frank Reich: Free Agent Head Coach → NYJ Off Co-ord
idx = find(data, "Frank", "Reich")
r = data[idx]['rating']
data[idx]['role'] = 'Off Co-ord'
data[idx]['teamID'] = 'NYJ'
data[idx]['OCcoach'] = r
data[idx]['OCcoachDev'] = r - 2
data[idx]['OCcoachMatch'] = r - 3
print(f"  Role change: Frank Reich → NYJ Off Co-ord (rating:{r})")

# -----------------------------------------------------------------------
# STEP 4 — New entries
# -----------------------------------------------------------------------
new_staff = [
    base_entry("Sean", "Duggan", "Def Co-ord", "MIA", 38, 70,
               off_style="West Coast", def_style="3-4 Zone", blitz="Medium",
               phys_boost="Knee Sprain", scout_boost="CB",
               salary=500000, start_season=2018),

    base_entry("Eric", "Bieniemy", "Off Co-ord", "KC", 56, 79,
               off_style="West Coast", def_style="4-3 Zone", blitz="Medium",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Hamstring Strain", scout_boost="RB",
               salary=900000, start_season=2007),

    base_entry("Sean", "Mannion", "Off Co-ord", "PHI", 35, 73,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               phys_boost="Ankle Sprain", scout_boost="QB",
               salary=550000, start_season=2021),

    base_entry("Daronte", "Jones", "Def Co-ord", "WAS", 43, 72,
               off_style="Spread", def_style="Hybrid Zone", blitz="Medium",
               phys_boost="Calf Strain", scout_boost="CB",
               salary=550000, start_season=2016),

    base_entry("Christian", "Parker", "Def Co-ord", "DAL", 34, 68,
               off_style="Spread", def_style="4-2 Man", blitz="High",
               fourth="Aggressive", rb_style="Lead Back",
               phys_boost="Shoulder Sprain", scout_boost="DE",
               salary=400000, start_season=2022),

    base_entry("Nick", "Caley", "Off Co-ord", "HOU", 40, 72,
               off_style="Pro Style", def_style="4-3 Zone", blitz="Medium",
               phys_boost="Hamstring Strain", scout_boost="WR",
               salary=550000, start_season=2017),

    base_entry("Brian", "Angelichio", "Off Co-ord", "PIT", 45, 73,
               off_style="West Coast", def_style="4-3 Zone", blitz="Low",
               fourth="Balanced", rb_style="Lead Back",
               phys_boost="Foot Sprain", scout_boost="WR",
               salary=600000, start_season=2014),
]

data.extend(new_staff)
print(f"  Added {len(new_staff)} new entries.")

# -----------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------
with open(FILE, 'w') as f:
    json.dump(data, f, separators=(',', ':'))

print(f"\nSaved {len(data)} total entries to {FILE}")
