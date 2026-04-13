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
- **#64 – Outsized Focus on Current 2026 Minimal Sample Size** – Implemented sample-size-based seasonal weighting with recency decay; stored `full_season_pa_threshold`, `full_season_ip_threshold`, and `season_recency_weights` in `smb4_player_reference.json`; replaced static year weights in `engine.py` with volume-adjusted fractional weights normalised across all available seasons; added tests confirming small current-season samples are outweighed by full prior seasons.
- **#66 – Missing Metrics for Pitchers That Should Be Available** – Added column-name aliases for `first_pitch_strike_pct`, `zone_pct`, `chase_rate`, and `movement_quality` in `savant.py`; added Baseball Reference fallbacks in `baseball_reference.py` (merged only when Savant value is absent); updated normalisation bounds in `smb4_player_reference.json`; added unit tests confirming all four metrics parse correctly and produce non-zero composite scores.
- **#67 – Elite Pitch Traits Almost Never Appear** – Fixed `rv_score` merge into `savant_pitch_details` before trait evaluation; lowered elite-pitch confidence threshold to match genuinely elite pitches (top 10–15 %); added priority bonus for elite-pitch traits so they survive the global 2-trait cap; recalibrated `rv_score` normalisation bounds; added regression tests confirming at least one `Elite *` trait appears for elite-grade pitchers and the 1-elite-pitch-trait cap is respected.

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

## Issue #72 – Players on Rehab Stints in the Minors Aren't Included

**Problem:** The roster filter currently uses the 26-man active roster as its base. Players on the 10-day or 60-day injured list who are on rehab assignments in the minors are excluded even though they remain on the 40-man roster and should be eligible for the SMB4 team.

### Steps

1. **Switch the roster base from the 26-man active list to the 40-man roster:**
   - Update the ingestion manifest schema and documentation to clarify that `roster_filter` should reference the 40-man roster, not the active 26-man list.
   - Adjust any roster-year filtering logic in `ingest/savant.py` and `ingest/baseball_reference.py` to accept all 40-man roster members (active + IL + rehab) as eligible.

2. **Update `PlayerInput` active flag logic:**
   - Review the `active` field on `PlayerInput`; ensure that players on the IL or on rehab stints still receive `active=True` so they pass the roster filter and appear in ratings output.
   - If a separate `on_il` flag would be useful for downstream display, add it as an optional field in `models.py` without changing rating logic.

3. **Update roster selector:**
   - Confirm that `roster_selector.py` does not inadvertently exclude IL players when building the 22-slot roster recommendation.
   - If IL players should be flagged but still included in recommendations, surface the `on_il` flag in the selector output.

4. **Update tests:**
   - Add a test with a player marked as active but on a rehab assignment and assert they appear in the rated output and roster recommendations.
   - Verify that purely off-roster (released/traded) players are still excluded correctly.

---

## Issue #73 – Verify Any Traits Not Included in the Logic

**Problem:** Some traits defined in `smb4_player_reference.json` may not have corresponding data sources or engine logic to populate them. A full audit is needed to identify gaps and assess feasibility of implementation.

### Steps

1. **Audit all defined traits against available data:**
   - For each trait in `smb4_player_reference.json`'s `trait_criteria.traits`, check whether the `trait_metrics.*` field it references is actually computed and populated in `engine.py`.
   - Produce a list of traits that are defined but whose metrics are never set (i.e. always `None` or missing at runtime).

2. **Categorise each unimplemented trait by feasibility:**
   - **Feasible from existing sources:** traits whose required data exists in Savant or Baseball Reference CSVs but is not yet parsed or computed — e.g. `Pinch Perfect` (pinch-hit splits), `Bunter` (bunt stats), `Stimulated`/`Choker`/`Clutch` (late-inning or high-leverage splits), `Surrounded` (runners-on splits for pitchers).
   - **Partially feasible:** traits that require proxies or derived metrics not directly exported — e.g. `Distractor` (stolen-base pressure), `Mind Gamer`/`Sign Stealer` (plate-discipline signals), `Crossed Up` (catcher sequencing).
   - **Not feasible with available data:** traits with no reliable public data equivalent — document and flag in `smb4_player_reference.json` with a `"feasibility": "none"` note.

3. **Implement logic for feasible traits:**
   - For each feasible trait, parse the required stat(s) in `savant.py` or `baseball_reference.py`, compute the `trait_metrics.*` value in `engine.py`, and update normalisation bounds in `smb4_player_reference.json`.
   - For partially feasible traits, implement the best available proxy and annotate the criterion with a `"proxy": true` flag.

4. **Update `PlayerInput` / `PlayerOutput` models if needed:**
   - Add any new `trait_metrics` keys as optional fields in `models.py` if they are not already present.

5. **Add tests:**
   - For each newly implemented trait metric, add a unit test confirming the metric is computed and the trait fires for a synthetic player at the expected threshold.
   - Add a smoke test that checks no trait in `smb4_player_reference.json` references a `trait_metrics.*` key that is permanently `None` for all plausible player inputs.
