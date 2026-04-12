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

---

## Open Issues

## Issue #38 – Secondary Positions

**Problem:** Secondary positions don't get populated. Almost all players have the ability to play a different position. If a player has any innings at a position in their career, that position should appear as a secondary position. Players who can cover an entire position group (all OF, all IF, etc.) should have a high likelihood of receiving the *Utility* trait.

### Steps

1. **Parse positional innings from ingestion sources:**
   - In `baseball_reference.py` (and `savant.py` if applicable), parse per-position innings or games from the fielding table.
   - Store as a `positional_games: dict[str, int]` (or `dict[str, float]` for innings) optional field on `PlayerInput`, keyed by position abbreviation.

2. **Derive secondary positions in `engine.py`:**
   - After determining the primary position, iterate `positional_games` and list every other position where the player has at least a configurable minimum number of innings/games (threshold in `smb4_player_reference.json`).
   - Populate a `secondary_positions: list[str]` field on `PlayerOutput`.

3. **Implement *Utility* trait logic:**
   - Define "full group coverage" in `smb4_player_reference.json` as position group sets (e.g. `["LF","CF","RF"]` for OF, `["1B","2B","3B","SS"]` for IF).
   - If a player's combined primary + secondary positions cover an entire group, raise the probability of awarding the *Utility* trait (weight configurable in `trait_criteria`).

4. **Add optional fields to `PlayerInput` in `models.py`:**
   - Add `positional_games: Optional[dict[str, float]] = None` to preserve backward compatibility.

5. **Update tests:**
   - Confirm that a player with innings at multiple IF positions has those positions listed as secondary positions.
   - Confirm that a player covering all OF positions receives the *Utility* trait.
   - Confirm graceful handling when `positional_games` is absent.

---

## Issue #39 – Cap Volume Predictor

**Problem:** Some players with unusual situations (e.g. Cody Ponce) receive unrealistically high projected volumes. The volume predictor should be capped at sensible maximums: **250 IP** for pitchers and **700 PA** for hitters.

### Steps

1. **Add configurable caps to `smb4_player_reference.json`:**
   - In the existing `volume_projection` block (or create one), add `max_projected_pa` (e.g. `700`) and `max_projected_ip` (e.g. `250`) keys.

2. **Apply caps in `engine.py`:**
   - After computing `resolved_projected_pa` and `resolved_projected_ip`, clamp each value to its respective maximum using the values from `smb4_player_reference.json`.

3. **Update tests:**
   - Add a test where inputs would produce a raw projection above the cap and confirm the output equals the cap value.
   - Confirm that projections below the cap are unaffected.

---

## Issue #40 – Metrics Available in Baseball Savant Not Being Properly Consumed

**Problem:** Several key Statcast metrics present in Baseball Savant CSV exports are not being parsed or wired into the rating engine. Key examples: `avg_exit_velocity`, `barrel_rate`, `sprint_speed`.

### Steps

1. **Audit `savant.py` against the full Statcast CSV schema:**
   - List all columns currently parsed vs. all columns present in a representative Savant export.
   - Identify high-value gaps beyond the known examples (`avg_exit_velocity`, `barrel_rate`, `sprint_speed`).

2. **Add parsing for missing columns in `savant.py`:**
   - Use existing `_pick_number` / `_pick_string` helper patterns to read each new column.
   - Store values via `player.set_metric(...)` with the canonical metric name.

3. **Add corresponding optional fields to `PlayerInput` in `models.py`:**
   - Add `avg_exit_velocity`, `barrel_rate`, `sprint_speed`, and any other newly parsed fields as `Optional[float] = None`.

4. **Wire new metrics into rating composites in `engine.py`:**
   - `avg_exit_velocity` and `barrel_rate` → `power` composite (with weights defined in `smb4_player_reference.json`).
   - `sprint_speed` → `speed` and `baserunning` composites.
   - Add normalisation bounds for each new metric in `smb4_player_reference.json`.

5. **Update tests:**
   - Add a test fixture row with the new columns and verify they are stored correctly after ingestion.
   - Add engine tests confirming that a player with high `barrel_rate` receives a higher `power` rating.

---

## Issue #41 – Find and Consume Other Missing Fields

**Problem:** Additional fields assumed to be available from Baseball Reference or Baseball Savant are not being consumed. Key gaps: `two_strike_contact_rate`, `oaa`, `drs`, `uzr`.

### Steps

1. **Identify source columns for each missing field:**
   - `two_strike_contact_rate`: Baseball Savant plate-discipline export (`two_strike_contact_pct` or similar column).
   - `oaa` (Outs Above Average): Baseball Savant OAA leaderboard CSV.
   - `drs` (Defensive Runs Saved): Baseball Reference or FanGraphs fielding leaderboard.
   - `uzr` (Ultimate Zone Rating): FanGraphs fielding leaderboard.
   - Document expected column names and source URLs as comments in `savant.py` / `baseball_reference.py`.

2. **Add parsing in `savant.py` and/or `baseball_reference.py`:**
   - Parse each field using existing `_pick_number` helpers.
   - Route defensive metrics through `_apply_fielding_row`; route plate-discipline metrics through the batting/stats row handler.

3. **Add optional fields to `PlayerInput` in `models.py`:**
   - `two_strike_contact_rate: Optional[float] = None`
   - `oaa: Optional[float] = None` (if not already present)
   - `drs: Optional[float] = None` (if not already present)
   - `uzr: Optional[float] = None` (if not already present)

4. **Wire fields into rating composites in `engine.py`:**
   - `two_strike_contact_rate` → `contact` or *Avoid K* trait criteria.
   - `oaa`, `drs`, `uzr` → `fielding` composite weights (already partially wired; confirm they are active).
   - Add or verify normalisation bounds in `smb4_player_reference.json`.

5. **Update tests:**
   - Confirm each new field is parsed correctly from a fixture CSV row.
   - Confirm a player with high `oaa` receives a higher `fielding` rating.
   - Confirm graceful handling when columns are absent from the CSV.
