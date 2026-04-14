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
- **#113 – Build up Generation Code** – Defined hitter/pitcher CSV output schemas; implemented CSV writer in the Generation layer producing one file per team; wired into the `generate` CLI sub-command; added tests confirming column headers and required fields for synthetic records.
- **#119 – Starters Are Still Underrated** – Added a configurable `sp_overall_bonus` (default 4.0) in `config.yaml` under `pitcher_adjustments`; loaded it in `refresh_runtime_tuning()`; modified `role_weighted_overall_numeric` to accept an optional `pitcher_role` argument and apply the bonus for SP-classified pitchers; updated both overall-computation call sites to pass the pitcher role; added tests asserting an SP rates higher than an identical RP and that a Skubal-tier ace reaches A+ (≥ 93) overall.

---

## Open Issues

### Issue #122 – Elite Hitters and Starters Are Still Too Low Rated

**Problem:** Relievers appear overrated relative to hitters and starters. The very best 1–2 players in each large position group (Hitters, Starters, Relievers) should be S-rated, with ratings scaling downward from there. Performance stats (OPS, wRC+, HR/AB, ERA, FIP, etc.) likely need more weight.

**Plan:**
1. **Intra-group percentile normalisation** – In `processing/core.py`, after computing raw composite scores, rank each player within their group (Hitters, Starters, Relievers) separately and re-map to percentiles before applying `percentile_to_rating`. This ensures each group has its own S-tier ceiling, independent of inter-group scale differences.
2. **Increase performance-stat weights** – In `config.yaml` (or `config.json`), raise the weight of real-performance composites (e.g. `wrc_plus`, `ops`, `era_minus`, `fip_minus`) relative to raw-stuff metrics. Start with +20 % on real-performance composites for hitters and starters.
3. **Reliever normalisation guard** – Ensure RP composites are not inadvertently boosted by the `sp_overall_bonus`; confirm the bonus applies only to SP role.
4. **Regression tests** – Add assertions that the top hitter in a synthetic population reaches ≥ 95 overall, and that the top starter also reaches ≥ 95, while an average reliever scores below both.

---

### Issue #123 – Pitchers with Good Raw Stuff but Poor Results Are Overrated

**Problem:** Players like Jacob Misiorowski score near the top despite weak real-world results; raw stuff (velocity, spin, movement) carries too much weight compared to actual outcome metrics.

**Plan:**
1. **Rebalance pitcher composite weights** – In `config.yaml` under `pitcher_weights` (or equivalent), reduce the weight of raw-stuff composites (`velocity`, `movement_quality`, `spin_rate`) and increase the weight of outcome composites (`era_minus`, `fip_minus`, `whip`, `k_pct`, `bb_pct`, `chase_rate`). A ratio of roughly 30 % raw stuff / 70 % outcomes for starters is the target.
2. **Minimum-sample outcome gate** – If a pitcher has fewer than a configurable `min_ip_for_outcome_weight` innings, fall back to a higher raw-stuff weighting (since outcomes are noisy). Store the threshold in `smb4_player_reference.json` or `config.yaml`.
3. **Starter vs. reliever weight profiles** – Outcome reliability differs between roles; allow separate weight profiles for SP and RP in config.
4. **Tests** – Add a test with a synthetic pitcher whose raw stuff is elite but ERA/FIP are poor; assert their overall rating does not exceed the "average" tier.

---

### Issue #124 – Pitchers Need Default Fielding Values

**Problem:** Non-two-way pitchers currently have no speed, fielding, or arm values. The game requires these slots to be filled; defaults should be 30 speed, 40 fielding, 50 arm.

**Plan:**
1. **Apply defaults in output layer** – In `processing/core.py` (or the Generation layer), after rating calculation, for any player whose `role` is `"pitcher"` (not `"two_way"`), set `speed = 30`, `fielding = 40`, and `arm = 50` if those fields are absent or zero.
2. **Store defaults in config** – Add `pitcher_default_speed`, `pitcher_default_fielding`, and `pitcher_default_arm` keys to `config.yaml` (defaulting to 30, 40, 50 respectively) so they can be tuned without code changes.
3. **Guard against overwriting real data** – Only apply defaults when the computed value is `None` or 0 (indicating no data), not when an actual fielding metric is present.
4. **Tests** – Add a unit test confirming a pitcher with no fielding data receives exactly the three default values, and a two-way pitcher does not have the defaults applied.

---

### Issue #125 – Shohei Ohtani Appears Only as a Hitter

**Problem:** Ohtani is a two-way player but currently only appears in hitter output. He should appear in the pitchers section as well, with his batting stats present.

**Plan:**
1. **Two-way player duplication in output** – In the Generation layer (`generation/`), detect players with `role == "two_way"` and emit two output records: one in the hitter file (with batting composites) and one in the pitcher file (with pitching composites + batting stats carried over).
2. **Preserve batting fields on pitcher record** – Extend the pitcher CSV/JSON schema to include a subset of batting stats (`contact`, `power`, `speed`) for two-way players, reflecting their dual value.
3. **Ingestion deduplication guard** – Ensure ingestion does not accidentally create two separate players when a two-way player appears in both Statcast batting and pitching exports. Use the existing composite merge key (player_id / name+team+season) to merge both export rows onto a single `PlayerInput` record with `role = "two_way"`.
4. **Roster selector** – Confirm `roster_selector.py` can recommend a two-way player for both a batting slot and a pitching slot simultaneously (or at minimum, for whichever slot best fits team needs).
5. **Tests** – Add a test with a synthetic two-way player fixture; assert they appear in both hitter and pitcher output sections and that their batting stats are non-zero in the pitcher record.

---

### Issue #128 – SMB4 League File Encoder/Decoder

**Problem:** Rated players need to be brought into SMB4 via the game's proprietary save format. Currently there is no tooling to write player data into that format or read it back out, making it impossible to load generated ratings directly into the game.

**Plan:**
1. **Reverse-engineer the save format** – Use any available external tools (e.g. hex editors, community-published format docs, SMB4 modding resources) to map the binary/JSON structure of an SMB4 league file. Document field offsets, data types, and encoding rules in a `SAVE_FORMAT.md` reference document.
2. **Implement the decoder** – Create `smb4_mlb_ratings/codec/decoder.py` that reads a raw SMB4 league file and returns a list of `PlayerInput`-compatible dicts (or a new `LeagueFile` model), making it easy to round-trip existing league data through the pipeline.
3. **Implement the encoder** – Create `smb4_mlb_ratings/codec/encoder.py` that accepts a list of `PlayerOutput` records (or a `LeagueFile` model) and writes a valid SMB4 league file, replacing or patching existing player slots as needed.
4. **CLI integration** – Add two new sub-commands to `cli.py`:
   - `decode <league_file> <output_json>` – decode a league file to JSON.
   - `encode <input_json> <league_file>` – encode rated players back into a league file.
5. **Config / reference data** – Store any format-version constants, field offsets, or encoding tables in `smb4_player_reference.json` or a new `codec_config.yaml` so they can be updated without code changes when the game patches.
6. **Tests** – Add round-trip tests: encode a synthetic `PlayerOutput` list to bytes, decode the bytes back, and assert field-level parity. Add a smoke test confirming the CLI sub-commands exit cleanly with a minimal fixture file.

---

## Completed Issues (continued)

- **#114 – Quick Layer-Specific Triggers** – Created `Makefile` with one target per pipeline layer (`ingest`, `aggregate`, `process`, `generate`, `rank`) plus a `run-all` target using configurable default paths; added layer-trigger documentation section to `README.md`; added `test_layer_commands_each_exit_zero_with_minimal_fixture` smoke test in `test_ingest.py`.
- **#116 – Elite Players Ratings Too Low** – Widened the upper tail of `percentile_to_rating` in `config.yaml` so the 90th percentile maps to ≥ 90 and the 95th percentile maps to ≥ 95; raised the Skubal-tier regression-test assertion from ≥ 93 to ≥ 95 (S tier); updated `test_interpolate_rating_expands_elite_percentile_band` to reflect the new curve knots.
- **#117 – Prioritize Positive Traits Over Negative Traits** – Added polarity as a secondary sort key in `trim_traits_for_output` (`traits.py`) so that positive traits beat negative ones when priority scores tie; added two regression tests confirming positive traits are kept over negative traits of equal confidence when the 2-trait cap forces a choice.
