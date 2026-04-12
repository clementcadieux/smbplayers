from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Iterable, Mapping, Sequence


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


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _parse_date(value: Any) -> date | None:
    raw_value = _as_str(value)
    if raw_value is None:
        return None
    try:
        return date.fromisoformat(raw_value)
    except ValueError:
        return None


def aggregate_split_stats(group: str, splits: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for split in splits:
        if not isinstance(split, Mapping):
            continue
        stat_line = split.get("stat", {})
        if not isinstance(stat_line, Mapping):
            continue
        for key in (
            "hits",
            "atBats",
            "baseOnBalls",
            "hitByPitch",
            "sacFlies",
            "totalBases",
            "strikeOuts",
            "plateAppearances",
            "battersFaced",
        ):
            value = _as_float(stat_line.get(key))
            if value is not None:
                totals[key] += value

    if group == "hitting":
        at_bats = totals.get("atBats", 0.0)
        plate_appearances = totals.get("plateAppearances", 0.0)
        hits = totals.get("hits", 0.0)
        total_bases = totals.get("totalBases", 0.0)
        walks = totals.get("baseOnBalls", 0.0)
        hit_by_pitch = totals.get("hitByPitch", 0.0)
        sac_flies = totals.get("sacFlies", 0.0)
        strikeouts = totals.get("strikeOuts", 0.0)
        avg = _ratio(hits, at_bats)
        obp = _ratio(hits + walks + hit_by_pitch, at_bats + walks + hit_by_pitch + sac_flies)
        slg = _ratio(total_bases, at_bats)
        iso = None if avg is None or slg is None else max(slg - avg, 0.0)
        strikeout_rate = _ratio(strikeouts, plate_appearances)
        return {
            "avg": avg or 0.0,
            "obp": obp or 0.0,
            "slg": slg or 0.0,
            "iso": iso or 0.0,
            "strikeout_rate": strikeout_rate or 0.0,
        }

    if group == "pitching":
        at_bats = totals.get("atBats", 0.0)
        batters_faced = totals.get("battersFaced", 0.0)
        hits = totals.get("hits", 0.0)
        total_bases = totals.get("totalBases", 0.0)
        walks = totals.get("baseOnBalls", 0.0)
        hit_by_pitch = totals.get("hitByPitch", 0.0)
        sac_flies = totals.get("sacFlies", 0.0)
        strikeouts = totals.get("strikeOuts", 0.0)
        avg = _ratio(hits, at_bats)
        obp = _ratio(hits + walks + hit_by_pitch, at_bats + walks + hit_by_pitch + sac_flies)
        slg = _ratio(total_bases, at_bats)
        ops = None if obp is None or slg is None else obp + slg
        strikeout_rate = _ratio(strikeouts, batters_faced)
        return {
            "avg": avg or 0.0,
            "obp": obp or 0.0,
            "slg": slg or 0.0,
            "ops": ops or 0.0,
            "strikeout_rate": strikeout_rate or 0.0,
        }

    return {}


def hitter_contact_platoon_delta(splits: Mapping[str, Mapping[str, float]]) -> float | None:
    vs_left = splits.get("vl") if isinstance(splits.get("vl"), Mapping) else None
    vs_right = splits.get("vr") if isinstance(splits.get("vr"), Mapping) else None
    if not isinstance(vs_left, Mapping) or not isinstance(vs_right, Mapping):
        return None
    avg_delta = (_as_float(vs_left.get("avg")) or 0.0) - (_as_float(vs_right.get("avg")) or 0.0)
    strikeout_delta = (_as_float(vs_right.get("strikeout_rate")) or 0.0) - (_as_float(vs_left.get("strikeout_rate")) or 0.0)
    return round((avg_delta * 1000.0) + (strikeout_delta * 100.0), 3)


def hitter_power_platoon_delta(splits: Mapping[str, Mapping[str, float]]) -> float | None:
    vs_left = splits.get("vl") if isinstance(splits.get("vl"), Mapping) else None
    vs_right = splits.get("vr") if isinstance(splits.get("vr"), Mapping) else None
    if not isinstance(vs_left, Mapping) or not isinstance(vs_right, Mapping):
        return None
    return round(((_as_float(vs_left.get("iso")) or 0.0) - (_as_float(vs_right.get("iso")) or 0.0)) * 1000.0, 3)


def hitter_split_score(split: Mapping[str, float]) -> float | None:
    if not isinstance(split, Mapping):
        return None
    obp = _as_float(split.get("obp"))
    slg = _as_float(split.get("slg"))
    iso = _as_float(split.get("iso"))
    strikeout_rate = _as_float(split.get("strikeout_rate"))
    if None in (obp, slg, iso, strikeout_rate):
        return None
    ops = (obp or 0.0) + (slg or 0.0)
    score = 50.0
    score += (ops - 0.72) * 150.0
    score += ((iso or 0.0) - 0.15) * 80.0
    score += (0.22 - (strikeout_rate or 0.0)) * 80.0
    return round(max(0.0, min(99.0, score)), 3)


def derive_hitter_situational_metrics(splits: Mapping[str, Mapping[str, float]]) -> dict[str, float | None]:
    first_pitch_score = hitter_split_score(splits.get("c00", {}))
    risp_score = hitter_split_score(splits.get("risp", {}))
    pressure_score = hitter_split_score(splits.get("lc", {}))
    late_game_score = hitter_split_score(splits.get("ig07", {}))
    trailing_score = hitter_split_score(splits.get("sbh", {}))
    bases_empty_score = hitter_split_score(splits.get("r0", {}))
    trailing_bases_empty_score = None
    if trailing_score is not None and bases_empty_score is not None:
        trailing_bases_empty_score = round(min(trailing_score, bases_empty_score), 3)
    return {
        "first_pitch_hitting": first_pitch_score,
        "risp_hitting": risp_score,
        "pressure_hitting": pressure_score,
        "late_game_hitting": late_game_score,
        "trailing_bases_empty_hitting": trailing_bases_empty_score,
    }


def pitcher_split_score(split: Mapping[str, float]) -> float | None:
    if not isinstance(split, Mapping):
        return None
    ops = _as_float(split.get("ops"))
    strikeout_rate = _as_float(split.get("strikeout_rate"))
    if None in (ops, strikeout_rate):
        return None
    score = 100.0 - max(((ops or 0.0) - 0.5) * 200.0, 0.0) + ((strikeout_rate or 0.0) * 100.0 * 0.25)
    return round(max(0.0, min(99.0, score)), 3)


def steal_suppression_score(stats: Mapping[str, Any]) -> float | None:
    stolen_bases = _as_float(stats.get("stolen_bases_allowed"))
    caught_stealing = _as_float(stats.get("caught_stealing"))
    pickoffs = _as_float(stats.get("pickoffs")) or 0.0
    stolen_base_percentage = _as_float(stats.get("stolen_base_percentage"))

    success_rate = None
    if stolen_base_percentage is not None:
        success_rate = stolen_base_percentage * 100.0 if 0.0 <= stolen_base_percentage <= 1.0 else stolen_base_percentage
    elif None not in (stolen_bases, caught_stealing):
        attempts = (stolen_bases or 0.0) + (caught_stealing or 0.0)
        if attempts > 0:
            success_rate = ((stolen_bases or 0.0) / attempts) * 100.0

    if success_rate is None:
        return None
    score = 110.0 - success_rate + (pickoffs * 4.0)
    return round(max(0.0, min(99.0, score)), 3)


def derive_pitcher_situational_metrics(
    splits: Mapping[str, Mapping[str, float]],
    season_stats: Mapping[str, Any],
) -> dict[str, float | None]:
    three_ball_scores = [
        pitcher_split_score(splits.get(code, {}))
        for code in ("c30", "c31", "c32")
        if pitcher_split_score(splits.get(code, {})) is not None
    ]
    three_ball_accuracy = round(sum(three_ball_scores) / len(three_ball_scores), 3) if three_ball_scores else None
    return {
        "first_pitch_pitching": pitcher_split_score(splits.get("c00", {})),
        "runners_on_pitching": pitcher_split_score(splits.get("ron", {})),
        "pressure_pitching": pitcher_split_score(splits.get("lc", {})),
        "three_ball_accuracy": three_ball_accuracy,
        "steal_suppression": steal_suppression_score(season_stats),
    }


def pitcher_handedness_score(throws: str | None, splits: Mapping[str, Mapping[str, float]], *, split_type: str) -> float | None:
    if throws == "L":
        key = "vl" if split_type == "same" else "vr"
    elif throws == "R":
        key = "vr" if split_type == "same" else "vl"
    else:
        return None
    split = splits.get(key) if isinstance(splits.get(key), Mapping) else None
    if not isinstance(split, Mapping):
        return None
    ops = _as_float(split.get("ops")) or 0.0
    strikeout_rate = _as_float(split.get("strikeout_rate")) or 0.0
    score = 100.0 - max((ops - 0.5) * 200.0, 0.0) + (strikeout_rate * 100.0 * 0.25)
    return round(max(0.0, min(99.0, score)), 3)


def pitcher_handedness_gap(throws: str | None, splits: Mapping[str, Mapping[str, float]], *, split_type: str) -> float | None:
    same_score = pitcher_handedness_score(throws, splits, split_type="same")
    opposite_score = pitcher_handedness_score(throws, splits, split_type="opposite")
    if same_score is None or opposite_score is None:
        return None
    if split_type == "same":
        return round(same_score - opposite_score, 3)
    if split_type == "opposite":
        return round(opposite_score - same_score, 3)
    return None


def game_log_days_on_roster(splits: Iterable[Mapping[str, Any]]) -> int | None:
    dates = [_parse_date(split.get("date")) for split in splits if isinstance(split, Mapping)]
    valid_dates = [game_date for game_date in dates if game_date is not None]
    if not valid_dates:
        return None
    return (max(valid_dates) - min(valid_dates)).days + 1