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

## Issue #75 – Improve Test Performance

**Problem:** The test suite currently takes close to 10 minutes to run. The run time must be reduced, either by improving the tests themselves or by improving the performance of the underlying production code.

### Steps

1. **Profile the existing test suite:**
   - Run `python -m pytest tests/ --durations=20` to identify the slowest tests and where the most time is being spent.
   - Distinguish between tests that are slow due to heavy computation in `engine.py` and those that are slow due to poor test design (e.g. redundant fixtures, over-broad end-to-end tests).

2. **Optimise the production code hot paths:**
   - Identify any repeated lookups or re-parses of `smb4_player_reference.json` that could be cached at module load time.
   - Look for O(n²) loops or other algorithmic inefficiencies in `engine.py` and `roster_selector.py` that are exercised repeatedly across many test cases.
   - Cache expensive constant computations (normalisation bounds, trait criteria) so they are not rebuilt per player.

3. **Refactor slow tests:**
   - Replace full end-to-end test scenarios with focused unit tests where the full pipeline is not needed.
   - Use smaller synthetic data payloads (fewer players, fewer seasons) in integration tests without sacrificing meaningful coverage.
   - Share expensive fixture setup across tests using `pytest` fixtures with appropriate scoping (`session` or `module` scope).

4. **Parallelise test execution if appropriate:**
   - Evaluate `pytest-xdist` for parallel test execution if the test suite is CPU-bound and tests are independent.
   - Only adopt additional dependencies with explicit user approval.

5. **Verify correctness is preserved:**
   - After any optimisation, confirm all previously passing tests still pass.
   - Measure the new total run time and confirm it is meaningfully below the previous benchmark.

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

---

## Issue #80 – Fix Player Identity Collisions in Rating Post-Processing When Names Are Duplicated

**Problem:** The rating pipeline maps players by name during downstream steps (personality and trait assignment). When two players share the same name, one record can overwrite the other, causing cross-assignment of metadata and traits.

### Steps

1. **Identify all name-keyed dictionaries in `engine.py`:**
   - Search for any `dict` or mapping built using player name as the sole key during personality and trait assignment post-processing.
   - Enumerate every place where a player lookup by name can silently overwrite an earlier entry.

2. **Replace name-only keys with a stable composite key:**
   - Define a helper that returns a stable identity key: prefer `player_id` from the source data when available; fall back to a deterministic composite of `(name, team, primary_position, roster_season)`.
   - Apply this key consistently throughout `engine.py` post-processing and in any downstream serialisation step.

3. **Update `PlayerInput` / `PlayerOutput` models if needed:**
   - Ensure `player_id` is an optional field in `PlayerInput` and is threaded through to `PlayerOutput` so it is available for keying at all pipeline stages.

4. **Add regression tests:**
   - Create a test with two synthetic players sharing the same name on different teams or positions and run them through the full rating pipeline in one batch.
   - Assert that each player retains its own traits and personality — no cross-assignment occurs.
   - Verify existing single-player tests are unaffected.

---

## Issue #81 – Use Full Secondary Positions in Roster Eligibility

**Problem:** Roster eligibility logic considers primary position plus only a single secondary position, while the data model supports a full list of secondary positions. Utility players may be under-eligible, leading to less accurate roster recommendations.

### Steps

1. **Audit `roster_selector.py` eligibility logic:**
   - Locate where `secondary_position` (singular) is read and used to determine slot eligibility.
   - Confirm that the `secondary_positions` (plural) list on `PlayerOutput` is ignored or only partially consumed.

2. **Expand eligibility to cover all secondary positions:**
   - Update the eligibility check so that a player qualifies for a slot if their primary position **or any** entry in `secondary_positions` maps to that slot's position group.
   - Preserve backwards compatibility with records that only populate the legacy `secondary_position` field (treat it as a one-element list fallback).

3. **Keep slot-count rules unchanged:**
   - Ensure the 22-slot composition (4 SP, 5 RP, 5 IF, 4 OF, 2 C, 2 Flex) is not altered by this change.
   - Multi-eligible players should be assigned to the slot that maximises overall team rating, consistent with the existing greedy selection logic.

4. **Add tests:**
   - Add a test with a synthetic player who has three valid positions and confirm they appear as eligible for all three corresponding slot groups.
   - Add a test verifying that a player with overlapping eligibility is assigned exactly once to the optimal slot and not duplicated.

---

## Issue #82 – Harden Mixed-Source Merge Key to Avoid Name Collisions

**Problem:** Mixed-source ingestion falls back to a normalised player name when source IDs are missing. This can incorrectly merge records for different players who share similar names, corrupting merged player records and producing unreliable downstream ratings.

### Steps

1. **Audit the current merge key logic in `ingest/savant.py` and `ingest/baseball_reference.py`:**
   - Identify where name normalisation is used as the sole fallback merge key.
   - Document the exact conditions under which a name-only key is accepted.

2. **Strengthen the fallback merge key:**
   - When no source ID is available, construct a composite key from normalised name **plus** additional disambiguating fields (e.g. team abbreviation, primary role/position, roster season).
   - Ensure the composite key is computed consistently across all ingest sources so cross-source merges still succeed for legitimate same-player records.

3. **Add ambiguity detection and warnings:**
   - After merge, detect cases where two source records produce the same composite key but differ on one or more non-key fields (e.g. handedness, birth year) that suggest they may be different players.
   - Emit a structured warning (logged to `stderr` or captured in ingest metadata) for each ambiguous merge so operators can review.

4. **Update ingest metadata model:**
   - Add a `merge_warnings` list to the ingest output metadata (or `PlayerInput`) to surface ambiguous merges for downstream inspection without failing the pipeline.

5. **Add regression tests:**
   - Add a test with two synthetic source records for players with the same name but different teams and assert they produce separate `PlayerInput` records, not one merged record.
   - Add a test where the same player appears in two sources with matching composite keys and assert a clean merge with no warning.

---

## Issue #83 – Remove Unverified SSL Default in Live Refresh Command

**Problem:** The live refresh path uses unverified SSL by default, disabling certificate validation and exposing the tool to potential man-in-the-middle attacks in insecure network environments.

### Steps

1. **Locate the unverified SSL usage:**
   - Search `cli.py` and any ingest helpers for HTTP/HTTPS requests that pass `verify=False` or equivalent.
   - Identify the specific command(s) and code paths affected.

2. **Switch to verified SSL by default:**
   - Remove or replace `verify=False` with the default `verify=True` (or omit the parameter, which defaults to verified).
   - Ensure the underlying library (e.g. `requests`, `urllib3`) respects system CA certificates.

3. **Add an explicit opt-in flag for insecure SSL:**
   - Add a CLI flag (e.g. `--insecure` or `--no-verify-ssl`) that allows users to bypass certificate verification when they explicitly need it (e.g. corporate proxies with self-signed certs).
   - Log a clear warning when the insecure flag is used.

4. **Update CLI help text and documentation:**
   - Document the secure default and the opt-in insecure flag in the relevant `--help` output and in any README/docs sections covering the live refresh command.

5. **Add tests:**
   - Add a test confirming that the default code path does **not** pass `verify=False`.
   - Add a test confirming the `--insecure` flag correctly sets `verify=False` when provided.

---

## Issue #84 – Memoize Repeated Weighted Metric Calculations for Performance

**Problem:** The engine recomputes weighted metric values many times inside nested component and peer loops, creating avoidable overhead that slows both the test suite and batch rating runs.

### Steps

1. **Profile the hot paths in `engine.py`:**
   - Run `python -m pytest tests/ --durations=20` and identify which engine functions consume the most time.
   - Instrument the weighted metric computation function(s) to count call frequency per player rating run.

2. **Add per-run memoization:**
   - Introduce a per-player cache (e.g. a local dict keyed by `(metric_name, season_weights_hash)`) that stores weighted metric results.
   - On each call to the weighted metric helper, check the cache before recomputing; store the result on first computation.
   - Scope the cache to a single `rate_player` invocation so it does not leak between players.

3. **Verify output parity:**
   - After adding memoization, run the full test suite and confirm all assertions pass with identical output values.
   - Add a determinism test that rates the same player twice in one run and asserts identical output.

4. **Measure and document the improvement:**
   - Record test suite runtime before and after the change.
   - Note the improvement in a comment near the cache or in the PR description.

5. **Preserve deterministic behavior:**
   - Ensure the cache does not cause stale results if the same player object is mutated between calls (treat inputs as immutable within a rating run).

---

## Issue #85 – Align Trait-Limit Documentation with Runtime Default

**Problem:** Documentation states the default final trait limit is 3, while runtime behaviour currently defaults to 2. This inconsistency causes user confusion and incorrect expectations during validation and tuning.

### Steps

1. **Determine the canonical default:**
   - Review `smb4_player_reference.json` (`max_traits_per_player`) and `engine.py` to confirm the runtime-enforced default.
   - Decide whether the intended canonical default is 2 or 3 (favour whatever the runtime currently enforces unless there is a design reason to change it).

2. **Align documentation to the runtime default:**
   - Search all documentation files (README, docstrings, comments, `PLAN.md`) for references to the trait limit.
   - Update every reference to match the confirmed canonical default.

3. **Align runtime to documentation if needed:**
   - If the decision is to change the runtime default (e.g. from 2 to 3), update `max_traits_per_player` in `smb4_player_reference.json` and any hard-coded fallback in `engine.py`.

4. **Update tests to reflect the chosen default:**
   - Search `tests/` for assertions on the number of traits assigned.
   - Update any test that hard-codes the old value.
   - Add a test that explicitly verifies no player exceeds the canonical trait limit after a full rating run.

5. **Capture in changelog or release notes:**
   - Add a brief entry noting the alignment change so it is visible in project history.

---

## Issue #89 – Refactor the Process into 4 Layers

**Problem:** The current codebase mixes ingestion, aggregation, processing, and generation concerns together, making the system harder to test, maintain, and modify. A clear 4-layer architecture will allow each layer to be run independently, reducing runtime during development and isolating changes.

### Layers

- **Ingestion** – Collects raw data from MLB API, Baseball Savant, and Baseball Reference; outputs raw CSV files.
- **Aggregation** – Converts raw CSV data into the normalised fields and values used for ratings calculations; outputs an intermediate structured format.
- **Processing** – Converts aggregated fields into actual player ratings, traits, and personality suggestions; outputs `PlayerOutput` records.
- **Generation** – Produces readable, formatted per-player breakdowns (may be left partially incomplete for now).

### Steps

1. **Audit the existing code boundaries:**
   - Map the current flow from `cli.py` → `ingest/savant.py` / `ingest/baseball_reference.py` → `engine.py` → output.
   - Identify which code belongs to each of the four layers and note any blending of concerns.

2. **Define layer interfaces:**
   - Decide on the intermediate data format between each layer (e.g. raw CSV files after Ingestion; a structured dict or Pydantic model after Aggregation).
   - Document the expected inputs and outputs for each layer as clear Python function or class contracts.

3. **Refactor Ingestion layer:**
   - Isolate all raw-data-fetching code into a dedicated module (or confirm `ingest/savant.py` and `ingest/baseball_reference.py` already cover this).
   - Ensure this layer's output is a set of raw CSV files only; no normalisation or rating logic should live here.

4. **Refactor Aggregation layer:**
   - Extract the code that converts raw CSV columns into the composite fields and values used by the engine into a dedicated `aggregation.py` (or equivalent) module.
   - By the end of this layer, all values needed by the Processing layer should be available in a clean intermediate structure.

5. **Refactor Processing layer:**
   - Ensure `engine.py` (or a refactored equivalent) only consumes the aggregated intermediate structure and outputs `PlayerOutput` records.
   - Remove any raw-data parsing or formatting logic that remains in `engine.py`.

6. **Implement/stub Generation layer:**
   - Create a `generation.py` module (stub is acceptable) that accepts `PlayerOutput` records and produces human-readable formatted output.
   - Wire it into the CLI but leave full implementation for a later issue if needed.

7. **Expose layer-level CLI entry points:**
   - Add CLI sub-commands (e.g. `ingest`, `aggregate`, `process`, `generate`) so each layer can be triggered independently.
   - Ensure the existing `rate` and `ingest-rate` commands continue to work end-to-end by chaining all layers.

8. **Update tests:**
   - Add or update unit tests for each layer in isolation.
   - Ensure the existing end-to-end tests still pass after the refactor.
   - Add integration tests that run adjacent layer pairs to verify the intermediate format contract.
