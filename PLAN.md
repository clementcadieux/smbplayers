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
- **#23 – Volume Predictor Should Ignore Injuries** – Added `injury_shortened` flag to per-season data; volume predictor excludes flagged seasons and falls back to career average.
- **#24 – Pitch Selector for Pitchers Based on Real-Life Pitch Mix** – Implemented `pitch_selector.py` with MLB → SMB4 pitch mappings in `smb4_player_reference.json`; `recommended_pitches` surfaced on `PlayerOutput`.
- **#28 – Improvements for Volume Predictor** – Replaced raw seasonal totals with a per-day rate metric using `days_on_roster`; full-season day targets stored in `smb4_player_reference.json`.
- **#31 – Find and Ingest Data for More In-Depth Trait Allocations** – Audited all traits; added a `trait_criteria` mapping table in `smb4_player_reference.json`; wired new columns into trait allocation in `engine.py`.
- **#34 – Fielding and Arm Strength Stats Almost Entirely Missing** – Added `pop_time` and `framing_runs` parsing in `savant.py`; wired both into the `arm`/`fielding` composites in `engine.py`; added normalisation bounds in `smb4_player_reference.json`.
- **#38 – Secondary Positions** – Parsed per-position innings from Baseball Reference; derived `secondary_positions` list in `engine.py` using a configurable minimum-innings threshold; implemented *Utility* trait logic for full position-group coverage; all fields added to `PlayerInput`/`PlayerOutput`.
- **#39 – Cap Volume Predictor** – Added `max_projected_pa` (700) and `max_projected_ip` (250) to `smb4_player_reference.json`; clamped projected volumes in `engine.py` after all other adjustments.
- **#40 – Metrics Available in Baseball Savant Not Being Properly Consumed** – Audited Statcast CSV schema; added parsing for `avg_exit_velocity`, `barrel_rate`, `sprint_speed` and other gaps in `savant.py`; wired into `power`, `speed`, and `baserunning` composites with normalisation bounds in `smb4_player_reference.json`.
- **#41 – Find and Consume Other Missing Fields** – Added parsing for `oaa`, `drs`, `uzr` (fielding composites) and removed `two_strike_contact_rate` (column absent from available exports); verified normalisation bounds active in `smb4_player_reference.json`.

---

## Open Issues

## Issue #45 – Position Players Have Innings Pitched

**Problem:** Non-pitchers are showing innings pitched values, which shouldn't happen. Position players should not have an innings-pitched stat populated.

### Steps

1. **Guard IP assignment in `engine.py`:**
   - When setting `projected_ip` or any innings-pitched output field, check the player's primary position.
   - Only populate IP-related fields if the player is classified as a pitcher (SP or RP).
   - Set IP to `None` / `0` for all position players regardless of raw data.

2. **Filter at ingestion in `baseball_reference.py` / `savant.py`:**
   - Skip or discard pitching-row data for players whose primary position is not a pitcher.

3. **Update tests:**
   - Add a test confirming that a position player (e.g. a 1B) has no innings-pitched output after rating.
   - Confirm pitchers are unaffected.

---

## Issue #48 – Trait Limitations

**Problem:** Players can receive more traits than the game allows. SMB4 limits each player to **2 traits**. Additionally, only **1 elite-pitch trait** should be assignable per player.

### Steps

1. **Enforce 2-trait maximum in `engine.py`:**
   - After scoring all candidate traits, sort by probability/score descending and keep only the top 2.
   - Remove or truncate any excess traits before writing to `PlayerOutput`.

2. **Add elite-pitch mutual-exclusivity rule:**
   - Define "elite pitch" traits in `smb4_player_reference.json` (e.g. `elite_fastball`, `elite_breaking`, `elite_offspeed`).
   - When multiple elite-pitch traits qualify, retain only the highest-scoring one.

3. **Make limits configurable:**
   - Store `max_traits_per_player` (default `2`) and `max_elite_pitch_traits` (default `1`) in `smb4_player_reference.json`.

4. **Update tests:**
   - Confirm a player never has more than 2 traits in output.
   - Confirm a player never has more than 1 elite-pitch trait.
   - Confirm the 2 traits chosen are the highest-scoring ones.

---

## Issue #49 – Ensure Anything Done in the Blue Jays Specific Test Flow Was Applied to Full Pipeline

**Problem:** Some changes appear to have been made specifically to support the Blue Jays integration test rather than being applied to the general pipeline. The full pipeline should behave consistently for any team.

### Steps

1. **Audit Blue Jays test fixtures and helpers:**
   - Review `tests/test_e2e_bluejays.py` and any test fixtures for team-specific overrides, hard-coded team IDs, or logic branches gated on "TOR" / "Blue Jays".

2. **Identify pipeline code with team-specific branches:**
   - Search `engine.py`, `ingest/`, `roster_selector.py`, and `cli.py` for any conditionals or data references that only apply to Toronto.

3. **Generalise all team-specific logic:**
   - Replace any hard-coded team references with configurable or data-driven equivalents.
   - Ensure ingest, rating, and roster-selection steps work identically for any team input.

4. **Expand integration test coverage:**
   - Add (or parameterise) the end-to-end test so it runs against at least one additional synthetic team dataset to confirm the pipeline is team-agnostic.

5. **Update tests:**
   - Confirm all previously passing Blue Jays test assertions still pass.
   - Confirm the new multi-team test passes.
