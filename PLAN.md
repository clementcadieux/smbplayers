# SMBPlayers – Issue Resolution Plan

---

## Completed Issues

- **#1 – Make MLB Stats Parsed Available Only on Local Machine** – Updated `.gitignore` to exclude CSV/JSON data files and allowed `smb4_player_reference.json`.
- **#2 – Ensure Ratings Calculation Takes Into Account Both Surface Metrics and Normal Stats** – Implemented surface-weight blending capped at 50%, scaling linearly with sample size.
- **#3 – Implement the Output Structure of the SMB4 Player Ratings** – Added per-team JSON files organized by league/division and a top-level `index.json`.
- **#4 – Implement Logic to Rank Players Based on Who Should Be Included in the Team** – Added `roster_selector.py` with 22-slot selection (4 SP, 5 RP, 5 IF, 4 OF, 2 C, 2 Flex) sorted by projected playing time then age.
- **#10 – Run a Full Process Test Using the Toronto Blue Jays** – Validated the complete ingest → rate → structured output → roster selection pipeline with a synthetic Blue Jays dataset in `tests/test_e2e_bluejays.py`.
- **#18 – Recommended Players Should Only Be from Current Season Roster and Injured List** – Duplicate of #20; resolved by the same fix.
- **#20 – Players from Non-Active Roster (Other Team) Are Getting Recommended** – Added `active` flag to `PlayerInput`, roster-year filtering in ingestion, and `--team` CLI flag to exclude off-roster players.

---

## Open Issues

## Issue #23 – Volume Predictor Should Ignore Injuries

**Problem:** The volume predictor (which estimates projected PA/IP and drives roster selection priority) is penalised by injury-shortened seasons. It should predict a player's healthy-season volume as if injuries did not occur.

### Steps

1. **Identify injury-shortened seasons during ingestion:**
   - In `savant.py` and `baseball_reference.py`, flag any season where the player's recorded games / PA / IP fall significantly below the positional median for a full season (configurable threshold in `smb4_player_reference.json`).
   - Add an `injury_shortened: bool` field to the per-season data structure.

2. **Exclude injury-shortened seasons from the volume baseline:**
   - In the volume predictor logic (wherever `projected_pa` / `projected_ip` is computed), filter out seasons marked `injury_shortened = True` before averaging or projecting.
   - Fall back to career average (excluding shortened seasons) if all recent seasons are flagged.

3. **Add a configurable threshold to `smb4_player_reference.json`:**
   - Add an `injury_threshold` block with `min_pa_fraction` and `min_ip_fraction` (e.g. `0.6` of median full-season volume) so thresholds are not hard-coded.

4. **Update tests:**
   - Add a test where a player has one injury-shortened season and confirm the volume predictor uses their healthy-season average instead.
   - Confirm the fallback to career average when all seasons are shortened.

---

## Issue #24 – Pitch Selector for Pitchers Based on Real-Life Pitch Mix

**Problem:** Each pitcher needs a recommended pitch mix derived from their real-life usage. Pitches must be mapped to their SMB4 equivalents where the game's pitch vocabulary differs from MLB terminology.

### Key Pitch Mappings

| MLB Pitch | SMB4 Equivalent |
|---|---|
| Sinker | 2-Seam Fastball |
| Splitter | Forkball |
| Sweeper | Slider |

### Steps

1. **Add pitch mix data to ingestion:**
   - In `savant.py`, parse pitch usage percentages from the Baseball Savant CSV (columns like `ff_pct`, `si_pct`, `sl_pct`, etc.).
   - Store raw pitch percentages as a `pitch_mix: dict[str, float]` field on `PlayerInput`.

2. **Define the MLB → SMB4 pitch mapping in `smb4_player_reference.json`:**
   - Add a `pitch_mappings` section listing each MLB pitch type, its SMB4 name (or `null` if unavailable in-game), and its merge target when a direct equivalent doesn't exist.

3. **Implement `select_pitch_mix(pitch_mix: dict[str, float]) -> list[str]` in a new `pitch_selector.py` module:**
   - Apply the mappings from `smb4_player_reference.json` to translate MLB pitches to SMB4 pitches.
   - Merge percentages for pitches that share an SMB4 equivalent (e.g. Sinker % + 4-Seam % → 2-Seam/Fastball % if both map to the same slot).
   - Select the top pitches by usage percentage up to the SMB4 pitcher pitch-slot limit (defined in `smb4_player_reference.json`).
   - Return the ordered list of recommended SMB4 pitches.

4. **Surface pitch recommendations in the output:**
   - Add a `recommended_pitches: list[str]` field to `RatingOutput` / `PlayerOutput` for pitchers.
   - Populate it by calling `select_pitch_mix` during the rating pipeline in `engine.py`.

5. **Add tests:**
   - Verify correct mapping (e.g. Sinker → 2-Seam FB, Sweeper → Slider).
   - Verify percentage merging when multiple MLB pitches map to the same SMB4 pitch.
   - Verify the output list is capped at the SMB4 pitch-slot limit.

---

## Issue #28 – Improvements for Volume Predictor

**Problem:** Some players (e.g. Trey Yesavage) are predicted to have much lower volume than expected because they were called up late in the season or missed time due to injury. Using raw IP or AB totals under-represents their true performance rate.

### Proposed Solution

Replace raw seasonal volume totals with a **per-day rate metric** (PA per active day for hitters, IP per active day for pitchers) so that partial-season call-ups and injury absences don't artificially deflate projections.

### Steps

1. **Expose days-on-roster in ingestion:**
   - In `savant.py` (and `baseball_reference.py` if applicable), parse or compute the number of days a player was on the active MLB roster for each season.
   - Store this as a `days_on_roster: int | None` field in the per-season data structure (alongside existing PA/IP fields).

2. **Add a `days_on_roster` field to `PlayerInput`:**
   - Add per-season `days_on_roster` entries in the same shape as existing sample-season dictionaries (`current`, `previous`, `two_years_ago`).
   - Keep it optional so existing data files without the field remain valid.

3. **Compute volume rate in the projection logic:**
   - In `engine.py`, in `resolved_projected_pa` / `resolved_projected_ip` (and wherever season volume is derived), if `days_on_roster` is available and > 0, compute the **rate** (PA / days or IP / days) and multiply by a configurable full-season day target.
   - Fall back to raw totals when `days_on_roster` is absent.

4. **Add configurable full-season day targets to `smb4_player_reference.json`:**
   - Add a `volume_projection` block with keys `full_season_days_hitter` and `full_season_days_pitcher` (e.g. `162` and `180`) so the targets are not hard-coded.

5. **Update tests:**
   - Add a test for a call-up scenario (partial season with high rate) and confirm the projected volume is closer to a full-season estimate than the raw total.
   - Confirm fallback to raw totals when `days_on_roster` is `None`.
