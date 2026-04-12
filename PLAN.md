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

---

## Issue #56 – Potential Undervaluing of Elite Pitches

**Problem:** Some elite pitches are being undervalued in the quality-score calculation. For example, Tarik Skubal's changeup is not being recognised as elite despite having strong run-value metrics. The fix is to ingest Statcast pitch-type run value (`run_value_per_100`) as an authoritative signal and incorporate it into `_savant_pitch_quality_score`.

### Steps

1. **Extend the manifest schema in `models.py`:**
   - Add `pitch_run_values` as a recognised file type so callers can supply the Statcast pitch-type leaderboard CSV alongside existing manifest entries.

2. **Add a new parser in `ingest/savant.py`:**
   - Implement `parse_savant_pitch_run_value_csv()` that reads the pitch-type detail export and returns a dict keyed by `(player_id, pitch_type)` → `run_value_per_100`.

3. **Merge run-value data into `savant_pitch_details`:**
   - During ingestion, combine the new per-pitch `run_value_per_100` values alongside the existing `xwoba` / `whiff_rate` inputs so the data is available when `engine.py` scores pitches.

4. **Update `_savant_pitch_quality_score` in `engine.py`:**
   - Add a `rv_score` component weighted ~25–30%:
     - Use `bounded_score(−2.0 − rv_per_100, 4.0)` so that elite values (−2.0 to −6.0 RV/100) map toward the top of the scale.
   - Adjust remaining component weights proportionally so the composite still sums to 100.

5. **Add normalisation bounds to `smb4_player_reference.json`:**
   - Store `pitch_rv_per_100_elite` (e.g. −2.0) and `pitch_rv_per_100_exceptional` (e.g. −6.0) as reference thresholds for the new bound.

6. **Update tests:**
   - Add a unit test with a synthetic pitcher whose changeup has `run_value_per_100 ≈ −2.5` and assert the pitch quality score reaches the elite tier.
   - Confirm that average pitches (RV/100 near 0) do not receive an outsized boost from the new component.

---

## Issue #58 – Perform Data Ingestion

**Problem:** The ingestion infrastructure is complete but no real MLB data has been ingested yet. Running a full ingestion with actual Statcast and Baseball Reference exports will accelerate further testing, validate the end-to-end pipeline against real player populations, and produce a baseline set of ratings that can be iteratively improved.

### Steps

1. **Gather source data files:**
   - Download the Baseball Savant hitter, pitcher, and fielding Statcast CSV exports for the primary stat season (2025) and the current roster season (2026) for all teams of interest.
   - Download the corresponding Baseball Reference batting and pitching standard-stat CSVs for the same seasons.
   - Download the Fangraphs advanced leaderboard CSV if additional metrics (DRS, UZR) are required.
   - Store all files in a local `data/exports/` directory (already excluded from version control via `.gitignore`).

2. **Build a multi-team ingest manifest:**
   - Create a `data/manifest.json` using the `IngestManifest` schema already defined in `ingest/savant.py`.
   - For each season entry, list the correct file paths under each source key (`savant_hitters`, `savant_pitchers`, `savant_fielding`, `baseball_reference_hitters`, `baseball_reference_pitchers`, `fangraphs`).
   - Include `roster_filter` entries (team abbreviation + roster season) to restrict output to active roster players.

3. **Run the ingest command:**
   - Execute `python -m smb4_mlb_ratings.cli ingest data/manifest.json data/players.json` and verify the output JSON is well-formed and contains the expected player count per team.
   - Check that key fields are populated: `metrics`, `pitch_mix`, `positional_games`, `days_on_roster`, `trait_metrics`.

4. **Run the rating pipeline:**
   - Execute `python -m smb4_mlb_ratings.cli rate data/players.json data/ratings.json` (optionally filtered per team with `--team`).
   - Inspect the output for overall rating distribution — verify elite players (expected 95+) and average regulars (expected 75–82) land in reasonable ranges.
   - Cross-reference a handful of well-known players (e.g. Tarik Skubal, Shohei Ohtani) against expected SMB4 tiers.

5. **Produce structured output and roster selections:**
   - Execute `python -m smb4_mlb_ratings.cli ingest-rate data/manifest.json data/structured_output/` to generate per-team JSON files and `index.json`.
   - Run the roster selector to confirm 22-slot rosters are produced correctly for each team.

6. **Document any data gaps found:**
   - Note any columns missing from the downloaded CSVs that the ingestion layer expects (e.g. new Statcast fields introduced in issues #40/#41).
   - Open follow-up issues or update `smb4_player_reference.json` normalisation bounds if real-world data reveals out-of-range values.

7. **Commit sanitised outputs (no raw player data):**
   - Do **not** commit the raw CSV or JSON data files.
   - Commit any changes to `smb4_player_reference.json` (updated bounds), `models.py`, or ingestion code that were required to handle real data cleanly.
