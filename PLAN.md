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
- **#52 – Ratings Are Too Conservative** – Recalibrated normalisation bounds, widened upper thresholds for key metrics (ERA-, FIP-, wRC+, barrel rate), adjusted composite weights so elite stat lines (e.g. Skubal-tier) produce overall ratings ≥ 95; added regression assertions for elite and average tiers.
- **#53 – Hitter Pitch Type/Location Specific Traits** – Identified Baseball Savant as the source for pitch-type and zone-level batting splits; extended `savant.py` and `models.py` with new split fields; wired splits into `engine.py` trait allocation and updated `smb4_player_reference.json` `trait_criteria`; added unit tests for fastball and location-specific traits.
- **#56 – Potential Undervaluing of Elite Pitches** – Added `pitch_run_values` manifest type; implemented `parse_savant_pitch_run_value_csv()` in `savant.py`; merged `run_value_per_100` into `savant_pitch_details`; added `rv_score` (~30% weight) to `_savant_pitch_quality_score` in `engine.py`; stored normalisation bounds in `smb4_player_reference.json`; added unit tests confirming elite pitches reach the top tier.

---

## Open Issues

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

---

## Issue #66 – Missing Metrics for Pitchers That Should Be Available

**Problem:** The engine references `first_pitch_strike_pct`, `zone_pct`, `chase_rate`, and `movement_quality` as pitcher composites, but these fields are currently absent or unreliable in the ingested data. At least partial equivalents are available on Baseball Savant and/or Baseball Reference.

### Steps

1. **Audit available columns in Savant pitcher exports:**
   - Review the Statcast pitcher leaderboard CSV headers for columns that map to `first_pitch_strike_pct` (e.g. `f_strike_pct`), `zone_pct` (e.g. `zone_pct` directly), `chase_rate` (e.g. `oz_swing_pct`), and `movement_quality` (derived from `pfx_x`/`pfx_z` or `movement_plus`).
   - Confirm which column names appear in practice versus what `_pick_number` currently tries.

2. **Extend `savant.py` fallback aliases:**
   - Add any missing column-name aliases to the `_pick_number` calls for each of the four metrics inside `_parse_pitcher_savant_row` (or the equivalent pitcher-row parser).
   - For `movement_quality`, if no direct column is present, keep the existing derived formula (`|horizontal_break| + |induced_vertical_break|`) but expose the flag so callers can see it is estimated.

3. **Add Baseball Reference fallbacks:**
   - For `first_pitch_strike_pct` and `zone_pct`, check whether Baseball Reference standard pitching CSVs expose a usable proxy (e.g. `F-Strike%`, `Zone%`) and parse them in `baseball_reference.py` if so.
   - Merge the Baseball Reference values into `PlayerInput.metrics` only when the Savant value is missing.

4. **Update normalisation bounds in `smb4_player_reference.json`:**
   - Ensure `normalization_bounds` has entries for all four metrics with realistic MLB ranges (e.g. `zone_pct`: 40–55 %, `chase_rate`: 25–40 %, `first_pitch_strike_pct`: 55–70 %, `movement_quality` composite: tuned to typical pfx magnitude).

5. **Update `PlayerInput` / `PlayerOutput` models if needed:**
   - If any of the four metrics are not already declared as optional fields in `models.py`, add them.

6. **Add / update tests:**
   - Add a unit test that provides a synthetic Savant CSV row containing the new column aliases and asserts that all four metrics are parsed and non-None.
   - Add a test confirming that, with the metrics populated, the corresponding pitcher composite scores (`junk`, `accuracy`) are non-zero.

---

## Issue #67 – Elite Pitch Traits Almost Never Appear

**Problem:** Elite pitch traits (`Elite 4F`, `Elite CB`, etc.) are absent from rated players even when pitch run-value scores are high. The trait selection pipeline scores and caps elite-pitch traits correctly in isolation, but something upstream prevents them from reaching `high`/`medium` confidence in practice.

### Steps

1. **Trace the elite-pitch scoring path:**
   - In `engine.py`, locate `_savant_pitch_quality_score` (used in issue #56) and verify that `rv_score` is actually being merged into `savant_pitch_details` before trait evaluation runs.
   - Confirm that `_assign_pitch_traits` reads `savant_pitch_details` and that the resulting `TraitSuggestion` for each pitch type reaches `all_player_traits`.

2. **Check confidence thresholds:**
   - Identify the minimum quality score or percentile that yields `high` confidence for an elite-pitch trait; compare against the score range produced by real or synthetic pitch data.
   - If the threshold is too high (e.g. requires a perfect 100-percentile score), lower it to match what a genuinely elite pitch produces (top 10–15 % of the population).

3. **Verify `elite_pitch_traits` set configuration:**
   - Confirm that `smb4_player_reference.json`'s `elite_pitch_traits` list matches the trait names emitted by the pitch-trait assignment code exactly (case-sensitive).
   - If there is a mismatch, align the names.

4. **Fix the `trim_traits_for_output` priority:**
   - In `final_trait_priority`, check whether elite-pitch traits receive a high enough base score to survive the global 2-trait cap.
   - If they are consistently outscored by non-pitch traits (e.g. `Contact Hitter`, `Power Hitter`), add a dedicated priority bonus for elite-pitch traits for pitchers, similar to the `explicit_names` bonus.

5. **Update `smb4_player_reference.json` normalisation bounds for pitch quality:**
   - If the `rv_score` normalisation range is too narrow or miscalibrated, widen it so that strong run values (e.g. −2 runs/100 pitches) clearly map to high percentiles.

6. **Add regression tests:**
   - Add a test with a pitcher whose `savant_pitch_details` contains an elite-grade pitch (high velocity + strong run value + high whiff rate) and assert that at least one `Elite *` trait appears in the final output.
   - Add a test confirming the 1-elite-pitch-trait cap is still respected when two pitches both qualify as elite.

---

## Issue #64 – Outsized Focus on Current 2026 Minimal Sample Size

**Problem:** The current ratings over-weight the 2026 season, which has a very small sample size. The 2025 full-season data should carry significantly more weight. The general rule: half a season's worth of current-year data should equal one full prior season in importance.

### Steps

1. **Audit current season-weighting logic in `engine.py`:**
   - Identify where per-season data is aggregated and how weights are currently assigned to each season.
   - Determine whether weights are static, sample-size-adjusted, or recency-based.

2. **Define a sample-size-based weight formula:**
   - Establish a "full season" threshold for batters (e.g. 500 PA) and pitchers (e.g. 150 IP) in `smb4_player_reference.json`.
   - Compute a fractional weight for a partial season as `actual_volume / full_season_threshold`, capped at 1.0.
   - Apply the rule: a partial season's weight equals `fraction × prior_season_weight`, so half a season ≈ one full prior season.

3. **Implement recency decay:**
   - Assign a recency multiplier to each historical season (e.g. current season weight × 1.0 after volume adjustment, prior season × 1.0, season −2 × 0.8, season −3 × 0.6, etc.) stored in `smb4_player_reference.json`.
   - Combine volume-based fractional weight with recency decay to produce the final per-season weight.

4. **Update `engine.py` aggregation:**
   - Replace static or naïve year weights with the new formula when blending multi-season metrics.
   - Ensure the weighted blend is normalised so weights sum to 1.0 across all seasons available for a player.

5. **Update `smb4_player_reference.json`:**
   - Add `full_season_pa_threshold`, `full_season_ip_threshold`, and `season_recency_weights` (list ordered from current to oldest) keys for easy tuning.

6. **Update tests:**
   - Add a test with a player who has a tiny 2026 sample and a strong 2025 season; assert the overall rating is driven primarily by 2025 data.
   - Add a test confirming that a player with a half-season of 2026 data receives roughly equal weight to a full 2025 season.
   - Regression-test that existing average/elite player score ranges are not materially affected by the change.
