# Traits Guide

This guide explains trait assignment flow and which keys in `config.yaml` tune the output.

## 1. Candidate Trait Sources

Trait candidates come from:
- Explicit player metadata traits.
- Metric-driven trait rules in processing.
- Trait hints/signals in metadata.

## 2. Confidence and Priority

Each trait candidate is scored with confidence weighting, polarity bias, and chemistry contribution.

Trait confidence is percentile-based:
- `high`: top 10% of peers
- `medium`: top 33% of peers
- `low`: top 50% of peers

Anything below the top 50% gate does not receive the trait.

Config keys:
- `confidence_weights.high`
- `confidence_weights.medium`
- `confidence_weights.low`

## 3. Conflict Resolution

Conflicting trait families cannot be assigned together.
The highest-priority candidate in each conflict family wins.

Config keys:
- `trait_conflict_groups`

## 4. Final Trait Limits

After ranking and conflict filtering, the final list is capped.

Config keys:
- `trait_limits.max_traits_per_player`
- `trait_limits.max_elite_pitch_traits`
- `trait_limits.elite_pitch_traits`

## 5. Personality Recommendations

Personality ranking combines personal trait distribution and team trait distribution.

Config keys:
- `personality_weights.personal`
- `personality_weights.team`

## 6. Position Threshold Tuning

Secondary-position eligibility and utility grouping are tunable.

Config keys:
- `secondary_positions.minimum_positional_games`
- `secondary_positions.coverage_groups`
- `secondary_positions.utility_bonus_weight`

## 7. Practical Tuning Loop

1. Edit trait thresholds in `smb4_player_reference.json` (`trait_criteria`).
2. Run `rate` or `ingest-rate` with `--config-path`.
3. Inspect `suggested_traits` and `assigned_traits` changes.
4. Iterate until trait distribution matches your roster goals.

## 8. Hitter Platoon Traits

Hitter platoon traits (`CON vs LHP`, `CON vs RHP`, `POW vs LHP`, `POW vs RHP`) are gated by configurable split-difference thresholds.

Config keys:
- `platoon_adjustment.contact.eligibility_gap`
- `platoon_adjustment.power.eligibility_gap`

Behavior:
- Below the configured eligibility gap, hitter platoon traits do not get assigned.
- At or above the eligibility gap, hitter platoon traits can be assigned if their configured criteria score threshold is met.
- The same eligibility gate is used by platoon percentile penalties in rating computation, so small split differences trigger neither trait assignment nor rating suppression.
- For players above the eligibility gate, rating penalties can be amplified by split-volume imbalance (`pa_vs_lhp` vs `pa_vs_rhp`) via `split_imbalance_weight`.
- Extreme one-sided usage adds a second path: if a hitter overwhelmingly faces one handedness and clears the override sample floors, `CON` and `POW` platoon traits are forced toward the side he mostly faces, even if the ordinary split-gap path would not assign them.

Additional config keys:
- `platoon_adjustment.extreme_usage_threshold`
- `platoon_adjustment.extreme_usage_min_weighted_pa`
- `platoon_adjustment.extreme_usage_min_split_pa`
- `platoon_adjustment.extreme_usage_force_traits`

## 9. Derived Trait Metrics (Issue 105)

Several trait metrics can be automatically derived from raw metrics and samples when no explicit
value is supplied.  Derivation runs inside `apply_hitter_metadata_traits` and
`apply_pitcher_metadata_traits` (via `_derive_missing_trait_metrics`) before the criteria engine
fires.  Explicit values always win — derivation only fills missing entries.

### Mind Gamer / Easy Target  (`trait_metrics.mind_games`)

Derived from the walk rate stored in `metrics.bb_pct` (decimal, e.g. `0.105` for 10.5 %).

```
pct_points = bb_pct * 100          # e.g. 10.5
mind_games = (pct_points - 4.0) / (20.0 - 4.0) * 100   # clipped [0, 100]
```

| mind_games percentile gate | Trait assigned |
|---------------------------|----------------|
| top 50% (`>= 50`)         | Mind Gamer     |
| bottom 50% (`<= 50`)      | Easy Target    |

Constants: `_MIND_GAMES_BB_PCT_LOW = 4.0`, `_MIND_GAMES_BB_PCT_HIGH = 20.0`

### Dive Wizard / Butter Fingers  (`trait_metrics.dive_recovery`)

Derived from the average of any available metrics: `oaa`, `drs`, `uzr`.

```
avg_range = mean(oaa, drs, uzr)   # whichever are present
dive_recovery = (avg_range - (-5.0)) / (20.0 - (-5.0)) * 100   # clipped [0, 100]
```

| dive_recovery percentile gate | Trait assigned   |
|------------------------------|------------------|
| top 50% (`>= 50`)            | Dive Wizard      |
| bottom 50% (`<= 50`)         | Butter Fingers   |

Constants: `_DIVE_RECOVERY_RANGE_LOW = -5.0`, `_DIVE_RECOVERY_RANGE_HIGH = 20.0`

### Durable / Injury Prone  (`trait_metrics.durability`)

Derived from season-level PA (hitters) or IP-equivalent/BF (pitchers).

```
# Hitter
seasons = season_dict(samples.weighted_pa)
full    = count(v >= 500 for v in seasons.values())
durability = full / len(seasons) * 100

# Pitcher — defensive_innings preferred; falls back to weighted_bf / 4.25
threshold = 150.0 (IP)
```

| durability percentile gate | Trait assigned |
|---------------------------|----------------|
| top 50% (`>= 50`)         | Durable        |
| bottom 50% (`<= 50`)      | Injury Prone   |

Thresholds are read from `config.yaml` → `season_weighting.full_season_pa_threshold` (default 500) and
`full_season_ip_threshold` (default 150).

### Workhorse  (`trait_metrics.workhorse`)

Pitchers only.  Derived from `resolved_projected_ip()`.

```
workhorse = projected_ip / workhorse_benchmark_ip * 100   # clipped [0, 100]
```

| workhorse percentile gate | Trait assigned |
|--------------------------|----------------|
| top 50% (`>= 50`)        | Workhorse      |

Thresholds are tunable in `config.yaml`:
- `season_weighting.workhorse_benchmark_ip` (default 250)
- `smb4_player_reference.json` → `trait_criteria.traits.Workhorse.criteria[0].value`

### Stimulated  (`trait_metrics.late_game_hitting` / `trait_metrics.late_game_pitching`)

When `late_game_hitting` is absent, the engine falls back to `pressure_hitting` as a proxy
(and likewise `late_game_pitching` → `pressure_pitching`).  If neither is available the metric
remains absent and the trait is not awarded.
