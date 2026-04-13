from __future__ import annotations

from dataclasses import dataclass
from collections import defaultdict
from statistics import mean
from typing import Mapping

from ..models import PersonalityRecommendation, PlayerInput, RatingOutput, SeasonValue, TraitSuggestion
from ..pitch_selector import select_pitch_mix
from ..reference import (
    SEASON_KEYS,
    load_processing_tuning_config,
    load_secondary_position_config,
    load_season_weighting_config,
    load_trait_catalog,
    load_trait_criteria_config,
    load_trait_limit_config,
    load_volume_projection_config,
    set_runtime_config_path,
)
from .. import traits as trait_layer


POSITION_GROUPS = {
    "C": "catcher",
    "1B": "infield",
    "2B": "infield",
    "3B": "infield",
    "SS": "infield",
    "IF": "infield",
    "LF": "outfield",
    "CF": "outfield",
    "RF": "outfield",
    "OF": "outfield",
}

PITCHER_ROLE_HINTS = {
    "sp": "SP",
    "starter": "SP",
    "starting": "SP",
    "rotation": "SP",
    "rp": "RP",
    "reliever": "RP",
    "relief": "RP",
    "bullpen": "RP",
    "closer": "RP",
    "setup": "RP",
}


GRADE_BREAKPOINTS: list[tuple[int, str]] = []
PERCENTILE_TO_RATING: list[tuple[float, int]] = []
CONFIDENCE_WEIGHTS: dict[str, float] = {}
PERSONALITY_PERSONAL_WEIGHT = 0.70
PERSONALITY_TEAM_WEIGHT = 0.30
DEFAULT_FINAL_TRAIT_LIMIT = 2
DEFAULT_MAX_ELITE_PITCH_TRAITS = 1
TRAIT_CONFLICT_GROUPS: tuple[frozenset[str], ...] = ()
ROLE_OVERALL_WEIGHTS: dict[str, dict[str, float]] = {}
PLATOON_ADJUSTMENT_CONFIG: dict[str, object] = {}
SURFACE_WEIGHT_CAPS: dict[str, float] = {}
HITTER_PLATOON_TRAIT_TO_SPEC = {
    "CON vs LHP": "contact",
    "CON vs RHP": "contact",
    "POW vs LHP": "power",
    "POW vs RHP": "power",
}
HITTER_PLATOON_TRAIT_TO_SIDE = {
    "CON vs LHP": "lhp",
    "CON vs RHP": "rhp",
    "POW vs LHP": "lhp",
    "POW vs RHP": "rhp",
}
HITTER_PLATOON_SPEC_TO_TRAITS = {
    "contact": frozenset({"CON vs LHP", "CON vs RHP"}),
    "power": frozenset({"POW vs LHP", "POW vs RHP"}),
}
HITTER_PLATOON_SIDE_METRICS = {
    "contact": {"lhp": "contact_vs_lhp", "rhp": "contact_vs_rhp"},
    "power": {"lhp": "power_vs_lhp", "rhp": "power_vs_rhp"},
}


def refresh_runtime_tuning() -> None:
    global GRADE_BREAKPOINTS
    global PERCENTILE_TO_RATING
    global CONFIDENCE_WEIGHTS
    global PERSONALITY_PERSONAL_WEIGHT
    global PERSONALITY_TEAM_WEIGHT
    global TRAIT_CONFLICT_GROUPS
    global ROLE_OVERALL_WEIGHTS
    global PLATOON_ADJUSTMENT_CONFIG
    global SURFACE_WEIGHT_CAPS

    tuning = load_processing_tuning_config()
    rating_curve = tuning.get("rating_curve", {})

    raw_percentile_to_rating = rating_curve.get("percentile_to_rating", []) if isinstance(rating_curve, Mapping) else []
    parsed_percentile_to_rating: list[tuple[float, int]] = []
    if isinstance(raw_percentile_to_rating, list):
        for row in raw_percentile_to_rating:
            if not isinstance(row, list) or len(row) != 2:
                continue
            try:
                parsed_percentile_to_rating.append((float(row[0]), int(row[1])))
            except (TypeError, ValueError):
                continue
    if not parsed_percentile_to_rating:
        parsed_percentile_to_rating = [(0.0, 5), (100.0, 99)]
    PERCENTILE_TO_RATING = sorted(parsed_percentile_to_rating, key=lambda entry: entry[0])

    raw_grade_breakpoints = rating_curve.get("grade_breakpoints", []) if isinstance(rating_curve, Mapping) else []
    parsed_grade_breakpoints: list[tuple[int, str]] = []
    if isinstance(raw_grade_breakpoints, list):
        for row in raw_grade_breakpoints:
            if not isinstance(row, list) or len(row) != 2:
                continue
            try:
                parsed_grade_breakpoints.append((int(row[0]), str(row[1])))
            except (TypeError, ValueError):
                continue
    if not parsed_grade_breakpoints:
        parsed_grade_breakpoints = [(97, "S"), (0, "D-")]
    GRADE_BREAKPOINTS = sorted(parsed_grade_breakpoints, key=lambda entry: entry[0], reverse=True)

    raw_surface_weight_caps = rating_curve.get("surface_weight_caps", {}) if isinstance(rating_curve, Mapping) else {}
    parsed_surface_weight_caps = {
        "power": 0.58,
        "contact": 0.72,
        "speed": 0.50,
        "fielding": 0.50,
        "arm": 0.50,
        "velocity": 0.50,
        "junk": 0.50,
        "accuracy": 0.50,
    }
    if isinstance(raw_surface_weight_caps, Mapping):
        for rating_name, raw_value in raw_surface_weight_caps.items():
            if not isinstance(rating_name, str):
                continue
            try:
                parsed_surface_weight_caps[rating_name] = clamp(float(raw_value), 0.0, 1.0)
            except (TypeError, ValueError):
                continue
    SURFACE_WEIGHT_CAPS = parsed_surface_weight_caps

    raw_confidence_weights = tuning.get("confidence_weights", {})
    parsed_confidence_weights: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.4}
    if isinstance(raw_confidence_weights, Mapping):
        for key in ("high", "medium", "low"):
            try:
                parsed_confidence_weights[key] = float(raw_confidence_weights.get(key, parsed_confidence_weights[key]))
            except (TypeError, ValueError):
                continue
    CONFIDENCE_WEIGHTS = parsed_confidence_weights

    raw_personality_weights = tuning.get("personality_weights", {})
    if isinstance(raw_personality_weights, Mapping):
        try:
            PERSONALITY_PERSONAL_WEIGHT = float(raw_personality_weights.get("personal", 0.70))
        except (TypeError, ValueError):
            PERSONALITY_PERSONAL_WEIGHT = 0.70
        try:
            PERSONALITY_TEAM_WEIGHT = float(raw_personality_weights.get("team", 0.30))
        except (TypeError, ValueError):
            PERSONALITY_TEAM_WEIGHT = 0.30
    else:
        PERSONALITY_PERSONAL_WEIGHT = 0.70
        PERSONALITY_TEAM_WEIGHT = 0.30

    raw_trait_conflicts = tuning.get("trait_conflict_groups", [])
    parsed_trait_conflicts: list[frozenset[str]] = []
    if isinstance(raw_trait_conflicts, list):
        for raw_group in raw_trait_conflicts:
            if not isinstance(raw_group, list):
                continue
            group_values = {
                str(item)
                for item in raw_group
                if isinstance(item, str) and str(item).strip()
            }
            if group_values:
                parsed_trait_conflicts.append(frozenset(group_values))
    TRAIT_CONFLICT_GROUPS = tuple(parsed_trait_conflicts)

    raw_role_weights = tuning.get("role_overall_weights", {})
    parsed_role_weights: dict[str, dict[str, float]] = {}
    if isinstance(raw_role_weights, Mapping):
        for role_name, raw_weights in raw_role_weights.items():
            if not isinstance(role_name, str) or not isinstance(raw_weights, Mapping):
                continue
            parsed: dict[str, float] = {}
            for rating_name, raw_value in raw_weights.items():
                if not isinstance(rating_name, str):
                    continue
                try:
                    parsed[rating_name] = float(raw_value)
                except (TypeError, ValueError):
                    continue
            if parsed:
                parsed_role_weights[role_name] = parsed
    ROLE_OVERALL_WEIGHTS = parsed_role_weights

    raw_platoon_adjustment = tuning.get("platoon_adjustment", {})
    parsed_platoon_adjustment: dict[str, object] = {
        "minimum_weighted_pa": 225.0,
        "contact": {
            "eligibility_gap": 20.0,
            "weak_side_percentile": 40.0,
            "strong_side_percentile": 60.0,
            "split_imbalance_weight": 0.35,
            "light_gap": 8.0,
            "moderate_gap": 14.0,
            "heavy_gap": 22.0,
            "light_penalty_percentile": 3.0,
            "moderate_penalty_percentile": 7.0,
            "heavy_penalty_percentile": 12.0,
            "max_penalty_percentile": 16.0,
        },
        "power": {
            "eligibility_gap": 20.0,
            "weak_side_percentile": 40.0,
            "strong_side_percentile": 60.0,
            "split_imbalance_weight": 0.35,
            "light_gap": 10.0,
            "moderate_gap": 18.0,
            "heavy_gap": 28.0,
            "light_penalty_percentile": 3.0,
            "moderate_penalty_percentile": 7.0,
            "heavy_penalty_percentile": 12.0,
            "max_penalty_percentile": 16.0,
        },
    }
    if isinstance(raw_platoon_adjustment, Mapping):
        minimum_weighted_pa = raw_platoon_adjustment.get("minimum_weighted_pa")
        try:
            if minimum_weighted_pa is not None:
                parsed_platoon_adjustment["minimum_weighted_pa"] = float(minimum_weighted_pa)
        except (TypeError, ValueError):
            pass
        for rating_name in ("contact", "power"):
            raw_rating_config = raw_platoon_adjustment.get(rating_name)
            default_rating_config = parsed_platoon_adjustment[rating_name]
            if not isinstance(raw_rating_config, Mapping) or not isinstance(default_rating_config, dict):
                continue
            merged_rating_config = dict(default_rating_config)
            for key in merged_rating_config:
                raw_value = raw_rating_config.get(key)
                try:
                    if raw_value is not None:
                        merged_rating_config[key] = float(raw_value)
                except (TypeError, ValueError):
                    continue
            parsed_platoon_adjustment[rating_name] = merged_rating_config
    PLATOON_ADJUSTMENT_CONFIG = parsed_platoon_adjustment


refresh_runtime_tuning()


CHEMISTRY_TYPES, TRAIT_CATALOG = load_trait_catalog()
VOLUME_PROJECTION_CONFIG = load_volume_projection_config()
SEASON_WEIGHTING_CONFIG = load_season_weighting_config()
TRAIT_CRITERIA_CONFIG = load_trait_criteria_config()
TRAIT_LIMIT_CONFIG = load_trait_limit_config()
SECONDARY_POSITION_CONFIG = load_secondary_position_config()


@dataclass(frozen=True)
class ComponentSpec:
    metric: str
    weight: float
    higher_is_better: bool = True
    position_groups: frozenset[str] | None = None
    is_surface_stat: bool = False


@dataclass(frozen=True)
class RatingSpec:
    name: str
    roles: frozenset[str]
    components: tuple[ComponentSpec, ...]
    sample_key: str
    stabilization_threshold: float
    review_threshold: float
    peer_mode: str
    volume_exponent: float = 1.0
    raw_tools_bias: bool = False


RATING_SPECS = (
    RatingSpec(
        name="power",
        roles=frozenset({"hitter", "two_way"}),
        sample_key="weighted_pa",
        stabilization_threshold=425,
        review_threshold=150,
        peer_mode="hitter",
        volume_exponent=0.65,
        raw_tools_bias=True,
        components=(
            ComponentSpec("iso", 0.35),
            ComponentSpec("hr_per_pa", 0.25),
            ComponentSpec("barrel_rate", 0.20),
            ComponentSpec("slugging", 0.10, is_surface_stat=True),
            ComponentSpec("avg_exit_velocity", 0.10),
        ),
    ),
    RatingSpec(
        name="contact",
        roles=frozenset({"hitter", "two_way"}),
        sample_key="weighted_pa",
        stabilization_threshold=600,
        review_threshold=150,
        peer_mode="hitter",
        components=(
            ComponentSpec("strikeout_rate", 0.35, higher_is_better=False, is_surface_stat=True),
            ComponentSpec("contact_rate", 0.25, is_surface_stat=True),
            ComponentSpec("batting_average", 0.20, is_surface_stat=True),
            ComponentSpec("adjusted_obp", 0.10, is_surface_stat=True),
            ComponentSpec("slugging", 0.10, is_surface_stat=True),
        ),
    ),
    RatingSpec(
        name="speed",
        roles=frozenset({"hitter", "two_way"}),
        sample_key="baserunning_opportunities",
        stabilization_threshold=60,
        review_threshold=25,
        peer_mode="hitter",
        volume_exponent=0.55,
        raw_tools_bias=True,
        components=(
            ComponentSpec("sprint_speed", 0.50),
            ComponentSpec("baserunning_value", 0.20),
            ComponentSpec("sb_attempt_rate", 0.15),
            ComponentSpec("sb_success_rate", 0.10),
            ComponentSpec("triple_double_rate", 0.05),
        ),
    ),
    RatingSpec(
        name="fielding",
        roles=frozenset({"hitter", "two_way"}),
        sample_key="defensive_innings",
        stabilization_threshold=500,
        review_threshold=150,
        peer_mode="position_group",
        components=(
            ComponentSpec("oaa", 0.35),
            ComponentSpec("drs", 0.22),
            ComponentSpec("uzr", 0.12),
            ComponentSpec("fielding_pct_proxy", 0.08),
            ComponentSpec("position_difficulty", 0.08),
            ComponentSpec("framing_runs", 0.15, position_groups=frozenset({"catcher"})),
        ),
    ),
    RatingSpec(
        name="arm",
        roles=frozenset({"hitter", "two_way"}),
        sample_key="defensive_innings",
        stabilization_threshold=180,
        review_threshold=80,
        peer_mode="position_group",
        volume_exponent=0.60,
        raw_tools_bias=True,
        components=(
            ComponentSpec("arm_strength", 0.35),
            ComponentSpec("catcher_throw_value", 0.18, position_groups=frozenset({"catcher"})),
            ComponentSpec("outfield_arm_runs", 0.18, position_groups=frozenset({"outfield"})),
            ComponentSpec("arm_position_baseline", 0.10),
            ComponentSpec("pop_time", 0.20, higher_is_better=False, position_groups=frozenset({"catcher"})),
        ),
    ),
    RatingSpec(
        name="velocity",
        roles=frozenset({"pitcher", "two_way"}),
        sample_key="tracked_fastballs",
        stabilization_threshold=175,
        review_threshold=80,
        peer_mode="pitcher_role",
        volume_exponent=0.50,
        raw_tools_bias=True,
        components=(
            ComponentSpec("avg_fastball_velocity", 0.70),
            ComponentSpec("peak_fastball_velocity", 0.20),
            ComponentSpec("fastball_usage", 0.10),
        ),
    ),
    RatingSpec(
        name="junk",
        roles=frozenset({"pitcher", "two_way"}),
        sample_key="tracked_pitches",
        stabilization_threshold=275,
        review_threshold=120,
        peer_mode="pitcher_role",
        volume_exponent=0.60,
        raw_tools_bias=True,
        components=(
            ComponentSpec("swinging_strike_rate", 0.25),
            ComponentSpec("chase_rate", 0.15),
            ComponentSpec("movement_quality", 0.20),
            ComponentSpec("stuff_metric", 0.20),
            ComponentSpec("arsenal_diversity", 0.10),
            ComponentSpec("weak_contact_rate", 0.10, is_surface_stat=True),
        ),
    ),
    RatingSpec(
        name="accuracy",
        roles=frozenset({"pitcher", "two_way"}),
        sample_key="weighted_bf",
        stabilization_threshold=800,
        review_threshold=250,
        peer_mode="pitcher_role",
        components=(
            ComponentSpec("walk_rate", 0.35, higher_is_better=False, is_surface_stat=True),
            ComponentSpec("strike_pct", 0.25, is_surface_stat=True),
            ComponentSpec("zone_pct", 0.15),
            ComponentSpec("first_pitch_strike_pct", 0.15),
            ComponentSpec("command_error_rate", 0.10, higher_is_better=False),
        ),
    ),
)


@dataclass
class PlayerState:
    player: PlayerInput
    samples: dict[str, float]
    position_group: str | None
    ratings: dict[str, int]
    percentiles: dict[str, float]
    component_percentiles: dict[str, dict[str, float]]
    split_percentiles: dict[str, float]
    review_flags: list[str]
    secondary_positions: list[str]


def configured_chemistry_types() -> list[str]:
    return trait_layer.configured_chemistry_types()


def trait_metadata(trait_name: str) -> dict[str, str | bool | None] | None:
    return trait_layer.trait_metadata(trait_name)


def trait_chemistry_type(trait_name: str) -> str | None:
    return trait_layer.trait_chemistry_type(trait_name)


def weighted_value(value: SeasonValue) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None

    total_weight = 0.0
    total_value = 0.0
    season_weights = SEASON_WEIGHTING_CONFIG["season_recency_weights"]
    for season_key, weight in season_weights.items():
        season_value = value.get(season_key)
        if season_value is None:
            continue
        total_weight += weight
        total_value += float(season_value) * weight

    if total_weight == 0:
        return None
    return total_value / total_weight


def current_season_value(value: SeasonValue) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, Mapping):
        return None

    for season_key in ("current", "previous", "two_years_ago"):
        season_value = value.get(season_key)
        if season_value is not None:
            return float(season_value)
    return None


def season_dict(value: SeasonValue) -> dict[str, float] | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return {"current": float(value)}
    if not isinstance(value, Mapping):
        return None

    normalized: dict[str, float] = {}
    for season_key, season_value in value.items():
        if season_value is None:
            continue
        normalized[season_key] = float(season_value)
    return normalized or None


def season_recency_weights() -> dict[str, float]:
    return dict(SEASON_WEIGHTING_CONFIG["season_recency_weights"])


def _player_metadata(player: PlayerInput | None) -> Mapping[str, object]:
    if player is None or not isinstance(player.metadata, Mapping):
        return {}
    return player.metadata


def resolve_full_season_threshold(
    sample_key: str | None,
    sample_seasons: Mapping[str, float] | None,
    *,
    player: PlayerInput | None = None,
) -> float | None:
    metadata = _player_metadata(player)
    if sample_key is not None:
        sample_specific_threshold = metadata_number(
            metadata,
            f"season_weighting.full_season_thresholds.{sample_key}",
            f"season_weighting.{sample_key}_threshold",
        )
        if sample_specific_threshold is not None and sample_specific_threshold > 0:
            return sample_specific_threshold

    if sample_key == "weighted_pa":
        threshold = metadata_number(metadata, "season_weighting.full_season_pa_threshold")
        if threshold is None:
            threshold = float(SEASON_WEIGHTING_CONFIG["full_season_pa_threshold"])
        return threshold if threshold > 0 else None

    if sample_key == "weighted_bf":
        threshold = metadata_number(
            metadata,
            "season_weighting.full_season_bf_threshold",
            "season_weighting.full_season_ip_threshold",
        )
        if threshold is None:
            threshold = float(SEASON_WEIGHTING_CONFIG["full_season_ip_threshold"])
        if threshold <= 0:
            return None
        if metadata_lookup(metadata, "season_weighting.full_season_bf_threshold") is not None:
            return threshold
        return threshold * 4.25

    if sample_seasons is None:
        return None

    available_seasons = [volume for volume in sample_seasons.values() if volume > 0]
    if not available_seasons:
        return None
    return max(available_seasons)


def season_progress(
    season_volume: float,
    *,
    sample_key: str | None,
    sample_seasons: Mapping[str, float] | None,
    player: PlayerInput | None,
    volume_exponent: float,
) -> float:
    threshold = resolve_full_season_threshold(sample_key, sample_seasons, player=player)
    if threshold is None or threshold <= 0 or season_volume <= 0:
        return 0.0
    return clamp(season_volume / threshold, 0.0, 1.0) ** volume_exponent


def metric_season_weights(
    metric_seasons: Mapping[str, float],
    sample_seasons: Mapping[str, float] | None,
    *,
    sample_key: str | None,
    player: PlayerInput | None,
    volume_exponent: float,
) -> dict[str, float]:
    weights: dict[str, float] = {}
    recency_weights = season_recency_weights()

    for season_key in metric_seasons:
        recency_weight = recency_weights.get(season_key, 0.0)
        if recency_weight <= 0:
            continue

        if sample_seasons is None:
            weights[season_key] = recency_weight
            continue

        season_volume = sample_seasons.get(season_key)
        if season_volume is None or season_volume <= 0:
            continue

        progress = season_progress(
            season_volume,
            sample_key=sample_key,
            sample_seasons=sample_seasons,
            player=player,
            volume_exponent=volume_exponent,
        )
        if progress <= 0:
            continue
        weights[season_key] = recency_weight * progress

    return weights


def prior_season_baseline(metric_seasons: Mapping[str, float]) -> float | None:
    recency_weights = season_recency_weights()
    total_weight = 0.0
    total_value = 0.0
    for season_key in ("previous", "two_years_ago"):
        metric_value = metric_seasons.get(season_key)
        recency_weight = recency_weights.get(season_key, 0.0)
        if metric_value is None or recency_weight <= 0:
            continue
        total_weight += recency_weight
        total_value += metric_value * recency_weight

    if total_weight == 0:
        return None
    return total_value / total_weight


def regress_current_season_toward_prior(
    blended_value: float,
    metric_seasons: Mapping[str, float],
    season_weights: Mapping[str, float],
    sample_seasons: Mapping[str, float] | None,
    *,
    sample_key: str | None,
    player: PlayerInput | None,
) -> float:
    current_value = metric_seasons.get("current")
    prior_baseline = prior_season_baseline(metric_seasons)
    current_weight = season_weights.get("current", 0.0)
    total_weight = sum(season_weights.values())
    if current_value is None or prior_baseline is None or current_weight <= 0 or total_weight <= 0:
        return blended_value

    if sample_seasons is None:
        return blended_value

    current_volume = sample_seasons.get("current", 0.0)
    if current_volume <= 0:
        return blended_value

    threshold = resolve_full_season_threshold(sample_key, sample_seasons, player=player)
    if threshold is None or threshold <= 0:
        return blended_value

    current_progress = clamp(current_volume / threshold, 0.0, 1.0)
    recency_weights = season_recency_weights()
    strongest_prior_weight = max(
        recency_weights.get(season_key, 0.0)
        for season_key in ("previous", "two_years_ago")
        if season_key in metric_seasons
    )
    if strongest_prior_weight <= 0:
        return blended_value

    current_full_weight = recency_weights.get("current", 0.0)
    if current_full_weight <= 0:
        return blended_value

    equivalence_progress = clamp(strongest_prior_weight / current_full_weight, 0.0, 1.0)
    if equivalence_progress == 0 or current_progress >= equivalence_progress:
        return blended_value

    regression_share = clamp((equivalence_progress - current_progress) / equivalence_progress, 0.0, 1.0)
    current_weight_share = current_weight / total_weight
    return blended_value - (current_value - prior_baseline) * current_weight_share * regression_share


def weighted_metric_value(
    metric_value: SeasonValue,
    sample_value: SeasonValue | None,
    *,
    sample_key: str | None = None,
    player: PlayerInput | None = None,
    volume_exponent: float = 1.0,
    age: int | None = None,
    raw_tools_bias: bool = False,
) -> float | None:
    if metric_value is None:
        return None
    if isinstance(metric_value, (int, float)):
        return float(metric_value)

    metric_seasons = season_dict(metric_value)
    if metric_seasons is None:
        return None

    sample_seasons = season_dict(sample_value)
    season_weights = metric_season_weights(
        metric_seasons,
        sample_seasons,
        sample_key=sample_key,
        player=player,
        volume_exponent=volume_exponent,
    )
    total_weight = sum(season_weights.values())

    if total_weight == 0:
        return None

    blended_value = sum(metric_seasons[season_key] * weight for season_key, weight in season_weights.items()) / total_weight
    blended_value = regress_current_season_toward_prior(
        blended_value,
        metric_seasons,
        season_weights,
        sample_seasons,
        sample_key=sample_key,
        player=player,
    )
    if not raw_tools_bias or age is None or not isinstance(metric_value, Mapping):
        return blended_value

    current_value = metric_seasons.get("current")
    prior_values = [
        metric_seasons[season_key]
        for season_key in ("previous", "two_years_ago")
        if season_key in metric_seasons
    ]
    if current_value is None or not prior_values:
        return blended_value

    prior_average = mean(prior_values)
    trend_delta = current_value - prior_average
    if trend_delta == 0:
        return blended_value

    current_volume = 0.0
    prior_volume = 0.0
    if sample_seasons is not None:
        current_volume = float(sample_seasons.get("current", 0.0) or 0.0)
        prior_volume = float(sum(sample_seasons.get(season_key, 0.0) or 0.0 for season_key in ("previous", "two_years_ago")))

    trend_reliability = clamp(current_volume / max(current_volume + prior_volume, 1.0), 0.15, 0.75)
    age_multiplier = raw_tools_age_multiplier(age, trend_delta)
    return blended_value + trend_delta * trend_reliability * age_multiplier


def raw_tools_age_multiplier(age: int, trend_delta: float) -> float:
    if age <= 24:
        return 1.00 if trend_delta > 0 else 0.55
    if age <= 27:
        return 0.75 if trend_delta > 0 else 0.70
    if age <= 30:
        return 0.55 if trend_delta > 0 else 0.85
    if age <= 33:
        return 0.35 if trend_delta > 0 else 1.00
    return 0.20 if trend_delta > 0 else 1.15


def infer_position_group(primary_position: str | None) -> str | None:
    if primary_position is None:
        return None
    return POSITION_GROUPS.get(primary_position.upper())


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return mean(values)


def stabilize_metric(raw_value: float, sample: float, threshold: float, league_average: float) -> float:
    reliability = clamp(sample / threshold, 0.0, 1.0)
    return league_average + reliability * (raw_value - league_average)


def surface_weight_factor(sample: float, threshold: float, cap: float = 0.5) -> float:
    if sample <= 0 or threshold <= 0:
        return 0.0
    return clamp(cap, 0.0, 1.0) * clamp(sample / threshold, 0.0, 1.0)


def blend_component_percentiles(
    component_percentiles: list[tuple[float, float, bool]],
    *,
    sample: float,
    threshold: float,
    surface_weight_cap: float = 0.5,
) -> float:
    underlying_components = [(percentile, weight) for percentile, weight, is_surface in component_percentiles if not is_surface]
    surface_components = [(percentile, weight) for percentile, weight, is_surface in component_percentiles if is_surface]

    def weighted_average(components: list[tuple[float, float]]) -> float:
        total_weight = sum(weight for _, weight in components)
        return sum(percentile * weight for percentile, weight in components) / total_weight

    if not underlying_components or not surface_components:
        return weighted_average([(percentile, weight) for percentile, weight, _ in component_percentiles])

    surface_share = surface_weight_factor(sample, threshold, cap=surface_weight_cap)
    if surface_share == 0.0:
        return weighted_average(underlying_components)

    underlying_share = 1.0 - surface_share
    underlying_score = weighted_average(underlying_components)
    surface_score = weighted_average(surface_components)
    return underlying_score * underlying_share + surface_score * surface_share


def percentile_rank(value: float, peers: list[float], higher_is_better: bool) -> float:
    if not peers:
        return 50.0

    transformed_value = value if higher_is_better else -value
    transformed_peers = [peer if higher_is_better else -peer for peer in peers]
    less_than = sum(peer < transformed_value for peer in transformed_peers)
    equal_to = sum(peer == transformed_value for peer in transformed_peers)
    return 100.0 * (less_than + 0.5 * equal_to) / len(transformed_peers)


def linear_scale(value: float, start: float, end: float, start_result: float, end_result: float) -> float:
    if end <= start:
        return end_result
    progress = clamp((value - start) / (end - start), 0.0, 1.0)
    return start_result + progress * (end_result - start_result)


def platoon_eligibility_gap(spec_name: str) -> float:
    raw_rating_config = PLATOON_ADJUSTMENT_CONFIG.get(spec_name, {})
    if not isinstance(raw_rating_config, Mapping):
        return 0.0
    raw_value = raw_rating_config.get("eligibility_gap")
    if raw_value is None:
        raw_value = raw_rating_config.get("light_gap", 0.0)
    try:
        return max(0.0, float(raw_value))
    except (TypeError, ValueError):
        return 0.0


def platoon_percentile_threshold(spec_name: str, key: str, default: float) -> float:
    raw_rating_config = PLATOON_ADJUSTMENT_CONFIG.get(spec_name, {})
    if not isinstance(raw_rating_config, Mapping):
        return default
    try:
        return clamp(float(raw_rating_config.get(key, default)), 0.0, 100.0)
    except (TypeError, ValueError):
        return default


def platoon_side_metric_name(spec_name: str, side: str) -> str | None:
    side_metrics = HITTER_PLATOON_SIDE_METRICS.get(spec_name)
    if not isinstance(side_metrics, Mapping):
        return None
    metric_name = side_metrics.get(side)
    return metric_name if isinstance(metric_name, str) else None


def opposite_platoon_side(side: str) -> str:
    return "rhp" if side == "lhp" else "lhp"


def hitter_platoon_trait_profile_matches(
    spec_name: str,
    trait_name: str,
    split_percentiles: Mapping[str, float] | None,
) -> bool:
    if not isinstance(split_percentiles, Mapping):
        return False
    favored_side = HITTER_PLATOON_TRAIT_TO_SIDE.get(trait_name)
    if favored_side is None:
        return False
    strong_metric_name = platoon_side_metric_name(spec_name, favored_side)
    weak_metric_name = platoon_side_metric_name(spec_name, opposite_platoon_side(favored_side))
    if strong_metric_name is None or weak_metric_name is None:
        return False
    strong_percentile = split_percentiles.get(strong_metric_name)
    weak_percentile = split_percentiles.get(weak_metric_name)
    if strong_percentile is None or weak_percentile is None:
        return False
    return (
        strong_percentile >= platoon_percentile_threshold(spec_name, "strong_side_percentile", 60.0)
        and weak_percentile <= platoon_percentile_threshold(spec_name, "weak_side_percentile", 40.0)
    )


def hitter_platoon_trait_eligible(state: PlayerState, trait_name: str) -> bool:
    spec_name = HITTER_PLATOON_TRAIT_TO_SPEC.get(trait_name)
    if spec_name is None:
        return True
    metric_name = "contact_vs_lhp_minus_rhp" if spec_name == "contact" else "power_vs_lhp_minus_rhp"
    gap_value = player_trait_metric(state.player, metric_name)
    if not isinstance(gap_value, (int, float)):
        return False
    if abs(float(gap_value)) < platoon_eligibility_gap(spec_name):
        return False
    return hitter_platoon_trait_profile_matches(spec_name, trait_name, state.split_percentiles)


def platoon_penalty_percentile(
    spec_name: str,
    player: PlayerInput,
    sample: float | None = None,
    *,
    split_percentiles: Mapping[str, float] | None = None,
    trait_names: set[str] | None = None,
) -> float:
    if spec_name not in {"contact", "power"}:
        return 0.0
    candidate_traits = trait_names if trait_names is not None else HITTER_PLATOON_SPEC_TO_TRAITS.get(spec_name, set())
    if not candidate_traits:
        return 0.0
    if not any(
        hitter_platoon_trait_profile_matches(spec_name, trait_name, split_percentiles)
        for trait_name in candidate_traits
    ):
        return 0.0
    raw_minimum_sample = PLATOON_ADJUSTMENT_CONFIG.get("minimum_weighted_pa", 0.0)
    try:
        minimum_sample = float(raw_minimum_sample)
    except (TypeError, ValueError):
        minimum_sample = 0.0
    effective_sample = float(sample) if sample is not None else float(weighted_value(player.samples.get("weighted_pa")) or 0.0)
    if effective_sample < minimum_sample:
        return 0.0

    metric_name = "contact_vs_lhp_minus_rhp" if spec_name == "contact" else "power_vs_lhp_minus_rhp"
    gap_value = player_trait_metric(player, metric_name)
    if gap_value is None:
        return 0.0
    severity = abs(float(gap_value))

    pa_vs_lhp = player_trait_metric(player, "pa_vs_lhp")
    pa_vs_rhp = player_trait_metric(player, "pa_vs_rhp")
    if isinstance(pa_vs_lhp, (int, float)) and isinstance(pa_vs_rhp, (int, float)):
        total_split_pa = float(pa_vs_lhp) + float(pa_vs_rhp)
        if total_split_pa > 0:
            split_imbalance = abs(float(pa_vs_lhp) - float(pa_vs_rhp)) / total_split_pa
            raw_rating_config = PLATOON_ADJUSTMENT_CONFIG.get(spec_name, {})
            if isinstance(raw_rating_config, Mapping):
                try:
                    imbalance_weight = max(0.0, float(raw_rating_config.get("split_imbalance_weight", 0.0)))
                except (TypeError, ValueError):
                    imbalance_weight = 0.0
                severity *= 1.0 + (clamp(split_imbalance, 0.0, 1.0) * imbalance_weight)

    if severity < platoon_eligibility_gap(spec_name):
        return 0.0

    raw_rating_config = PLATOON_ADJUSTMENT_CONFIG.get(spec_name, {})
    if not isinstance(raw_rating_config, Mapping):
        return 0.0
    try:
        light_gap = float(raw_rating_config.get("light_gap", 0.0))
        moderate_gap = float(raw_rating_config.get("moderate_gap", light_gap))
        heavy_gap = float(raw_rating_config.get("heavy_gap", moderate_gap))
        light_penalty = float(raw_rating_config.get("light_penalty_percentile", 0.0))
        moderate_penalty = float(raw_rating_config.get("moderate_penalty_percentile", light_penalty))
        heavy_penalty = float(raw_rating_config.get("heavy_penalty_percentile", moderate_penalty))
        max_penalty = float(raw_rating_config.get("max_penalty_percentile", heavy_penalty))
    except (TypeError, ValueError):
        return 0.0

    if severity < light_gap:
        return 0.0
    if severity < moderate_gap:
        return linear_scale(severity, light_gap, moderate_gap, light_penalty, moderate_penalty)
    if severity < heavy_gap:
        return linear_scale(severity, moderate_gap, heavy_gap, moderate_penalty, heavy_penalty)
    overflow_gap = max(heavy_gap * 1.5, heavy_gap + 1.0)
    return linear_scale(severity, heavy_gap, overflow_gap, heavy_penalty, max_penalty)


def assigned_platoon_trait_names(output: RatingOutput, spec_name: str) -> set[str]:
    spec_traits = HITTER_PLATOON_SPEC_TO_TRAITS.get(spec_name)
    if not spec_traits:
        return set()
    return {
        trait.name
        for trait in output.assigned_traits
        if trait.name in spec_traits
    }


def cache_hitter_platoon_split_percentiles(states: list[PlayerState]) -> None:
    hitter_states = [state for state in states if state.player.role in {"hitter", "two_way"}]
    if not hitter_states:
        return

    for side_metrics in HITTER_PLATOON_SIDE_METRICS.values():
        for side, metric_name in side_metrics.items():
            if side not in {"lhp", "rhp"}:
                continue
            peer_values = [
                metric_value
                for state in hitter_states
                if (metric_value := player_trait_metric(state.player, metric_name)) is not None
            ]
            if not peer_values:
                continue
            for state in hitter_states:
                metric_value = player_trait_metric(state.player, metric_name)
                if metric_value is None:
                    continue
                state.split_percentiles[metric_name] = round(
                    percentile_rank(metric_value, peer_values, higher_is_better=True),
                    2,
                )


def interpolate_rating(percentile: float) -> int:
    bounded = clamp(percentile, 0.0, 100.0)
    previous_pct, previous_rating = PERCENTILE_TO_RATING[0]
    for next_pct, next_rating in PERCENTILE_TO_RATING[1:]:
        if bounded <= next_pct:
            segment = (bounded - previous_pct) / (next_pct - previous_pct)
            rating = previous_rating + segment * (next_rating - previous_rating)
            return int(round(rating))
        previous_pct, previous_rating = next_pct, next_rating
    return PERCENTILE_TO_RATING[-1][1]


def overall_grade(value: int | None) -> str | None:
    if value is None:
        return None
    for minimum, grade in GRADE_BREAKPOINTS:
        if value >= minimum:
            return grade
    return None


def role_weighted_overall_numeric(role: str, ratings: Mapping[str, int]) -> int | None:
    if not ratings:
        return None

    role_weights = ROLE_OVERALL_WEIGHTS.get(role, {})
    weighted_total = 0.0
    total_weight = 0.0
    role_values: list[float] = []

    for rating_name, weight in role_weights.items():
        rating_value = ratings.get(rating_name)
        if rating_value is None:
            continue
        numeric_value = float(rating_value)
        weighted_total += numeric_value * weight
        total_weight += weight
        role_values.append(numeric_value)

    if total_weight > 0:
        base_overall = weighted_total / total_weight
    else:
        role_values = [float(value) for value in ratings.values()]
        base_overall = mean(role_values)

    if not role_values:
        return int(round(base_overall))

    sorted_values = sorted(role_values, reverse=True)
    top_value = sorted_values[0]
    second_value = sorted_values[1] if len(sorted_values) > 1 else sorted_values[0]
    min_value = sorted_values[-1]
    bonus = 0.0

    # Keep average players in the middle band, but stop flattening clear elite builds.
    if role == "pitcher":
        if top_value >= 94 and second_value >= 86:
            bonus += 4.0 + (top_value - 94.0) * 0.5 + max(0.0, second_value - 86.0) * 0.25
        if min_value >= 82:
            bonus += 2.0
    elif role == "hitter":
        if base_overall >= 80 and top_value >= 93 and second_value >= 88:
            bonus += 2.5
        if base_overall >= 84 and min_value >= 78:
            bonus += 1.5
    elif role == "two_way":
        if base_overall >= 82 and top_value >= 93 and second_value >= 88:
            bonus += 2.5
        if base_overall >= 86 and min_value >= 76:
            bonus += 1.0

    return int(round(clamp(base_overall + bonus, 1.0, 99.0)))


def confidence_level(flags: list[str]) -> str:
    if not flags:
        return "high"
    if len(flags) <= 2:
        return "medium"
    return "low"


def state_from_player(player: PlayerInput) -> PlayerState:
    sample_values = {
        key: value
        for key, raw_value in player.samples.items()
        if (value := weighted_value(raw_value)) is not None
    }
    return PlayerState(
        player=player,
        samples=sample_values,
        position_group=infer_position_group(player.primary_position),
        ratings={},
        percentiles={},
        component_percentiles={},
        split_percentiles={},
        review_flags=[],
        secondary_positions=derive_secondary_positions(player),
    )


def injury_shortened_seasons(player: PlayerInput) -> set[str]:
    ingest_metadata = player.metadata.get("ingest") if isinstance(player.metadata, Mapping) else None
    if not isinstance(ingest_metadata, Mapping):
        return set()
    raw = ingest_metadata.get("injury_shortened")
    if isinstance(raw, Mapping):
        return {str(season_key) for season_key, flagged in raw.items() if flagged}
    if isinstance(raw, list):
        return {str(season_key) for season_key in raw}
    return set()


def season_average_excluding_injuries(value: SeasonValue, shortened_seasons: set[str]) -> float | None:
    season_values = season_dict(value)
    if season_values is None:
        return None

    healthy_values = [season_value for season_key, season_value in season_values.items() if season_key not in shortened_seasons]
    if healthy_values:
        return mean(healthy_values)
    if season_values:
        return mean(season_values.values())
    return None


def projected_season_average(
    value: SeasonValue,
    shortened_seasons: set[str],
    *,
    days_on_roster: dict[str, float] | None = None,
    full_season_days: float | None = None,
) -> float | None:
    season_values = season_dict(value)
    if season_values is None:
        return None

    def projected_value(season_key: str, season_value: float) -> float:
        if full_season_days is None or not days_on_roster:
            return season_value
        roster_days = days_on_roster.get(season_key)
        if roster_days is None or roster_days <= 0:
            return season_value
        return season_value / roster_days * full_season_days

    healthy_values = [
        projected_value(season_key, season_value)
        for season_key, season_value in season_values.items()
        if season_key not in shortened_seasons
    ]
    if healthy_values:
        return mean(healthy_values)
    if season_values:
        return mean(projected_value(season_key, season_value) for season_key, season_value in season_values.items())
    return None


def pitcher_season_ip_dict(player: PlayerInput) -> dict[str, float] | None:
    defensive_innings = season_dict(player.samples.get("defensive_innings"))
    if defensive_innings is not None:
        return defensive_innings

    weighted_bf = season_dict(player.samples.get("weighted_bf"))
    if weighted_bf is None:
        return None
    return {season_key: round(batters_faced / 4.25, 2) for season_key, batters_faced in weighted_bf.items()}


def resolved_projected_pa(player: PlayerInput) -> float | None:
    if player.projected_pa is not None:
        projected_pa = float(player.projected_pa)
    else:
        projected_pa = projected_season_average(
        player.samples.get("weighted_pa"),
        injury_shortened_seasons(player),
        days_on_roster=player.days_on_roster,
        full_season_days=VOLUME_PROJECTION_CONFIG["full_season_days_hitter"],
        )
    if projected_pa is None:
        return None
    return min(projected_pa, VOLUME_PROJECTION_CONFIG["max_projected_pa"])


def resolved_projected_ip(player: PlayerInput) -> float | None:
    primary_position = player.primary_position.strip().upper() if isinstance(player.primary_position, str) else None
    if player.role not in {"pitcher", "two_way"}:
        return None
    if player.role == "pitcher" and primary_position != "P":
        return None

    if player.projected_ip is not None:
        projected_ip = float(player.projected_ip)
    else:
        projected_ip = projected_season_average(
        pitcher_season_ip_dict(player),
        injury_shortened_seasons(player),
        days_on_roster=player.days_on_roster,
        full_season_days=VOLUME_PROJECTION_CONFIG["full_season_days_pitcher"],
        )
    if projected_ip is None:
        return None
    return min(projected_ip, VOLUME_PROJECTION_CONFIG["max_projected_ip"])


def normalized_position(position: str | None) -> str | None:
    if not isinstance(position, str):
        return None
    candidate = position.strip().upper()
    return candidate if candidate in POSITION_GROUPS else None


def derive_secondary_positions(player: PlayerInput) -> list[str]:
    if not isinstance(player.positional_games, Mapping):
        return []

    minimum_positional_games = SECONDARY_POSITION_CONFIG["minimum_positional_games"]
    primary_position = normalized_position(player.primary_position)
    ranked_positions: list[tuple[str, float]] = []
    for position, raw_value in player.positional_games.items():
        normalized = normalized_position(position)
        if normalized is None or normalized == "P" or normalized == primary_position:
            continue
        try:
            positional_games = float(raw_value)
        except (TypeError, ValueError):
            continue
        if positional_games < minimum_positional_games:
            continue
        ranked_positions.append((normalized, positional_games))

    ranked_positions.sort(key=lambda item: (-item[1], item[0]))
    ordered_unique: list[str] = []
    seen: set[str] = set()
    for position, _ in ranked_positions:
        if position in seen:
            continue
        seen.add(position)
        ordered_unique.append(position)
    return ordered_unique


def player_positions_for_coverage(player: PlayerInput, secondary_positions: list[str]) -> set[str]:
    positions = {position for position in [normalized_position(player.primary_position), *secondary_positions] if position is not None}
    if "OF" in positions:
        positions.update({"LF", "CF", "RF"})
    if "IF" in positions:
        positions.update({"1B", "2B", "3B", "SS"})
    return positions


def utility_covered_groups(player: PlayerInput, secondary_positions: list[str]) -> list[str]:
    coverage_groups = SECONDARY_POSITION_CONFIG.get("coverage_groups", {})
    if not isinstance(coverage_groups, Mapping):
        return []
    covered_positions = player_positions_for_coverage(player, secondary_positions)
    matched_groups: list[str] = []
    for group_name, required_positions in coverage_groups.items():
        if not isinstance(group_name, str) or not isinstance(required_positions, list):
            continue
        normalized_required = {
            str(position).upper()
            for position in required_positions
            if isinstance(position, str) and str(position).strip()
        }
        if normalized_required and normalized_required.issubset(covered_positions):
            matched_groups.append(group_name)
    return sorted(matched_groups)


def trait_confidence(score: float) -> str:
    if score >= 30:
        return "high"
    if score >= 18:
        return "medium"
    return "low"


def add_trait(
    suggestions: dict[str, TraitSuggestion],
    *,
    name: str,
    polarity: str,
    score: float,
    reason: str,
) -> None:
    if score < 10:
        return
    existing = suggestions.get(name)
    suggestion = TraitSuggestion(
        name=name,
        chemistry_type=trait_chemistry_type(name),
        polarity=polarity,
        confidence=trait_confidence(score),
        reason=reason,
    )
    if existing is None:
        suggestions[name] = suggestion
        return
    rank = {"low": 1, "medium": 2, "high": 3}
    if rank[suggestion.confidence] > rank[existing.confidence]:
        suggestions[name] = suggestion


def component_percentile(state: PlayerState, rating_name: str, metric: str) -> float | None:
    return state.component_percentiles.get(rating_name, {}).get(metric)


def trait_weight(trait: TraitSuggestion) -> float:
    base_weight = CONFIDENCE_WEIGHTS.get(trait.confidence, 0.4)
    if trait.polarity == "negative":
        return base_weight * 0.95
    return base_weight


def normalize_trait_key(name: str) -> str:
    return "".join(character.lower() if character.isalnum() else "_" for character in name).strip("_")


def metadata_lookup(metadata: Mapping[str, object], dotted_key: str) -> object | None:
    current: object = metadata
    for part in dotted_key.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def metadata_number(metadata: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        value = metadata_lookup(metadata, key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def metadata_list(metadata: Mapping[str, object], *keys: str) -> list[str]:
    for key in keys:
        value = metadata_lookup(metadata, key)
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
    return []


def player_trait_metric(player: PlayerInput, metric_name: str) -> float | None:
    if isinstance(player.trait_metrics, Mapping):
        value = player.trait_metrics.get(metric_name)
        if (weighted := weighted_value(value)) is not None:
            return weighted
    return metadata_number(player.metadata, metric_name, f"trait_metrics.{metric_name}")


def player_trait_list(player: PlayerInput, list_name: str) -> list[str]:
    if isinstance(player.trait_lists, Mapping):
        values = player.trait_lists.get(list_name)
        if isinstance(values, list):
            return [str(item) for item in values if item is not None]
    return metadata_list(player.metadata, list_name, f"trait_lists.{list_name}")


def player_trait_stat(player: PlayerInput, stat_name: str) -> float | list[str] | None:
    if stat_name.startswith("trait_metrics."):
        return player_trait_metric(player, stat_name.removeprefix("trait_metrics."))
    if stat_name.startswith("trait_lists."):
        return player_trait_list(player, stat_name.removeprefix("trait_lists."))
    if stat_name.startswith("metrics."):
        return weighted_value(player.metrics.get(stat_name.removeprefix("metrics.")))
    if stat_name.startswith("samples."):
        return weighted_value(player.samples.get(stat_name.removeprefix("samples.")))
    if stat_name.startswith("metadata."):
        value = metadata_lookup(player.metadata, stat_name.removeprefix("metadata."))
        if isinstance(value, list):
            return [str(item) for item in value if item is not None]
        if isinstance(value, (int, float)):
            return float(value)
        return None
    if (metric_value := player_trait_metric(player, stat_name)) is not None:
        return metric_value
    if (metadata_value := metadata_number(player.metadata, stat_name)) is not None:
        return metadata_value
    return metadata_list(player.metadata, stat_name) or None


ELITE_PITCH_QUALITY_METRICS = frozenset(
    {
        "pitch_quality_4f",
        "pitch_quality_2f",
        "pitch_quality_cf",
        "pitch_quality_cb",
        "pitch_quality_ch",
        "pitch_quality_fk",
        "pitch_quality_sl",
        "pitch_quality_sb",
    }
)
ELITE_PITCH_PERCENTILE_MIN_PEERS = 8
ELITE_FASTBALL_TRAIT_NAMES = frozenset({"Elite 4F", "Elite 2F", "Elite CF"})


def cache_elite_pitch_quality_percentiles(states: list[PlayerState]) -> None:
    peer_values_by_metric: dict[str, list[float]] = {}
    for metric_name in ELITE_PITCH_QUALITY_METRICS:
        peers: list[float] = []
        for state in states:
            if state.player.role not in {"pitcher", "two_way"}:
                continue
            value = player_trait_metric(state.player, metric_name)
            if isinstance(value, (int, float)):
                peers.append(float(value))
        peer_values_by_metric[metric_name] = peers

    for state in states:
        if state.player.role not in {"pitcher", "two_way"}:
            continue
        percentile_values: dict[str, float] = {}
        peer_counts: dict[str, int] = {}
        mlb_percentiles = metadata_lookup(state.player.metadata, "mlb_trait_metric_percentiles")
        mlb_peer_counts = metadata_lookup(state.player.metadata, "mlb_trait_metric_percentile_peer_counts")
        if not isinstance(mlb_percentiles, Mapping):
            mlb_percentiles = metadata_lookup(state.player.metadata, "source_details.baseball_savant.mlb_trait_metric_percentiles")
        if not isinstance(mlb_peer_counts, Mapping):
            mlb_peer_counts = metadata_lookup(state.player.metadata, "source_details.baseball_savant.mlb_trait_metric_percentile_peer_counts")
        for metric_name, peers in peer_values_by_metric.items():
            if isinstance(mlb_percentiles, Mapping) and isinstance(mlb_peer_counts, Mapping):
                mlb_percentile = mlb_percentiles.get(metric_name)
                mlb_peers = mlb_peer_counts.get(metric_name)
                if isinstance(mlb_percentile, (int, float)) and isinstance(mlb_peers, (int, float)):
                    percentile_values[metric_name] = round(float(mlb_percentile), 2)
                    peer_counts[metric_name] = int(mlb_peers)
                    continue
            if not peers:
                continue
            value = player_trait_metric(state.player, metric_name)
            if not isinstance(value, (int, float)):
                continue
            peer_counts[metric_name] = len(peers)
            percentile_values[metric_name] = round(percentile_rank(float(value), peers, higher_is_better=True), 2)
        if percentile_values:
            state.player.metadata.setdefault("trait_metric_percentiles", {}).update(percentile_values)
            state.player.metadata.setdefault("trait_metric_percentile_peer_counts", {}).update(peer_counts)


def trait_scope_matches_player(role_scope: str | None, player_role: str) -> bool:
    if role_scope == "pitcher":
        return player_role in {"pitcher", "two_way"}
    if role_scope == "non_pitcher":
        return player_role in {"hitter", "two_way"}
    return True


def trait_rule_score(player: PlayerInput, rule: Mapping[str, object]) -> tuple[float, str] | None:
    stat_name = rule.get("stat")
    operator = rule.get("operator")
    weight = rule.get("weight", 1.0)
    if not isinstance(stat_name, str) or not isinstance(operator, str):
        return None
    try:
        weight_value = float(weight)
    except (TypeError, ValueError):
        return None
    stat_value = player_trait_stat(player, stat_name)
    if operator == "contains":
        if not isinstance(stat_value, list):
            return None
        target = rule.get("value")
        if target in stat_value:
            base_score = rule.get("base_score", 35.0)
            try:
                score = float(base_score) * weight_value
            except (TypeError, ValueError):
                return None
            return score, f"{stat_name} contains {target}"
        return None
    if not isinstance(stat_value, (int, float)):
        return None
    numeric_value = float(stat_value)
    target_value = rule.get("value")
    if operator == ">=":
        if stat_name.startswith("trait_metrics.pitch_quality_"):
            metric_name = stat_name.removeprefix("trait_metrics.")
            percentile_value = metadata_number(player.metadata, f"trait_metric_percentiles.{metric_name}")
            percentile_peers = metadata_number(player.metadata, f"trait_metric_percentile_peer_counts.{metric_name}")
            if percentile_value is not None and percentile_peers is not None and percentile_peers >= ELITE_PITCH_PERCENTILE_MIN_PEERS:
                if not isinstance(target_value, (int, float)) or percentile_value < float(target_value):
                    return None
                score = (percentile_value - float(target_value) + 10.0) * weight_value
                # Elite pitch traits need to compete with high-confidence pitcher traits after final trimming.
                score += 20.0 * weight_value
                return score, f"{metric_name} percentile {percentile_value:.2f} >= {target_value}"
        if not isinstance(target_value, (int, float)) or numeric_value < float(target_value):
            return None
        score = (numeric_value - float(target_value) + 10.0) * weight_value
        if stat_name.startswith("trait_metrics.pitch_quality_"):
            # Elite pitch traits need to compete with high-confidence pitcher traits after final trimming.
            score += 20.0 * weight_value
        return score, f"{stat_name} >= {target_value}"
    if operator == "<=":
        if not isinstance(target_value, (int, float)) or numeric_value > float(target_value):
            return None
        score = (float(target_value) - numeric_value + 10.0) * weight_value
        return score, f"{stat_name} <= {target_value}"
    if operator == "between":
        if not isinstance(target_value, list) or len(target_value) != 2:
            return None
        low, high = target_value
        if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
            return None
        low_value = float(low)
        high_value = float(high)
        if numeric_value < low_value or numeric_value > high_value:
            return None
        score = (10.0 + min(numeric_value - low_value, high_value - numeric_value)) * weight_value
        return score, f"{low_value} <= {stat_name} <= {high_value}"
    return None


def apply_configured_trait_criteria(
    state: PlayerState,
    suggestions: dict[str, TraitSuggestion],
    *,
    role_scope: str,
) -> None:
    traits = TRAIT_CRITERIA_CONFIG.get("traits", {})
    if not isinstance(traits, Mapping):
        return
    default_minimum = TRAIT_CRITERIA_CONFIG.get("minimum_score", 10.0)
    for trait_name, payload in traits.items():
        if not isinstance(trait_name, str) or not isinstance(payload, Mapping):
            continue
        metadata = trait_metadata(trait_name)
        if metadata is None:
            continue
        configured_scope = payload.get("role_scope", metadata.get("role_scope"))
        if configured_scope not in {role_scope, "all"}:
            continue
        if not trait_scope_matches_player(str(configured_scope), state.player.role):
            continue
        criteria = payload.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            continue
        minimum_score = payload.get("minimum_score", default_minimum)
        try:
            minimum_value = float(minimum_score)
        except (TypeError, ValueError):
            minimum_value = 10.0
        total_score = 0.0
        matched_rules: list[str] = []
        for rule in criteria:
            if not isinstance(rule, Mapping):
                continue
            result = trait_rule_score(state.player, rule)
            if result is None:
                continue
            score, summary = result
            total_score += score
            matched_rules.append(summary)
        if total_score < minimum_value:
            continue
        if role_scope == "non_pitcher" and not hitter_platoon_trait_eligible(state, trait_name):
            continue
        reason = payload.get("description")
        if not isinstance(reason, str) or not reason:
            reason = f"Configured trait criteria matched: {', '.join(matched_rules)}."
        elif matched_rules:
            reason = f"{reason} Matched criteria: {', '.join(matched_rules)}."
        add_catalog_trait(suggestions, name=trait_name, score=total_score, reason=reason)


def catalog_trait_polarity(trait_name: str) -> str:
    metadata = trait_metadata(trait_name)
    polarity = metadata.get("polarity") if metadata else None
    return str(polarity or "unknown")


def add_catalog_trait(
    suggestions: dict[str, TraitSuggestion],
    *,
    name: str,
    score: float,
    reason: str,
) -> None:
    if name not in TRAIT_CATALOG:
        return
    add_trait(
        suggestions,
        name=name,
        polarity=catalog_trait_polarity(name),
        score=score,
        reason=reason,
    )


def add_signal_pair(
    suggestions: dict[str, TraitSuggestion],
    *,
    positive_trait: str,
    negative_trait: str,
    signal: float | None,
    positive_reason: str,
    negative_reason: str,
    high_threshold: float = 65.0,
    low_threshold: float = 35.0,
) -> None:
    if signal is None:
        return
    if signal >= high_threshold:
        add_catalog_trait(
            suggestions,
            name=positive_trait,
            score=signal - (high_threshold - 10),
            reason=positive_reason,
        )
    elif signal <= low_threshold:
        add_catalog_trait(
            suggestions,
            name=negative_trait,
            score=(low_threshold + 10) - signal,
            reason=negative_reason,
        )


def explicit_player_traits(player: PlayerInput) -> list[TraitSuggestion]:
    return trait_layer.explicit_player_traits(player)


def hinted_catalog_traits(player: PlayerInput) -> list[TraitSuggestion]:
    return trait_layer.hinted_catalog_traits(player)


def apply_hitter_metadata_traits(state: PlayerState, suggestions: dict[str, TraitSuggestion]) -> None:
    apply_configured_trait_criteria(state, suggestions, role_scope="non_pitcher")


def apply_pitcher_metadata_traits(state: PlayerState, suggestions: dict[str, TraitSuggestion]) -> None:
    apply_configured_trait_criteria(state, suggestions, role_scope="pitcher")
    two_way_positions = set(player_trait_list(state.player, "secondary_field_positions"))
    two_way_positions.update(player_trait_list(state.player, "two_way_positions"))
    for position_group, trait_name in (("C", "Two Way (C)"), ("IF", "Two Way (IF)"), ("OF", "Two Way (OF)")):
        if position_group in two_way_positions:
            add_catalog_trait(
                suggestions,
                name=trait_name,
                score=35,
                reason=f"Two-way defensive usage at {position_group} supports the {trait_name} trait.",
            )


def all_player_traits(output: RatingOutput, player: PlayerInput) -> list[TraitSuggestion]:
    return trait_layer.all_player_traits(output, player)


def explicit_trait_names(player: PlayerInput) -> set[str]:
    return trait_layer.explicit_trait_names(player)


def trait_conflicts(existing_names: set[str], candidate_name: str) -> bool:
    return trait_layer.trait_conflicts(existing_names, candidate_name)


def final_trait_limit(player: PlayerInput, explicit_count: int) -> int:
    return trait_layer.final_trait_limit(player, explicit_count)


def elite_pitch_trait_names() -> set[str]:
    return trait_layer.elite_pitch_trait_names()


def top_personality_scores(output: RatingOutput) -> dict[str, float]:
    return trait_layer.top_personality_scores(output)


def final_trait_priority(
    trait: TraitSuggestion,
    *,
    explicit_names: set[str],
    personality_scores: dict[str, float],
    player_role: str,
    elite_trait_names: set[str],
) -> float:
    return trait_layer.final_trait_priority(
        trait,
        explicit_names=explicit_names,
        personality_scores=personality_scores,
        player_role=player_role,
        elite_trait_names_set=elite_trait_names,
    )


def trim_traits_for_output(output: RatingOutput, player: PlayerInput) -> list[TraitSuggestion]:
    return trait_layer.trim_traits_for_output(output, player)


def chemistry_scores_from_traits(traits: list[TraitSuggestion]) -> dict[str, float]:
    return trait_layer.chemistry_scores_from_traits(traits)


def normalized_scores(scores: dict[str, float]) -> dict[str, float]:
    return trait_layer.normalized_scores(scores)


def _normalized_identity_value(value: str | None) -> str:
    return value and " ".join(value.strip().lower().split()) if isinstance(value, str) else ""


def _player_identity_key(player: PlayerInput) -> str:
    return trait_layer.player_identity_key(player)


def _output_identity_key(output: RatingOutput) -> str:
    return trait_layer.output_identity_key(output)


def team_trait_scores(outputs: list[RatingOutput], players_by_identity: dict[str, PlayerInput]) -> dict[str, dict[str, float]]:
    return trait_layer.team_trait_scores(outputs, players_by_identity)


def personality_reason(
    chemistry_type: str,
    personal_share: float,
    team_share: float,
    player_traits: list[TraitSuggestion],
    team_scores: dict[str, float],
) -> str:
    return trait_layer.personality_reason(
        chemistry_type,
        personal_share,
        team_share,
        player_traits,
        team_scores,
    )


def recommend_personalities_for_output(
    output: RatingOutput,
    player: PlayerInput,
    team_scores: dict[str, float],
) -> list[PersonalityRecommendation]:
    return trait_layer.recommend_personalities_for_output(output, player, team_scores)


def suggest_traits(state: PlayerState) -> list[TraitSuggestion]:
    suggestions: dict[str, TraitSuggestion] = {}
    derived_secondary_positions = state.secondary_positions

    if state.player.role in {"hitter", "two_way"}:
        contact_pct = state.percentiles.get("contact")
        power_pct = state.percentiles.get("power")
        speed_pct = state.percentiles.get("speed")
        fielding_pct = state.percentiles.get("fielding")
        arm_pct = state.percentiles.get("arm")

        strikeout_pct = component_percentile(state, "contact", "strikeout_rate")
        contact_rate_pct = component_percentile(state, "contact", "contact_rate")
        batting_average_pct = component_percentile(state, "contact", "batting_average")
        sprint_pct = component_percentile(state, "speed", "sprint_speed")
        baserunning_pct = component_percentile(state, "speed", "baserunning_value")
        attempt_pct = component_percentile(state, "speed", "sb_attempt_rate")
        success_pct = component_percentile(state, "speed", "sb_success_rate")
        arm_strength_pct = component_percentile(state, "arm", "arm_strength")
        oaa_pct = component_percentile(state, "fielding", "oaa")
        fielding_proxy_pct = component_percentile(state, "fielding", "fielding_pct_proxy")

        contact_bridge_signal = max(
            value
            for value in (
                contact_pct,
                contact_rate_pct,
                batting_average_pct,
            )
            if value is not None
        ) if any(value is not None for value in (contact_pct, contact_rate_pct, batting_average_pct)) else None
        contact_bridge_gap = None
        if contact_bridge_signal is not None and strikeout_pct is not None:
            contact_bridge_gap = contact_bridge_signal - strikeout_pct
        if strikeout_pct is not None and contact_bridge_signal is not None and strikeout_pct <= 40 and contact_bridge_gap is not None and contact_bridge_gap >= 18:
            score = contact_bridge_gap * 0.85 + max((contact_pct or 0) - 42, 0) * 0.15
            add_trait(
                suggestions,
                name="Whiffer",
                polarity="negative",
                score=score,
                reason="The bat still carries playable contact indicators, but strikeout rate is a clear negative outlier within the contact profile.",
            )
        if (
            strikeout_pct is not None
            and contact_rate_pct is not None
            and batting_average_pct is not None
            and strikeout_pct >= 72
            and contact_rate_pct <= 60
            and batting_average_pct <= 60
            and (contact_pct is None or contact_pct <= 70)
        ):
            add_trait(
                suggestions,
                name="Tough Out",
                polarity="positive",
                score=(strikeout_pct - 62) + max(60 - max(contact_rate_pct, batting_average_pct), 0) * 0.25,
                reason="Strikeout avoidance is a clear strength even though the broader contact profile is only middling.",
            )
        if contact_rate_pct is not None and batting_average_pct is not None and max(contact_rate_pct, batting_average_pct) >= 75:
            score = max(contact_rate_pct, batting_average_pct) - 55
            add_trait(
                suggestions,
                name="Bad Ball Hitter",
                polarity="positive",
                score=score,
                reason="Ball-in-play and contact quality traits stand out even when the total contact blend is smoothed.",
            )

        if sprint_pct is not None and sprint_pct >= 82:
            add_trait(
                suggestions,
                name="Sprinter",
                polarity="positive",
                score=sprint_pct - 52,
                reason="Raw sprint speed is an outlier tool and should remain visible beyond the blended speed rating.",
            )
        if attempt_pct is not None and success_pct is not None and attempt_pct >= 70 and success_pct >= 65:
            add_trait(
                suggestions,
                name="Stealer",
                polarity="positive",
                score=((attempt_pct + success_pct) / 2) - 48,
                reason="Steal aggression and success indicate a base-stealing trait beyond raw speed alone.",
            )
        if baserunning_pct is not None and baserunning_pct >= 65 and (speed_pct or 0) >= 55:
            add_trait(
                suggestions,
                name="Base Rounder",
                polarity="positive",
                score=(baserunning_pct - 55) + max((speed_pct or 0) - 60, 0) * 0.25,
                reason="Baserunning value and speed percentile both support an above-average base-rounding profile.",
            )
        if sprint_pct is not None and sprint_pct <= 22:
            add_trait(
                suggestions,
                name="Slow Poke",
                polarity="negative",
                score=42 - sprint_pct,
                reason="Raw sprint speed is poor enough to deserve a negative running trait.",
            )
        if baserunning_pct is not None and baserunning_pct <= 25 and (speed_pct or 0) <= 45:
            add_trait(
                suggestions,
                name="Base Jogger",
                polarity="negative",
                score=45 - baserunning_pct,
                reason="Baserunning impact lags badly and reinforces a weak functional speed profile.",
            )
        if attempt_pct is not None and success_pct is not None and attempt_pct >= 55 and success_pct <= 30:
            add_trait(
                suggestions,
                name="Bad Jumps",
                polarity="negative",
                score=(attempt_pct - success_pct) * 0.6,
                reason="The player runs enough to test defenses but converts steals too poorly to avoid a negative baserunning trait.",
            )

        if arm_strength_pct is not None and arm_strength_pct >= 80:
            add_trait(
                suggestions,
                name="Cannon Arm",
                polarity="positive",
                score=arm_strength_pct - 50,
                reason="Throwing strength is an outlier raw tool and should remain visible even if the full arm rating is moderated.",
            )
        if arm_strength_pct is not None and arm_strength_pct <= 22:
            add_trait(
                suggestions,
                name="Noodle Arm",
                polarity="negative",
                score=42 - arm_strength_pct,
                reason="Throwing strength is weak enough to warrant a negative arm trait.",
            )
        if arm_strength_pct is not None and fielding_pct is not None and arm_strength_pct >= 75 and fielding_pct <= 35:
            add_trait(
                suggestions,
                name="Wild Thrower",
                polarity="negative",
                score=(arm_strength_pct - fielding_pct) * 0.5,
                reason="Big arm strength paired with shaky defensive execution suggests a volatile throwing profile.",
            )

        if oaa_pct is not None and fielding_proxy_pct is not None and min(oaa_pct, fielding_proxy_pct) >= 72:
            add_trait(
                suggestions,
                name="Magic Hands",
                polarity="positive",
                score=min(oaa_pct, fielding_proxy_pct) - 42,
                reason="Range and conversion reliability both support an above-rating defensive hands trait.",
            )
        if fielding_proxy_pct is not None and fielding_proxy_pct <= 25:
            add_trait(
                suggestions,
                name="Butter Fingers",
                polarity="negative",
                score=45 - fielding_proxy_pct,
                reason="Handling reliability is poor enough to require a negative fielding trait.",
            )
        covered_groups = utility_covered_groups(state.player, derived_secondary_positions)
        if covered_groups:
            utility_config = TRAIT_CRITERIA_CONFIG.get("traits", {}).get("Utility", {})
            utility_weight = SECONDARY_POSITION_CONFIG["utility_bonus_weight"]
            if isinstance(utility_config, Mapping):
                configured_weight = utility_config.get("coverage_bonus_weight")
                try:
                    utility_weight = float(configured_weight)
                except (TypeError, ValueError):
                    utility_weight = SECONDARY_POSITION_CONFIG["utility_bonus_weight"]
            base_score = max((fielding_pct or 55) - 35, 10)
            utility_score = base_score + len(covered_groups) * (20.0 * utility_weight)
            add_trait(
                suggestions,
                name="Utility",
                polarity="positive",
                score=utility_score,
                reason=f"Defensive usage covers full position groups ({', '.join(covered_groups)}), boosting utility profile confidence.",
            )

        if power_pct is not None and contact_pct is not None and power_pct >= 75 and contact_pct <= 40:
            add_trait(
                suggestions,
                name="Big Hack",
                polarity="positive",
                score=(power_pct - contact_pct) * 0.45,
                reason="Power materially outpaces contact, which fits a power-over-contact offensive trait.",
            )
        if power_pct is not None and contact_pct is not None and contact_pct >= 75 and power_pct <= 42:
            add_trait(
                suggestions,
                name="Little Hack",
                polarity="positive",
                score=(contact_pct - power_pct) * 0.40,
                reason="Contact materially outpaces power, preserving a bat-control identity beyond the aggregate profile.",
            )

    if state.player.role in {"pitcher", "two_way"}:
        junk_pct = state.percentiles.get("junk")
        accuracy_pct = state.percentiles.get("accuracy")
        velocity_pct = state.percentiles.get("velocity")

        whiff_pct = component_percentile(state, "junk", "swinging_strike_rate")
        chase_pct = component_percentile(state, "junk", "chase_rate")
        first_pitch_pct = component_percentile(state, "accuracy", "first_pitch_strike_pct")
        walk_pct = component_percentile(state, "accuracy", "walk_rate")
        fastball_pct = component_percentile(state, "velocity", "avg_fastball_velocity")

        if junk_pct is not None and whiff_pct is not None and whiff_pct >= 78:
            add_trait(
                suggestions,
                name="K Collector",
                polarity="positive",
                score=max(whiff_pct, chase_pct or 0) - 48,
                reason="Swing-and-miss ability is strong enough to deserve a strikeout trait on top of the base junk rating.",
            )
        if junk_pct is not None and whiff_pct is not None and junk_pct >= 50 and whiff_pct <= 30:
            add_trait(
                suggestions,
                name="K Neglecter",
                polarity="negative",
                score=(junk_pct - whiff_pct) * 0.6,
                reason="The overall stuff blend holds up, but the strikeout component lags enough to deserve a negative trait.",
            )
        if accuracy_pct is not None and first_pitch_pct is not None and first_pitch_pct >= 78:
            add_trait(
                suggestions,
                name="Gets Ahead",
                polarity="positive",
                score=first_pitch_pct - 50,
                reason="First-pitch strike ability is a distinct strength beyond the full accuracy blend.",
            )
        if accuracy_pct is not None and walk_pct is not None and walk_pct >= 78:
            add_trait(
                suggestions,
                name="Composed",
                polarity="positive",
                score=walk_pct - 48,
                reason="Walk suppression remains strong enough to warrant a count-control accuracy trait.",
            )
        if (
            player_trait_metric(state.player, "pitch_quality_4f") is None
            and velocity_pct is not None
            and fastball_pct is not None
            and velocity_pct >= 85
            and fastball_pct >= 92
        ):
            repertoire = set(state.player.metadata.get("pitch_repertoire_codes", []))
            if "4F" in repertoire:
                add_trait(
                    suggestions,
                    name="Elite 4F",
                    polarity="positive",
                    score=fastball_pct - 65,
                    reason="Fallback heuristic: fastball velocity is an elite carrying tool and the repertoire includes a four-seamer.",
                )

    if state.player.role in {"hitter", "two_way"}:
        apply_hitter_metadata_traits(state, suggestions)
    if state.player.role in {"pitcher", "two_way"}:
        apply_pitcher_metadata_traits(state, suggestions)
    for trait in hinted_catalog_traits(state.player):
        suggestions[trait.name] = trait

    ordered = sorted(
        suggestions.values(),
        key=lambda trait: ({"high": 3, "medium": 2, "low": 1}[trait.confidence], trait.name),
        reverse=True,
    )
    return ordered


def player_matches_spec(state: PlayerState, spec: RatingSpec) -> bool:
    if state.player.role not in spec.roles:
        return False
    if spec.name in {"fielding", "arm"} and state.position_group is None:
        return False
    return True


def component_applies_to_state(component: ComponentSpec, state: PlayerState) -> bool:
    if component.position_groups is None:
        return True
    return state.position_group in component.position_groups


def pitcher_role_bucket_for_state(state: PlayerState) -> str | None:
    if state.player.role not in {"pitcher", "two_way"}:
        return None

    metadata = state.player.metadata if isinstance(state.player.metadata, Mapping) else {}
    for key in ("pitching_role", "projected_role", "roster_role", "depth_chart_role"):
        value = metadata.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.lower()
        for hint, bucket in PITCHER_ROLE_HINTS.items():
            if hint in normalized:
                return bucket

    if state.player.projected_ip is not None:
        return "SP" if state.player.projected_ip >= 80 else "RP"

    weighted_bf = state.samples.get("weighted_bf")
    if weighted_bf is not None:
        return "SP" if (weighted_bf / 4.25) >= 80 else "RP"

    if state.player.role == "pitcher":
        return "RP"
    return None


def build_peer_state_index(states: list[PlayerState]) -> dict[str, dict[str | None, list[PlayerState]]]:
    indexed: dict[str, dict[str | None, list[PlayerState]]] = {}
    for spec in RATING_SPECS:
        eligible = [state for state in states if player_matches_spec(state, spec)]
        if spec.peer_mode == "position_group":
            grouped: dict[str | None, list[PlayerState]] = defaultdict(list)
            for state in eligible:
                grouped[state.position_group].append(state)
            indexed[spec.name] = dict(grouped)
        elif spec.peer_mode == "pitcher_role":
            grouped = defaultdict(list)
            grouped[None] = list(eligible)
            for state in eligible:
                role_bucket = pitcher_role_bucket_for_state(state)
                if role_bucket is None:
                    continue
                grouped[role_bucket].append(state)
            indexed[spec.name] = dict(grouped)
        else:
            indexed[spec.name] = {None: eligible}
    return indexed


def peer_states_for_component(
    peer_state_index: dict[str, dict[str | None, list[PlayerState]]],
    spec: RatingSpec,
    target_state: PlayerState,
) -> list[PlayerState]:
    eligible_by_group = peer_state_index.get(spec.name, {})
    if spec.peer_mode == "position_group":
        return eligible_by_group.get(target_state.position_group, [])
    if spec.peer_mode == "pitcher_role":
        role_bucket = pitcher_role_bucket_for_state(target_state)
        if role_bucket is not None and eligible_by_group.get(role_bucket):
            return eligible_by_group[role_bucket]
        return eligible_by_group.get(None, [])
    return eligible_by_group.get(None, [])


def apply_review_flags(state: PlayerState, spec: RatingSpec, available_weight: float, missing_components: list[str]) -> None:
    sample = state.samples.get(spec.sample_key, 0.0)
    if sample < spec.review_threshold:
        state.review_flags.append(f"{spec.name}: sample below review threshold ({sample:.1f} < {spec.review_threshold})")
    if missing_components:
        missing_text = ", ".join(sorted(missing_components))
        state.review_flags.append(f"{spec.name}: missing metrics [{missing_text}]")
    if available_weight < 0.6:
        state.review_flags.append(f"{spec.name}: low component coverage ({available_weight:.2f})")


def _rate_players_core(
    players: list[PlayerInput | dict],
    trim_final_traits: bool = True,
    config_path: str | None = None,
) -> list[RatingOutput]:
    set_runtime_config_path(config_path)
    refresh_runtime_tuning()
    trait_layer.refresh_runtime_tuning()
    player_objects = [player if isinstance(player, PlayerInput) else PlayerInput.from_dict(player) for player in players]
    player_objects = [player for player in player_objects if player.active]
    players_by_identity = {_player_identity_key(player): player for player in player_objects}
    states = [state_from_player(player) for player in player_objects]
    states_by_identity = {_player_identity_key(state.player): state for state in states}
    cache_hitter_platoon_split_percentiles(states)
    peer_state_index = build_peer_state_index(states)
    weighted_metric_cache: dict[tuple[int, str, str | None, float, bool], float | None] = {}

    def cached_weighted_metric_value(player: PlayerInput, metric_name: str, spec: RatingSpec) -> float | None:
        # Cache weighted metric calculations for this rate_players invocation.
        cache_key = (id(player), metric_name, spec.sample_key, spec.volume_exponent, spec.raw_tools_bias)
        if cache_key in weighted_metric_cache:
            return weighted_metric_cache[cache_key]
        value = weighted_metric_value(
            player.metrics.get(metric_name),
            player.samples.get(spec.sample_key),
            sample_key=spec.sample_key,
            player=player,
            volume_exponent=spec.volume_exponent,
            age=player.age,
            raw_tools_bias=spec.raw_tools_bias,
        )
        weighted_metric_cache[cache_key] = value
        return value

    for spec in RATING_SPECS:
        eligible_states = [state for state in states if player_matches_spec(state, spec)]
        if not eligible_states:
            continue

        for state in eligible_states:
            component_percentiles: list[tuple[float, float, bool]] = []
            missing_components: list[str] = []

            for component in spec.components:
                if not component_applies_to_state(component, state):
                    continue

                raw_value = cached_weighted_metric_value(state.player, component.metric, spec)
                if raw_value is None:
                    missing_components.append(component.metric)
                    continue

                peers = peer_states_for_component(peer_state_index, spec, state)
                peer_values = [
                    cached_weighted_metric_value(peer.player, component.metric, spec)
                    for peer in peers
                    if component_applies_to_state(component, peer)
                ]
                peer_values = [peer_value for peer_value in peer_values if peer_value is not None]
                league_average = mean_or_none(peer_values)
                if league_average is None:
                    missing_components.append(component.metric)
                    continue

                stabilized_value = stabilize_metric(
                    raw_value=raw_value,
                    sample=state.samples.get(spec.sample_key, 0.0),
                    threshold=spec.stabilization_threshold,
                    league_average=league_average,
                )
                stabilized_peers = [
                    stabilize_metric(
                        raw_value=peer_value,
                        sample=peer.samples.get(spec.sample_key, 0.0),
                        threshold=spec.stabilization_threshold,
                        league_average=league_average,
                    )
                    for peer, peer_value in (
                        (
                            peer,
                            cached_weighted_metric_value(peer.player, component.metric, spec),
                        )
                        for peer in peers
                    )
                    if component_applies_to_state(component, peer) and peer_value is not None
                ]

                percentile = percentile_rank(
                    value=stabilized_value,
                    peers=stabilized_peers,
                    higher_is_better=component.higher_is_better,
                )
                state.component_percentiles.setdefault(spec.name, {})[component.metric] = round(percentile, 2)
                component_percentiles.append((percentile, component.weight, component.is_surface_stat))

            available_weight = sum(weight for _, weight, _ in component_percentiles)
            if available_weight == 0:
                apply_review_flags(
                    state,
                    spec,
                    available_weight,
                    [component.metric for component in spec.components if component_applies_to_state(component, state)],
                )
                continue

            combined_percentile = blend_component_percentiles(
                component_percentiles,
                sample=state.samples.get(spec.sample_key, 0.0),
                threshold=spec.stabilization_threshold,
                surface_weight_cap=SURFACE_WEIGHT_CAPS.get(spec.name, 0.5),
            )
            combined_percentile = clamp(combined_percentile, 0.0, 100.0)
            state.percentiles[spec.name] = round(combined_percentile, 2)
            state.ratings[spec.name] = interpolate_rating(combined_percentile)
            apply_review_flags(state, spec, available_weight, missing_components)

        if spec.name in {"fielding", "arm"}:
            group_counts = {}
            for state in eligible_states:
                group_counts[state.position_group] = group_counts.get(state.position_group, 0) + 1
            for group, count in group_counts.items():
                if count < 4:
                    for state in eligible_states:
                        if state.position_group == group:
                            state.review_flags.append(f"{spec.name}: peer group '{group}' is small ({count})")

    # Elite pitch trait thresholds prefer MLB-wide percentile metadata when available,
    # then fall back to percentiles within the active pitcher pool.
    cache_elite_pitch_quality_percentiles(states)

    outputs: list[RatingOutput] = []
    for state in states:
        derived_secondary_positions = state.secondary_positions
        covered_groups = utility_covered_groups(state.player, derived_secondary_positions)
        overall_numeric = role_weighted_overall_numeric(state.player.role, state.ratings)
        deduped_flags = sorted(set(state.review_flags))
        output_metadata = dict(state.player.metadata)
        output_metadata.setdefault("positions", {})
        if isinstance(output_metadata["positions"], Mapping):
            output_metadata["positions"] = dict(output_metadata["positions"])
            output_metadata["positions"]["covered_groups"] = covered_groups
        outputs.append(
            RatingOutput(
                name=state.player.name,
                role=state.player.role,
                team=state.player.team,
                primary_position=state.player.primary_position,
                ratings=dict(sorted(state.ratings.items())),
                percentiles=dict(sorted(state.percentiles.items())),
                overall_numeric=overall_numeric,
                overall_grade=overall_grade(overall_numeric),
                confidence=confidence_level(deduped_flags),
                review_flags=deduped_flags,
                suggested_traits=suggest_traits(state),
                assigned_traits=[],
                recommended_personalities=[],
                secondary_position=derived_secondary_positions[0] if derived_secondary_positions else state.player.secondary_position,
                secondary_positions=derived_secondary_positions,
                age=state.player.age,
                projected_pa=resolved_projected_pa(state.player),
                projected_ip=resolved_projected_ip(state.player),
                recommended_pitches=select_pitch_mix(state.player.pitch_mix) if state.player.role in {"pitcher", "two_way"} else [],
                on_il=state.player.on_il if state.player.on_il is not None else metadata_lookup(state.player.metadata, "on_il"),
                player_id=state.player.player_id or metadata_lookup(state.player.metadata, "source_player_id"),
                metadata=output_metadata,
            )
        )

    team_scores = team_trait_scores(outputs, players_by_identity)
    for output in outputs:
        player = players_by_identity.get(_output_identity_key(output))
        if player is None:
            continue
        output.recommended_personalities = recommend_personalities_for_output(
            output,
            player,
            team_scores.get(output.team or "", {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}),
        )
        if trim_final_traits:
            output.assigned_traits = trim_traits_for_output(output, player)
        else:
            output.assigned_traits = all_player_traits(output, player)

        weighted_pa_sample = weighted_value(player.samples.get("weighted_pa")) or 0.0
        state = states_by_identity.get(_output_identity_key(output))
        for spec_name in ("contact", "power"):
            if spec_name not in output.percentiles:
                continue
            assigned_trait_names = assigned_platoon_trait_names(output, spec_name)
            if not assigned_trait_names or state is None:
                continue
            penalty = platoon_penalty_percentile(
                spec_name,
                player,
                weighted_pa_sample,
                split_percentiles=state.split_percentiles,
                trait_names=assigned_trait_names,
            )
            if penalty <= 0.0:
                continue
            penalized_percentile = clamp(output.percentiles[spec_name] - penalty, 0.0, 100.0)
            output.percentiles[spec_name] = round(penalized_percentile, 2)
            output.ratings[spec_name] = interpolate_rating(penalized_percentile)

        output.overall_numeric = role_weighted_overall_numeric(player.role, output.ratings)
        output.overall_grade = overall_grade(output.overall_numeric)
    return outputs


def rate_players(
    players: list[PlayerInput | dict],
    trim_final_traits: bool = True,
    config_path: str | None = None,
) -> list[RatingOutput]:
    # Compatibility wrapper: the processing layer is the preferred public entrypoint.
    return _rate_players_core(players, trim_final_traits=trim_final_traits, config_path=config_path)
