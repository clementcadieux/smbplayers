# Traits Guide

This guide explains trait assignment flow and which keys in `config.yaml` tune the output.

## 1. Candidate Trait Sources

Trait candidates come from:
- Explicit player metadata traits.
- Metric-driven trait rules in processing.
- Trait hints/signals in metadata.

## 2. Confidence and Priority

Each trait candidate is scored with confidence weighting, polarity bias, and chemistry contribution.

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

1. Edit trait thresholds in `config.yaml`.
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
