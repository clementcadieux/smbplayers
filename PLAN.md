# SMBPlayers – Issue Resolution Plan

This document outlines the plan to resolve all four open issues in this repository.

---

## Issue #1 – Make MLB Stats Parsed Available Only on Local Machine

**Problem:** Parsed/downloaded stats (CSV exports, ingested JSON, ratings output, etc.) must never be committed to the public repo.

### Steps

1. Update `.gitignore` to exclude all common data file patterns:
   - `*.csv` – exported stat files from Baseball Savant / Baseball Reference
   - Common output directories: `exports/`, `data/`, `output/`, `ratings/`
   - Ingestion artifacts: `normalized_*.json`, `ratings_*.json`
2. Add an explanatory comment block in `.gitignore` to make the intent clear for future contributors.
3. Explicitly allow `smb4_player_reference.json` so that the reference catalog (part of the source code) is never caught by the new ignore rules.

---

## Issue #2 – Ensure Ratings Calculation Takes Into Account Both Surface Metrics and Normal Stats

**Problem:** Underlying/Sabermetric metrics should carry 50–100% of the rating weight. Surface stats fill the remainder, but their share is capped at 50%. Small samples rely entirely on underlying metrics; the largest samples reach a 50/50 blend.

### Steps

1. Add an `is_surface_stat: bool = False` flag to `ComponentSpec` to distinguish surface stats (e.g. `batting_average`, `slugging`, `strikeout_rate`) from underlying metrics (e.g. `barrel_rate`, `avg_exit_velocity`, `xwOBA`).
2. Implement a `surface_weight_factor(sample: float, threshold: float) -> float` function:
   - Returns `0.0` when `sample == 0` (underlying-only at zero volume).
   - Scales linearly up to `0.5` as `sample` approaches or exceeds the stabilization threshold.
3. In the rating computation loop in `engine.py`, split component percentiles into two pools — underlying and surface. Compute the blended component score so the surface pool's total contribution is capped by `surface_weight_factor`, and the underlying pool absorbs the remaining weight budget.
4. Tag the relevant `ComponentSpec` entries in `RATING_SPECS`:
   - **Hitters:** `batting_average`, `slugging`, `strikeout_rate`, `contact_rate`, `adjusted_obp` → surface
   - **Pitchers:** `walk_rate`, `strike_pct`, `weak_contact_rate` → surface
5. Add or extend tests to verify:
   - Small samples → only underlying metrics contribute.
   - Large samples (at or above stabilization threshold) → surface stats reach but do not exceed 50%.

---

## Issue #3 – Implement the Output Structure of the SMB4 Player Ratings

**Problem:** Output should be organized into per-team files, grouped by division and league (not a single flat file).

### MLB Team Hierarchy

Two leagues (AL / NL), each with three divisions (East / Central / West), totalling 30 teams.

### Steps

1. Define a `TEAM_DIVISIONS` mapping (team abbreviation → `(league, division)`) in a new `output.py` module.
2. Add `write_structured_output(ratings: list[RatingOutput], output_dir: Path) -> None`:
   - Groups players by team.
   - Writes one JSON file per team at `<output_dir>/<league>/<division>/<team>.json`.
   - Writes a top-level `<output_dir>/index.json` listing all teams and their file paths, organized by league and division.
3. Add a `--structured-output <dir>` flag to the `ingest-rate` CLI subcommand so users can request directory-based output instead of a single flat file.
4. Update `README.md` to document the new output directory layout.
5. Add tests confirming the correct file layout by league → division → team.

---

## Issue #4 – Implement Logic to Rank Players Based on Who Should Be Included in the Team

**Problem:** SMB4 rosters are 22 players (not 26). Players must be ranked by position, projected playing time, and age, with IL awareness. The two flex spots must be resolved from the three eligible options.

### Roster Structure

| Slot | Count |
|---|---|
| Starting Pitchers | 4 |
| Relief Pitchers | 5 |
| Infielders | 5 |
| Outfielders | 4 |
| Catchers | 2 |
| Flex (3rd C **or** 6th IF **or** 5th OF) | 2 |
| **Total** | **22** |

### Ranking Criteria

1. **Primary:** Expected 2026 innings pitched (pitchers) or plate appearances (hitters) — a proxy for projected role and playing time.
2. **Tiebreaker:** Age — younger players (top prospects) are prioritised over equally skilled older players.
3. **IL awareness:** Players on the Injured List are flagged but still ranked; they still occupy a roster spot but may be deprioritised for the 22 active slots.

### Steps

1. Add a `roster_selector.py` module containing:
   - `RosterSlot` dataclass with `position_group`, `slot_type`, and `player: RatingOutput` fields.
   - `rank_players_by_role(players: list[RatingOutput]) -> dict[str, list[RatingOutput]]`: groups players by role (SP, RP, C, IF, OF) and sorts each group by projected playing time descending, then age ascending.
   - `select_roster(players: list[RatingOutput], injured_list: set[str] | None = None) -> list[RosterSlot]`:
     - Selects top 4 SPs, 5 RPs, 5 IFs, 4 OFs, 2 Cs.
     - Evaluates all three flex combinations (3rd C / 6th IF / 5th OF) and fills the 2 remaining slots using overall rating as the deciding factor.
     - Marks IL players in the output.
2. Expose projected playing time as optional fields on `PlayerInput`:
   - `projected_pa` for hitters
   - `projected_ip` for pitchers
   - Falls back to the most-recent-season sample volume when not provided.
3. Add a `rank` CLI subcommand that accepts a ratings JSON and produces a 22-slot roster JSON.
4. Integrate the roster selector with the structured output (Issue #3) so each team file includes both the full rated-player list and the recommended 22-man roster.
5. Add tests covering:
   - Correct slot counts per position group.
   - Age tiebreaker applied correctly.
   - Flex spot resolution across all three options.
   - IL-aware ordering.

---

## Issue #20 – Players from Non-Active Roster (Other Team) Are Getting Recommended

**Problem:** Players who are no longer on a team's active 2026 roster (e.g. traded or released players like Kiner-Falefa for the Blue Jays) are still appearing in the recommended roster output. Only players on the team's current active roster should be rated and recommended.

### Steps

1. **Add a `roster_year` and `active_roster` filter to the ingestion pipeline:**
   - In the manifest schema, add an optional `roster_filter: { team: str, year: int }` field so callers can declare which team and season to restrict ingestion to.
   - In `savant.py` and `baseball_reference.py`, after parsing each player row, skip (or flag) any player whose `team` column does not match the requested `roster_filter.team` for the target `roster_filter.year`.

2. **Add an `active` flag to `PlayerInput`:**
   - Add `active: bool = True` to the `PlayerInput` dataclass in `models.py`.
   - During ingestion, set `active = False` for any player whose most-recent season (`current`) was played for a different team than the manifest's target team, rather than hard-dropping them (preserves historical data while marking them inactive).

3. **Filter inactive players before rating and roster selection:**
   - In `engine.py` (or the CLI pipeline), skip players where `player.active is False` before computing ratings.
   - In `roster_selector.py`, add a guard at the top of `select_roster` to reject any `RatingOutput` whose `team` does not match the target team abbreviation passed in (raise or warn if `team` is `None`).

4. **Expose a `--team` filter on the CLI:**
   - Add an optional `--team <ABBR>` flag to both the `rate` and `ingest-rate` subcommands in `cli.py`.
   - When provided, filter the loaded player list to only include players whose `PlayerInput.team` matches the flag value (case-insensitive) before rating.

5. **Update the integration test (`tests/test_e2e_bluejays.py`):**
   - Add a synthetic player assigned to a different team (e.g. `team="NYY"`) to the Blue Jays test dataset.
   - Assert that this player does **not** appear in the rated output or roster selection results when `--team TOR` (or equivalent programmatic filter) is applied.

6. **Update `README.md`:**
   - Document the `--team` filter flag under the CLI usage section.
   - Note that only players whose `team` field matches the target team are included in rating and roster selection.

---

## Issue #10 – Run a Full Process Test Using the Toronto Blue Jays

**Problem:** The complete pipeline (ingest → rate → structured output → roster selection) has not been validated end-to-end with real team data. Using the Toronto Blue Jays as the test team will confirm that every stage produces correct, consistent output for a real MLB roster.

### Steps

1. **Prepare sample Blue Jays data files:**
   - Export a Baseball Savant CSV (`savant_bluejays.csv`) and a Baseball Reference CSV (`bref_bluejays.csv`) covering the 2025 Blue Jays 40-man roster.
   - Create an ingestion manifest (`bluejays_manifest.json`) pointing to both CSVs, with `team: "TOR"` set for all players.
   - Store these files locally (they are covered by `.gitignore` and must not be committed).

2. **Run each pipeline stage in sequence and capture output:**
   - `ingest`: `python -m smb4_mlb_ratings.cli ingest bluejays_manifest.json /tmp/tor_normalized.json`
   - `ingest-rate` with structured output: `python -m smb4_mlb_ratings.cli ingest-rate bluejays_manifest.json /tmp/tor_ratings.json --normalized-output /tmp/tor_normalized.json --structured-output /tmp/tor_structured/`
   - `rank`: `python -m smb4_mlb_ratings.cli rank /tmp/tor_ratings.json /tmp/tor_roster.json`

3. **Validate normalized output (`tor_normalized.json`):**
   - All expected Blue Jays players are present (no silent drops during ingestion).
   - Required fields (`name`, `position`, `sample_size`, stat fields) are populated for every player.
   - No players from other teams are included.

4. **Validate ratings output (`tor_ratings.json`):**
   - Every player has an `overall` rating in the valid SMB4 range (1–99).
   - Surface-stat blending is correctly applied (underlying metrics dominate at low sample sizes).
   - Position-specific rating components match those defined in `smb4_player_reference.json`.

5. **Validate structured output directory (`tor_structured/`):**
   - Confirm the file `tor_structured/AL/East/TOR.json` exists.
   - Confirm `tor_structured/index.json` lists `TOR` under `AL → East`.
   - Confirm player data in the team file matches the flat ratings output.

6. **Validate roster selection output (`tor_roster.json`):**
   - Exactly 22 roster slots are selected.
   - Slot counts per group are correct: 4 SP, 5 RP, 5 IF, 4 OF, 2 C, 2 Flex.
   - Flex slots are filled by the best candidate among 3rd C, 6th IF, and 5th OF.
   - Players are sorted by projected playing time descending, then age ascending within each group.

7. **Add an end-to-end integration test (`tests/test_e2e_bluejays.py`):**
   - Use a minimal synthetic Blue Jays dataset (small enough to commit) that covers all position groups.
   - Run the full `ingest-rate → rank` pipeline programmatically (not via subprocess) against a temp directory.
   - Assert all validation criteria from steps 3–6 on the synthetic dataset output.
   - Mark the test with `pytest.mark.integration` so it can be run separately from unit tests.

8. **Document the manual test procedure in `README.md`:**
   - Add a "Full Pipeline Walkthrough" section with the exact CLI commands for steps 2–6 using the Blue Jays as the example team.
