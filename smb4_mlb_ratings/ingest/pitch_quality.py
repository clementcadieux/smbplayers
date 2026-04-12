from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping


ELITE_PITCH_SPECS = {
    "4F": {
        "metric_key": "pitch_quality_4f",
        "column": "Pitch Quality 4F",
        "arsenal_codes": ("FF",),
        "savant_codes": ("FF",),
        "kind": "fastball",
        "velocity_baseline": 90.0,
    },
    "2F": {
        "metric_key": "pitch_quality_2f",
        "column": "Pitch Quality 2F",
        "arsenal_codes": ("SI", "FT"),
        "savant_codes": ("SI", "FT"),
        "kind": "fastball",
        "velocity_baseline": 89.0,
    },
    "CF": {
        "metric_key": "pitch_quality_cf",
        "column": "Pitch Quality CF",
        "arsenal_codes": ("FC",),
        "savant_codes": ("FC",),
        "kind": "fastball",
        "velocity_baseline": 87.0,
    },
    "CB": {
        "metric_key": "pitch_quality_cb",
        "column": "Pitch Quality CB",
        "arsenal_codes": ("CU", "KC"),
        "savant_codes": ("CU", "KC"),
        "kind": "secondary",
        "target_gap": 15.0,
    },
    "CH": {
        "metric_key": "pitch_quality_ch",
        "column": "Pitch Quality CH",
        "arsenal_codes": ("CH",),
        "savant_codes": ("CH",),
        "kind": "secondary",
        "target_gap": 9.0,
    },
    "FK": {
        "metric_key": "pitch_quality_fk",
        "column": "Pitch Quality FK",
        "arsenal_codes": ("FS", "FO"),
        "savant_codes": ("FS", "FO"),
        "kind": "secondary",
        "target_gap": 10.0,
    },
    "SL": {
        "metric_key": "pitch_quality_sl",
        "column": "Pitch Quality SL",
        "arsenal_codes": ("SL", "SV"),
        "savant_codes": ("SL", "SV"),
        "kind": "secondary",
        "target_gap": 11.0,
    },
    "SB": {
        "metric_key": "pitch_quality_sb",
        "column": "Pitch Quality SB",
        "arsenal_codes": ("SC",),
        "savant_codes": ("SC",),
        "kind": "secondary",
        "target_gap": 13.0,
    },
}


REFERENCE_PATH = Path(__file__).resolve().parents[2] / "smb4_player_reference.json"
DEFAULT_PITCH_RV_THRESHOLDS = {
    "elite": -2.0,
    "exceptional": -6.0,
}


def _load_pitch_rv_thresholds() -> dict[str, float]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_PITCH_RV_THRESHOLDS)

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

    if exceptional > elite:
        elite, exceptional = exceptional, elite
    return {
        "elite": elite,
        "exceptional": exceptional,
    }


PITCH_RV_THRESHOLDS = _load_pitch_rv_thresholds()


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def parse_savant_pitch_details(payload: str) -> dict[str, dict[str, float]]:
    match = re.search(r"window\.serverVals\.pitchDetails\s*=\s*(\[.*?\]);", payload, re.DOTALL)
    if not match:
        return {}
    try:
        raw_rows = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw_rows, list):
        return {}

    details: dict[str, dict[str, float]] = {}
    for row in raw_rows:
        if not isinstance(row, dict):
            continue
        pitch_code = _as_str(row.get("api_pitch_type"))
        if not pitch_code:
            continue
        details[pitch_code.upper()] = {
            "xba": _as_float(row.get("xba")) or 0.0,
            "xwoba": _as_float(row.get("xwoba")) or 0.0,
            "xslg": _as_float(row.get("xslg")) or 0.0,
            "obp": _as_float(row.get("obp")) or 0.0,
            "slg": _as_float(row.get("slg")) or 0.0,
            "iso": _as_float(row.get("iso")) or 0.0,
            "k_percent": _as_float(row.get("k_percent")) or 0.0,
            "hard_hit_percent": _as_float(row.get("hard_hit_percent")) or 0.0,
            "brl_percent": _as_float(row.get("brl_percent")) or 0.0,
            "swings": _as_float(row.get("swings")) or 0.0,
            "misses": _as_float(row.get("misses")) or 0.0,
            "avg_plate_x": _as_float(row.get("avg_plate_x")) or 0.0,
            "avg_plate_z": _as_float(row.get("avg_plate_z")) or 0.0,
            "pa": _as_float(row.get("pa")) or 0.0,
            "release_speed": _as_float(row.get("release_speed")) or 0.0,
            "pitches": _as_float(row.get("pitches")) or 0.0,
            "total_pitches": _as_float(row.get("total_pitches")) or 0.0,
            "run_value_per_100": _as_float(row.get("run_value_per_100")) or _as_float(row.get("rv_per_100")) or 0.0,
        }
    return details


def pitch_quality_columns(metrics: Mapping[str, float | None]) -> dict[str, float | None]:
    return {
        str(spec["column"]): metrics.get(str(spec["metric_key"]))
        for spec in ELITE_PITCH_SPECS.values()
    }


def arsenal_percentage(arsenal: Mapping[str, Mapping[str, Any]], pitch_code: str) -> float | None:
    stat_line = arsenal.get(pitch_code)
    if not isinstance(stat_line, Mapping):
        return None
    raw_percentage = _as_float(stat_line.get("percentage"))
    if raw_percentage is None:
        return None
    return round(raw_percentage * 100.0, 3)


def arsenal_percentage_for_codes(arsenal: Mapping[str, Mapping[str, Any]], pitch_codes: tuple[str, ...]) -> float | None:
    total_percentage = 0.0
    found_code = False
    for pitch_code in pitch_codes:
        stat_line = arsenal.get(pitch_code)
        if not isinstance(stat_line, Mapping):
            continue
        raw_percentage = _as_float(stat_line.get("percentage"))
        if raw_percentage is None:
            continue
        total_percentage += raw_percentage
        found_code = True
    if not found_code:
        return None
    return round(total_percentage * 100.0, 3)


def fastball_velocity(arsenal: Mapping[str, Mapping[str, Any]], *, mode: str) -> float | None:
    fastball_codes = ("FF", "SI", "FC", "FT")
    if mode == "peak":
        velocities = [
            velocity
            for code in fastball_codes
            if code in arsenal and (velocity := _as_float(arsenal[code].get("averageSpeed"))) is not None
        ]
        return round(max(velocities), 3) if velocities else None

    weighted_velocity = 0.0
    total_percentage = 0.0
    for code in fastball_codes:
        stat_line = arsenal.get(code)
        if not isinstance(stat_line, Mapping):
            continue
        percentage = _as_float(stat_line.get("percentage"))
        velocity = _as_float(stat_line.get("averageSpeed"))
        if percentage is None or velocity is None:
            continue
        weighted_velocity += percentage * velocity
        total_percentage += percentage
    if total_percentage <= 0:
        return None
    return round(weighted_velocity / total_percentage, 3)


def pitch_average_speed_for_codes(arsenal: Mapping[str, Mapping[str, Any]], pitch_codes: tuple[str, ...]) -> float | None:
    weighted_velocity = 0.0
    total_percentage = 0.0
    for pitch_code in pitch_codes:
        stat_line = arsenal.get(pitch_code)
        if not isinstance(stat_line, Mapping):
            continue
        percentage = _as_float(stat_line.get("percentage"))
        velocity = _as_float(stat_line.get("averageSpeed"))
        if percentage is None or velocity is None:
            continue
        weighted_velocity += percentage * velocity
        total_percentage += percentage
    if total_percentage <= 0:
        return None
    return round(weighted_velocity / total_percentage, 3)


def derive_pitch_quality_metrics(
    arsenal: Mapping[str, Mapping[str, Any]],
    savant_pitch_details: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, float | None]:
    fastball_avg_velocity = fastball_velocity(arsenal, mode="average") or 0.0
    primary_fastball_usage = max(
        (
            arsenal_percentage_for_codes(arsenal, tuple(spec["arsenal_codes"])) or 0.0
            for spec in ELITE_PITCH_SPECS.values()
            if spec["kind"] == "fastball"
        ),
        default=0.0,
    )
    details = savant_pitch_details or {}
    metrics: dict[str, float | None] = {}
    for spec in ELITE_PITCH_SPECS.values():
        metric_key = str(spec["metric_key"])
        if spec["kind"] == "fastball":
            metrics[metric_key] = _pitch_quality_fastball_family(
                arsenal,
                details,
                arsenal_codes=tuple(spec["arsenal_codes"]),
                savant_codes=tuple(spec["savant_codes"]),
                primary_fastball_usage=primary_fastball_usage,
                velocity_baseline=float(spec["velocity_baseline"]),
            )
            continue
        metrics[metric_key] = _pitch_quality_secondary_family(
            arsenal,
            details,
            arsenal_codes=tuple(spec["arsenal_codes"]),
            savant_codes=tuple(spec["savant_codes"]),
            fastball_avg_velocity=fastball_avg_velocity,
            primary_fastball_usage=primary_fastball_usage,
            target_gap=float(spec["target_gap"]),
        )
    return metrics


def _pitch_quality_fastball_family(
    arsenal: Mapping[str, Mapping[str, Any]],
    savant_pitch_details: Mapping[str, Mapping[str, float]],
    *,
    arsenal_codes: tuple[str, ...],
    savant_codes: tuple[str, ...],
    primary_fastball_usage: float,
    velocity_baseline: float,
) -> float | None:
    usage = arsenal_percentage_for_codes(arsenal, arsenal_codes)
    velocity = pitch_average_speed_for_codes(arsenal, arsenal_codes)
    if usage is None or velocity is None:
        return None
    quality_score = _family_savant_pitch_quality_score(savant_pitch_details, savant_codes)
    fallback_quality = max((velocity - velocity_baseline) * 5.0, 0.0)
    score = (quality_score * 0.8) + (fallback_quality * 0.2)
    score += _pitch_usage_modifier(usage, primary_fastball_usage)
    if primary_fastball_usage and usage >= primary_fastball_usage * 0.9:
        score += 3.0
    return round(max(0.0, min(99.0, score)), 3)


def _pitch_quality_secondary_family(
    arsenal: Mapping[str, Mapping[str, Any]],
    savant_pitch_details: Mapping[str, Mapping[str, float]],
    *,
    arsenal_codes: tuple[str, ...],
    savant_codes: tuple[str, ...],
    fastball_avg_velocity: float,
    primary_fastball_usage: float,
    target_gap: float,
) -> float | None:
    usage = arsenal_percentage_for_codes(arsenal, arsenal_codes)
    velocity = pitch_average_speed_for_codes(arsenal, arsenal_codes)
    if usage is None or velocity is None or fastball_avg_velocity <= 0:
        return None
    velocity_gap = fastball_avg_velocity - velocity
    gap_bonus = max(18.0 - abs(velocity_gap - target_gap) * 2.0, 0.0)
    quality_score = _family_savant_pitch_quality_score(savant_pitch_details, savant_codes)
    fallback_quality = 22.0 + gap_bonus
    score = (quality_score * 0.8) + (fallback_quality * 0.2)
    score += _pitch_usage_modifier(usage, primary_fastball_usage)
    return round(max(0.0, min(99.0, score)), 3)


def _family_savant_pitch_quality_score(
    savant_pitch_details: Mapping[str, Mapping[str, float]],
    pitch_codes: tuple[str, ...],
) -> float:
    weighted_score = 0.0
    total_weight = 0.0
    for pitch_code in pitch_codes:
        pitch_detail = savant_pitch_details.get(pitch_code)
        if not isinstance(pitch_detail, Mapping):
            continue
        weight = _pitch_detail_weight(pitch_detail)
        if weight is None or weight <= 0:
            continue
        weighted_score += _savant_pitch_quality_score(pitch_detail, pitch_code=pitch_code) * weight
        total_weight += weight
    if total_weight <= 0:
        return 0.0
    return weighted_score / total_weight


def _pitch_detail_weight(pitch_detail: Mapping[str, float]) -> float | None:
    for key in ("pitches", "swings"):
        value = _as_float(pitch_detail.get(key))
        if value is not None and value > 0:
            return value
    return 1.0 if pitch_detail else None


def _savant_pitch_quality_score(pitch_detail: Mapping[str, float], *, pitch_code: str) -> float:
    xwoba = _as_float(pitch_detail.get("xwoba")) or 0.0
    xba = _as_float(pitch_detail.get("xba")) or 0.0
    xslg = _as_float(pitch_detail.get("xslg")) or 0.0
    hard_hit_percent = _as_float(pitch_detail.get("hard_hit_percent")) or 0.0
    barrel_percent = _as_float(pitch_detail.get("brl_percent")) or 0.0
    swings = _as_float(pitch_detail.get("swings")) or 0.0
    misses = _as_float(pitch_detail.get("misses")) or 0.0
    whiff_percent = (misses / swings) * 100.0 if swings > 0 else 0.0
    release_speed = _as_float(pitch_detail.get("release_speed")) or 0.0
    run_value_per_100 = _as_float(pitch_detail.get("run_value_per_100"))
    if run_value_per_100 is None:
        run_value_per_100 = _as_float(pitch_detail.get("rv_per_100")) or 0.0

    score = 0.0
    score += _bounded_score(0.420 - xwoba, 0.220) * 24.0
    score += _bounded_score(0.300 - xba, 0.160) * 10.0
    score += _bounded_score(0.650 - xslg, 0.350) * 13.0
    score += _bounded_score(whiff_percent - 15.0, 30.0) * 10.0
    score += _bounded_score(55.0 - hard_hit_percent, 35.0) * 7.0
    score += _bounded_score(12.0 - barrel_percent, 10.0) * 4.0
    elite_rv = PITCH_RV_THRESHOLDS["elite"]
    exceptional_rv = PITCH_RV_THRESHOLDS["exceptional"]
    rv_scale = max(elite_rv - exceptional_rv, 0.001)
    score += _bounded_score(elite_rv - run_value_per_100, rv_scale) * 27.0
    if pitch_code in {"FF", "SI", "FT", "FC"}:
        score += _bounded_score(release_speed - 92.0, 6.0) * 5.0
    return max(0.0, min(99.0, score))


def _pitch_usage_modifier(usage: float, primary_fastball_usage: float) -> float:
    modifier = _bounded_score(usage - 8.0, 24.0) * 6.0
    if primary_fastball_usage > 0:
        if usage >= primary_fastball_usage:
            modifier += 10.0
        elif usage >= primary_fastball_usage * 0.75:
            modifier += 6.0
        elif usage >= primary_fastball_usage * 0.5:
            modifier += 3.0
    return modifier


def _bounded_score(value: float, scale: float) -> float:
    if scale <= 0:
        return 0.0
    return max(0.0, min(1.0, value / scale))