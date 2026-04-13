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
