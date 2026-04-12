from __future__ import annotations

import json
from dataclasses import dataclass
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Mapping

from .models import PersonalityRecommendation, PlayerInput, RatingOutput, SeasonValue, TraitSuggestion
from .pitch_selector import select_pitch_mix


SEASON_WEIGHTS = {
    "current": 0.50,
    "previous": 0.30,
    "two_years_ago": 0.20,
}


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


GRADE_BREAKPOINTS = [
    (97, "S"),
    (93, "A+"),
    (89, "A"),
    (85, "A-"),
    (79, "B+"),
    (73, "B"),
    (67, "B-"),
    (60, "C+"),
    (53, "C"),
    (46, "C-"),
    (38, "D+"),
    (30, "D"),
    (0, "D-"),
]


PERCENTILE_TO_RATING = [
    (0.0, 5),
    (5.0, 20),
    (15.0, 32),
    (35.0, 47),
    (55.0, 62),
    (75.0, 75),
    (88.0, 84),
    (95.0, 91),
    (99.0, 96),
    (100.0, 99),
]


CHEMISTRY_TYPES = (
    "Competitive",
    "Spirited",
    "Disciplined",
    "Scholarly",
    "Crafty",
)

DEFAULT_VOLUME_PROJECTION = {
    "full_season_days_hitter": 162.0,
    "full_season_days_pitcher": 180.0,
}


REFERENCE_PATH = Path(__file__).resolve().parent.parent / "smb4_player_reference.json"


CONFIDENCE_WEIGHTS = {
    "high": 1.0,
    "medium": 0.7,
    "low": 0.4,
}


PERSONALITY_PERSONAL_WEIGHT = 0.70
PERSONALITY_TEAM_WEIGHT = 0.30
DEFAULT_FINAL_TRAIT_LIMIT = 3


TRAIT_CONFLICT_GROUPS = (
    frozenset({"First Pitch Slayer", "First Pitch Prayer"}),
    frozenset({"CON vs LHP", "CON vs RHP"}),
    frozenset({"POW vs LHP", "POW vs RHP"}),
    frozenset({"RBI Hero", "RBI Zero"}),
    frozenset({"Consistent", "Volatile"}),
    frozenset({"Durable", "Injury Prone"}),
    frozenset({"Clutch", "Choker"}),
    frozenset({"Sprinter", "Slow Poke"}),
    frozenset({"Cannon Arm", "Noodle Arm"}),
    frozenset({"Magic Hands", "Butter Fingers"}),
    frozenset({"K Collector", "K Neglecter"}),
    frozenset({"Composed", "BB Prone"}),
    frozenset({"Gets Ahead", "Falls Behind"}),
    frozenset({"Rally Stopper", "Surrounded"}),
    frozenset({"Pick Officer", "Easy Jumps"}),
    frozenset({"Reverse Splits", "Specialist"}),
    frozenset({"Big Hack", "Little Hack"}),
    frozenset({"Two Way (C)", "Two Way (IF)", "Two Way (OF)"}),
)


def load_trait_catalog() -> tuple[tuple[str, ...], dict[str, dict[str, str | bool | None]]]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return CHEMISTRY_TYPES, {}

    chemistry_types = tuple(payload.get("chemistry_types", CHEMISTRY_TYPES))
    catalog: dict[str, dict[str, str | bool | None]] = {}
    for trait_group in payload.get("traits", {}).values():
        if not isinstance(trait_group, list):
            continue
        for trait in trait_group:
            if not isinstance(trait, dict) or "name" not in trait:
                continue
            catalog[str(trait["name"])] = {
                "chemistry_type": trait.get("chemistry_type"),
                "polarity": trait.get("polarity"),
                "role_scope": trait.get("role_scope"),
                "chemistry_scaled": trait.get("chemistry_scaled"),
            }
    return chemistry_types, catalog


def load_volume_projection_config() -> dict[str, float]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_VOLUME_PROJECTION)

    projection_payload = payload.get("volume_projection", {})
    if not isinstance(projection_payload, dict):
        return dict(DEFAULT_VOLUME_PROJECTION)

    try:
        return {
            "full_season_days_hitter": float(projection_payload.get("full_season_days_hitter", DEFAULT_VOLUME_PROJECTION["full_season_days_hitter"])),
            "full_season_days_pitcher": float(projection_payload.get("full_season_days_pitcher", DEFAULT_VOLUME_PROJECTION["full_season_days_pitcher"])),
        }
    except (TypeError, ValueError):
        return dict(DEFAULT_VOLUME_PROJECTION)


def load_trait_criteria_config() -> dict[str, object]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"minimum_score": 10.0, "traits": {}}

    trait_payload = payload.get("trait_criteria", {})
    if not isinstance(trait_payload, dict):
        return {"minimum_score": 10.0, "traits": {}}

    minimum_score = trait_payload.get("minimum_score", 10.0)
    traits = trait_payload.get("traits", {})
    try:
        parsed_minimum = float(minimum_score)
    except (TypeError, ValueError):
        parsed_minimum = 10.0
    return {
        "minimum_score": parsed_minimum,
        "traits": traits if isinstance(traits, dict) else {},
    }


CHEMISTRY_TYPES, TRAIT_CATALOG = load_trait_catalog()
VOLUME_PROJECTION_CONFIG = load_volume_projection_config()
TRAIT_CRITERIA_CONFIG = load_trait_criteria_config()


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
            ComponentSpec("two_strike_contact_rate", 0.10),
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
            ComponentSpec("oaa", 0.40),
            ComponentSpec("drs", 0.25),
            ComponentSpec("uzr", 0.15),
            ComponentSpec("fielding_pct_proxy", 0.10),
            ComponentSpec("position_difficulty", 0.10),
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
            ComponentSpec("arm_strength", 0.45),
            ComponentSpec("catcher_throw_value", 0.20, position_groups=frozenset({"catcher"})),
            ComponentSpec("outfield_arm_runs", 0.20, position_groups=frozenset({"outfield"})),
            ComponentSpec("arm_position_baseline", 0.15),
        ),
    ),
    RatingSpec(
        name="velocity",
        roles=frozenset({"pitcher", "two_way"}),
        sample_key="tracked_fastballs",
        stabilization_threshold=175,
        review_threshold=80,
        peer_mode="pitcher",
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
        peer_mode="pitcher",
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
        peer_mode="pitcher",
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
    review_flags: list[str]


def configured_chemistry_types() -> list[str]:
    return list(CHEMISTRY_TYPES)


def trait_metadata(trait_name: str) -> dict[str, str | bool | None] | None:
    return TRAIT_CATALOG.get(trait_name)


def trait_chemistry_type(trait_name: str) -> str | None:
    metadata = trait_metadata(trait_name)
    if metadata is None:
        return None
    chemistry_type = metadata.get("chemistry_type")
    return chemistry_type if isinstance(chemistry_type, str) else None


def weighted_value(value: SeasonValue) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return None

    total_weight = 0.0
    total_value = 0.0
    for season_key, weight in SEASON_WEIGHTS.items():
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


def weighted_metric_value(
    metric_value: SeasonValue,
    sample_value: SeasonValue | None,
    *,
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
    total_weight = 0.0
    total_value = 0.0

    for season_key, metric in metric_seasons.items():
        recency_weight = SEASON_WEIGHTS.get(season_key, 0.0)
        if recency_weight == 0:
            continue

        volume = 1.0
        if sample_seasons is not None:
            season_volume = sample_seasons.get(season_key)
            if season_volume is None or season_volume <= 0:
                continue
            volume = season_volume ** volume_exponent

        combined_weight = recency_weight * volume
        total_weight += combined_weight
        total_value += metric * combined_weight

    if total_weight == 0:
        return None

    blended_value = total_value / total_weight
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


def surface_weight_factor(sample: float, threshold: float) -> float:
    if sample <= 0 or threshold <= 0:
        return 0.0
    return 0.5 * clamp(sample / threshold, 0.0, 1.0)


def blend_component_percentiles(
    component_percentiles: list[tuple[float, float, bool]],
    *,
    sample: float,
    threshold: float,
) -> float:
    underlying_components = [(percentile, weight) for percentile, weight, is_surface in component_percentiles if not is_surface]
    surface_components = [(percentile, weight) for percentile, weight, is_surface in component_percentiles if is_surface]

    def weighted_average(components: list[tuple[float, float]]) -> float:
        total_weight = sum(weight for _, weight in components)
        return sum(percentile * weight for percentile, weight in components) / total_weight

    if not underlying_components or not surface_components:
        return weighted_average([(percentile, weight) for percentile, weight, _ in component_percentiles])

    surface_share = surface_weight_factor(sample, threshold)
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
        review_flags=[],
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
        return float(player.projected_pa)
    return projected_season_average(
        player.samples.get("weighted_pa"),
        injury_shortened_seasons(player),
        days_on_roster=player.days_on_roster,
        full_season_days=VOLUME_PROJECTION_CONFIG["full_season_days_hitter"],
    )


def resolved_projected_ip(player: PlayerInput) -> float | None:
    if player.projected_ip is not None:
        return float(player.projected_ip)
    return projected_season_average(
        pitcher_season_ip_dict(player),
        injury_shortened_seasons(player),
        days_on_roster=player.days_on_roster,
        full_season_days=VOLUME_PROJECTION_CONFIG["full_season_days_pitcher"],
    )


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
        if not isinstance(target_value, (int, float)) or numeric_value < float(target_value):
            return None
        score = (numeric_value - float(target_value) + 10.0) * weight_value
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
    trait_names: list[str] = []
    for key in ("traits", "existing_traits", "manual_traits"):
        raw_traits = player.metadata.get(key)
        if isinstance(raw_traits, list):
            trait_names.extend(str(item) for item in raw_traits if item)

    seen: set[str] = set()
    explicit_traits: list[TraitSuggestion] = []
    for trait_name in trait_names:
        if trait_name in seen:
            continue
        seen.add(trait_name)
        metadata = trait_metadata(trait_name)
        if metadata is None:
            explicit_traits.append(
                TraitSuggestion(
                    name=trait_name,
                    chemistry_type=None,
                    polarity="unknown",
                    confidence="medium",
                    reason="Provided explicitly in player metadata but not found in the SMB4 reference catalog.",
                )
            )
            continue
        explicit_traits.append(
            TraitSuggestion(
                name=trait_name,
                chemistry_type=trait_chemistry_type(trait_name),
                polarity=str(metadata.get("polarity") or "unknown"),
                confidence="high",
                reason="Provided explicitly in player metadata and counted directly for chemistry fit.",
            )
        )
    return explicit_traits


def hinted_catalog_traits(player: PlayerInput) -> list[TraitSuggestion]:
    metadata = player.metadata
    hinted: dict[str, TraitSuggestion] = {}
    sources = []
    for key in ("trait_hints", "trait_signals", "trait_scores"):
        value = metadata.get(key)
        if isinstance(value, Mapping):
            sources.append(value)

    normalized_catalog = {normalize_trait_key(name): name for name in TRAIT_CATALOG}

    def register(trait_name: str, payload: object) -> None:
        if trait_name not in TRAIT_CATALOG:
            return
        score = None
        confidence = "medium"
        reason = "Suggested from player metadata trait signal."
        if isinstance(payload, (int, float)):
            score = float(payload)
        elif isinstance(payload, bool):
            score = 30.0 if payload else None
        elif isinstance(payload, Mapping):
            raw_score = payload.get("score")
            if isinstance(raw_score, (int, float)):
                score = float(raw_score)
            elif payload.get("enabled") is True:
                score = 30.0
            raw_confidence = payload.get("confidence")
            if isinstance(raw_confidence, str):
                confidence = raw_confidence
            raw_reason = payload.get("reason")
            if isinstance(raw_reason, str) and raw_reason:
                reason = raw_reason
        if score is None or score < 10:
            return
        hinted[trait_name] = TraitSuggestion(
            name=trait_name,
            chemistry_type=trait_chemistry_type(trait_name),
            polarity=catalog_trait_polarity(trait_name),
            confidence=confidence,
            reason=reason,
        )

    for source in sources:
        for raw_key, payload in source.items():
            key_name = str(raw_key)
            trait_name = key_name if key_name in TRAIT_CATALOG else normalized_catalog.get(normalize_trait_key(key_name))
            if trait_name:
                register(trait_name, payload)

    for trait_name in TRAIT_CATALOG:
        normalized_key = normalize_trait_key(trait_name)
        for candidate_key in (
            normalized_key,
            f"{normalized_key}_score",
            f"trait_metrics.{normalized_key}",
            f"trait_scores.{normalized_key}",
            f"trait_signals.{normalized_key}",
        ):
            value = metadata_lookup(metadata, candidate_key)
            if value is None:
                continue
            register(trait_name, value)
            break

    return list(hinted.values())


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
    combined: dict[str, TraitSuggestion] = {}
    for trait in explicit_player_traits(player) + output.suggested_traits:
        existing = combined.get(trait.name)
        if existing is None:
            combined[trait.name] = trait
            continue
        rank = {"low": 1, "medium": 2, "high": 3}
        if rank.get(trait.confidence, 1) > rank.get(existing.confidence, 1):
            combined[trait.name] = trait
    return list(combined.values())


def explicit_trait_names(player: PlayerInput) -> set[str]:
    return {trait.name for trait in explicit_player_traits(player)}


def trait_conflicts(existing_names: set[str], candidate_name: str) -> bool:
    for conflict_group in TRAIT_CONFLICT_GROUPS:
        if candidate_name not in conflict_group:
            continue
        if existing_names.intersection(conflict_group):
            return True
    return False


def final_trait_limit(player: PlayerInput, explicit_count: int) -> int:
    raw_limit = metadata_lookup(player.metadata, "final_trait_limit")
    if not isinstance(raw_limit, int):
        raw_limit = metadata_lookup(player.metadata, "trait_limit")
    if not isinstance(raw_limit, int):
        raw_limit = DEFAULT_FINAL_TRAIT_LIMIT
    return max(raw_limit, explicit_count)


def top_personality_scores(output: RatingOutput) -> dict[str, float]:
    top_two = output.recommended_personalities[:2]
    return {item.chemistry_type: item.score for item in top_two}


def final_trait_priority(
    trait: TraitSuggestion,
    *,
    explicit_names: set[str],
    personality_scores: dict[str, float],
) -> float:
    score = CONFIDENCE_WEIGHTS.get(trait.confidence, 0.4) * 100.0
    if trait.name in explicit_names:
        score += 35.0
    if trait.chemistry_type is not None:
        score += personality_scores.get(trait.chemistry_type, 0.0) * 0.35
    if trait.polarity == "positive":
        score += 8.0
    elif trait.polarity == "negative":
        score += 4.0
    if "Provided explicitly" in trait.reason:
        score += 10.0
    if "metadata" in trait.reason.lower() or "preprocessing" in trait.reason.lower():
        score += 4.0
    return score


def trim_traits_for_output(output: RatingOutput, player: PlayerInput) -> list[TraitSuggestion]:
    all_traits = all_player_traits(output, player)
    explicit_names = explicit_trait_names(player)
    limit = final_trait_limit(player, len(explicit_names))
    personality_scores = top_personality_scores(output)

    ordered_traits = sorted(
        all_traits,
        key=lambda trait: (
            final_trait_priority(trait, explicit_names=explicit_names, personality_scores=personality_scores),
            trait.name,
        ),
        reverse=True,
    )

    selected: list[TraitSuggestion] = []
    selected_names: set[str] = set()
    for trait in ordered_traits:
        if len(selected) >= limit:
            break
        if trait_conflicts(selected_names, trait.name):
            continue
        selected.append(trait)
        selected_names.add(trait.name)
    return selected


def chemistry_scores_from_traits(traits: list[TraitSuggestion]) -> dict[str, float]:
    scores = {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}
    for trait in traits:
        if trait.chemistry_type is None:
            continue
        scores[trait.chemistry_type] += trait_weight(trait)
    return scores


def normalized_scores(scores: dict[str, float]) -> dict[str, float]:
    total = sum(scores.values())
    if total <= 0:
        return {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}
    return {
        chemistry_type: score / total
        for chemistry_type, score in scores.items()
    }


def team_trait_scores(outputs: list[RatingOutput], players_by_name: dict[str, PlayerInput]) -> dict[str, dict[str, float]]:
    totals_by_team: dict[str, dict[str, float]] = defaultdict(lambda: {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()})
    for output in outputs:
        if not output.team:
            continue
        player = players_by_name[output.name]
        player_scores = chemistry_scores_from_traits(all_player_traits(output, player))
        for chemistry_type, score in player_scores.items():
            totals_by_team[output.team][chemistry_type] += score
    return dict(totals_by_team)


def personality_reason(
    chemistry_type: str,
    personal_share: float,
    team_share: float,
    player_traits: list[TraitSuggestion],
    team_scores: dict[str, float],
) -> str:
    personal_traits = [trait.name for trait in player_traits if trait.chemistry_type == chemistry_type]
    if personal_traits:
        return (
            f"Personal traits lean {chemistry_type} through {', '.join(personal_traits[:3])}; "
            f"team context adds a secondary {chemistry_type} push."
        )
    team_peak = max(team_scores, key=lambda key: team_scores[key]) if team_scores else chemistry_type
    if team_share > 0 and team_peak == chemistry_type:
        return f"Personal evidence is light, but the team trait mix most strongly supports {chemistry_type}."
    return f"Limited direct personal-trait evidence; {chemistry_type} remains a secondary fit from the combined roster context."


def recommend_personalities_for_output(
    output: RatingOutput,
    player: PlayerInput,
    team_scores: dict[str, float],
) -> list[PersonalityRecommendation]:
    personal_traits = all_player_traits(output, player)
    personal_raw = chemistry_scores_from_traits(personal_traits)
    team_minus_self = dict(team_scores)
    for chemistry_type, score in personal_raw.items():
        team_minus_self[chemistry_type] = max(0.0, team_minus_self.get(chemistry_type, 0.0) - score)

    personal_share = normalized_scores(personal_raw)
    team_share = normalized_scores(team_minus_self)

    recommendations: list[PersonalityRecommendation] = []
    for chemistry_type in configured_chemistry_types():
        blended_score = (
            PERSONALITY_PERSONAL_WEIGHT * personal_share[chemistry_type]
            + PERSONALITY_TEAM_WEIGHT * team_share[chemistry_type]
        ) * 100.0
        recommendations.append(
            PersonalityRecommendation(
                chemistry_type=chemistry_type,
                score=round(blended_score, 2),
                personal_score=round(personal_share[chemistry_type] * 100.0, 2),
                team_score=round(team_share[chemistry_type] * 100.0, 2),
                reason=personality_reason(
                    chemistry_type=chemistry_type,
                    personal_share=personal_share[chemistry_type],
                    team_share=team_share[chemistry_type],
                    player_traits=personal_traits,
                    team_scores=team_minus_self,
                ),
            )
        )

    return sorted(recommendations, key=lambda item: (item.score, item.personal_score, item.team_score), reverse=True)


def suggest_traits(state: PlayerState) -> list[TraitSuggestion]:
    suggestions: dict[str, TraitSuggestion] = {}

    if state.player.role in {"hitter", "two_way"}:
        contact_pct = state.percentiles.get("contact")
        power_pct = state.percentiles.get("power")
        speed_pct = state.percentiles.get("speed")
        fielding_pct = state.percentiles.get("fielding")
        arm_pct = state.percentiles.get("arm")

        strikeout_pct = component_percentile(state, "contact", "strikeout_rate")
        two_strike_pct = component_percentile(state, "contact", "two_strike_contact_rate")
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
                two_strike_pct,
                contact_rate_pct,
                batting_average_pct,
            )
            if value is not None
        ) if any(value is not None for value in (contact_pct, two_strike_pct, contact_rate_pct, batting_average_pct)) else None
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
        if two_strike_pct is not None and two_strike_pct >= 75:
            score = two_strike_pct - 55
            add_trait(
                suggestions,
                name="Tough Out",
                polarity="positive",
                score=score,
                reason="Strong two-strike contact supports contact value beyond the base rating.",
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
        if state.player.secondary_position and (fielding_pct or 0) >= 60:
            add_trait(
                suggestions,
                name="Utility",
                polarity="positive",
                score=(fielding_pct or 60) - 35,
                reason="A solid fielding profile with multi-position use supports a no-penalty secondary-position trait.",
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


def peer_states_for_component(states: list[PlayerState], spec: RatingSpec, target_state: PlayerState) -> list[PlayerState]:
    eligible = [state for state in states if player_matches_spec(state, spec)]
    if spec.peer_mode == "position_group":
        return [state for state in eligible if state.position_group == target_state.position_group]
    return eligible


def apply_review_flags(state: PlayerState, spec: RatingSpec, available_weight: float, missing_components: list[str]) -> None:
    sample = state.samples.get(spec.sample_key, 0.0)
    if sample < spec.review_threshold:
        state.review_flags.append(f"{spec.name}: sample below review threshold ({sample:.1f} < {spec.review_threshold})")
    if missing_components:
        missing_text = ", ".join(sorted(missing_components))
        state.review_flags.append(f"{spec.name}: missing metrics [{missing_text}]")
    if available_weight < 0.6:
        state.review_flags.append(f"{spec.name}: low component coverage ({available_weight:.2f})")


def rate_players(players: list[PlayerInput | dict], trim_final_traits: bool = True) -> list[RatingOutput]:
    player_objects = [player if isinstance(player, PlayerInput) else PlayerInput.from_dict(player) for player in players]
    player_objects = [player for player in player_objects if player.active]
    players_by_name = {player.name: player for player in player_objects}
    states = [state_from_player(player) for player in player_objects]

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

                raw_value = weighted_metric_value(
                    state.player.metrics.get(component.metric),
                    state.player.samples.get(spec.sample_key),
                    volume_exponent=spec.volume_exponent,
                    age=state.player.age,
                    raw_tools_bias=spec.raw_tools_bias,
                )
                if raw_value is None:
                    missing_components.append(component.metric)
                    continue

                peers = peer_states_for_component(states, spec, state)
                peer_values = [
                    weighted_metric_value(
                        peer.player.metrics.get(component.metric),
                        peer.player.samples.get(spec.sample_key),
                        volume_exponent=spec.volume_exponent,
                        age=peer.player.age,
                        raw_tools_bias=spec.raw_tools_bias,
                    )
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
                            weighted_metric_value(
                                peer.player.metrics.get(component.metric),
                                peer.player.samples.get(spec.sample_key),
                                volume_exponent=spec.volume_exponent,
                                age=peer.player.age,
                                raw_tools_bias=spec.raw_tools_bias,
                            ),
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
            )
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

    outputs: list[RatingOutput] = []
    for state in states:
        overall_numeric = int(round(mean(state.ratings.values()))) if state.ratings else None
        deduped_flags = sorted(set(state.review_flags))
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
                secondary_position=state.player.secondary_position,
                age=state.player.age,
                projected_pa=resolved_projected_pa(state.player),
                projected_ip=resolved_projected_ip(state.player),
                recommended_pitches=select_pitch_mix(state.player.pitch_mix) if state.player.role in {"pitcher", "two_way"} else [],
                metadata=dict(state.player.metadata),
            )
        )

    team_scores = team_trait_scores(outputs, players_by_name)
    for output in outputs:
        output.recommended_personalities = recommend_personalities_for_output(
            output,
            players_by_name[output.name],
            team_scores.get(output.team or "", {chemistry_type: 0.0 for chemistry_type in configured_chemistry_types()}),
        )
        if trim_final_traits:
            output.assigned_traits = trim_traits_for_output(output, players_by_name[output.name])
        else:
            output.assigned_traits = all_player_traits(output, players_by_name[output.name])
    return outputs
