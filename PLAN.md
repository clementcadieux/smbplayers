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
- **#45 – Position Players Have Innings Pitched** – Guarded IP assignment in `engine.py` so only SP/RP receive `projected_ip`; discarded pitching-row data for non-pitchers during ingestion; added tests confirming position players emit no IP output.
- **#48 – Trait Limitations** – Enforced 2-trait maximum in `engine.py` by keeping the top-2 highest-scoring traits; added elite-pitch mutual-exclusivity rule (only the top-scoring elite-pitch trait retained); stored `max_traits_per_player` and `max_elite_pitch_traits` limits in `smb4_player_reference.json`.
- **#49 – Ensure Anything Done in the Blue Jays Specific Test Flow Was Applied to Full Pipeline** – Audited and removed all team-specific conditionals from `engine.py`, `ingest/`, `roster_selector.py`, and `cli.py`; parameterised the end-to-end test to run against a second synthetic team (DET) confirming the pipeline is team-agnostic.

---

## Open Issues

## Issue #52 – Ratings Are Too Conservative

**Problem:** Overall ratings skew too low. Elite players (e.g. Tarik Skubal, the consensus best pitcher in baseball) receive scores well below expected (88 vs. 95+).

### Steps

1. **Audit current rating formula in `engine.py`:**
   - Review composite-score weights, normalisation bounds, and the final aggregation that produces the overall rating.
   - Compare the output distribution against expected SMB4 rating distributions (where elite players typically land 95–99 and average MLB regulars around 75–80).

2. **Recalibrate normalisation bounds in `smb4_player_reference.json`:**
   - Widen or adjust the upper bounds for key metrics (ERA-, FIP-, xFIP-, wRC+, barrel rate, etc.) so that historically elite seasonal values map closer to the top of the scale rather than being clipped by overly conservative ceilings.

3. **Review and adjust composite weights:**
   - Ensure that elite indicators (e.g. sub-3.00 ERA with high K/9 and low BB/9) drive the overall rating to the 95+ range rather than being dampened by secondary composites.

4. **Add percentile-based or z-score scaling option:**
   - Consider replacing hard min/max normalisation with a percentile or z-score approach anchored on a reference population (e.g. all qualified MLB starters/hitters in a given season) so ratings naturally spread across the full 1–99 scale.

5. **Update tests:**
   - Add regression assertions that synthetic elite-tier stat lines produce ratings ≥ 95.
   - Confirm average-tier stat lines still land in the 70–82 range to avoid grade inflation throughout the scale.

---

## Issue #53 – Hitter Pitch Type/Location Specific Traits

**Problem:** Several hitter traits are conditioned on pitch location (inside, outside, high, low) and pitch type (fastball, breaking ball, offspeed). The current ingestion flow does not capture split-level performance against these pitch categories, resulting in inaccurate trait assignments.

### Steps

1. **Identify required data source:**
   - Research whether Baseball Savant exports pitch-type or zone-level batting splits (e.g. `woba_against_fastball`, `whiff_rate_inside_zone`).
   - Determine the correct CSV export endpoint or Statcast query parameters needed to pull these splits.

2. **Extend `ingest/savant.py`:**
   - Add parsing for pitch-type split columns (e.g. `ba_vs_fastball`, `ba_vs_breaking`, `ba_vs_offspeed`).
   - Add parsing for zone/location split columns (e.g. `woba_inside`, `woba_outside`, `woba_high`, `woba_low`) if available.
   - Map new columns to corresponding fields on `PlayerInput`.

3. **Update `models.py`:**
   - Add optional fields for each new pitch-type / location split on `PlayerInput`.

4. **Wire splits into trait allocation in `engine.py`:**
   - For each location/pitch-type hitter trait defined in `smb4_player_reference.json`, reference the appropriate new `PlayerInput` split field when computing trait eligibility scores.

5. **Update `smb4_player_reference.json`:**
   - Add or update `trait_criteria` entries for all location- and pitch-type-specific hitter traits, pointing to the new split fields and appropriate thresholds.

6. **Update tests:**
   - Add unit tests confirming that a synthetic hitter with strong fastball metrics receives a fastball-related trait.
   - Add unit tests for at least one location-specific trait (e.g. a hitter with elite inside-pitch performance receives the corresponding inside-pitch trait).
