from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
HITTER_TRAIT_METRIC_COLUMNS: dict[str, tuple[tuple[str, ...], bool]] = {
    "bb_pct": (("bb_pct", "bb_percent", "walk_pct", "walk_rate"), True),
    "zone_contact_pct": (("z_contact_pct", "zone_contact_pct", "iz_contact_percent"), True),
    "out_of_zone_contact_pct": (("o_contact_pct", "out_of_zone_contact_pct", "oz_contact_percent"), True),
    "dive_recovery": (("dive_recovery", "dive_recovery_score", "fielding_recovery"), False),
    "chase_pct": (("chase_pct", "o_swing_pct", "out_of_zone_swing_pct"), True),
    "hard_hit_pct": (("hard_hit_pct", "hard_hit_rate"), True),
    "xwoba": (("xwoba",), False),
    "pull_pct": (("pull_pct",), True),
    "center_pct": (("cent_pct", "center_pct"), True),
    "oppo_pct": (("oppo_pct", "opposite_field_pct"), True),
    "ground_ball_pct": (("gb_pct", "ground_ball_pct"), True),
    "fly_ball_pct": (("fb_pct", "fly_ball_pct"), True),
    "line_drive_pct": (("ld_pct", "line_drive_pct"), True),
    "first_pitch_hitting": (("first_pitch_hitting", "first_pitch_hitting_score"), False),
    "contact_vs_lhp_minus_rhp": (("contact_vs_lhp_minus_rhp",), False),
    "power_vs_lhp_minus_rhp": (("power_vs_lhp_minus_rhp",), False),
    "trailing_bases_empty_hitting": (("trailing_bases_empty_hitting",), False),
    "risp_hitting": (("risp_hitting",), False),
    "fastball_hitting": (("fastball_hitting",), False),
    "offspeed_hitting": (("offspeed_hitting",), False),
    "zone_hitting_high": (("zone_hitting_high", "high_pitch_hitting"), False),
    "zone_hitting_low": (("zone_hitting_low", "low_pitch_hitting"), False),
    "zone_hitting_inside": (("zone_hitting_inside", "inside_pitch_hitting"), False),
    "zone_hitting_outside": (("zone_hitting_outside", "outside_pitch_hitting"), False),
    "consistency": (("consistency",), False),
    "vs_ace_hitting": (("vs_ace_hitting",), False),
    "bunt_value": (("bunt_value",), False),
    "pinch_hitting": (("pinch_hitting",), False),
    "pressure_hitting": (("pressure_hitting", "high_leverage_hitting"), False),
    "baserunning_pressure": (("baserunning_pressure", "distraction_value"), False),
    "mind_games": (("mind_games", "plate_presence"), False),
    "sign_stealing": (("sign_stealing", "pitch_pickup"), False),
    "late_game_hitting": (("late_game_hitting", "late_game_mojo"), False),
    "durability": (("durability", "availability"), False),
}

PITCHER_TRAIT_METRIC_COLUMNS: dict[str, tuple[tuple[str, ...], bool]] = {
    "durability": (("durability", "availability"), False),
    "workhorse": (("workhorse", "stamina_workload", "innings_capacity"), False),
    "pressure_pitching": (("pressure_pitching", "high_leverage_pitching"), False),
    "runners_on_pitching": (("runners_on_pitching",), False),
    "three_ball_accuracy": (("three_ball_accuracy",), False),
    "first_pitch_pitching": (("first_pitch_pitching",), False),
    "steal_suppression": (("steal_suppression", "running_game_control"), False),
    "opposite_handed_pitching": (("opposite_handed_pitching",), False),
    "opposite_handed_pitching_gap": (("opposite_handed_pitching_gap",), False),
    "same_handed_pitching": (("same_handed_pitching",), False),
    "same_handed_pitching_gap": (("same_handed_pitching_gap",), False),
    "late_game_pitching": (("late_game_pitching", "late_game_mojo"), False),
    "meltdown_risk": (("meltdown_risk", "collapse_risk"), False),
    "wildness": (("wildness", "power_pitch_wildness"), False),
    "crossed_up_risk": (("crossed_up_risk", "catcher_handling_risk"), False),
    "metal_head": (("metal_head", "comeback_recovery"), False),
    "pitch_quality_4f": (("pitch_quality_4f", "pitch_quality_ff", "pitch_quality_four_seam"), False),
    "pitch_quality_2f": (("pitch_quality_2f", "pitch_quality_ft", "pitch_quality_si", "pitch_quality_two_seam", "pitch_quality_sinker"), False),
    "pitch_quality_cf": (("pitch_quality_cf", "pitch_quality_fc", "pitch_quality_cut_fastball", "pitch_quality_cutter"), False),
    "pitch_quality_cb": (("pitch_quality_cb", "pitch_quality_curveball"), False),
    "pitch_quality_ch": (("pitch_quality_ch", "pitch_quality_changeup"), False),
    "pitch_quality_fk": (("pitch_quality_fk", "pitch_quality_fo", "pitch_quality_fs", "pitch_quality_forkball", "pitch_quality_splitter"), False),
    "pitch_quality_sl": (("pitch_quality_sl", "pitch_quality_slider"), False),
    "pitch_quality_sb": (("pitch_quality_sb", "pitch_quality_sc", "pitch_quality_screwball"), False),
}
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

from .pitch_quality import pitch_rv_per_100_score


SEASON_KEYS = ("current", "previous", "two_years_ago")
SUPPORTED_SOURCES = frozenset({"baseball_savant", "baseball_reference", "fangraphs", "mixed"})
MIXABLE_SOURCES = frozenset({"baseball_savant", "baseball_reference", "fangraphs"})
SUPPORTED_FILE_TYPES = frozenset({"hitters", "pitchers", "fielding", "running", "roster", "pitch_run_values"})

POSITION_ALIASES = {
    "C": "C",
    "CATCHER": "C",
    "1B": "1B",
    "FIRST": "1B",
    "FIRSTBASE": "1B",
    "2B": "2B",
    "SECOND": "2B",
    "SECONDBASE": "2B",
    "3B": "3B",
    "THIRD": "3B",
    "THIRDBASE": "3B",
    "SS": "SS",
    "SHORTSTOP": "SS",
    "LF": "LF",
    "LEFTFIELD": "LF",
    "CF": "CF",
    "CENTERFIELD": "CF",
    "CENTER": "CF",
    "RF": "RF",
    "RIGHTFIELD": "RF",
    "OF": "OF",
    "OUTFIELD": "OF",
    "IF": "IF",
    "INFIELD": "IF",
    "DH": "DH",
    "DESIGNATEDHITTER": "DH",
    "P": "P",
    "SP": "P",
    "RP": "P",
    "RHP": "P",
    "LHP": "P",
    "PITCHER": "P",
}

POSITION_DIFFICULTY = {
    "C": 0.98,
    "SS": 0.92,
    "CF": 0.82,
    "3B": 0.78,
    "2B": 0.76,
    "LF": 0.62,
    "RF": 0.62,
    "1B": 0.46,
    "OF": 0.60,
    "IF": 0.70,
    "DH": 0.12,
    "P": 0.35,
}

ARM_POSITION_BASELINE = {
    "C": 0.95,
    "RF": 0.85,
    "3B": 0.80,
    "SS": 0.72,
    "CF": 0.68,
    "LF": 0.58,
    "2B": 0.48,
    "1B": 0.38,
    "OF": 0.64,
    "IF": 0.60,
    "DH": 0.10,
    "P": 0.50,
}

PITCH_USAGE_COLUMNS = {
    "ff": ("ff_pct", "four_seam_pct", "fourseam_pct", "fb_pct"),
    "ft": ("ft_pct", "two_seam_pct", "twoseam_pct", "two_seamer_pct"),
    "si": ("si_pct", "sinker_pct"),
    "fc": ("fc_pct", "cutter_pct"),
    "sl": ("sl_pct", "slider_pct"),
    "cu": ("cu_pct", "curve_pct", "curveball_pct", "kc_pct"),
    "ch": ("ch_pct", "changeup_pct"),
    "fs": ("fs_pct", "splitter_pct", "splitfinger_pct"),
    "fo": ("fo_pct", "forkball_pct"),
    "sc": ("sc_pct", "screwball_pct"),
    "sv": ("sv_pct", "sweeper_pct"),
    "kn": ("kn_pct", "knuckleball_pct"),
}


REFERENCE_PATH = Path(__file__).resolve().parents[2] / "smb4_player_reference.json"
DEFAULT_INJURY_THRESHOLD = {"min_pa_fraction": 0.6, "min_ip_fraction": 0.6}
ROSTER_DAY_COLUMNS = (
    "days_on_roster",
    "days_on_active_roster",
    "active_roster_days",
    "active_days",
    "roster_days",
)

SECONDARY_FIELD_POSITION_COLUMNS = (
    "secondary_field_positions",
    "secondary_positions",
    "two_way_positions",
)

PITCH_RUN_VALUE_METRIC_KEYS = {
    "FF": "pitch_quality_4f",
    "SI": "pitch_quality_2f",
    "FT": "pitch_quality_2f",
    "FC": "pitch_quality_cf",
    "CU": "pitch_quality_cb",
    "KC": "pitch_quality_cb",
    "CH": "pitch_quality_ch",
    "FS": "pitch_quality_fk",
    "FO": "pitch_quality_fk",
    "SL": "pitch_quality_sl",
    "SV": "pitch_quality_sl",
    "SC": "pitch_quality_sb",
}

RUN_VALUE_BLEND_EXISTING_WEIGHT = 0.50
RUN_VALUE_BLEND_RV_WEIGHT = 0.50

PITCH_NAME_TO_CODE = {
    "4-SEAM FASTBALL": "FF",
    "FOUR-SEAM FASTBALL": "FF",
    "2-SEAM FASTBALL": "FT",
    "TWO-SEAM FASTBALL": "FT",
    "SINKER": "SI",
    "CUTTER": "FC",
    "CURVEBALL": "CU",
    "KNUCKLE CURVE": "KC",
    "CHANGEUP": "CH",
    "SPLITTER": "FS",
    "FORKBALL": "FO",
    "SLIDER": "SL",
    "SWEEPER": "SV",
    "SCREWBALL": "SC",
}

def load_injury_threshold_config() -> dict[str, float]:
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(DEFAULT_INJURY_THRESHOLD)

    threshold_payload = payload.get("injury_threshold", {})
    if not isinstance(threshold_payload, dict):
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


INJURY_THRESHOLD_CONFIG = load_injury_threshold_config()


def _normalized_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _normalize_field_name(value: str) -> str:
    value = value.strip().lower().replace("%", " pct ").replace("/", " ")
    pieces = [piece for piece in value.replace("-", " ").split() if piece]
    return "_".join(pieces)


def _normalize_row(row: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        if key is None:
            continue
        normalized[_normalize_field_name(key)] = value.strip() if isinstance(value, str) else value
    return normalized


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or cleaned in {"--", "-", "N/A", "n/a", "null", "None"}:
        return None
    cleaned = cleaned.replace(",", "")
    if cleaned.endswith("%"):
        try:
            return float(cleaned[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _coerce_rate(value: float | None) -> float | None:
    if value is None:
        return None
    if value > 1.0:
        return value / 100.0
    return value


def _pick_first(row: dict[str, str], *aliases: str) -> str | None:
    for alias in aliases:
        value = row.get(alias)
        if value not in (None, ""):
            return value
    return None


def _pick_number(row: dict[str, str], *aliases: str, rate: bool = False) -> float | None:
    value = _as_float(_pick_first(row, *aliases))
    return _coerce_rate(value) if rate else value


def _canonical_pitch_type(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().upper()
    if not cleaned:
        return None
    if cleaned in PITCH_RUN_VALUE_METRIC_KEYS:
        return cleaned
    return PITCH_NAME_TO_CODE.get(cleaned)


def parse_savant_pitch_run_value_csv(rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], float] = {}
    for row in rows:
        player_id = _pick_first(row, "player_id", "pitcher_id", "id", "mlb_id")
        if player_id is None:
            continue
        pitch_type = _canonical_pitch_type(_pick_first(row, "api_pitch_type", "pitch_type", "pitch"))
        if pitch_type is None:
            continue
        run_value_per_100 = _pick_number(
            row,
            "run_value_per_100",
            "rv_per_100",
            "run_value_per_100_pitches",
            "run_value_per_100_pitch",
        )
        if run_value_per_100 is None:
            continue
        values[(player_id.strip(), pitch_type)] = float(run_value_per_100)
    return values


def _apply_pitch_run_values_to_trait_metrics(
    player: PlayerAccumulator,
    season_key: str,
    pitch_run_values: dict[str, float],
) -> None:
    for pitch_type, run_value_per_100 in pitch_run_values.items():
        metric_key = PITCH_RUN_VALUE_METRIC_KEYS.get(pitch_type)
        if metric_key is None:
            continue
        rv_score = pitch_rv_per_100_score(run_value_per_100)
        existing = player.trait_metrics.get(metric_key, {}).get(season_key)
        if existing is None:
            merged_score = rv_score
        else:
            merged_score = round(
                (float(existing) * RUN_VALUE_BLEND_EXISTING_WEIGHT)
                + (rv_score * RUN_VALUE_BLEND_RV_WEIGHT),
                3,
            )
        player.set_trait_metric(metric_key, season_key, merged_score)


def _percentile_rank(value: float, peers: list[float]) -> float:
    if not peers:
        return 50.0
    less_than = sum(peer < value for peer in peers)
    equal_to = sum(peer == value for peer in peers)
    return 100.0 * (less_than + 0.5 * equal_to) / len(peers)


def _pick_percentage_points(row: dict[str, str], *aliases: str) -> float | None:
    raw_value = _pick_first(row, *aliases)
    if raw_value is None:
        return None
    value = _as_float(raw_value)
    if value is None:
        return None
    if isinstance(raw_value, str) and "%" in raw_value:
        return value * 100.0
    if 0.0 <= value <= 1.0:
        return value * 100.0
    return value


def _row_trait_metrics(row: dict[str, str], specs: dict[str, tuple[tuple[str, ...], bool]]) -> dict[str, float]:
    trait_metrics: dict[str, float] = {}
    for metric_name, (aliases, percent_like) in specs.items():
        value = _pick_percentage_points(row, *aliases) if percent_like else _pick_number(row, *aliases)
        if value is not None:
            trait_metrics[metric_name] = round(float(value), 6)
    return trait_metrics


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _estimate_chase_rate_from_whiff_rate(swinging_strike_rate: float | None) -> float | None:
    if swinging_strike_rate is None:
        return None
    return _clamp(0.12 + (swinging_strike_rate * 1.4), 0.18, 0.45)


def _estimate_zone_pct_from_strike_pct(strike_pct: float | None) -> float | None:
    if strike_pct is None:
        return None
    return _clamp(strike_pct - 0.15, 0.35, 0.60)


def _estimate_first_pitch_strike_pct(
    strike_pct: float | None,
    zone_pct: float | None,
) -> float | None:
    if zone_pct is not None:
        return _clamp(zone_pct + 0.13, 0.45, 0.75)
    if strike_pct is not None:
        return _clamp(strike_pct - 0.02, 0.45, 0.75)
    return None


def _normalize_distribution(values: dict[str, float]) -> dict[str, float]:
    total = sum(values.values())
    if total <= 0:
        return {}
    return {key: round(value / total, 6) for key, value in sorted(values.items()) if value > 0}


def _clamp(value: float | None, minimum: float, maximum: float) -> float | None:
    if value is None:
        return None
    return max(minimum, min(maximum, value))


def _canonical_position(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    cleaned = _normalized_key(raw_value)
    return POSITION_ALIASES.get(cleaned.upper()) or POSITION_ALIASES.get(cleaned)


def _canonical_positions(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    pieces = (
        raw_value.replace("/", ",")
        .replace(";", ",")
        .replace("|", ",")
        .replace("-", ",")
        .split(",")
    )
    positions: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        position = _canonical_position(piece.strip())
        if position is None or position in seen:
            continue
        seen.add(position)
        positions.append(position)
    return positions


def _row_positions(row: dict[str, str]) -> list[str]:
    candidates: list[str] = []
    for field_name in ("primary_position", "position", "pos", "fielding_position", "mlb_pos"):
        raw_value = _pick_first(row, field_name)
        if isinstance(raw_value, str) and raw_value.strip():
            candidates.extend(_canonical_positions(raw_value))
    for field_name in SECONDARY_FIELD_POSITION_COLUMNS:
        raw_value = _pick_first(row, field_name)
        if isinstance(raw_value, str) and raw_value.strip():
            candidates.extend(_canonical_positions(raw_value))
    raw_secondary = _pick_first(row, "secondary_position", "secondary_pos")
    if isinstance(raw_secondary, str) and raw_secondary.strip():
        candidates.extend(_canonical_positions(raw_secondary))

    ordered: list[str] = []
    seen: set[str] = set()
    for position in candidates:
        if position in seen:
            continue
        seen.add(position)
        ordered.append(position)
    return ordered


def _row_player_name(row: dict[str, str]) -> str | None:
    direct = _pick_first(row, "player_name", "player", "name", "full_name")
    if direct:
        return direct
    first_name = _pick_first(row, "first_name", "firstname")
    last_name = _pick_first(row, "last_name", "lastname")
    if first_name or last_name:
        return " ".join(part for part in (first_name, last_name) if part)
    return None


def _row_player_id(row: dict[str, str]) -> str | None:
    raw = _pick_first(row, "player_id", "mlbam_id", "batter", "pitcher", "playerid", "id")
    if raw is None:
        return None
    numeric = _as_float(raw)
    if numeric is not None:
        return str(int(numeric))
    return raw.strip() or None


def _normalized_name(name: str) -> str:
    return " ".join(name.lower().split())


def _row_pitch_mix(row: dict[str, str]) -> dict[str, float]:
    pitch_mix: dict[str, float] = {}
    for pitch_code, aliases in PITCH_USAGE_COLUMNS.items():
        value = _pick_number(row, *aliases, rate=True)
        if value is not None and value > 0:
            pitch_mix[pitch_code] = value
    return _normalize_distribution(pitch_mix)


def _row_days_on_roster(row: dict[str, str]) -> float | None:
    return _pick_number(row, *ROSTER_DAY_COLUMNS)


def _position_group_from_code(position: str | None) -> str | None:
    if position == "C":
        return "C"
    if position in {"1B", "2B", "3B", "SS", "IF"}:
        return "IF"
    if position in {"LF", "CF", "RF", "OF"}:
        return "OF"
    return None


def _row_secondary_field_positions(row: dict[str, str]) -> list[str]:
    groups: set[str] = set()
    raw_positions = _pick_first(row, *SECONDARY_FIELD_POSITION_COLUMNS)
    if raw_positions:
        for piece in raw_positions.replace("/", ",").replace(";", ",").split(","):
            group = _position_group_from_code(_canonical_position(piece.strip()))
            if group is not None:
                groups.add(group)
    secondary_position = _position_group_from_code(_canonical_position(_pick_first(row, "secondary_position", "secondary_pos")))
    if secondary_position is not None:
        groups.add(secondary_position)
    return sorted(groups)


@dataclass(slots=True)
class SeasonInputs:
    year: int | None = None
    files: dict[str, Path] = field(default_factory=dict)
    source_files: dict[str, dict[str, Path]] = field(default_factory=dict)


@dataclass(slots=True)
class RosterFilter:
    team: str
    year: int


@dataclass(slots=True)
class IngestManifest:
    source: str
    seasons: dict[str, SeasonInputs]
    manifest_path: Path
    roster_filter: RosterFilter | None = None


@dataclass(slots=True)
class PlayerAccumulator:
    name: str
    source: str = "baseball_savant"
    source_id: str | None = None
    active: bool = True
    matched_current_roster_filter: bool = False
    roster_status: str | None = None
    roster_status_code: str | None = None
    team: str | None = None
    age: int | None = None
    primary_position: str | None = None
    secondary_position: str | None = None
    bats: str | None = None
    throws: str | None = None
    roles: set[str] = field(default_factory=set)
    metrics: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    samples: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    trait_metrics: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    trait_lists: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    days_on_roster_by_season: dict[str, float] = field(default_factory=dict)
    positional_games: dict[str, float] = field(default_factory=dict)
    pitch_mix_by_season: dict[str, dict[str, float]] = field(default_factory=lambda: defaultdict(dict))
    estimated_metrics: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    missing_files: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    injury_shortened_seasons: set[str] = field(default_factory=set)
    source_years: dict[str, int] = field(default_factory=dict)

    def set_metric(self, metric_name: str, season_key: str, value: float | None, estimated: bool = False) -> None:
        if value is None:
            return
        self.metrics[metric_name][season_key] = round(float(value), 6)
        if estimated and metric_name not in self.estimated_metrics[season_key]:
            self.estimated_metrics[season_key].append(metric_name)

    def set_sample(self, sample_name: str, season_key: str, value: float | None) -> None:
        if value is None:
            return
        self.samples[sample_name][season_key] = round(float(value), 6)

    def set_trait_metric(self, metric_name: str, season_key: str, value: float | None) -> None:
        if value is None:
            return
        self.trait_metrics[metric_name][season_key] = round(float(value), 6)

    def set_trait_metrics(self, season_key: str, values: dict[str, float]) -> None:
        for metric_name, value in values.items():
            self.set_trait_metric(metric_name, season_key, value)

    def add_trait_list_values(self, list_name: str, values: list[str]) -> None:
        if not values:
            return
        self.trait_lists[list_name].update(value for value in values if value)

    def note_missing_file(self, season_key: str, file_type: str) -> None:
        if file_type not in self.missing_files[season_key]:
            self.missing_files[season_key].append(file_type)

    def set_days_on_roster(self, season_key: str, value: float | None) -> None:
        if value is None or value <= 0:
            return
        self.days_on_roster_by_season[season_key] = round(float(value), 6)

    def set_pitch_mix(self, season_key: str, pitch_mix: dict[str, float]) -> None:
        if not pitch_mix:
            return
        self.pitch_mix_by_season[season_key] = dict(sorted(pitch_mix.items()))

    def add_positional_games(self, position: str | None, value: float | None) -> None:
        if position is None or value is None or value <= 0:
            return
        self.positional_games[position] = round(self.positional_games.get(position, 0.0) + float(value), 6)

    def aggregated_pitch_mix(self) -> dict[str, float]:
        weighted_totals: dict[str, float] = defaultdict(float)
        total_weight = 0.0
        fallback_totals: dict[str, float] = defaultdict(float)
        fallback_count = 0
        for season_key, season_mix in sorted(self.pitch_mix_by_season.items()):
            if not season_mix:
                continue
            tracked_pitches = self.samples.get("tracked_pitches", {}).get(season_key)
            if tracked_pitches is not None and tracked_pitches > 0:
                total_weight += tracked_pitches
                for pitch_code, usage in season_mix.items():
                    weighted_totals[pitch_code] += usage * tracked_pitches
                continue
            fallback_count += 1
            for pitch_code, usage in season_mix.items():
                fallback_totals[pitch_code] += usage
        if total_weight > 0:
            return _normalize_distribution(weighted_totals)
        if fallback_count > 0:
            return _normalize_distribution(fallback_totals)
        return {}

    def to_player_dict(self) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "source": self.source,
            "source_years": dict(sorted(self.source_years.items())),
            "ingest": {
                "estimated_metrics": {season: sorted(values) for season, values in sorted(self.estimated_metrics.items()) if values},
                "missing_files": {season: sorted(values) for season, values in sorted(self.missing_files.items()) if values},
                "injury_shortened": {season: True for season in sorted(self.injury_shortened_seasons)},
            },
        }
        if self.source_id:
            metadata["source_player_id"] = self.source_id
        if self.roster_status:
            metadata["status"] = self.roster_status
            metadata["on_il"] = _is_injured_list_or_rehab(self.roster_status, self.roster_status_code)
        if self.roster_status_code:
            metadata["status_code"] = self.roster_status_code
        role = "two_way" if {"hitter", "pitcher"}.issubset(self.roles) else ("pitcher" if "pitcher" in self.roles else "hitter")
        player_dict = {
            "name": self.name,
            "role": role,
            "player_id": self.source_id,
            "on_il": metadata.get("on_il") if isinstance(metadata.get("on_il"), bool) else None,
            "active": self.active,
            "team": self.team,
            "age": self.age,
            "primary_position": self.primary_position,
            "secondary_position": self.secondary_position,
            "bats": self.bats,
            "throws": self.throws,
            "metrics": {name: dict(sorted(values.items())) for name, values in sorted(self.metrics.items()) if values},
            "samples": {name: dict(sorted(values.items())) for name, values in sorted(self.samples.items()) if values},
            "metadata": metadata,
        }
        if self.days_on_roster_by_season:
            player_dict["days_on_roster"] = dict(sorted(self.days_on_roster_by_season.items()))
        if self.positional_games:
            player_dict["positional_games"] = dict(sorted(self.positional_games.items()))
        pitch_mix = self.aggregated_pitch_mix()
        if pitch_mix:
            player_dict["pitch_mix"] = pitch_mix

        if self.trait_metrics:
            player_dict["trait_metrics"] = {
                name: dict(sorted(values.items()))
                for name, values in sorted(self.trait_metrics.items())
                if values
            }
        if self.trait_lists:
            player_dict["trait_lists"] = {
                name: sorted(values)
                for name, values in sorted(self.trait_lists.items())
                if values
            }
        return player_dict


def load_manifest(path: Path) -> IngestManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    source = str(data.get("source", "")).strip().lower()
    if source not in SUPPORTED_SOURCES:
        raise ValueError("Manifest source must be one of: baseball_savant, baseball_reference, fangraphs, mixed")

    raw_seasons = data.get("seasons")
    if not isinstance(raw_seasons, dict):
        raise ValueError("Manifest must contain a 'seasons' object")

    seasons: dict[str, SeasonInputs] = {}
    base_dir = path.parent
    roster_filter_payload = data.get("roster_filter")
    roster_filter: RosterFilter | None = None
    if roster_filter_payload is not None:
        if not isinstance(roster_filter_payload, dict):
            raise ValueError("Manifest roster_filter must be an object")
        team_value = roster_filter_payload.get("team")
        year_value = roster_filter_payload.get("year")
        if not isinstance(team_value, str) or not team_value.strip():
            raise ValueError("Manifest roster_filter.team must be a non-empty string")
        if year_value is None:
            raise ValueError("Manifest roster_filter.year is required")
        roster_filter = RosterFilter(team=team_value.strip().upper(), year=int(year_value))

    def resolve_files(files_payload: dict[str, object], season_key: str) -> dict[str, Path]:
        files: dict[str, Path] = {}
        for file_type, raw_path in files_payload.items():
            if file_type not in SUPPORTED_FILE_TYPES:
                raise ValueError(f"Unsupported file type '{file_type}' in season '{season_key}'")
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"File path for '{file_type}' in season '{season_key}' must be a non-empty string")
            file_path = Path(raw_path)
            if not file_path.is_absolute():
                file_path = base_dir / file_path
            files[file_type] = file_path.resolve()
        return files

    for season_key, payload in raw_seasons.items():
        if season_key not in SEASON_KEYS:
            raise ValueError(f"Unsupported season key '{season_key}'. Expected one of {', '.join(SEASON_KEYS)}")
        if not isinstance(payload, dict):
            raise ValueError(f"Season '{season_key}' must be an object")

        year_value = payload.get("year")
        year = int(year_value) if year_value is not None else None
        if source == "mixed":
            raw_sources = payload.get("sources")
            if not isinstance(raw_sources, dict):
                raise ValueError(f"Mixed season '{season_key}' must contain a 'sources' object")
            source_files: dict[str, dict[str, Path]] = {}
            for nested_source, nested_payload in raw_sources.items():
                if nested_source not in MIXABLE_SOURCES:
                    raise ValueError(f"Unsupported mixed source '{nested_source}' in season '{season_key}'")
                if not isinstance(nested_payload, dict):
                    raise ValueError(f"Mixed source '{nested_source}' in season '{season_key}' must be an object")
                files_payload = nested_payload.get("files", {})
                if not isinstance(files_payload, dict):
                    raise ValueError(f"Mixed source '{nested_source}' files in season '{season_key}' must be an object")
                source_files[nested_source] = resolve_files(files_payload, season_key)
            seasons[season_key] = SeasonInputs(year=year, files={}, source_files=source_files)
        else:
            files_payload = payload.get("files", {})
            if not isinstance(files_payload, dict):
                raise ValueError(f"Season '{season_key}' files must be an object")
            seasons[season_key] = SeasonInputs(year=year, files=resolve_files(files_payload, season_key))

    if not seasons:
        raise ValueError("Manifest must declare at least one season")

    return IngestManifest(source=source, seasons=seasons, manifest_path=path, roster_filter=roster_filter)


def _normalized_team(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned.upper()


def _is_injured_list_or_rehab(status: str | None, status_code: str | None) -> bool:
    normalized_status = status.lower() if isinstance(status, str) else ""
    if "injured" in normalized_status or "rehab" in normalized_status:
        return True
    normalized_code = status_code.upper() if isinstance(status_code, str) else ""
    return normalized_code in {"D10", "D15", "D60", "IL10", "IL15", "IL60", "RL"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [_normalize_row(row) for row in reader if any((value or "").strip() for value in row.values())]


def _player_key(row: dict[str, str], *, season_year: int | None = None) -> tuple[str, str]:
    player_id = _row_player_id(row)
    if player_id:
        return ("id", player_id)
    name = _row_player_name(row)
    if not name:
        raise ValueError("CSV row is missing both player id and player name")
    normalized_name = _normalized_name(name)
    team = _normalized_team(_pick_first(row, "team", "team_abbr", "team_name", "last_team")) or ""
    primary_position = _canonical_position(_pick_first(row, "primary_position", "position", "pos", "fielding_position", "mlb_pos")) or ""
    role = "pitcher" if primary_position == "P" else "hitter"
    season_text = str(season_year) if season_year is not None else ""
    return ("composite", f"{normalized_name}|{team}|{primary_position}|{role}|{season_text}")


def _ensure_player(
    players: dict[tuple[str, str], PlayerAccumulator],
    row: dict[str, str],
    *,
    source: str = "baseball_savant",
    season_year: int | None = None,
) -> PlayerAccumulator:
    key = _player_key(row, season_year=season_year)
    player = players.get(key)
    if player is None:
        player = PlayerAccumulator(name=_row_player_name(row) or key[1], source=source, source_id=_row_player_id(row))
        players[key] = player
    player.source = source
    if player.source_id is None:
        player.source_id = _row_player_id(row)
    return player


def _mark_active_status(
    player: PlayerAccumulator,
    row: dict[str, str],
    *,
    season_key: str | None,
    season_year: int | None,
    roster_filter: RosterFilter | None,
    is_roster_row: bool = False,
) -> None:
    if roster_filter is None or season_year != roster_filter.year or season_key != "current":
        return
    row_team = _normalized_team(_pick_first(row, "team", "team_abbr", "team_name", "last_team"))
    if is_roster_row:
        if row_team == roster_filter.team:
            player.matched_current_roster_filter = True
            player.active = True
        elif row_team is not None and row_team != roster_filter.team:
            player.active = False
        return
    if player.matched_current_roster_filter:
        return
    if row_team is not None and row_team != roster_filter.team:
        player.active = False


def _apply_identity(player: PlayerAccumulator, row: dict[str, str], *, default_position: str | None = None) -> None:
    team = _pick_first(row, "team", "team_abbr", "team_name", "last_team")
    if team:
        player.team = team
    roster_status = _pick_first(row, "status", "status_description", "roster_status")
    if roster_status:
        player.roster_status = roster_status
    roster_status_code = _pick_first(row, "status_code", "statuscode", "roster_status_code")
    if roster_status_code:
        player.roster_status_code = roster_status_code
    age_value = _pick_number(row, "age")
    if age_value is not None:
        player.age = int(age_value)
    row_positions = _row_positions(row)
    primary_position = row_positions[0] if row_positions else None
    if primary_position:
        player.primary_position = primary_position
    elif default_position and player.primary_position is None:
        player.primary_position = default_position
    secondary_position = row_positions[1] if len(row_positions) > 1 else _canonical_position(_pick_first(row, "secondary_position", "secondary_pos"))
    if secondary_position:
        player.secondary_position = secondary_position
    if player.primary_position in row_positions:
        start_index = row_positions.index(player.primary_position) + 1
        for alternate_position in row_positions[start_index:]:
            player.add_positional_games(alternate_position, 1.0)
    player.add_trait_list_values("secondary_field_positions", _row_secondary_field_positions(row))
    bats = _pick_first(row, "bats", "bat_side", "stand", "stands")
    if bats:
        player.bats = bats
    throws = _pick_first(row, "throws", "pitch_hand", "throws_hand", "p_throws")
    if throws:
        player.throws = throws


def _apply_roster_rows(
    players: dict[tuple[str, str], PlayerAccumulator],
    rows: list[dict[str, str]],
    *,
    source: str = "baseball_savant",
    season_key: str | None = None,
    season_year: int | None = None,
    roster_filter: RosterFilter | None = None,
) -> None:
    for row in rows:
        player = _ensure_player(players, row, source=source, season_year=season_year)
        if season_key is not None and season_year is not None:
            player.source_years[season_key] = season_year
        _mark_active_status(
            player,
            row,
            season_key=season_key,
            season_year=season_year,
            roster_filter=roster_filter,
            is_roster_row=True,
        )
        _apply_identity(player, row)


def _finalize_active_status(
    players: dict[tuple[str, str], PlayerAccumulator],
    *,
    roster_filter: RosterFilter | None,
) -> None:
    if roster_filter is None:
        return
    for player in players.values():
        if player.matched_current_roster_filter:
            continue
        if "current" not in player.source_years:
            player.active = False


def _position_metric(position: str | None, mapping: dict[str, float], default: float | None = None) -> float | None:
    if position is None:
        return default
    return mapping.get(position, default)


def _pitcher_season_ip(player: PlayerAccumulator, season_key: str) -> float | None:
    defensive_innings = player.samples.get("defensive_innings", {}).get(season_key)
    if defensive_innings is not None:
        return float(defensive_innings)
    weighted_bf = player.samples.get("weighted_bf", {}).get(season_key)
    if weighted_bf is None:
        return None
    return float(weighted_bf) / 4.25


def _flag_injury_shortened_seasons(players: dict[tuple[str, str], PlayerAccumulator]) -> None:
    season_keys = sorted({season_key for player in players.values() for season_key in player.source_years})
    min_pa_fraction = INJURY_THRESHOLD_CONFIG["min_pa_fraction"]
    min_ip_fraction = INJURY_THRESHOLD_CONFIG["min_ip_fraction"]

    for season_key in season_keys:
        hitter_volumes = [
            float(volume)
            for player in players.values()
            if "hitter" in player.roles and (volume := player.samples.get("weighted_pa", {}).get(season_key)) is not None and volume > 0
        ]
        pitcher_volumes = [
            float(volume)
            for player in players.values()
            if "pitcher" in player.roles and (volume := _pitcher_season_ip(player, season_key)) is not None and volume > 0
        ]

        hitter_median = median(hitter_volumes) if hitter_volumes else None
        pitcher_median = median(pitcher_volumes) if pitcher_volumes else None

        for player in players.values():
            if hitter_median is not None and "hitter" in player.roles:
                plate_appearances = player.samples.get("weighted_pa", {}).get(season_key)
                if plate_appearances is not None and plate_appearances < hitter_median * min_pa_fraction:
                    player.injury_shortened_seasons.add(season_key)
            if pitcher_median is not None and "pitcher" in player.roles:
                innings_pitched = _pitcher_season_ip(player, season_key)
                if innings_pitched is not None and innings_pitched < pitcher_median * min_ip_fraction:
                    player.injury_shortened_seasons.add(season_key)


def _apply_hitter_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    player.roles.add("hitter")
    _apply_identity(player, row)
    player.set_days_on_roster(season_key, _row_days_on_roster(row))
    player.set_trait_metrics(season_key, _row_trait_metrics(row, HITTER_TRAIT_METRIC_COLUMNS))

    plate_appearances = _pick_number(row, "pa", "plate_appearances")
    at_bats = _pick_number(row, "ab", "at_bats")
    hits = _pick_number(row, "h", "hits")
    doubles = _pick_number(row, "2b", "doubles")
    triples = _pick_number(row, "3b", "triples")
    home_runs = _pick_number(row, "hr", "home_runs")
    walks = _pick_number(row, "bb", "walks")
    hit_by_pitch = _pick_number(row, "hbp", "hit_by_pitch")
    stolen_bases = _pick_number(row, "sb", "stolen_bases")
    caught_stealing = _pick_number(row, "cs", "caught_stealing")

    singles = None
    if hits is not None:
        singles = hits - (doubles or 0) - (triples or 0) - (home_runs or 0)
        singles = max(singles, 0)

    strikeout_rate = _pick_number(row, "k_pct", "k_percent", "strikeout_rate", "strikeout_pct", rate=True)
    contact_rate = _pick_number(row, "contact_rate", "contact_pct", "contact_percent", rate=True)
    if contact_rate is None:
        whiff_rate = _pick_number(row, "whiff_rate", "whiff_pct", "whiff_percent", rate=True)
        if whiff_rate is not None:
            contact_rate = _clamp(1.0 - whiff_rate, 0.0, 1.0)

    adjusted_obp = _pick_number(row, "adjusted_obp", "obp", "on_base_pct", "on_base_percentage", "xobp")
    baserunning_value = _pick_number(row, "baserunning_value", "bsr", "running_value", "baserunning_run_value")
    if baserunning_value is None and stolen_bases is not None:
        baserunning_value = stolen_bases - ((caught_stealing or 0) * 1.5)
        player.estimated_metrics[season_key].append("baserunning_value")

    baserunning_opportunities = _pick_number(row, "baserunning_opportunities", "br_opportunities")
    if baserunning_opportunities is None and any(value is not None for value in (singles, walks, hit_by_pitch)):
        baserunning_opportunities = max((singles or 0) + (walks or 0) + (hit_by_pitch or 0), 1)

    steal_attempts = None
    if stolen_bases is not None or caught_stealing is not None:
        steal_attempts = (stolen_bases or 0) + (caught_stealing or 0)

    metric_specs = {
        "iso": (_pick_number(row, "iso", "isolated_power"), False),
        "hr_per_pa": (_safe_divide(home_runs, plate_appearances), home_runs is not None and plate_appearances is not None),
        "barrel_rate": (_pick_number(row, "barrel_rate", "barrel_pct", "barrel_percent", "barrels_per_bbe", "brl_percent", "barrel", rate=True), False),
        "slugging": (_pick_number(row, "slg", "slugging", "slugging_pct"), False),
        "avg_exit_velocity": (_pick_number(row, "avg_exit_velocity", "avg_hit_speed", "ev", "exit_velocity_avg", "avg_ev", "exit_velocity"), False),
        "strikeout_rate": (strikeout_rate, False),
        "contact_rate": (contact_rate, contact_rate is not None and _pick_first(row, "contact_rate", "contact_pct", "contact_percent") is None),
        "batting_average": (_pick_number(row, "batting_average", "avg", "ba"), False),
        "adjusted_obp": (adjusted_obp, adjusted_obp is not None and _pick_first(row, "adjusted_obp") is None),
        "sprint_speed": (_pick_number(row, "sprint_speed", "sprint_speed_ft_sec", "spdscr"), False),
        "baserunning_value": (baserunning_value, _pick_first(row, "baserunning_value", "bsr", "running_value", "baserunning_run_value") is None and baserunning_value is not None),
        "sb_attempt_rate": (_safe_divide(steal_attempts, baserunning_opportunities or plate_appearances), steal_attempts is not None),
        "sb_success_rate": (_safe_divide(stolen_bases, steal_attempts), steal_attempts is not None),
        "triple_double_rate": (_safe_divide((doubles or 0) + (triples or 0), plate_appearances), doubles is not None or triples is not None),
    }

    for metric_name, (value, estimated) in metric_specs.items():
        player.set_metric(metric_name, season_key, value, estimated=estimated)

    player.set_sample("weighted_pa", season_key, plate_appearances)
    player.set_sample("baserunning_opportunities", season_key, baserunning_opportunities)


def _apply_pitcher_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    player.roles.add("pitcher")
    _apply_identity(player, row, default_position="P")
    player.set_days_on_roster(season_key, _row_days_on_roster(row))
    player.set_trait_metrics(season_key, _row_trait_metrics(row, PITCHER_TRAIT_METRIC_COLUMNS))

    pitch_mix = _row_pitch_mix(row)
    tracked_pitches = _pick_number(row, "pitches", "tracked_pitches", "pitch_count", "total_pitches")
    batters_faced = _pick_number(row, "bf", "batters_faced")
    fastball_usage = _pick_number(row, "fastball_usage", "fastball_pct", "ff_pct", rate=True)
    tracked_fastballs = _pick_number(row, "tracked_fastballs", "fastballs", "ff")
    if tracked_fastballs is None and tracked_pitches is not None and fastball_usage is not None:
        tracked_fastballs = tracked_pitches * fastball_usage

    swinging_strike_rate = _pick_number(row, "swinging_strike_rate", "swstr_rate", "swstr_pct", rate=True)
    chase_rate = _pick_number(
        row,
        "chase_rate",
        "chase_pct",
        "chase_percent",
        "oz_swing_pct",
        "o_swing_pct",
        "out_of_zone_swing_pct",
        rate=True,
    )
    chase_rate_estimated = False
    if chase_rate is None:
        chase_rate = _estimate_chase_rate_from_whiff_rate(swinging_strike_rate)
        chase_rate_estimated = chase_rate is not None
    strike_pct = _pick_number(row, "strike_pct", "strk_pct", rate=True)
    zone_pct = _pick_number(row, "zone_pct", "zone_percent", "zone_percentage", rate=True)
    zone_pct_estimated = False
    if zone_pct is None:
        zone_pct = _estimate_zone_pct_from_strike_pct(strike_pct)
        zone_pct_estimated = zone_pct is not None
    first_pitch_strike_pct = _pick_number(
        row,
        "first_pitch_strike_pct",
        "first_pitch_strike_percent",
        "f_strike_pct",
        "f_strike_percent",
        "fps_pct",
        rate=True,
    )
    first_pitch_strike_pct_estimated = False
    if first_pitch_strike_pct is None:
        first_pitch_strike_pct = _estimate_first_pitch_strike_pct(strike_pct, zone_pct)
        first_pitch_strike_pct_estimated = first_pitch_strike_pct is not None

    horizontal_break = _pick_number(row, "horizontal_break", "horizontal_movement", "hb", "avg_horz_break", "pfx_x")
    induced_vertical_break = _pick_number(
        row,
        "induced_vertical_break",
        "vertical_break",
        "ivb",
        "avg_induced_vert_break",
        "pfx_z",
    )
    movement_quality = _pick_number(row, "movement_quality", "movement_plus", "movement_grade")
    movement_estimated = False
    if movement_quality is None and (horizontal_break is not None or induced_vertical_break is not None):
        movement_quality = abs(horizontal_break or 0) + abs(induced_vertical_break or 0)
        movement_estimated = True

    stuff_metric = _pick_number(row, "stuff_metric", "stuff_plus", "stuff", "pitching_plus")
    stuff_estimated = False
    if stuff_metric is None:
        velocity = _pick_number(row, "avg_fastball_velocity", "avg_fb_velocity", "avg_fastball_speed", "release_speed")
        if velocity is not None and swinging_strike_rate is not None and chase_rate is not None:
            stuff_metric = (velocity - 85.0) * 2.0 + swinging_strike_rate * 100.0 + chase_rate * 60.0
            stuff_estimated = True

    arsenal_diversity = _pick_number(row, "arsenal_diversity", "pitch_mix_diversity")
    arsenal_estimated = False
    if arsenal_diversity is None:
        usage_values = list(pitch_mix.values())
        usage_sum = sum(usage_values)
        if usage_sum > 0 and len(usage_values) > 1:
            normalized_values = [value / usage_sum for value in usage_values]
            entropy = -sum(value * math.log(value) for value in normalized_values if value > 0)
            arsenal_diversity = entropy / math.log(len(normalized_values))
            arsenal_estimated = True

    weak_contact_rate = _pick_number(row, "weak_contact_rate", "weak_pct", "weak_percent", rate=True)
    weak_contact_estimated = False
    if weak_contact_rate is None:
        hard_hit_rate = _pick_number(row, "hard_hit_rate", "hard_hit_pct", "hard_hit_percent", rate=True)
        if hard_hit_rate is not None:
            weak_contact_rate = _clamp(1.0 - hard_hit_rate, 0.0, 1.0)
            weak_contact_estimated = True

    command_error_rate = _pick_number(row, "command_error_rate", "ball_pct", "miss_zone_pct", rate=True)
    command_error_estimated = False
    if command_error_rate is None and strike_pct is not None:
        command_error_rate = _clamp(1.0 - strike_pct, 0.0, 1.0)
        command_error_estimated = True

    metric_specs = {
        "avg_fastball_velocity": (_pick_number(row, "avg_fastball_velocity", "avg_fb_velocity", "avg_fastball_speed", "release_speed"), False),
        "peak_fastball_velocity": (_pick_number(row, "peak_fastball_velocity", "max_fastball_velocity", "max_fb_velocity", "release_speed_max"), False),
        "fastball_usage": (fastball_usage, False),
        "swinging_strike_rate": (swinging_strike_rate, False),
        "chase_rate": (chase_rate, chase_rate_estimated),
        "movement_quality": (movement_quality, movement_estimated),
        "stuff_metric": (stuff_metric, stuff_estimated),
        "arsenal_diversity": (arsenal_diversity, arsenal_estimated),
        "weak_contact_rate": (weak_contact_rate, weak_contact_estimated),
        "walk_rate": (_pick_number(row, "walk_rate", "bb_pct", "bb_percent", rate=True), False),
        "strike_pct": (strike_pct, False),
        "zone_pct": (zone_pct, zone_pct_estimated),
        "first_pitch_strike_pct": (first_pitch_strike_pct, first_pitch_strike_pct_estimated),
        "command_error_rate": (command_error_rate, command_error_estimated),
    }
    for metric_name, (value, estimated) in metric_specs.items():
        player.set_metric(metric_name, season_key, value, estimated=estimated)

    player.set_sample("weighted_bf", season_key, batters_faced)
    player.set_sample("tracked_pitches", season_key, tracked_pitches)
    player.set_sample("tracked_fastballs", season_key, tracked_fastballs)
    player.set_pitch_mix(season_key, pitch_mix)


def _should_apply_pitcher_row(player: PlayerAccumulator, row: dict[str, str]) -> bool:
    row_position = _canonical_position(_pick_first(row, "primary_position", "position", "pos", "fielding_position", "mlb_pos"))
    if row_position is not None and row_position != "P":
        return False
    if player.primary_position is not None and player.primary_position != "P" and "pitcher" not in player.roles:
        return False
    return True


def _apply_fielding_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    # Expected leaderboard CSVs for specialized defensive inputs:
    # - https://baseballsavant.mlb.com/leaderboard/outs_above_average -> oaa / outs_above_average, innings
    # - https://baseballsavant.mlb.com/leaderboard/arm-strength -> arm_strength / throw_speed
    # - https://baseballsavant.mlb.com/leaderboard/poptime -> pop_time, catcher_throw_value / cs_above_average
    # - https://baseballsavant.mlb.com/catcher_framing -> framing_runs
    # - outfield arm exports usually expose outfield_arm_runs as arm_value or outfielder_jump_runs
    _apply_identity(player, row)
    player.set_trait_metrics(season_key, _row_trait_metrics(row, HITTER_TRAIT_METRIC_COLUMNS))
    innings = _pick_number(row, "defensive_innings", "innings", "inn", "fielding_innings")
    games = _pick_number(row, "g", "games", "fielding_games")
    row_positions = _row_positions(row)
    position = row_positions[0] if row_positions else (_canonical_position(_pick_first(row, "position", "pos", "primary_position")) or player.primary_position)
    oaa = _pick_number(row, "oaa", "outs_above_average")
    drs = _pick_number(row, "drs", "defensive_runs_saved", "drs_total")
    uzr = _pick_number(row, "uzr", "uzr_150", "ultimate_zone_rating")
    fielding_pct = _pick_number(row, "fielding_pct_proxy", "fielding_pct", "fld_pct")
    if fielding_pct is None:
        putouts = _pick_number(row, "po", "putouts")
        assists = _pick_number(row, "a", "assists")
        errors = _pick_number(row, "e", "errors")
        chances = None
        if putouts is not None or assists is not None or errors is not None:
            chances = (putouts or 0) + (assists or 0) + (errors or 0)
        fielding_pct = _safe_divide((putouts or 0) + (assists or 0), chances)
    arm_strength = _pick_number(row, "arm_strength", "arm_strength_avg", "throw_speed", "avg_throw_speed")
    catcher_throw_value = _pick_number(row, "catcher_throw_value", "caught_stealing_above_average", "cs_above_average")
    outfield_arm_runs = _pick_number(row, "outfield_arm_runs", "arm_value", "outfielder_jump_runs")
    pop_time = _pick_number(row, "pop_time", "pop_2b_sba", "exchange_2b_sba", "pop_time_2b", "avg_pop_time_2b")
    framing_runs = _pick_number(row, "framing_runs", "framing", "framing_run_value", "catcher_framing_runs")

    player.set_metric("oaa", season_key, oaa)
    player.set_metric("drs", season_key, drs)
    player.set_metric("uzr", season_key, uzr)
    player.set_metric("fielding_pct_proxy", season_key, fielding_pct, estimated=_pick_first(row, "fielding_pct_proxy", "fielding_pct", "fld_pct") is None and fielding_pct is not None)
    player.set_metric("position_difficulty", season_key, _position_metric(position, POSITION_DIFFICULTY, 0.55), estimated=True)
    player.set_metric("arm_strength", season_key, arm_strength)
    player.set_metric("catcher_throw_value", season_key, catcher_throw_value)
    player.set_metric("outfield_arm_runs", season_key, outfield_arm_runs)
    player.set_metric("pop_time", season_key, pop_time)
    player.set_metric("framing_runs", season_key, framing_runs)
    player.set_metric("arm_position_baseline", season_key, _position_metric(position, ARM_POSITION_BASELINE, 0.50), estimated=True)
    player.set_sample("defensive_innings", season_key, innings)
    if row_positions:
        total_value = innings if innings is not None else games
        if total_value is not None and total_value > 0:
            share = total_value / len(row_positions)
            for parsed_position in row_positions:
                player.add_positional_games(parsed_position, share)
        else:
            for parsed_position in row_positions:
                player.add_positional_games(parsed_position, 1.0)
    else:
        player.add_positional_games(position, innings if innings is not None else games)


def _apply_running_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    _apply_identity(player, row)
    player.set_trait_metrics(season_key, _row_trait_metrics(row, HITTER_TRAIT_METRIC_COLUMNS))
    sprint_speed = _pick_number(row, "sprint_speed", "sprint_speed_ft_sec", "spdscr")
    baserunning_value = _pick_number(row, "baserunning_value", "bsr", "running_value", "baserunning_run_value")
    opportunities = _pick_number(row, "baserunning_opportunities", "br_opportunities")

    player.set_metric("sprint_speed", season_key, sprint_speed)
    player.set_metric("baserunning_value", season_key, baserunning_value)
    player.set_sample("baserunning_opportunities", season_key, opportunities)


def ingest_from_manifest(manifest: IngestManifest | Path) -> list[dict[str, Any]]:
    manifest_obj = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    if manifest_obj.source != "baseball_savant":
        raise ValueError("Baseball Savant adapter received a non-Savant manifest")
    players: dict[tuple[str, str], PlayerAccumulator] = {}
    mlb_pitch_quality_scores_by_metric: dict[str, list[float]] = defaultdict(list)
    mlb_pitch_quality_scores_by_player: dict[str, dict[str, float]] = defaultdict(dict)

    for season_key, season_inputs in manifest_obj.seasons.items():
        season_pitch_run_values: dict[str, dict[str, float]] = defaultdict(dict)
        pitch_run_values_path = season_inputs.files.get("pitch_run_values")
        if pitch_run_values_path is not None:
            parsed_pitch_run_values = parse_savant_pitch_run_value_csv(_read_csv(pitch_run_values_path))
            for (player_id, pitch_type), run_value_per_100 in parsed_pitch_run_values.items():
                season_pitch_run_values[player_id][pitch_type] = run_value_per_100
                metric_key = PITCH_RUN_VALUE_METRIC_KEYS.get(pitch_type)
                if metric_key is None:
                    continue
                rv_score = pitch_rv_per_100_score(run_value_per_100)
                mlb_pitch_quality_scores_by_metric[metric_key].append(rv_score)
                existing = mlb_pitch_quality_scores_by_player[player_id].get(metric_key)
                if existing is None or rv_score > existing:
                    mlb_pitch_quality_scores_by_player[player_id][metric_key] = rv_score

        if season_inputs.year is not None:
            for player in players.values():
                player.source_years.setdefault(season_key, season_inputs.year)

        roster_path = season_inputs.files.get("roster")
        if roster_path is not None:
            _apply_roster_rows(
                players,
                _read_csv(roster_path),
                source=manifest_obj.source,
                season_key=season_key,
                season_year=season_inputs.year,
                roster_filter=manifest_obj.roster_filter,
            )

        hitters_path = season_inputs.files.get("hitters")
        if hitters_path is not None:
            for row in _read_csv(hitters_path):
                player = _ensure_player(players, row, source=manifest_obj.source, season_year=season_inputs.year)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_hitter_row(player, season_key, row)

        pitchers_path = season_inputs.files.get("pitchers")
        if pitchers_path is not None:
            for row in _read_csv(pitchers_path):
                player = _ensure_player(players, row, source=manifest_obj.source, season_year=season_inputs.year)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                if not _should_apply_pitcher_row(player, row):
                    continue
                _apply_pitcher_row(player, season_key, row)
                if player.source_id:
                    pitch_values = season_pitch_run_values.get(player.source_id)
                    if pitch_values:
                        _apply_pitch_run_values_to_trait_metrics(player, season_key, pitch_values)

        fielding_path = season_inputs.files.get("fielding")
        if fielding_path is not None:
            for row in _read_csv(fielding_path):
                player = _ensure_player(players, row, source=manifest_obj.source, season_year=season_inputs.year)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_fielding_row(player, season_key, row)
        else:
            for player in players.values():
                player.note_missing_file(season_key, "fielding")

        running_path = season_inputs.files.get("running")
        if running_path is not None:
            for row in _read_csv(running_path):
                player = _ensure_player(players, row, source=manifest_obj.source, season_year=season_inputs.year)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_running_row(player, season_key, row)
        else:
            for player in players.values():
                player.note_missing_file(season_key, "running")

    _flag_injury_shortened_seasons(players)
    _finalize_active_status(players, roster_filter=manifest_obj.roster_filter)
    outputs = [player.to_player_dict() for player in players.values() if player.roles]

    for output in outputs:
        metadata = output.get("metadata")
        if not isinstance(metadata, dict):
            continue
        source_player_id = metadata.get("source_player_id")
        if not isinstance(source_player_id, str):
            continue
        player_scores = mlb_pitch_quality_scores_by_player.get(source_player_id)
        if not player_scores:
            continue

        percentile_values: dict[str, float] = {}
        peer_counts: dict[str, int] = {}
        for metric_key, score in player_scores.items():
            peers = mlb_pitch_quality_scores_by_metric.get(metric_key, [])
            if not peers:
                continue
            percentile_values[metric_key] = round(_percentile_rank(score, peers), 2)
            peer_counts[metric_key] = len(peers)

        if percentile_values:
            metadata.setdefault("mlb_trait_metric_percentiles", {}).update(percentile_values)
            metadata.setdefault("mlb_trait_metric_percentile_peer_counts", {}).update(peer_counts)

    outputs.sort(key=lambda item: (item["role"], item["name"]))
    return outputs