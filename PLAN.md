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
- **#58 – Perform Data Ingestion** – Ran full ingestion with real Statcast and Baseball Reference exports; validated end-to-end pipeline against a real player population; produced a baseline set of ratings; documented data gaps found and updated normalisation bounds in `smb4_player_reference.json`.
- **#72 – Players on Rehab Stints in the Minors Aren't Included** – Switched roster base from 26-man active list to 40-man roster; updated `active` flag logic in `PlayerInput` so IL and rehab players are included; confirmed `roster_selector.py` surfaces these players in recommendations; added regression tests.
- **#73 – Verify Any Traits Not Included in the Logic** – Audited all traits against available data sources; implemented logic for all feasible traits; documented partially feasible traits with proxy flags; marked infeasible traits in `smb4_player_reference.json`; added unit and smoke tests.
- **#75 – Improve Test Performance** – Profiled the test suite and identified hot paths; optimised `engine.py` constant-loading and eliminated O(n²) loops; refactored slow end-to-end tests into focused unit tests with smaller synthetic fixtures; reduced total test suite runtime significantly.
- **#80 – Fix Player Identity Collisions in Rating Post-Processing When Names Are Duplicated** – Replaced name-only identity mapping with a stable composite key (preferring `player_id`, falling back to `name+team+position+roster_season`) throughout `engine.py`; added regression tests for same-name players on different teams.
- **#81 – Use Full Secondary Positions in Roster Eligibility** – Updated `roster_selector.py` to consider all entries in `secondary_positions` when determining slot eligibility; maintained backward compatibility with the legacy `secondary_position` field; added tests for multi-position eligibility.
- **#82 – Harden Mixed-Source Merge Key to Avoid Name Collisions** – Strengthened the fallback merge key in `ingest/savant.py` and `ingest/baseball_reference.py` to use a composite of name + team + position + season; added ambiguity detection warnings; added regression tests for same-name players from different sources.
- **#83 – Remove Unverified SSL Default in Live Refresh Command** – Replaced `verify=False` with verified SSL as default in all HTTP request paths; added an explicit `--insecure` CLI flag with a clear warning; updated help text and added tests confirming secure default.
- **#84 – Memoize Repeated Weighted Metric Calculations for Performance** – Added per-player cache for weighted metric computations in `engine.py`; verified output parity against baseline; measured and documented runtime improvement; ensured deterministic behaviour.
- **#85 – Align Trait-Limit Documentation with Runtime Default** – Confirmed canonical default is 2 traits per player; updated all documentation references to match; aligned tests to assert the 2-trait cap; added changelog entry.
- **#89 – Refactor the Process into 4 Layers** – Separated codebase into Ingestion, Aggregation, Processing, and Generation layers; added layer-level CLI sub-commands (`ingest`, `aggregate`, `process`, `generate`); ensured existing `rate` and `ingest-rate` commands continue to work end-to-end; added layer-isolation tests.
- **#91 – Make Config Values Easily Viewable and Editable** – Extracted all tunable constants (season weights, season count, rating aggressiveness, trait thresholds) into a human-readable `config.json`; created `RATINGS_GUIDE.md` and `TRAITS_GUIDE.md`; updated engine to load config at startup; added config validation tests.
- **#92 – More Extreme Platoon Separation** – Defined a platoon-dependence score based on split ratios; applied a configurable base-rating penalty for heavy platoon players; confirmed platoon trait still fires correctly; added named-player test assertions; documented in `RATINGS_GUIDE.md`.
- **#94 – Boost Starting Pitcher Ratings** – Implemented role-specific percentile ranking (SPs ranked against SPs, RPs against RPs) in `engine.py` to eliminate cross-role comparison bias; added configurable starter-quality multiplier in config; added assertions confirming average SP score ≥ average RP score.
- **#95 – Elite Hitters Should Reach Extreme Rating Values** – Switched to percentile-based rating mapping with a non-linear curve for all hitting components; stored curve parameters in config; validated that the top power and contact players reach 95–99; verified no general rating inflation; updated all affected tests.
- **#100 – Platoon Traits Are Too Common** – Defined a statistically meaningful minimum split threshold (wRC+/OPS difference) below which the platoon trait is not assigned; decoupled the platoon penalty from trait assignment so balanced hitters receive neither; applied threshold gate in `engine.py` before computing the penalty; stored threshold in config; added tests for balanced, heavy-platoon, and borderline cases; updated `RATINGS_GUIDE.md`.
- **#104 – Improved Handling of HTTP Failure During Ingestion** – Tracked failed HTTP requests in an in-memory failure list during ingestion; added a single retry pass at the end of ingestion that removes players from the list on success; logged/returned persistent failures after the retry pass; added tests for failure tracking, successful retry, and persistent failure reporting.
- **#105 – Additional Traits Not Being Produced** – Implemented *Mind Gamer* (high BB%), *Easy Target* (low BB%), *Workhorse* (high-volume starter), *Stimulated* (high-leverage performance), *Dive Wizard* (high range metrics), *Butter Finger* (low range metrics), *Durable* (high % of full-volume seasons), and *Injury Prone* (low % of full-volume seasons); defined thresholds in `smb4_player_reference.json`/`config.json`; added unit tests and updated `TRAITS_GUIDE.md`.
- **#108 – Some Traits Are Too Common** – Replaced raw-value thresholds with percentile-based confidence classification (High: top 10 %, Medium: top 33 %, Low: top 50 %) for all trait-specific metrics; updated thresholds in `smb4_player_reference.json`/`config.json`; removed hard-coded raw cutoffs; added boundary tests; updated `TRAITS_GUIDE.md`.
- **#109 – Catcher Framing Runs Are Missing** – Diagnosed the data gap; expanded CSV column aliases for `framing_runs` in `savant.py`; added a Baseball Reference fallback for catchers; validated normalisation bounds in `smb4_player_reference.json`; added regression tests for both primary and fallback parse paths.

---

## Open Issues

## Issue #113 – Build up Generation Code

**Problem:** The Generation layer currently lacks a structured CSV output. Each team's players need to be exported in a well-defined format that can be directly consumed downstream.

### Steps

1. **Define output schema:**
   - *Hitters:* Name, Throw Hand, Bat Hand, Primary Position, Secondary Positions, Contact, Power, Speed, Fielding, Arm, Trait 1, Trait 2.
   - *Pitchers:* Name, Throw Hand, Bat Hand, Arsenal, Velocity, Junk, Accuracy, Trait 1, Trait 2, Contact, Power, Speed, Fielding, Arm.

2. **Implement CSV writer** in the Generation layer (`smb4_mlb_ratings/generation/`) that produces one file per team, splitting hitters and pitchers into the correct column sets.

3. **Wire into the `generate` CLI sub-command** so running `python -m smb4_mlb_ratings.cli generate <processed_data> <output_dir>` writes one CSV per team.

4. **Add tests** confirming column headers match the schema and all required fields are populated for synthetic hitter and pitcher records.

---

## Issue #114 – Quick Layer-Specific Triggers

**Problem:** Running individual pipeline layers requires memorising the full CLI invocation. A convenient shortcut mechanism is needed so each of the four layers (Ingest, Aggregate, Process, Generate) can be triggered independently with minimal typing.

### Steps

1. **Audit existing CLI sub-commands** (`ingest`, `aggregate`, `process`, `generate`) to confirm they are each independently invocable.

2. **Create trigger scripts or a `Makefile`** (one target per layer plus a `run-all` target) that wraps the full CLI invocation with sensible defaults for input/output paths.

3. **Document usage** in `README.md` (or a dedicated `RUNNING.md`) with one-line examples for each layer trigger.

4. **Add a smoke test** that invokes each trigger script/target with a minimal synthetic fixture and asserts zero exit code.

---

## Issue #116 – Elite Players Ratings Too Low

**Problem:** Elite players' overall ratings are still not extreme enough. Top-tier pitchers like Skubal should floor at A+ and very likely reach S; the current curve does not push truly elite stat lines into the highest rating bands.

### Steps

1. **Audit the percentile-to-rating curve** in `config.json` to identify where elite percentile scores are being capped below the S/A+ band.

2. **Widen the upper tail** of the non-linear rating curve so that the top 5 % of performers map to 95–99 and the top 10 % map to at least 90; store updated curve parameters in `config.json`.

3. **Add or update named-player regression tests** asserting that a Skubal-level stat line produces an overall SP rating ≥ 90 (A+) and almost certainly ≥ 95 (S).

4. **Verify no general inflation** – confirm that average-tier players do not drift above their expected mid-range bands.

---

## Issue #117 – Prioritize Positive Traits Over Negative Traits

**Problem:** When a player qualifies for both positive and negative traits and the 2-trait cap forces a tie-break, negative traits are sometimes chosen over positive ones, which unfairly punishes players.

### Steps

1. **Classify all traits** in `smb4_player_reference.json` (or `config.json`) as `positive`, `negative`, or `neutral`.

2. **Update trait selection logic** in `engine.py` so that, after scoring, positive traits are ranked above negative traits of equal confidence score before applying the 2-trait cap.

3. **Preserve the elite-pitch priority rule** – elite-pitch traits (already boosted) should still outrank ordinary positive traits.

4. **Add unit tests** for a player who qualifies for one positive and one negative trait at equal confidence, asserting only the positive trait is kept, and for a player with two positives and one negative, asserting both positives are kept.
