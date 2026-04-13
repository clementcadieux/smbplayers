# Ratings Guide

This guide explains how ratings are produced and which keys in `config.yaml` change behavior.

## 1. Inputs and Season Blending

The engine reads per-player metrics and sample volumes, then blends season windows (`current`, `previous`, `two_years_ago`).

Config keys:
- `season_weighting.full_season_pa_threshold`
- `season_weighting.full_season_ip_threshold`
- `season_weighting.season_recency_weights.current`
- `season_weighting.season_recency_weights.previous`
- `season_weighting.season_recency_weights.two_years_ago`

Higher current-season recency weight increases responsiveness to recent performance.

## 2. Component Percentiles

Each rating component is normalized against peers to produce percentiles.
Example: `power` combines `iso`, `hr_per_pa`, `barrel_rate`, etc.

The weighted percentile is then converted to a 1-99 rating using `rating_curve.percentile_to_rating`.

Config keys:
- `rating_curve.percentile_to_rating`

## 3. Numeric Ratings to Grade Labels

Final numeric overall is mapped to a grade label by breakpoint table.

Config keys:
- `rating_curve.grade_breakpoints`

## 4. Role-Weighted Overall

Each role aggregates component ratings differently.

Config keys:
- `role_overall_weights.hitter`
- `role_overall_weights.pitcher`
- `role_overall_weights.two_way`

## 5. Confidence and Review Behavior

Confidence labels are derived from review flags and weighted during trait/personality scoring.

Config keys:
- `confidence_weights.high`
- `confidence_weights.medium`
- `confidence_weights.low`

## 6. Personality Blend

Recommended personalities blend personal trait fit with team chemistry fit.

Config keys:
- `personality_weights.personal`
- `personality_weights.team`

## 7. Editing Workflow

1. Copy `config.yaml` and edit the desired section.
2. Run ratings with default config:
   - `python -m smb4_mlb_ratings.cli rate players.json ratings.json`
3. Run ratings with alternate config:
   - `python -m smb4_mlb_ratings.cli rate players.json ratings.json --config-path my-config.yaml`
4. Compare outputs and keep changes that match your tuning goal.

## 8. Platoon Adjustment Gate

Hitter platoon splits now use a shared eligibility gate for both trait assignment and percentile penalties.

Behavior:
- If absolute split gap is below the configured `eligibility_gap`, no hitter platoon trait is assigned and no platoon percentile penalty is applied.
- If absolute split gap meets or exceeds `eligibility_gap`, trait logic and penalty logic are both eligible to run.
- For eligible hitters, penalty severity scales up when split volume is more imbalanced (`pa_vs_lhp` vs `pa_vs_rhp`) using `split_imbalance_weight`.
- Penalties still require `minimum_weighted_pa` to be met.
- Separately, extreme one-sided usage can trigger an override: if split imbalance and sample thresholds are met, the hitter receives same-side `CON` and `POW` platoon traits based on the side he mostly faces, and contact/power both take at least the configured override penalty.

Config keys:
- `platoon_adjustment.minimum_weighted_pa`
- `platoon_adjustment.extreme_usage_threshold`
- `platoon_adjustment.extreme_usage_min_weighted_pa`
- `platoon_adjustment.extreme_usage_min_split_pa`
- `platoon_adjustment.extreme_usage_force_traits`
- `platoon_adjustment.contact.eligibility_gap`
- `platoon_adjustment.power.eligibility_gap`
- `platoon_adjustment.contact.split_imbalance_weight`
- `platoon_adjustment.power.split_imbalance_weight`
- `platoon_adjustment.contact.light_gap`
- `platoon_adjustment.contact.moderate_gap`
- `platoon_adjustment.contact.heavy_gap`
- `platoon_adjustment.contact.extreme_usage_penalty_percentile`
- `platoon_adjustment.power.light_gap`
- `platoon_adjustment.power.moderate_gap`
- `platoon_adjustment.power.heavy_gap`
- `platoon_adjustment.power.extreme_usage_penalty_percentile`
