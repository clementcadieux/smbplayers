from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping


SEASON_KEYS = ("current", "previous", "two_years_ago")

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
    "max_projected_pa": 700.0,
    "max_projected_ip": 250.0,
}

DEFAULT_SEASON_WEIGHTING = {
    "full_season_pa_threshold": 500.0,
    "full_season_ip_threshold": 150.0,
    "workhorse_benchmark_ip": 250.0,
    "season_recency_weights": {
        "current": 2.0,
        "previous": 1.0,
        "two_years_ago": 0.8,
    },
}

DEFAULT_SECONDARY_POSITION_CONFIG = {
    "minimum_positional_games": 1.0,
    "coverage_groups": {
        "OF": ["LF", "CF", "RF"],
        "IF": ["1B", "2B", "3B", "SS"],
    },
    "utility_bonus_weight": 1.0,
}

DEFAULT_FINAL_TRAIT_LIMIT = 2
DEFAULT_MAX_ELITE_PITCH_TRAITS = 1

DEFAULT_PITCH_SLOT_LIMIT = 4
DEFAULT_PITCH_MAPPINGS = {
    "ff": {"mlb_name": "Four-Seam Fastball", "smb4_name": "4-Seam Fastball", "merge_target": None},
    "si": {"mlb_name": "Sinker", "smb4_name": "2-Seam Fastball", "merge_target": None},
    "fc": {"mlb_name": "Cutter", "smb4_name": "Cut Fastball", "merge_target": None},
    "sl": {"mlb_name": "Slider", "smb4_name": "Slider", "merge_target": None},
    "cu": {"mlb_name": "Curveball", "smb4_name": "Curveball", "merge_target": None},
    "ch": {"mlb_name": "Changeup", "smb4_name": "Changeup", "merge_target": None},
    "fs": {"mlb_name": "Splitter", "smb4_name": "Forkball", "merge_target": None},
    "sv": {"mlb_name": "Sweeper", "smb4_name": None, "merge_target": "Slider"},
    "kn": {"mlb_name": "Knuckleball", "smb4_name": None, "merge_target": None},
}

DEFAULT_PITCH_RV_THRESHOLDS = {
    "elite": 2.0,
    "exceptional": 6.0,
}

DEFAULT_INJURY_THRESHOLD = {
    "min_pa_fraction": 0.6,
    "min_ip_fraction": 0.6,
}

DEFAULT_PROCESSING_TUNING = {
    "season_weighting": {
        "full_season_pa_threshold": 500.0,
        "full_season_ip_threshold": 150.0,
        "workhorse_benchmark_ip": 250.0,
        "season_recency_weights": {
            "current": 2.0,
            "previous": 1.0,
            "two_years_ago": 0.8,
        },
    },
    "rating_curve": {
        "percentile_to_rating": [
            [0.0, 5],
            [5.0, 20],
            [15.0, 32],
            [35.0, 47],
            [55.0, 62],
            [75.0, 75],
            [88.0, 85],
            [93.0, 90],
            [96.0, 94],
            [98.0, 96],
            [99.5, 98],
            [100.0, 99],
        ],
        "grade_breakpoints": [
            [97, "S"],
            [93, "A+"],
            [89, "A"],
            [85, "A-"],
            [79, "B+"],
            [73, "B"],
            [67, "B-"],
            [60, "C+"],
            [53, "C"],
            [46, "C-"],
            [38, "D+"],
            [30, "D"],
            [0, "D-"],
        ],
    },
    "confidence_weights": {
        "high": 1.0,
        "medium": 0.7,
        "low": 0.4,
    },
    "personality_weights": {
        "personal": 0.70,
        "team": 0.30,
    },
    "trait_limits": {
        "max_traits_per_player": 2,
        "max_elite_pitch_traits": 1,
        "elite_pitch_traits": [],
    },
    "trait_conflict_groups": [
        ["First Pitch Slayer", "First Pitch Prayer"],
        ["CON vs LHP", "CON vs RHP"],
        ["POW vs LHP", "POW vs RHP"],
        ["RBI Hero", "RBI Zero"],
        ["Consistent", "Volatile"],
        ["Durable", "Injury Prone"],
        ["Clutch", "Choker"],
        ["Mind Gamer", "Easy Target"],
        ["Sprinter", "Slow Poke"],
        ["Base Rounder", "Base Jogger"],
        ["Cannon Arm", "Noodle Arm"],
        ["Magic Hands", "Butter Fingers"],
        ["K Collector", "K Neglecter"],
        ["Composed", "BB Prone"],
        ["Gets Ahead", "Falls Behind"],
        ["Rally Stopper", "Surrounded"],
        ["Pick Officer", "Easy Jumps"],
        ["Reverse Splits", "Specialist"],
        ["Big Hack", "Little Hack"],
        ["Tough Out", "Whiffer"],
        ["Two Way (C)", "Two Way (IF)", "Two Way (OF)"],
    ],
    "role_overall_weights": {
        "hitter": {
            "power": 0.30,
            "contact": 0.30,
            "speed": 0.20,
            "fielding": 0.12,
            "arm": 0.08,
        },
        "pitcher": {
            "velocity": 0.38,
            "junk": 0.37,
            "accuracy": 0.25,
        },
        "two_way": {
            "power": 0.14,
            "contact": 0.14,
            "speed": 0.10,
            "fielding": 0.08,
            "velocity": 0.18,
            "junk": 0.18,
            "accuracy": 0.18,
        },
    },
    "secondary_positions": {
        "minimum_positional_games": 1.0,
        "coverage_groups": {
            "OF": ["LF", "CF", "RF"],
            "IF": ["1B", "2B", "3B", "SS"],
        },
        "utility_bonus_weight": 1.0,
    },
}

REFERENCE_PATH = Path(__file__).resolve().parent.parent / "smb4_player_reference.json"
RUNTIME_CONFIG_DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config.yaml"
_runtime_config_path = RUNTIME_CONFIG_DEFAULT_PATH


@lru_cache(maxsize=1)
def load_reference_payload() -> dict[str, object]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


def _deep_merge(defaults: Mapping[str, object], overrides: Mapping[str, object]) -> dict[str, object]:
    merged: dict[str, object] = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)  # type: ignore[arg-type]
        else:
            merged[key] = value
    return merged


def _parse_runtime_config_payload(raw_text: str) -> dict[str, object]:
    try:
        import yaml  # type: ignore

        payload = yaml.safe_load(raw_text)
    except ModuleNotFoundError:
        try:
            payload = json.loads(raw_text)
        except Exception:
            return {}
    except Exception:
        try:
            payload = json.loads(raw_text)
        except Exception:
            return {}

    if not isinstance(payload, Mapping):
        return {}
    return dict(payload)


@lru_cache(maxsize=1)
def load_runtime_config_payload() -> dict[str, object]:
    try:
        raw_text = _runtime_config_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return {}
    return _parse_runtime_config_payload(raw_text)


def set_runtime_config_path(config_path: str | Path | None) -> None:
    global _runtime_config_path
    if config_path is None:
        _runtime_config_path = RUNTIME_CONFIG_DEFAULT_PATH
    else:
        _runtime_config_path = Path(config_path).expanduser().resolve()
    load_runtime_config_payload.cache_clear()


def current_runtime_config_path() -> Path:
    return _runtime_config_path


def load_processing_tuning_config() -> dict[str, object]:
    payload = load_runtime_config_payload()
    if not payload:
        return dict(DEFAULT_PROCESSING_TUNING)
    return _deep_merge(DEFAULT_PROCESSING_TUNING, payload)


def load_trait_catalog() -> tuple[tuple[str, ...], dict[str, dict[str, str | bool | None]]]:
    payload = load_reference_payload()
    if not payload:
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
    payload = load_reference_payload()
    if not payload:
        return dict(DEFAULT_VOLUME_PROJECTION)

    projection_payload = payload.get("volume_projection", {})
    if not isinstance(projection_payload, dict):
        return dict(DEFAULT_VOLUME_PROJECTION)

    try:
        return {
            "full_season_days_hitter": float(projection_payload.get("full_season_days_hitter", DEFAULT_VOLUME_PROJECTION["full_season_days_hitter"])),
            "full_season_days_pitcher": float(projection_payload.get("full_season_days_pitcher", DEFAULT_VOLUME_PROJECTION["full_season_days_pitcher"])),
            "max_projected_pa": float(projection_payload.get("max_projected_pa", DEFAULT_VOLUME_PROJECTION["max_projected_pa"])),
            "max_projected_ip": float(projection_payload.get("max_projected_ip", DEFAULT_VOLUME_PROJECTION["max_projected_ip"])),
        }
    except (TypeError, ValueError):
        return dict(DEFAULT_VOLUME_PROJECTION)


def load_season_weighting_config() -> dict[str, object]:
    runtime_config = load_processing_tuning_config()
    runtime_season_weighting = runtime_config.get("season_weighting", {})
    if isinstance(runtime_season_weighting, Mapping):
        recency_payload = runtime_season_weighting.get(
            "season_recency_weights",
            DEFAULT_SEASON_WEIGHTING["season_recency_weights"],
        )
        recency_weights = dict(DEFAULT_SEASON_WEIGHTING["season_recency_weights"])
        if isinstance(recency_payload, Mapping):
            for season_key in SEASON_KEYS:
                try:
                    recency_weights[season_key] = float(recency_payload.get(season_key, recency_weights[season_key]))
                except (TypeError, ValueError):
                    continue
        try:
            full_season_pa_threshold = float(
                runtime_season_weighting.get(
                    "full_season_pa_threshold",
                    DEFAULT_SEASON_WEIGHTING["full_season_pa_threshold"],
                )
            )
        except (TypeError, ValueError):
            full_season_pa_threshold = DEFAULT_SEASON_WEIGHTING["full_season_pa_threshold"]
        try:
            full_season_ip_threshold = float(
                runtime_season_weighting.get(
                    "full_season_ip_threshold",
                    DEFAULT_SEASON_WEIGHTING["full_season_ip_threshold"],
                )
            )
        except (TypeError, ValueError):
            full_season_ip_threshold = DEFAULT_SEASON_WEIGHTING["full_season_ip_threshold"]
        try:
            workhorse_benchmark_ip = float(
                runtime_season_weighting.get(
                    "workhorse_benchmark_ip",
                    DEFAULT_SEASON_WEIGHTING["workhorse_benchmark_ip"],
                )
            )
        except (TypeError, ValueError):
            workhorse_benchmark_ip = DEFAULT_SEASON_WEIGHTING["workhorse_benchmark_ip"]

        return {
            "full_season_pa_threshold": full_season_pa_threshold,
            "full_season_ip_threshold": full_season_ip_threshold,
            "workhorse_benchmark_ip": workhorse_benchmark_ip,
            "season_recency_weights": recency_weights,
        }

    payload = load_reference_payload()
    if not payload:
        return {
            "full_season_pa_threshold": DEFAULT_SEASON_WEIGHTING["full_season_pa_threshold"],
            "full_season_ip_threshold": DEFAULT_SEASON_WEIGHTING["full_season_ip_threshold"],
            "workhorse_benchmark_ip": DEFAULT_SEASON_WEIGHTING["workhorse_benchmark_ip"],
            "season_recency_weights": dict(DEFAULT_SEASON_WEIGHTING["season_recency_weights"]),
        }

    try:
        full_season_pa_threshold = float(
            payload.get("full_season_pa_threshold", DEFAULT_SEASON_WEIGHTING["full_season_pa_threshold"])
        )
    except (TypeError, ValueError):
        full_season_pa_threshold = DEFAULT_SEASON_WEIGHTING["full_season_pa_threshold"]

    try:
        full_season_ip_threshold = float(
            payload.get("full_season_ip_threshold", DEFAULT_SEASON_WEIGHTING["full_season_ip_threshold"])
        )
    except (TypeError, ValueError):
        full_season_ip_threshold = DEFAULT_SEASON_WEIGHTING["full_season_ip_threshold"]
    try:
        workhorse_benchmark_ip = float(
            payload.get("workhorse_benchmark_ip", DEFAULT_SEASON_WEIGHTING["workhorse_benchmark_ip"])
        )
    except (TypeError, ValueError):
        workhorse_benchmark_ip = DEFAULT_SEASON_WEIGHTING["workhorse_benchmark_ip"]

    recency_payload = payload.get("season_recency_weights", DEFAULT_SEASON_WEIGHTING["season_recency_weights"])
    recency_weights = dict(DEFAULT_SEASON_WEIGHTING["season_recency_weights"])
    if isinstance(recency_payload, Mapping):
        for season_key in SEASON_KEYS:
            try:
                recency_weights[season_key] = float(recency_payload.get(season_key, recency_weights[season_key]))
            except (TypeError, ValueError):
                continue
    elif isinstance(recency_payload, list):
        for season_key, weight in zip(SEASON_KEYS, recency_payload):
            try:
                recency_weights[season_key] = float(weight)
            except (TypeError, ValueError):
                continue

    return {
        "full_season_pa_threshold": full_season_pa_threshold,
        "full_season_ip_threshold": full_season_ip_threshold,
        "workhorse_benchmark_ip": workhorse_benchmark_ip,
        "season_recency_weights": recency_weights,
    }


def load_trait_criteria_config() -> dict[str, object]:
    payload = load_reference_payload()
    if not payload:
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
    parsed_traits = traits if isinstance(traits, dict) else {}

    runtime_config = load_processing_tuning_config()
    runtime_trait_payload = runtime_config.get("trait_criteria", {})
    if isinstance(runtime_trait_payload, Mapping):
        raw_runtime_minimum = runtime_trait_payload.get("minimum_score", parsed_minimum)
        try:
            parsed_minimum = float(raw_runtime_minimum)
        except (TypeError, ValueError):
            pass
        runtime_traits = runtime_trait_payload.get("traits", {})
        if isinstance(runtime_traits, Mapping):
            parsed_traits = _deep_merge(parsed_traits, runtime_traits)

    return {
        "minimum_score": parsed_minimum,
        "traits": parsed_traits,
    }


def load_trait_limit_config() -> dict[str, object]:
    runtime_config = load_processing_tuning_config()
    runtime_trait_limits = runtime_config.get("trait_limits", {})
    if isinstance(runtime_trait_limits, Mapping):
        try:
            max_traits_per_player = int(runtime_trait_limits.get("max_traits_per_player", DEFAULT_FINAL_TRAIT_LIMIT))
        except (TypeError, ValueError):
            max_traits_per_player = DEFAULT_FINAL_TRAIT_LIMIT
        try:
            max_elite_pitch_traits = int(
                runtime_trait_limits.get("max_elite_pitch_traits", DEFAULT_MAX_ELITE_PITCH_TRAITS)
            )
        except (TypeError, ValueError):
            max_elite_pitch_traits = DEFAULT_MAX_ELITE_PITCH_TRAITS
        elite_pitch_traits: set[str] = set()
        raw_elite_pitch_traits = runtime_trait_limits.get("elite_pitch_traits", [])
        if isinstance(raw_elite_pitch_traits, list):
            elite_pitch_traits = {
                str(item)
                for item in raw_elite_pitch_traits
                if isinstance(item, str) and str(item).strip()
            }
        return {
            "max_traits_per_player": max(max_traits_per_player, 0),
            "max_elite_pitch_traits": max(max_elite_pitch_traits, 0),
            "elite_pitch_traits": elite_pitch_traits,
        }

    payload = load_reference_payload()
    if not payload:
        return {
            "max_traits_per_player": DEFAULT_FINAL_TRAIT_LIMIT,
            "max_elite_pitch_traits": DEFAULT_MAX_ELITE_PITCH_TRAITS,
            "elite_pitch_traits": set(),
        }

    limits_payload = payload.get("trait_limits", {})
    if not isinstance(limits_payload, dict):
        limits_payload = {}

    try:
        max_traits_per_player = int(limits_payload.get("max_traits_per_player", DEFAULT_FINAL_TRAIT_LIMIT))
    except (TypeError, ValueError):
        max_traits_per_player = DEFAULT_FINAL_TRAIT_LIMIT
    try:
        max_elite_pitch_traits = int(limits_payload.get("max_elite_pitch_traits", DEFAULT_MAX_ELITE_PITCH_TRAITS))
    except (TypeError, ValueError):
        max_elite_pitch_traits = DEFAULT_MAX_ELITE_PITCH_TRAITS

    raw_elite_pitch_traits = payload.get("elite_pitch_traits", [])
    elite_pitch_traits: set[str] = set()
    if isinstance(raw_elite_pitch_traits, list):
        elite_pitch_traits = {
            str(item)
            for item in raw_elite_pitch_traits
            if isinstance(item, str) and str(item).strip()
        }

    return {
        "max_traits_per_player": max(max_traits_per_player, 0),
        "max_elite_pitch_traits": max(max_elite_pitch_traits, 0),
        "elite_pitch_traits": elite_pitch_traits,
    }


def load_secondary_position_config() -> dict[str, object]:
    runtime_config = load_processing_tuning_config()
    runtime_secondary_payload = runtime_config.get("secondary_positions", {})
    if isinstance(runtime_secondary_payload, Mapping):
        minimum_positional_games = runtime_secondary_payload.get(
            "minimum_positional_games",
            DEFAULT_SECONDARY_POSITION_CONFIG["minimum_positional_games"],
        )
        coverage_groups = runtime_secondary_payload.get("coverage_groups", DEFAULT_SECONDARY_POSITION_CONFIG["coverage_groups"])
        utility_bonus_weight = runtime_secondary_payload.get(
            "utility_bonus_weight",
            DEFAULT_SECONDARY_POSITION_CONFIG["utility_bonus_weight"],
        )
        try:
            minimum_value = float(minimum_positional_games)
        except (TypeError, ValueError):
            minimum_value = float(DEFAULT_SECONDARY_POSITION_CONFIG["minimum_positional_games"])
        try:
            utility_weight = float(utility_bonus_weight)
        except (TypeError, ValueError):
            utility_weight = float(DEFAULT_SECONDARY_POSITION_CONFIG["utility_bonus_weight"])

        normalized_groups: dict[str, list[str]] = {}
        if isinstance(coverage_groups, Mapping):
            for group_name, raw_positions in coverage_groups.items():
                if not isinstance(group_name, str) or not isinstance(raw_positions, list):
                    continue
                normalized = [
                    str(position).upper()
                    for position in raw_positions
                    if isinstance(position, str) and str(position).strip()
                ]
                if normalized:
                    normalized_groups[str(group_name).upper()] = normalized
        if not normalized_groups:
            normalized_groups = dict(DEFAULT_SECONDARY_POSITION_CONFIG["coverage_groups"])

        return {
            "minimum_positional_games": minimum_value,
            "coverage_groups": normalized_groups,
            "utility_bonus_weight": utility_weight,
        }

    payload = load_reference_payload()
    if not payload:
        return dict(DEFAULT_SECONDARY_POSITION_CONFIG)

    secondary_payload = payload.get("secondary_positions", {})
    if not isinstance(secondary_payload, Mapping):
        secondary_payload = {}

    minimum_positional_games = secondary_payload.get(
        "minimum_positional_games",
        DEFAULT_SECONDARY_POSITION_CONFIG["minimum_positional_games"],
    )
    coverage_groups = secondary_payload.get("coverage_groups", DEFAULT_SECONDARY_POSITION_CONFIG["coverage_groups"])
    utility_bonus_weight = secondary_payload.get(
        "utility_bonus_weight",
        DEFAULT_SECONDARY_POSITION_CONFIG["utility_bonus_weight"],
    )
    try:
        minimum_value = float(minimum_positional_games)
    except (TypeError, ValueError):
        minimum_value = float(DEFAULT_SECONDARY_POSITION_CONFIG["minimum_positional_games"])
    try:
        utility_weight = float(utility_bonus_weight)
    except (TypeError, ValueError):
        utility_weight = float(DEFAULT_SECONDARY_POSITION_CONFIG["utility_bonus_weight"])

    normalized_groups: dict[str, list[str]] = {}
    if isinstance(coverage_groups, Mapping):
        for group_name, raw_positions in coverage_groups.items():
            if not isinstance(group_name, str) or not isinstance(raw_positions, list):
                continue
            normalized = [
                str(position).upper()
                for position in raw_positions
                if isinstance(position, str) and str(position).strip()
            ]
            if normalized:
                normalized_groups[str(group_name).upper()] = normalized
    if not normalized_groups:
        normalized_groups = dict(DEFAULT_SECONDARY_POSITION_CONFIG["coverage_groups"])

    return {
        "minimum_positional_games": minimum_value,
        "coverage_groups": normalized_groups,
        "utility_bonus_weight": utility_weight,
    }


def load_pitch_selector_config() -> tuple[int, dict[str, dict[str, str | None]]]:
    payload = load_reference_payload()

    slot_limit = DEFAULT_PITCH_SLOT_LIMIT
    raw_slot_limit = payload.get("pitch_slot_limit")
    if raw_slot_limit is not None:
        try:
            slot_limit = max(1, int(raw_slot_limit))
        except (TypeError, ValueError):
            slot_limit = DEFAULT_PITCH_SLOT_LIMIT

    raw_mappings: Mapping[str, object] = DEFAULT_PITCH_MAPPINGS
    configured_mappings = payload.get("pitch_mappings")
    if isinstance(configured_mappings, Mapping) and configured_mappings:
        raw_mappings = configured_mappings

    mappings: dict[str, dict[str, str | None]] = {}
    for pitch_code, raw_mapping in raw_mappings.items():
        if not isinstance(raw_mapping, Mapping):
            continue
        mappings[str(pitch_code).lower()] = {
            "mlb_name": str(raw_mapping.get("mlb_name", pitch_code)),
            "smb4_name": str(raw_mapping["smb4_name"]) if raw_mapping.get("smb4_name") is not None else None,
            "merge_target": str(raw_mapping["merge_target"]) if raw_mapping.get("merge_target") is not None else None,
        }

    return slot_limit, mappings


def load_pitch_rv_thresholds() -> dict[str, float]:
    payload = load_reference_payload()

    elite_value = payload.get("pitch_rv_per_100_elite", DEFAULT_PITCH_RV_THRESHOLDS["elite"])
    exceptional_value = payload.get("pitch_rv_per_100_exceptional", DEFAULT_PITCH_RV_THRESHOLDS["exceptional"])

    try:
        elite = float(elite_value)
    except (TypeError, ValueError):
        elite = DEFAULT_PITCH_RV_THRESHOLDS["elite"]
    try:
        exceptional = float(exceptional_value)
    except (TypeError, ValueError):
        exceptional = DEFAULT_PITCH_RV_THRESHOLDS["exceptional"]

    if exceptional < elite:
        elite, exceptional = exceptional, elite
    return {
        "elite": elite,
        "exceptional": exceptional,
    }


def load_injury_threshold_config() -> dict[str, float]:
    payload = load_reference_payload()

    threshold_payload = payload.get("injury_threshold", {})
    if not isinstance(threshold_payload, Mapping):
        return dict(DEFAULT_INJURY_THRESHOLD)

    min_pa_fraction = threshold_payload.get("min_pa_fraction", DEFAULT_INJURY_THRESHOLD["min_pa_fraction"])
    min_ip_fraction = threshold_payload.get("min_ip_fraction", DEFAULT_INJURY_THRESHOLD["min_ip_fraction"])
    try:
        return {
            "min_pa_fraction": float(min_pa_fraction),
            "min_ip_fraction": float(min_ip_fraction),
        }
    except (TypeError, ValueError):
        return dict(DEFAULT_INJURY_THRESHOLD)
