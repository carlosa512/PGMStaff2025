# CLAUDE.md - NFL Roster Data Instructions

## Local Reference Data (USE FIRST)

This repo contains pre-pulled NFL roster data in `./reference/`. **Always check these files before searching the web for any player, roster, or team data.** This saves tokens and is more accurate than web searches.

### Available data files:

- `./reference/nflverse_rosters_2026.csv` - Current season rosters with positions, teams, jersey numbers, draft info
- `./reference/nflverse_rosters_weekly_2026.csv` - Weekly roster snapshots (latest week = current state)
- `./reference/nflverse_players.csv` - Master player database with all IDs (gsis, espn, pfr, pff, etc.)
- `./reference/nflverse_draft_picks.csv` - Draft picks by season (filter season=2026 for rookies)
- `./reference/nflverse_transactions.csv` - Trade history

### Workflow for roster edits:

1. Read the relevant CSV file(s) from `./reference/` to get accurate player data
2. Cross-reference player names, positions, and teams against the CSV before making changes
3. Use `nflverse_players.csv` for full name spellings and position verification
4. Use `nflverse_draft_picks.csv` (filtered to season=2026) for rookie class data
5. Only search the web if a player is not found in the local files (e.g., UDFA signings, very recent moves)

### Important reminders (from existing PGM3 conventions):

- Verify player presence in the roster file before creating new entries
- Never assign players to teams they are not actually on
- Use only valid PGM3 positions (never "EDGE" or invented positions)
- Free agents must always be preserved
- Appearance values should reflect real-life racial likeness
- Draft years for non-current-year rookies should be rolled back by one relative to in-game start year

### Refreshing the data:

If the data seems stale, run: `python scripts/pull_nflverse_rosters.py`

This pulls fresh data from nflverse (updates daily at 7AM UTC, including offseason).
Requires `pandas` (`pip install pandas`).

---

## Appearance System

Player appearances are stored as a 9-element array:
```
[Head, Eyes, Hair, Beard, Eyebrows, Nose, Mouth, Glasses, Clothes]
```

### Skin tone groups (1-5)

The Head number encodes skin tone and **must match** the Nose, Mouth, and Eyebrows numbers:
- **Group 1-2**: Lighter skin tones
- **Group 3-4**: Medium skin tones
- **Group 5**: Darker skin tones

Mismatched groups (e.g., Head5a + Nose1b) cause **face clipping/rendering glitches** in-game.

### Valid appearance pools

| Component | Valid values |
|-----------|-------------|
| Head | Head1a-d, Head2a-d, Head3a-d, Head4b-d, Head5a,5b,5d |
| Eyes | Eyes1a-e |
| Hair | Hair1a-e, Hair2a,2c,2d, Hair3a-d, Hair4a-b, Hair5a-b, Hair6a-d |
| Beard | Beard1a-e, Beard2a-b, Beard3a-b, Beard4a, Beard5a, Beard6a |
| Eyebrows | Eyebrows1a-b, 2a-b, 3a-b, 4a-b, 5a-b, 6a-b |
| Nose | Nose1a-d, Nose2a-d, Nose3a,3c, Nose4a-d, Nose5a-b |
| Mouth | Mouth1a-b, Mouth2a-b, Mouth3a-b, Mouth4a-b, Mouth5a-b |
| Glasses | Glasses1a-e (1e = no glasses) |
| Clothes | Clothes1, Clothes2 |

**Note:** The actual roster data contains extended variants (Hair1r1, Beard2f1, etc.) beyond these pools. The pools above are from the generation scripts.

### Appearance accuracy rules

- Head is the **authoritative** skin tone indicator — when fixing mismatches, trust the Head and update Nose/Mouth/Eyebrows to match
- For star players (OVR 75+), verify the Head tone group matches the real player's likeness
- Hair and Beard use a different numbering system (hair color, not skin tone) and are not tone-constrained
- The `rand_appearance()` function in `add_missing_players.py` seeds on player name for deterministic results

---

## Rating System

### OVR calculation

The in-game OVR is computed from **all** individual stats using position-specific weights. The `rating` field in the JSON is metadata — if stats (especially mental stats) are zeroed out, the in-game OVR will display much lower than the stored `rating`.

### Rating formula (used by fix_ratings.py and add_missing_players.py)

```
rating = base_by_experience + w_av_bonus + draft_pick_bonus + jitter
```

- **Base by experience**: 0-1yr → 61, 2-3yr → 63, 4-6yr → 65, 7+ → 67
- **w_av bonus**: PFR weighted career value (0-90 scale) → 0-20 bonus
- **Draft pick bonus**: Pick 1 → +10, Pick 260 → +0 (granular by overall pick)
- **Jitter**: Name-seeded ±2-3 for variation
- **Floor**: 55 for team players (enforced), 60 in formula
- **Ceiling**: 92 (fix_ratings) or 95 (add_missing_players)

### Rating thresholds

- **55 OVR**: Minimum for active roster players (team players)
- **55 OVR**: Free agents below this are pruned by `trim_rosters.py`
- Individual position stats: `max(60, min(99, rating ± random(-3,3)))`

### Position stats (POS_STATS)

Each position has specific "active" stats that get non-zero values. All other stats were historically 0.

| Position | Active stat count | Key stats |
|----------|-------------------|-----------|
| QB | 16 | throwOnRun, sPassAcc, dPassAcc, mPassAcc, decisions, vision, intelligence |
| RB | 12 | trucking, ballSecurity, elusiveness, catching, rushBlock |
| WR | 10 | routeRun, catching, ballSecurity, elusiveness, skillMove |
| TE | 13 | routeRun, catching, rushBlock, passBlock |
| OL (OT/OG/C) | 10 | passBlock, rushBlock, intelligence, discipline |
| DL (DE/DT) | 10 | blockShedding, tackle, ballStrip, intelligence |
| LB (OLB/MLB) | 10 | blockShedding, tackle, zoneCover, ballStrip, intelligence |
| DB (CB/S) | 11 | manCover, zoneCover, tackle, ballStrip, intelligence |
| K/P | 4 | kickAccuracy, burst, stamina, jumping |

### Mental stat baselines

**All positions** now receive non-zero values for intelligence, vision, decisions, and discipline:
- Derived from OVR: `max(30, min(75, rating - 15 + jitter))`
- These are lower than primary position stats but prevent the in-game OVR from being dragged down to ~40
- If a mental stat is already a primary stat for the position (e.g., intelligence for QB), it keeps its full value

---

## Available Scripts

| Script | Purpose |
|--------|---------|
| `scripts/pull_nflverse_rosters.py` | Pull fresh reference data from nflverse |
| `scripts/add_missing_players.py` | Add NFL players missing from roster (uses nflverse data) |
| `scripts/fix_ratings.py` | Bump <55 to 55, re-rate 68-floor artifacts using w_av formula |
| `scripts/fix_appearances_and_ratings.py` | Fix appearance clipping (tone mismatches), add mental stat baselines |
| `scripts/trim_rosters.py` | Enforce 53-man roster limits, prune low-rated FAs |
| `scripts/update_roster_2026.py` | Apply offseason moves (trades, FA signings, cuts) |
| `scripts/update_appearances.py` | Manual appearance corrections by player name |
| `scripts/update_staff_2026.py` | Update coaching staff for 2026 |
| `scripts/update_staff_2026_round2.py` | Staff audit fixes (dupes, vacancies) |
| `scripts/update_st_coaches_2026.py` | Special teams coach updates |

---

## Data Files

| File | Description |
|------|-------------|
| `PGMRoster_2026_Final.json` | Main roster (~4,216 players). Modified in-place by scripts. |
| `PGMStaff_2026_Final.json` | Coaching staff (~447 entries) |

### Player JSON structure (key fields)

```json
{
  "forename": "...", "surname": "...",
  "position": "WR", "teamID": "LV",
  "rating": 78, "potential": 80,
  "age": 26, "years_exp": 4,
  "appearance": ["Head5a", "Eyes1b", ...],
  "growthType": [0, 0, ...],  // 31-element decline curve
  "intelligence": 0, "vision": 0, "decisions": 0, "discipline": 0,
  // ... position-specific stats
}
```

### Valid PGM3 positions

QB, RB, WR, TE, OT, OG, C, DE, DT, OLB, MLB, CB, S, K, P

Never use: EDGE, FB, LS, ILB, NT, FS, SAF, DL, OL, LB, DB (map these to valid positions using POS_MAP in add_missing_players.py)
