from __future__ import annotations

import csv
import io
import json
import re
from ssl import SSLContext
from typing import Any, Callable, Iterable, Mapping
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .live_metrics import (
    aggregate_split_stats,
    derive_hitter_pitch_type_metrics,
    derive_hitter_situational_metrics,
    derive_hitter_zone_metrics,
    derive_pitcher_situational_metrics,
    game_log_days_on_roster,
    hitter_contact_platoon_delta,
    hitter_power_platoon_delta,
    pitcher_handedness_gap,
    pitcher_handedness_score,
)
from .pitch_quality import (
    arsenal_percentage,
    derive_pitch_quality_metrics,
    fastball_velocity,
    parse_savant_pitch_details,
    pitch_quality_columns,
)


DEFAULT_MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
DEFAULT_BASEBALL_SAVANT = "https://baseballsavant.mlb.com"
DEFAULT_FANGRAPHS = "https://www.fangraphs.com"
_INJURY_STATUS_CODES = frozenset({"D10", "D15", "D60", "IL10", "IL15", "IL60", "RL"})

_POSITION_OUTS_COLUMN_MAP: dict[str, str] = {
    "outs_2": "C",
    "outs_3": "1B",
    "outs_4": "2B",
    "outs_5": "3B",
    "outs_6": "SS",
    "outs_7": "LF",
    "outs_8": "CF",
    "outs_9": "RF",
}


def _extract_embedded_json_array(payload: str, key: str) -> list[Mapping[str, Any]]:
    marker = f"{key}:"
    marker_index = payload.find(marker)
    if marker_index < 0:
        return []

    array_start = payload.find("[", marker_index + len(marker))
    if array_start < 0:
        return []

    try:
        rows, _ = json.JSONDecoder().raw_decode(payload[array_start:])
    except json.JSONDecodeError:
        return []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]



def parse_savant_statcast_summary(payload: str, *, season: int) -> dict[str, float]:
    rows = _extract_embedded_json_array(payload, "statcast")
    if not rows:
        return {}

    for row in rows:
        if _as_int(row.get("year")) != season:
            continue
        zone_contact_pct = _as_float(row.get("iz_contact_percent"))
        out_of_zone_contact_pct = _as_float(row.get("oz_contact_percent"))
        summary: dict[str, float] = {}
        if zone_contact_pct is not None:
            summary["zone_contact_pct"] = zone_contact_pct
        if out_of_zone_contact_pct is not None:
            summary["out_of_zone_contact_pct"] = out_of_zone_contact_pct

        avg_exit_velocity = _as_float(row.get("exit_velocity_avg"))
        barrel_rate = _as_float(row.get("barrel_batted_rate"))
        sprint_speed = _as_float(row.get("sprint_speed"))

        if avg_exit_velocity is not None:
            summary["avg_exit_velocity"] = avg_exit_velocity
        if barrel_rate is not None:
            summary["barrel_rate"] = barrel_rate
        if sprint_speed is not None:
            summary["sprint_speed"] = sprint_speed

        return summary
    return {}


def fetch_team_players(
    team_id: int,
    *,
    team_abbreviation: str,
    roster_season: int,
    primary_stat_season: int,
    fallback_stat_season: int,
    ssl_context: SSLContext | None = None,
    min_players: int | None = None,
    mlb_stats_api: str = DEFAULT_MLB_STATS_API,
    baseball_savant: str = DEFAULT_BASEBALL_SAVANT,
) -> list[dict[str, Any]]:
    roster_payload = _fetch_json(
        f"{mlb_stats_api}/teams/{team_id}/roster?rosterType=40Man&season={roster_season}",
        ssl_context=ssl_context,
    )
    roster_entries = roster_payload.get("roster", [])
    if not isinstance(roster_entries, list):
        return []

    players: list[dict[str, Any]] = []
    seasons = (primary_stat_season, fallback_stat_season)
    for roster_entry in roster_entries:
        if not isinstance(roster_entry, dict):
            continue
        player = _fetch_roster_player(
            roster_entry,
            team_abbreviation=team_abbreviation,
            seasons=seasons,
            ssl_context=ssl_context,
            mlb_stats_api=mlb_stats_api,
            baseball_savant=baseball_savant,
        )
        if player is not None:
            players.append(player)

    _apply_savant_arm_strength(
        players,
        seasons=seasons,
        ssl_context=ssl_context,
        baseball_savant=baseball_savant,
    )
    _apply_savant_catcher_defense(
        players,
        seasons=seasons,
        ssl_context=ssl_context,
        baseball_savant=baseball_savant,
    )

    if min_players is not None and len(players) < min_players:
        raise ValueError(f"Expected at least {min_players} live players, found {len(players)}")
    return sorted(players, key=lambda player: (str(player.get("type") or ""), str(player.get("name") or "")))


def build_roster_rows(players: Iterable[Mapping[str, Any]], *, team_abbreviation: str) -> list[dict[str, object]]:
    return [
        {
            "player_id": player.get("player_id"),
            "player_name": player.get("name"),
            "team": player.get("team", team_abbreviation),
            "status": player.get("status"),
            "status_code": player.get("status_code"),
            "age": player.get("age"),
            "position": player.get("position"),
            "bats": player.get("bats"),
            "throws": player.get("throws"),
        }
        for player in players
    ]


def build_baseball_reference_hitter_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    extra_players: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in list(players) + list(extra_players):
        if player.get("type") != "hitter":
            continue
        if (_as_int(player.get("plate_appearances")) or 0) <= 0:
            continue
        hitting_splits = player.get("hitting_handedness_splits") if isinstance(player.get("hitting_handedness_splits"), Mapping) else {}
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player.get("name"),
                "team": player.get("team", team_abbreviation),
                "position": player.get("position"),
                "Days On Roster": player.get("days_on_roster"),
                "PA": player.get("plate_appearances"),
                "AB": player.get("at_bats"),
                "H": player.get("hits"),
                "2B": player.get("doubles"),
                "3B": player.get("triples"),
                "HR": player.get("home_runs"),
                "BB": player.get("walks"),
                "SO": player.get("strikeouts"),
                "HBP": player.get("hit_by_pitch"),
                "SB": player.get("stolen_bases"),
                "CS": player.get("caught_stealing"),
                "BA": player.get("avg"),
                "OBP": player.get("obp"),
                "SLG": player.get("slg"),
                "Contact vs LHP Minus RHP": hitter_contact_platoon_delta(hitting_splits),
                "Power vs LHP Minus RHP": hitter_power_platoon_delta(hitting_splits),
            }
        )
    return rows


def build_savant_hitter_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    extra_players: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in list(players) + list(extra_players):
        if player.get("type") != "hitter":
            continue
        if (_as_int(player.get("plate_appearances")) or 0) <= 0:
            continue
        advanced = player.get("advanced_hitting") if isinstance(player.get("advanced_hitting"), Mapping) else {}
        hitting_splits = player.get("hitting_handedness_splits") if isinstance(player.get("hitting_handedness_splits"), Mapping) else {}
        savant_hitting_summary = player.get("savant_hitting_summary") if isinstance(player.get("savant_hitting_summary"), Mapping) else {}
        situational_hitting_metrics = player.get("situational_hitting_metrics") if isinstance(player.get("situational_hitting_metrics"), Mapping) else {}
        pitch_type_hitting_metrics = player.get("pitch_type_hitting_metrics") if isinstance(player.get("pitch_type_hitting_metrics"), Mapping) else {}
        zone_hitting_metrics = player.get("zone_hitting_metrics") if isinstance(player.get("zone_hitting_metrics"), Mapping) else {}
        total_swings = _as_int(advanced.get("totalSwings"))
        swing_and_misses = _as_int(advanced.get("swingAndMisses"))
        contact_pct = None
        if total_swings not in (None, 0) and swing_and_misses is not None:
            contact_pct = round((1.0 - (swing_and_misses / total_swings)) * 100.0, 3)
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player.get("name"),
                "team": player.get("team", team_abbreviation),
                "position": player.get("position"),
                "Days On Roster": player.get("days_on_roster"),
                "PA": player.get("plate_appearances"),
                "ISO": _as_str(advanced.get("iso")) or _format_decimal((_as_float(player.get("slg")) or 0.0) - (_as_float(player.get("avg")) or 0.0)),
                "HR": player.get("home_runs"),
                "SLG": player.get("slg"),
                "AVG": player.get("avg"),
                "OBP": player.get("obp"),
                "K %": _percentage(player.get("strikeouts"), player.get("plate_appearances")),
                "Contact %": contact_pct,
                "Barrel %": savant_hitting_summary.get("barrel_rate"),
                "Avg Exit Velocity": savant_hitting_summary.get("avg_exit_velocity"),
                "z_contact_pct": savant_hitting_summary.get("zone_contact_pct"),
                "o_contact_pct": savant_hitting_summary.get("out_of_zone_contact_pct"),
                "Sprint Speed": savant_hitting_summary.get("sprint_speed"),
                "first_pitch_hitting": situational_hitting_metrics.get("first_pitch_hitting"),
                "risp_hitting": situational_hitting_metrics.get("risp_hitting"),
                "pressure_hitting": situational_hitting_metrics.get("pressure_hitting"),
                "late_game_hitting": situational_hitting_metrics.get("late_game_hitting"),
                "trailing_bases_empty_hitting": situational_hitting_metrics.get("trailing_bases_empty_hitting"),
                "fastball_hitting": pitch_type_hitting_metrics.get("fastball_hitting"),
                "offspeed_hitting": pitch_type_hitting_metrics.get("offspeed_hitting"),
                "zone_hitting_high": zone_hitting_metrics.get("zone_hitting_high"),
                "zone_hitting_low": zone_hitting_metrics.get("zone_hitting_low"),
                "zone_hitting_inside": zone_hitting_metrics.get("zone_hitting_inside"),
                "zone_hitting_outside": zone_hitting_metrics.get("zone_hitting_outside"),
                "2B": player.get("doubles"),
                "3B": player.get("triples"),
                "SB": player.get("stolen_bases"),
                "CS": player.get("caught_stealing"),
                "BB": player.get("walks"),
                "HBP": player.get("hit_by_pitch"),
                "H": player.get("hits"),
                "Contact vs LHP Minus RHP": hitter_contact_platoon_delta(hitting_splits),
                "Power vs LHP Minus RHP": hitter_power_platoon_delta(hitting_splits),
            }
        )
    return rows


def build_savant_fielding_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    season: int | None = None,
    ssl_context: SSLContext | None = None,
    baseball_savant: str = DEFAULT_BASEBALL_SAVANT,
    fielding_run_value_payload: str | None = None,
    oaa_payload: str | None = None,
) -> list[dict[str, object]]:
    player_list = list(players)
    rows: list[dict[str, object]] = []
    for player in player_list:
        if player.get("type") != "hitter":
            continue
        fielding = player.get("fielding_stats") if isinstance(player.get("fielding_stats"), Mapping) else {}
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player.get("name"),
                "team": player.get("team", team_abbreviation),
                "position": player.get("position"),
                "Defensive Innings": _as_float(fielding.get("innings")) or _as_float(fielding.get("inningsPlayed")),
                "OAA": _as_float(fielding.get("outsAboveAverage")) or _as_float(fielding.get("oaa")),
                "DRS": _as_float(fielding.get("defensiveRunsSaved")) or _as_float(fielding.get("drs")),
                "UZR": _as_float(fielding.get("uzr")),
                "Fielding %": _as_float(fielding.get("fielding")),
                "PO": _as_float(fielding.get("putOuts")),
                "A": _as_float(fielding.get("assists")),
                "E": _as_float(fielding.get("errors")),
                "Arm Strength": _as_float(fielding.get("armStrength")) or _as_float(fielding.get("averageThrowingVelocity")),
                "Catcher Throw Value": _as_float(fielding.get("catcherThrowValue")) or _as_float(fielding.get("caughtStealingAboveAverage")),
                "Outfield Arm Runs": _as_float(fielding.get("outfieldArmRuns")) or _as_float(fielding.get("armRuns")),
                "Pop Time": _as_float(fielding.get("popTime")) or _as_float(fielding.get("avgPopTime2B")),
                "Framing Runs": _as_float(fielding.get("framingRuns")) or _as_float(fielding.get("catcherFramingRuns")),
            }
        )

    if season is None:
        return rows

    fallback_rows = _build_savant_defensive_fallback_rows(
        player_list,
        team_abbreviation=team_abbreviation,
        season=season,
        ssl_context=ssl_context,
        baseball_savant=baseball_savant,
        fielding_run_value_payload=fielding_run_value_payload,
        oaa_payload=oaa_payload,
    )
    if not fallback_rows:
        return rows

    merged_by_key: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        player_id = _as_str(row.get("player_id"))
        position = _as_str(row.get("position"))
        if not player_id or not position:
            continue
        merged_by_key[(player_id, position.upper())] = dict(row)

    for fallback in fallback_rows:
        player_id = _as_str(fallback.get("player_id"))
        position = _as_str(fallback.get("position"))
        if not player_id:
            continue
        if not position:
            # Fall back to player's listed primary position if Savant row omits explicit position.
            position = _as_str(next((p.get("position") for p in player_list if _as_str(p.get("player_id")) == player_id), None))
        if not position:
            continue

        key = (player_id, position.upper())
        existing = merged_by_key.get(key)
        if existing is None:
            merged_by_key[key] = dict(fallback)
            continue
        if existing.get("Defensive Innings") is None and fallback.get("Defensive Innings") is not None:
            existing["Defensive Innings"] = fallback.get("Defensive Innings")
        for metric_key in ("OAA", "DRS", "UZR", "Outfield Arm Runs", "Catcher Throw Value", "Framing Runs"):
            if fallback.get(metric_key) is not None:
                existing[metric_key] = fallback.get(metric_key)

    merged_rows = list(merged_by_key.values())
    merged_rows.sort(key=lambda row: (_as_str(row.get("player_name")) or "", _as_str(row.get("position")) or ""))
    return merged_rows


def parse_fangraphs_fielding_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload))
    parsed_rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        name = _as_str(row.get("Name") or row.get("Player") or row.get("player_name"))
        if not name:
            continue
        team = _as_str(row.get("Team") or row.get("Tm") or row.get("team"))
        drs = _as_float(row.get("DRS") or row.get("drs") or row.get("Defensive Runs Saved"))
        uzr = _as_float(row.get("UZR") or row.get("uzr") or row.get("UZR/150") or row.get("uzr_150"))
        if drs is None and uzr is None:
            continue
        parsed_rows.append(
            {
                "name": name,
                "team": team.upper() if team else None,
                "drs": drs,
                "uzr": uzr,
            }
        )
    return parsed_rows


def parse_savant_fielding_run_value_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    parsed_rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        name = _player_name_from_row(row)
        if not name:
            continue
        player_id = _as_int(row.get("player_id") or row.get("id"))
        team = _as_str(row.get("Team") or row.get("Tm") or row.get("team") or row.get("display_team_name"))
        position = _as_str(
            row.get("position")
            or row.get("pos")
            or row.get("fielder_position")
            or row.get("fielding_position")
            or row.get("display_position")
            or row.get("position_name")
            or row.get("primary_pos_formatted")
        )
        fielding_run_value = _as_float(
            row.get("Fielding Run Value")
            or row.get("fielding_run_value")
            or row.get("FRV")
            or row.get("total_runs")
        )
        range_runs = _as_float(row.get("Range") or row.get("range") or row.get("range_runs"))
        arm_runs = _as_float(row.get("Arm") or row.get("arm") or row.get("arm_runs"))
        framing_runs = _as_float(row.get("Framing") or row.get("framing") or row.get("framing_runs"))
        throwing_runs = _as_float(row.get("Throwing") or row.get("throwing") or row.get("throwing_runs"))
        positional_outs: dict[str, float] = {}
        for outs_column, parsed_position in _POSITION_OUTS_COLUMN_MAP.items():
            outs_value = _as_float(row.get(outs_column))
            if outs_value is not None and outs_value > 0:
                positional_outs[parsed_position] = outs_value
        if all(value is None for value in (fielding_run_value, range_runs, arm_runs, framing_runs, throwing_runs)):
            continue
        parsed_rows.append(
            {
                "name": name,
                "player_id": player_id,
                "team": team.upper() if team else None,
                "position": position.upper() if position else None,
                "fielding_run_value": fielding_run_value,
                "range_runs": range_runs,
                "arm_runs": arm_runs,
                "framing_runs": framing_runs,
                "throwing_runs": throwing_runs,
                "positional_outs": positional_outs,
            }
        )
    return parsed_rows


def parse_savant_oaa_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    parsed_rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        name = _player_name_from_row(row)
        if not name:
            continue
        player_id = _as_int(row.get("player_id") or row.get("id"))
        team = _as_str(row.get("Team") or row.get("Tm") or row.get("team") or row.get("display_team_name"))
        position = _as_str(
            row.get("position")
            or row.get("pos")
            or row.get("fielder_position")
            or row.get("fielding_position")
            or row.get("display_position")
            or row.get("position_name")
            or row.get("primary_pos_formatted")
        )
        oaa = _as_float(
            row.get("OAA")
            or row.get("outs_above_average")
            or row.get("outs above average")
        )
        runs_prevented = _as_float(
            row.get("Runs Prevented")
            or row.get("runs_prevented")
            or row.get("fielding_runs_prevented")
        )
        if oaa is None and runs_prevented is None:
            continue
        parsed_rows.append(
            {
                "name": name,
                "player_id": player_id,
                "team": team.upper() if team else None,
                "position": position.upper() if position else None,
                "oaa": oaa,
                "runs_prevented": runs_prevented,
            }
        )
    return parsed_rows


def parse_savant_arm_strength_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    parsed_rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        name = _player_name_from_row(row)
        if not name:
            continue
        player_id = _as_int(row.get("player_id") or row.get("id"))
        team = _as_str(row.get("team_name") or row.get("Team") or row.get("Tm") or row.get("team"))
        arm_strength = _as_float(
            row.get("arm_overall")
            or row.get("arm_strength")
            or row.get("max_arm_strength")
            or row.get("throw_speed")
            or row.get("avg_throw_speed")
        )
        if arm_strength is None:
            continue
        parsed_rows.append(
            {
                "name": name,
                "player_id": player_id,
                "team": team.upper() if team else None,
                "arm_strength": arm_strength,
            }
        )
    return parsed_rows


def parse_savant_catcher_throwing_csv(payload: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(payload.lstrip("\ufeff")))
    parsed_rows: list[dict[str, Any]] = []
    for row in reader:
        if not isinstance(row, dict):
            continue
        name = _player_name_from_row(row)
        if not name:
            continue
        player_id = _as_int(row.get("player_id") or row.get("id"))
        team = _as_str(row.get("team_name") or row.get("Team") or row.get("Tm") or row.get("team"))
        catcher_throw_value = _as_float(
            row.get("caught_stealing_above_average")
            or row.get("catcher_throw_value")
            or row.get("cs_above_average")
        )
        pop_time = _as_float(
            row.get("pop_time")
            or row.get("avg_pop_time_2b")
            or row.get("pop_2b_sba")
        )
        arm_strength = _as_float(
            row.get("arm_strength")
            or row.get("arm_overall")
            or row.get("throw_speed")
        )
        if catcher_throw_value is None and pop_time is None and arm_strength is None:
            continue
        parsed_rows.append(
            {
                "name": name,
                "player_id": player_id,
                "team": team.upper() if team else None,
                "catcher_throw_value": catcher_throw_value,
                "pop_time": pop_time,
                "arm_strength": arm_strength,
            }
        )
    return parsed_rows


def build_fangraphs_fielding_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    season: int,
    ssl_context: SSLContext | None = None,
    fangraphs: str = DEFAULT_FANGRAPHS,
    baseball_savant: str = DEFAULT_BASEBALL_SAVANT,
    csv_payload: str | None = None,
    savant_fielding_run_value_payload: str | None = None,
    savant_oaa_payload: str | None = None,
) -> list[dict[str, object]]:
    payload = csv_payload
    if payload is None:
        payload = _fetch_fangraphs_fielding_csv(season=season, ssl_context=ssl_context, fangraphs=fangraphs)
    if not payload:
        return _build_savant_defensive_fallback_rows(
            players,
            team_abbreviation=team_abbreviation,
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
            fielding_run_value_payload=savant_fielding_run_value_payload,
            oaa_payload=savant_oaa_payload,
        )

    parsed = parse_fangraphs_fielding_csv(payload)
    by_name_team = {
        (_normalized_name(row["name"]), row.get("team")): row
        for row in parsed
        if isinstance(row.get("name"), str)
    }
    by_name = {
        _normalized_name(row["name"]): row
        for row in parsed
        if isinstance(row.get("name"), str)
    }

    rows: list[dict[str, object]] = []
    for player in players:
        if player.get("type") != "hitter":
            continue
        player_name = _as_str(player.get("name"))
        if not player_name:
            continue
        team = _as_str(player.get("team")) or team_abbreviation
        normalized = _normalized_name(player_name)
        match = by_name_team.get((normalized, (team or "").upper())) or by_name.get(normalized)
        if not match:
            continue
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player_name,
                "team": team,
                "position": player.get("position"),
                "DRS": match.get("drs"),
                "UZR": match.get("uzr"),
            }
        )
    return rows


def _build_savant_defensive_fallback_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    season: int,
    ssl_context: SSLContext | None,
    baseball_savant: str,
    fielding_run_value_payload: str | None,
    oaa_payload: str | None,
    career_oaa_payload: str | None = None,
) -> list[dict[str, object]]:
    frv_payload = fielding_run_value_payload
    if frv_payload is None:
        frv_payload = _fetch_savant_fielding_run_value_csv(
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
    oaa_csv_payload = oaa_payload
    if oaa_csv_payload is None:
        oaa_csv_payload = _fetch_savant_oaa_csv(
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
    career_oaa_csv_payload = career_oaa_payload
    if career_oaa_csv_payload is None and oaa_payload is None:
        career_oaa_csv_payload = _fetch_savant_oaa_csv(
            season=season,
            start_year=max(2015, season - 12),
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )

    frv_rows = parse_savant_fielding_run_value_csv(frv_payload) if frv_payload else []
    oaa_rows = parse_savant_oaa_csv(oaa_csv_payload) if oaa_csv_payload else []
    if career_oaa_csv_payload:
        oaa_rows.extend(parse_savant_oaa_csv(career_oaa_csv_payload))
    if not frv_rows and not oaa_rows:
        return []

    frv_by_id_key = {
        (int(row["player_id"]), row.get("position")): row
        for row in frv_rows
        if isinstance(row.get("player_id"), int)
    }
    oaa_by_id_key = {
        (int(row["player_id"]), row.get("position")): row
        for row in oaa_rows
        if isinstance(row.get("player_id"), int)
    }
    frv_by_name_team_key = {
        (_normalized_name(str(row.get("name") or "")), row.get("team"), row.get("position")): row
        for row in frv_rows
        if isinstance(row.get("name"), str)
    }
    oaa_by_name_team_key = {
        (_normalized_name(str(row.get("name") or "")), row.get("team"), row.get("position")): row
        for row in oaa_rows
        if isinstance(row.get("name"), str)
    }

    rows: list[dict[str, object]] = []
    for player in players:
        if player.get("type") != "hitter":
            continue
        player_name = _as_str(player.get("name"))
        if not player_name:
            continue
        team = (_as_str(player.get("team")) or team_abbreviation).upper()
        normalized = _normalized_name(player_name)
        player_position = _as_str(player.get("position"))
        player_id = _as_int(player.get("player_id"))

        candidate_positions: set[str | None] = set()
        frv_general_row: Mapping[str, Any] | None = None
        if player_id is not None:
            candidate_positions.update(position for pid, position in frv_by_id_key if pid == player_id)
            candidate_positions.update(position for pid, position in oaa_by_id_key if pid == player_id)
            frv_general_row = frv_by_id_key.get((player_id, None))
        if not candidate_positions:
            candidate_positions.update(
                position
                for name_key, team_key, position in frv_by_name_team_key
                if name_key == normalized and team_key == team
            )
            candidate_positions.update(
                position
                for name_key, team_key, position in oaa_by_name_team_key
                if name_key == normalized and team_key == team
            )

        if frv_general_row is None:
            frv_general_row = frv_by_name_team_key.get((normalized, team, None))

        positional_outs = frv_general_row.get("positional_outs") if isinstance(frv_general_row, Mapping) else None
        if isinstance(positional_outs, Mapping):
            for parsed_position, outs_value in positional_outs.items():
                numeric_outs = _as_float(outs_value)
                if numeric_outs is not None and numeric_outs > 0:
                    normalized_position = _as_str(parsed_position)
                    if normalized_position:
                        candidate_positions.add(normalized_position)

        candidate_keys = sorted(candidate_positions, key=lambda value: str(value or ""))
        if not candidate_keys:
            candidate_keys = [player_position.upper() if player_position else None]

        matched_any = False
        for candidate_position in candidate_keys:
            frv = None
            oaa_row = None
            if player_id is not None:
                frv = frv_by_id_key.get((player_id, candidate_position))
                oaa_row = oaa_by_id_key.get((player_id, candidate_position))
            if frv is None:
                frv = frv_by_name_team_key.get((normalized, team, candidate_position))
            if frv is None and isinstance(frv_general_row, Mapping):
                frv = frv_general_row
            if oaa_row is None:
                oaa_row = oaa_by_name_team_key.get((normalized, team, candidate_position))
            if frv is None and oaa_row is None:
                continue
            matched_any = True

            fielding_run_value = _as_float(frv.get("fielding_run_value")) if isinstance(frv, Mapping) else None
            range_runs = _as_float(frv.get("range_runs")) if isinstance(frv, Mapping) else None
            arm_runs = _as_float(frv.get("arm_runs")) if isinstance(frv, Mapping) else None
            framing_runs = _as_float(frv.get("framing_runs")) if isinstance(frv, Mapping) else None
            throwing_runs = _as_float(frv.get("throwing_runs")) if isinstance(frv, Mapping) else None
            oaa = _as_float(oaa_row.get("oaa")) if isinstance(oaa_row, Mapping) else None
            runs_prevented = _as_float(oaa_row.get("runs_prevented")) if isinstance(oaa_row, Mapping) else None

            drs_proxy = fielding_run_value
            if drs_proxy is None:
                drs_proxy = runs_prevented
            if drs_proxy is None:
                drs_proxy = oaa

            uzr_proxy = range_runs
            if uzr_proxy is None:
                uzr_proxy = runs_prevented
            if uzr_proxy is None:
                uzr_proxy = oaa

            defensive_innings = None
            if isinstance(frv, Mapping):
                frv_positional_outs = frv.get("positional_outs")
                if isinstance(frv_positional_outs, Mapping):
                    outs_value = _as_float(frv_positional_outs.get(candidate_position or ""))
                    if outs_value is not None and outs_value > 0:
                        defensive_innings = round(outs_value / 3.0, 3)

            rows.append(
                {
                    "player_id": player.get("player_id"),
                    "player_name": player_name,
                    "team": team,
                    "position": candidate_position or player_position,
                    "Defensive Innings": defensive_innings,
                    "OAA": oaa,
                    "DRS": drs_proxy,
                    "UZR": uzr_proxy,
                    "Outfield Arm Runs": arm_runs,
                    "Catcher Throw Value": throwing_runs,
                    "Framing Runs": framing_runs,
                }
            )

        if matched_any:
            continue
    return rows


def build_baseball_reference_pitcher_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
        if player.get("type") != "pitcher":
            continue
        if (_as_int(player.get("batters_faced")) or 0) <= 0:
            continue
        pitching_splits = player.get("pitching_handedness_splits") if isinstance(player.get("pitching_handedness_splits"), Mapping) else {}
        throws = _as_str(player.get("throws"))
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player.get("name"),
                "team": player.get("team", team_abbreviation),
                "position": "P",
                "Days On Roster": player.get("days_on_roster"),
                "BF": player.get("batters_faced"),
                "BB": player.get("walks"),
                "SO": player.get("strikeouts"),
                "HR": player.get("home_runs"),
                "H": player.get("hits"),
                "IP": player.get("innings_pitched"),
                "Pitches": player.get("number_of_pitches"),
                "Strikes": player.get("strikes"),
                "Same Handed Pitching": pitcher_handedness_score(throws, pitching_splits, split_type="same"),
                "Same Handed Pitching Gap": pitcher_handedness_gap(throws, pitching_splits, split_type="same"),
                "Opposite Handed Pitching": pitcher_handedness_score(throws, pitching_splits, split_type="opposite"),
                "Opposite Handed Pitching Gap": pitcher_handedness_gap(throws, pitching_splits, split_type="opposite"),
            }
        )
    return rows


def build_savant_pitcher_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
        if player.get("type") != "pitcher":
            continue
        if (_as_int(player.get("batters_faced")) or 0) <= 0:
            continue
        advanced = player.get("advanced_pitching") if isinstance(player.get("advanced_pitching"), Mapping) else {}
        arsenal_data = player.get("pitch_arsenal") if isinstance(player.get("pitch_arsenal"), Mapping) else {}
        pitching_splits = player.get("pitching_handedness_splits") if isinstance(player.get("pitching_handedness_splits"), Mapping) else {}
        situational_pitching_metrics = player.get("situational_pitching_metrics") if isinstance(player.get("situational_pitching_metrics"), Mapping) else {}
        savant_pitch_details = player.get("savant_pitch_details") if isinstance(player.get("savant_pitch_details"), Mapping) else {}
        pitch_quality = derive_pitch_quality_metrics(arsenal_data, savant_pitch_details)
        throws = _as_str(player.get("throws"))
        chase_rate = _pick_mapping_percentage(
            advanced,
            "chasePercentage",
            "chasePercent",
            "chase_rate",
            "chase_pct",
            "oz_swing_pct",
            "o_swing_pct",
            "out_of_zone_swing_pct",
        )
        zone_pct = _pick_mapping_percentage(
            advanced,
            "zonePercentage",
            "zonePercent",
            "zone_pct",
            "zone_percentage",
        )
        first_pitch_strike_pct = _pick_mapping_percentage(
            advanced,
            "firstPitchStrikePercentage",
            "firstPitchStrikePercent",
            "first_pitch_strike_pct",
            "first_pitch_strike_percentage",
            "f_strike_pct",
            "fps_pct",
        )
        movement_quality = _pick_mapping_float(
            advanced,
            "movementQuality",
            "movement_quality",
            "movementPlus",
            "movement_plus",
            "movementGrade",
            "movement_grade",
        )
        horizontal_break = _weighted_arsenal_metric(
            arsenal_data,
            "horizontalBreak",
            "horizontal_break",
            "horizontalMovement",
            "horizontal_movement",
            "breakX",
            "break_x",
            "pfxX",
            "pfx_x",
        )
        induced_vertical_break = _weighted_arsenal_metric(
            arsenal_data,
            "inducedVerticalBreak",
            "induced_vertical_break",
            "verticalBreak",
            "vertical_break",
            "breakZ",
            "break_z",
            "pfxZ",
            "pfx_z",
            "ivb",
        )
        rows.append(
            {
                "player_id": player.get("player_id"),
                "player_name": player.get("name"),
                "team": player.get("team", team_abbreviation),
                "position": "P",
                "Days On Roster": player.get("days_on_roster"),
                "BF": player.get("batters_faced"),
                "Pitches": player.get("number_of_pitches"),
                "Avg Fastball Velocity": fastball_velocity(arsenal_data, mode="average"),
                "Peak Fastball Velocity": fastball_velocity(arsenal_data, mode="peak"),
                "FF %": arsenal_percentage(arsenal_data, "FF"),
                "FT %": arsenal_percentage(arsenal_data, "FT"),
                "SI %": arsenal_percentage(arsenal_data, "SI"),
                "FC %": arsenal_percentage(arsenal_data, "FC"),
                "SL %": arsenal_percentage(arsenal_data, "SL"),
                "CU %": arsenal_percentage(arsenal_data, "CU"),
                "CH %": arsenal_percentage(arsenal_data, "CH"),
                "FS %": arsenal_percentage(arsenal_data, "FS"),
                "FO %": arsenal_percentage(arsenal_data, "FO"),
                "SC %": arsenal_percentage(arsenal_data, "SC"),
                "SV %": arsenal_percentage(arsenal_data, "SV"),
                "SwStr %": _as_percentage_string(advanced.get("whiffPercentage")),
                "Chase %": chase_rate,
                "BB %": _percentage(player.get("walks"), player.get("batters_faced")),
                "Strike %": _as_percentage_string(player.get("strike_percentage")),
                "Zone %": zone_pct,
                "First Pitch Strike %": first_pitch_strike_pct,
                "Movement Quality": movement_quality,
                "Horizontal Break": horizontal_break,
                "Induced Vertical Break": induced_vertical_break,
                "first_pitch_pitching": situational_pitching_metrics.get("first_pitch_pitching"),
                "runners_on_pitching": situational_pitching_metrics.get("runners_on_pitching"),
                "pressure_pitching": situational_pitching_metrics.get("pressure_pitching"),
                "three_ball_accuracy": situational_pitching_metrics.get("three_ball_accuracy"),
                "steal_suppression": situational_pitching_metrics.get("steal_suppression"),
                **pitch_quality_columns(pitch_quality),
                "Same Handed Pitching": pitcher_handedness_score(throws, pitching_splits, split_type="same"),
                "Same Handed Pitching Gap": pitcher_handedness_gap(throws, pitching_splits, split_type="same"),
                "Opposite Handed Pitching": pitcher_handedness_score(throws, pitching_splits, split_type="opposite"),
                "Opposite Handed Pitching Gap": pitcher_handedness_gap(throws, pitching_splits, split_type="opposite"),
            }
        )
    return rows


def build_mixed_source_manifest(
    *,
    team_abbreviation: str,
    roster_season: int,
    roster_file: str,
    savant_hitters_file: str,
    savant_pitchers_file: str,
    savant_fielding_file: str | None = None,
    baseball_reference_hitters_file: str,
    baseball_reference_pitchers_file: str,
    current_year: int | None = None,
    previous_year: int | None = None,
    previous_savant_hitters_file: str | None = None,
    previous_savant_pitchers_file: str | None = None,
    previous_savant_fielding_file: str | None = None,
    previous_baseball_reference_hitters_file: str | None = None,
    previous_baseball_reference_pitchers_file: str | None = None,
) -> dict[str, Any]:
    savant_files: dict[str, str] = {
        "roster": roster_file,
        "hitters": savant_hitters_file,
        "pitchers": savant_pitchers_file,
    }
    if savant_fielding_file:
        savant_files["fielding"] = savant_fielding_file

    sources: dict[str, dict[str, dict[str, str]]] = {
        "baseball_reference": {
            "files": {
                "hitters": baseball_reference_hitters_file,
                "pitchers": baseball_reference_pitchers_file,
            }
        },
        "baseball_savant": {
            "files": savant_files
        },
    }

    manifest = {
        "source": "mixed",
        "roster_filter": {"team": team_abbreviation, "year": roster_season},
        "seasons": {
            "current": {
                "year": current_year if current_year is not None else roster_season,
                "sources": sources,
            }
        },
    }

    previous_savant_files: dict[str, str] = {}
    if previous_savant_hitters_file:
        previous_savant_files["hitters"] = previous_savant_hitters_file
    if previous_savant_pitchers_file:
        previous_savant_files["pitchers"] = previous_savant_pitchers_file
    if previous_savant_fielding_file:
        previous_savant_files["fielding"] = previous_savant_fielding_file

    previous_baseball_reference_files: dict[str, str] = {}
    if previous_baseball_reference_hitters_file:
        previous_baseball_reference_files["hitters"] = previous_baseball_reference_hitters_file
    if previous_baseball_reference_pitchers_file:
        previous_baseball_reference_files["pitchers"] = previous_baseball_reference_pitchers_file

    if previous_year is not None and (previous_savant_files or previous_baseball_reference_files):
        previous_sources: dict[str, dict[str, dict[str, str]]] = {}
        if previous_baseball_reference_files:
            previous_sources["baseball_reference"] = {"files": previous_baseball_reference_files}
        if previous_savant_files:
            previous_sources["baseball_savant"] = {"files": previous_savant_files}
        manifest["seasons"]["previous"] = {
            "year": previous_year,
            "sources": previous_sources,
        }

    return manifest


def _fetch_roster_player(
    roster_entry: Mapping[str, Any],
    *,
    team_abbreviation: str,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
    baseball_savant: str,
) -> dict[str, Any] | None:
    person_summary = roster_entry.get("person", {})
    if not isinstance(person_summary, Mapping):
        return None
    player_id = _as_int(person_summary.get("id"))
    if player_id is None:
        return None

    person_payload = _fetch_json(f"{mlb_stats_api}/people/{player_id}", ssl_context=ssl_context)
    people = person_payload.get("people", [])
    if not isinstance(people, list) or not people:
        return None
    person = people[0]
    if not isinstance(person, Mapping):
        return None

    roster_position = roster_entry.get("position", {})
    if not isinstance(roster_position, Mapping):
        roster_position = {}
    primary_position = person.get("primaryPosition", {})
    if not isinstance(primary_position, Mapping):
        primary_position = {}
    status_payload = roster_entry.get("status", {})
    if not isinstance(status_payload, Mapping):
        status_payload = {}
    status = _as_str(status_payload.get("description")) or "Active"
    status_code = _as_str(status_payload.get("code")) or "A"
    normalized_status = status.lower()
    if (
        status != "Active"
        and "injured" not in normalized_status
        and "rehab" not in normalized_status
        and status_code.upper() not in _INJURY_STATUS_CODES
    ):
        return None

    position = _as_str(roster_position.get("abbreviation")) or _as_str(primary_position.get("abbreviation"))
    position_type = _as_str(roster_position.get("type"))
    if position_type == "Pitcher" or position == "P":
        stat_group = "pitching"
        player_type = "pitcher"
    else:
        stat_group = "hitting"
        player_type = "hitter"

    base_player: dict[str, Any] = {
        "player_id": player_id,
        "name": _as_str(person.get("fullName")) or _as_str(person_summary.get("fullName")),
        "team": team_abbreviation,
        "type": player_type,
        "position": position,
        "status": status,
        "status_code": status_code,
        "age": _as_int(person.get("currentAge")),
        "bats": _nested_str(person, "batSide", "code"),
        "throws": _nested_str(person, "pitchHand", "code"),
        "days_on_roster": _fetch_days_on_roster(
            player_id,
            stat_group,
            seasons=seasons,
            ssl_context=ssl_context,
            mlb_stats_api=mlb_stats_api,
        ),
    }

    stats = _fetch_stats(player_id, stat_group, seasons=seasons, ssl_context=ssl_context, mlb_stats_api=mlb_stats_api)
    if stats is None:
        return base_player

    if player_type == "hitter":
        plate_appearances = _as_int(stats.get("plateAppearances")) or 0
        if plate_appearances == 0:
            return base_player
        advanced_stats = _fetch_stats(
            player_id,
            stat_group,
            seasons=seasons,
            ssl_context=ssl_context,
            mlb_stats_api=mlb_stats_api,
            stats_type="seasonAdvanced",
        ) or {}
        handedness_splits = _fetch_handedness_splits(
            player_id,
            stat_group,
            seasons=seasons,
            ssl_context=ssl_context,
            mlb_stats_api=mlb_stats_api,
        )
        savant_hitting_summary = _fetch_savant_hitter_summary(
            player_id,
            season=seasons[0],
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
        savant_hitter_pitch_details = _fetch_savant_hitter_pitch_details(
            player_id,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
        situational_hitting_splits = _fetch_situation_splits(
            player_id,
            stat_group,
            codes=("c00", "risp", "lc", "ig07", "sbh", "r0"),
            seasons=seasons,
            ssl_context=ssl_context,
            mlb_stats_api=mlb_stats_api,
        )
        pitch_type_hitting_splits = _derive_hitter_pitch_type_splits(savant_hitter_pitch_details)
        zone_hitting_splits = _derive_hitter_zone_splits(
            savant_hitter_pitch_details,
            bats=_nested_str(person, "batSide", "code"),
        )
        base_player.update(
            {
                "plate_appearances": plate_appearances,
                "at_bats": _as_int(stats.get("atBats")) or 0,
                "hits": _as_int(stats.get("hits")) or 0,
                "doubles": _as_int(stats.get("doubles")) or 0,
                "triples": _as_int(stats.get("triples")) or 0,
                "home_runs": _as_int(stats.get("homeRuns")) or 0,
                "walks": _as_int(stats.get("baseOnBalls")) or 0,
                "strikeouts": _as_int(stats.get("strikeOuts")) or 0,
                "hit_by_pitch": _as_int(stats.get("hitByPitch")) or 0,
                "stolen_bases": _as_int(stats.get("stolenBases")) or 0,
                "caught_stealing": _as_int(stats.get("caughtStealing")) or 0,
                "avg": _as_str(stats.get("avg")) or "0.000",
                "obp": _as_str(stats.get("obp")) or "0.000",
                "slg": _as_str(stats.get("slg")) or "0.000",
                "advanced_hitting": advanced_stats,
                "savant_hitting_summary": savant_hitting_summary,
                "situational_hitting_metrics": derive_hitter_situational_metrics(situational_hitting_splits),
                "pitch_type_hitting_metrics": derive_hitter_pitch_type_metrics(pitch_type_hitting_splits),
                "zone_hitting_metrics": derive_hitter_zone_metrics(zone_hitting_splits),
                "hitting_handedness_splits": handedness_splits,
                "fielding_stats": _fetch_stats(
                    player_id,
                    "fielding",
                    seasons=seasons,
                    ssl_context=ssl_context,
                    mlb_stats_api=mlb_stats_api,
                )
                or {},
            }
        )
        return base_player

    batters_faced = _as_int(stats.get("battersFaced")) or 0
    if batters_faced == 0:
        return base_player
    advanced_stats = _fetch_stats(
        player_id,
        stat_group,
        seasons=seasons,
        ssl_context=ssl_context,
        mlb_stats_api=mlb_stats_api,
        stats_type="seasonAdvanced",
    ) or {}
    handedness_splits = _fetch_handedness_splits(
        player_id,
        stat_group,
        seasons=seasons,
        ssl_context=ssl_context,
        mlb_stats_api=mlb_stats_api,
    )
    situational_pitching_splits = _fetch_situation_splits(
        player_id,
        stat_group,
        codes=("c00", "ron", "lc", "c30", "c31", "c32"),
        seasons=seasons,
        ssl_context=ssl_context,
        mlb_stats_api=mlb_stats_api,
    )
    pitch_arsenal = _fetch_pitch_arsenal(
        player_id,
        seasons=seasons,
        ssl_context=ssl_context,
        mlb_stats_api=mlb_stats_api,
    )
    base_player.update(
        {
            "batters_faced": batters_faced,
            "walks": _as_int(stats.get("baseOnBalls")) or 0,
            "strikeouts": _as_int(stats.get("strikeOuts")) or 0,
            "home_runs": _as_int(stats.get("homeRuns")) or 0,
            "hits": _as_int(stats.get("hits")) or 0,
            "innings_pitched": _as_str(stats.get("inningsPitched")) or "0.0",
            "number_of_pitches": _as_int(stats.get("numberOfPitches")) or 0,
            "strikes": _as_int(stats.get("strikes")) or 0,
            "strike_percentage": _as_str(stats.get("strikePercentage")) or _as_str(advanced_stats.get("strikePercentage")),
            "stolen_bases_allowed": _as_int(stats.get("stolenBases")) or 0,
            "caught_stealing": _as_int(stats.get("caughtStealing")) or 0,
            "pickoffs": _as_int(stats.get("pickoffs")) or 0,
            "stolen_base_percentage": _as_str(stats.get("stolenBasePercentage")),
            "advanced_pitching": advanced_stats,
            "situational_pitching_metrics": derive_pitcher_situational_metrics(
                situational_pitching_splits,
                {
                    "stolen_bases_allowed": _as_int(stats.get("stolenBases")) or 0,
                    "caught_stealing": _as_int(stats.get("caughtStealing")) or 0,
                    "pickoffs": _as_int(stats.get("pickoffs")) or 0,
                    "stolen_base_percentage": _as_str(stats.get("stolenBasePercentage")),
                },
            ),
            "pitching_handedness_splits": handedness_splits,
            "savant_pitch_details": _fetch_savant_pitch_details(
                player_id,
                ssl_context=ssl_context,
                baseball_savant=baseball_savant,
            ),
            "pitch_arsenal": pitch_arsenal,
        }
    )
    return base_player


def _fetch_json(url: str, *, ssl_context: SSLContext | None) -> dict[str, Any]:
    with urlopen(url, timeout=30, context=ssl_context) as response:
        return json.load(response)


def _fetch_text(url: str, *, ssl_context: SSLContext | None, headers: dict[str, str] | None = None) -> str:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=30, context=ssl_context) as response:
        return response.read().decode("utf-8", errors="replace")


def _fetch_stats(
    player_id: int,
    group: str,
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
    stats_type: str = "season",
) -> dict[str, Any] | None:
    for season in seasons:
        payload = _fetch_json(
            f"{mlb_stats_api}/people/{player_id}/stats?stats={stats_type}&group={group}&season={season}",
            ssl_context=ssl_context,
        )
        stats = payload.get("stats", [])
        if not isinstance(stats, list) or not stats:
            continue
        first_stats = stats[0]
        if not isinstance(first_stats, Mapping):
            continue
        splits = first_stats.get("splits", [])
        if not isinstance(splits, list) or not splits:
            continue
        first_split = splits[0]
        if not isinstance(first_split, Mapping):
            continue
        stat_line = first_split.get("stat", {})
        if isinstance(stat_line, Mapping):
            return dict(stat_line)
    return None


def _fetch_pitch_arsenal(
    player_id: int,
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
) -> dict[str, dict[str, Any]]:
    for season in seasons:
        payload = _fetch_json(
            f"{mlb_stats_api}/people/{player_id}/stats?stats=pitchArsenal&group=pitching&season={season}",
            ssl_context=ssl_context,
        )
        stats = payload.get("stats", [])
        if not isinstance(stats, list) or not stats:
            continue
        first_stats = stats[0]
        if not isinstance(first_stats, Mapping):
            continue
        splits = first_stats.get("splits", [])
        if not isinstance(splits, list) or not splits:
            continue
        arsenal_data: dict[str, dict[str, Any]] = {}
        for split in splits:
            if not isinstance(split, Mapping):
                continue
            stat_line = split.get("stat", {})
            if not isinstance(stat_line, Mapping):
                continue
            pitch_type = stat_line.get("type", {})
            if not isinstance(pitch_type, Mapping):
                continue
            pitch_code = _as_str(pitch_type.get("code"))
            if not pitch_code:
                continue
            arsenal_data[pitch_code.upper()] = dict(stat_line)
        if arsenal_data:
            return arsenal_data
    return {}


def _fetch_savant_pitch_details(
    player_id: int,
    *,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> dict[str, dict[str, float]]:
    payload = _fetch_text(
        f"{baseball_savant}/player-services/statcast-pitches-breakdown?playerId={player_id}&position=1&pitchBreakdown=pitches",
        ssl_context=ssl_context,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{baseball_savant}/",
            "Accept": "application/json,text/plain,*/*",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    return parse_savant_pitch_details(payload)


def _fetch_savant_hitter_pitch_details(
    player_id: int,
    *,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> dict[str, dict[str, float]]:
    payload = _fetch_text(
        f"{baseball_savant}/player-services/statcast-pitches-breakdown?playerId={player_id}&position=0&pitchBreakdown=pitches",
        ssl_context=ssl_context,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": f"{baseball_savant}/",
            "Accept": "application/json,text/plain,*/*",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    return parse_savant_pitch_details(payload)


def _derive_hitter_pitch_type_splits(
    pitch_details: Mapping[str, Mapping[str, float]],
) -> dict[str, dict[str, float]]:
    return {
        "fastball": _weighted_hitter_split_from_pitch_details(pitch_details, pitch_codes=("FF", "FT", "SI", "FC")),
        "offspeed": _weighted_hitter_split_from_pitch_details(pitch_details, pitch_codes=("CH", "FS", "FO")),
        "breaking": _weighted_hitter_split_from_pitch_details(pitch_details, pitch_codes=("SL", "CU", "KC", "SV")),
    }


def _derive_hitter_zone_splits(
    pitch_details: Mapping[str, Mapping[str, float]],
    *,
    bats: str | None,
) -> dict[str, dict[str, float]]:
    is_left_handed = (bats or "").upper() == "L"

    def _avg_plate_x_is_inside(value: float) -> bool:
        return value >= 0.0 if is_left_handed else value <= 0.0

    return {
        "high": _weighted_hitter_split_from_pitch_details(
            pitch_details,
            predicate=lambda row: (row.get("avg_plate_z") or 0.0) >= 2.75,
        ),
        "low": _weighted_hitter_split_from_pitch_details(
            pitch_details,
            predicate=lambda row: (row.get("avg_plate_z") or 0.0) <= 2.25,
        ),
        "inside": _weighted_hitter_split_from_pitch_details(
            pitch_details,
            predicate=lambda row: _avg_plate_x_is_inside(row.get("avg_plate_x") or 0.0),
        ),
        "outside": _weighted_hitter_split_from_pitch_details(
            pitch_details,
            predicate=lambda row: not _avg_plate_x_is_inside(row.get("avg_plate_x") or 0.0),
        ),
    }


def _weighted_hitter_split_from_pitch_details(
    pitch_details: Mapping[str, Mapping[str, float]],
    *,
    pitch_codes: tuple[str, ...] | None = None,
    predicate: Callable[[Mapping[str, float]], bool] | None = None,
) -> dict[str, float]:
    rows: list[Mapping[str, float]] = []
    for pitch_code, row in pitch_details.items():
        if not isinstance(row, Mapping):
            continue
        if pitch_codes is not None and pitch_code not in pitch_codes:
            continue
        if predicate is not None and not predicate(row):
            continue
        rows.append(row)

    if not rows:
        return {}

    def _weight(row: Mapping[str, float]) -> float:
        return (row.get("pa") or 0.0) if (row.get("pa") or 0.0) > 0 else (row.get("pitches") or 0.0)

    def _weighted_value(stat_key: str, *, percentage_to_rate: bool = False) -> float | None:
        weighted_sum = 0.0
        total_weight = 0.0
        for row in rows:
            raw_value = _as_float(row.get(stat_key))
            weight = _weight(row)
            if raw_value is None or weight <= 0:
                continue
            value = (raw_value / 100.0) if percentage_to_rate else raw_value
            weighted_sum += value * weight
            total_weight += weight
        if total_weight <= 0:
            return None
        return round(weighted_sum / total_weight, 6)

    obp = _weighted_value("obp")
    slg = _weighted_value("slg")
    iso = _weighted_value("iso")
    strikeout_rate = _weighted_value("k_percent", percentage_to_rate=True)

    if None in (obp, slg, iso, strikeout_rate):
        return {}

    return {
        "obp": float(obp),
        "slg": float(slg),
        "iso": float(iso),
        "strikeout_rate": float(strikeout_rate),
    }


def _fetch_savant_hitter_summary(
    player_id: int,
    *,
    season: int,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> dict[str, float]:
    payload = _fetch_text(
        f"{baseball_savant}/savant-player/player-{player_id}?stats=statcast-r-hitting-mlb",
        ssl_context=ssl_context,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return parse_savant_statcast_summary(payload, season=season)


def _fetch_fangraphs_fielding_csv(
    *,
    season: int,
    ssl_context: SSLContext | None,
    fangraphs: str,
) -> str | None:
    url = (
        f"{fangraphs}/leaders-legacy.aspx?pos=all&stats=fld&lg=all&qual=0&type=8"
        f"&season={season}&month=0&season1={season}&ind=0&team=0&rost=0&age=0"
        "&filter=&players=0&startdate=&enddate=&page=1_2000&csv=1"
    )
    try:
        payload = _fetch_text(url, ssl_context=ssl_context, headers={"User-Agent": "Mozilla/5.0"})
    except (HTTPError, URLError, TimeoutError, OSError):
        return None
    if "Name" not in payload or "DRS" not in payload:
        return None
    return payload


def _fetch_savant_fielding_run_value_csv(
    *,
    season: int,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> str | None:
    candidate_urls = (
        (
            f"{baseball_savant}/leaderboard/fielding-run-value"
            f"?type=player&startYear={season}&endYear={season}&team=&position=&min=0&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/fielding-run-value"
            f"?startYear={season}&endYear={season}&csv=true"
        ),
    )
    return _fetch_first_valid_csv(
        candidate_urls,
        required_headers=("name", "total_runs"),
        ssl_context=ssl_context,
    )


def _fetch_savant_oaa_csv(
    *,
    season: int,
    start_year: int | None = None,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> str | None:
    effective_start_year = start_year if start_year is not None else season
    candidate_urls = (
        (
            f"{baseball_savant}/leaderboard/outs_above_average"
            f"?type=Fielder&startYear={effective_start_year}&endYear={season}&split=yes&team=&range=year"
            "&min=0&pos=&roles=&viz=hide&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/outs_above_average"
            f"?type=Fielder&startYear={effective_start_year}&endYear={season}&split=no&team=&range=year"
            "&min=0&pos=&roles=&viz=hide&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/outs_above_average"
            f"?startYear={effective_start_year}&endYear={season}&csv=true"
        ),
    )
    return _fetch_first_valid_csv(
        candidate_urls,
        required_headers=("outs_above_average",),
        ssl_context=ssl_context,
    )


def _fetch_savant_arm_strength_csv(
    *,
    season: int,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> str | None:
    candidate_urls = (
        (
            f"{baseball_savant}/leaderboard/arm-strength"
            f"?type=player&year={season}&minThrows=0&team=&pos=&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/arm-strength"
            f"?year={season}&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/arm-strength"
            f"?startYear={season}&endYear={season}&csv=true"
        ),
    )
    return _fetch_first_valid_csv(
        candidate_urls,
        required_headers=("fielder_name", "arm_overall"),
        ssl_context=ssl_context,
    )


def _fetch_savant_catcher_throwing_csv(
    *,
    season: int,
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> str | None:
    candidate_urls = (
        (
            f"{baseball_savant}/leaderboard/catcher-throwing"
            f"?year={season}&csv=true"
        ),
        (
            f"{baseball_savant}/leaderboard/catcher-throwing"
            f"?startYear={season}&endYear={season}&csv=true"
        ),
    )
    return _fetch_first_valid_csv(
        candidate_urls,
        required_headers=("player_id", "caught_stealing_above_average", "pop_time"),
        ssl_context=ssl_context,
    )


def _apply_savant_arm_strength(
    players: list[dict[str, Any]],
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> None:
    arm_by_id: dict[int, float] = {}
    arm_by_name: dict[str, float] = {}

    for season in seasons:
        payload = _fetch_savant_arm_strength_csv(
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
        if not payload:
            continue
        for row in parse_savant_arm_strength_csv(payload):
            arm_strength = _as_float(row.get("arm_strength"))
            if arm_strength is None:
                continue
            player_id = _as_int(row.get("player_id"))
            if player_id is not None and player_id not in arm_by_id:
                arm_by_id[player_id] = arm_strength
            row_name = _as_str(row.get("name"))
            if row_name:
                normalized = _normalized_name(row_name)
                if normalized and normalized not in arm_by_name:
                    arm_by_name[normalized] = arm_strength

    if not arm_by_id and not arm_by_name:
        return

    for player in players:
        if player.get("type") != "hitter":
            continue
        fielding = player.get("fielding_stats") if isinstance(player.get("fielding_stats"), dict) else {}
        existing_arm = _as_float(fielding.get("armStrength")) or _as_float(fielding.get("averageThrowingVelocity"))
        if existing_arm is not None:
            continue
        player_id = _as_int(player.get("player_id"))
        arm_strength = arm_by_id.get(player_id) if player_id is not None else None
        if arm_strength is None:
            player_name = _as_str(player.get("name"))
            if player_name:
                arm_strength = arm_by_name.get(_normalized_name(player_name))
        if arm_strength is None:
            continue
        fielding["armStrength"] = arm_strength
        player["fielding_stats"] = fielding


def _apply_savant_catcher_defense(
    players: list[dict[str, Any]],
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    baseball_savant: str,
) -> None:
    catcher_by_id: dict[int, dict[str, float]] = {}
    catcher_by_name: dict[str, dict[str, float]] = {}
    frv_by_name: dict[str, dict[str, float]] = {}

    for season in seasons:
        catcher_payload = _fetch_savant_catcher_throwing_csv(
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
        if catcher_payload:
            for row in parse_savant_catcher_throwing_csv(catcher_payload):
                player_id = _as_int(row.get("player_id"))
                row_name = _as_str(row.get("name"))
                metrics = {
                    key: value
                    for key, value in {
                        "catcher_throw_value": _as_float(row.get("catcher_throw_value")),
                        "pop_time": _as_float(row.get("pop_time")),
                        "arm_strength": _as_float(row.get("arm_strength")),
                    }.items()
                    if value is not None
                }
                if not metrics:
                    continue
                if player_id is not None and player_id not in catcher_by_id:
                    catcher_by_id[player_id] = metrics
                if row_name:
                    normalized = _normalized_name(row_name)
                    if normalized and normalized not in catcher_by_name:
                        catcher_by_name[normalized] = metrics

        frv_payload = _fetch_savant_fielding_run_value_csv(
            season=season,
            ssl_context=ssl_context,
            baseball_savant=baseball_savant,
        )
        if frv_payload:
            for row in parse_savant_fielding_run_value_csv(frv_payload):
                player_name = _as_str(row.get("name"))
                if not player_name:
                    continue
                metrics = {
                    key: value
                    for key, value in {
                        "framing_runs": _as_float(row.get("framing_runs")),
                        "catcher_throw_value": _as_float(row.get("throwing_runs")),
                    }.items()
                    if value is not None
                }
                if not metrics:
                    continue
                # FRV does not currently expose player_id in our parsed row,
                # so name-based matching is the primary lookup for this table.
                normalized = _normalized_name(player_name)
                if normalized and normalized not in frv_by_name:
                    frv_by_name[normalized] = metrics

    if not catcher_by_id and not catcher_by_name and not frv_by_name:
        return

    for player in players:
        if player.get("type") != "hitter" or _as_str(player.get("position")) != "C":
            continue
        fielding = player.get("fielding_stats") if isinstance(player.get("fielding_stats"), dict) else {}
        player_id = _as_int(player.get("player_id"))
        player_name = _as_str(player.get("name"))
        normalized_name = _normalized_name(player_name) if player_name else None

        catcher_metrics = catcher_by_id.get(player_id) if player_id is not None else None
        if catcher_metrics is None and normalized_name:
            catcher_metrics = catcher_by_name.get(normalized_name)

        frv_metrics = frv_by_name.get(normalized_name) if normalized_name else None

        if catcher_metrics:
            if _as_float(fielding.get("caughtStealingAboveAverage")) is None and _as_float(fielding.get("catcherThrowValue")) is None:
                ctv = _as_float(catcher_metrics.get("catcher_throw_value"))
                if ctv is not None:
                    fielding["caughtStealingAboveAverage"] = ctv
            if _as_float(fielding.get("avgPopTime2B")) is None and _as_float(fielding.get("popTime")) is None:
                pop = _as_float(catcher_metrics.get("pop_time"))
                if pop is not None:
                    fielding["avgPopTime2B"] = pop
            if _as_float(fielding.get("armStrength")) is None and _as_float(fielding.get("averageThrowingVelocity")) is None:
                arm = _as_float(catcher_metrics.get("arm_strength"))
                if arm is not None:
                    fielding["armStrength"] = arm

        if frv_metrics and _as_float(fielding.get("framingRuns")) is None and _as_float(fielding.get("catcherFramingRuns")) is None:
            framing = _as_float(frv_metrics.get("framing_runs"))
            if framing is not None:
                fielding["framingRuns"] = framing
        if frv_metrics and _as_float(fielding.get("caughtStealingAboveAverage")) is None and _as_float(fielding.get("catcherThrowValue")) is None:
            ctv = _as_float(frv_metrics.get("catcher_throw_value"))
            if ctv is not None:
                fielding["caughtStealingAboveAverage"] = ctv

        player["fielding_stats"] = fielding


def _fetch_first_valid_csv(
    candidate_urls: tuple[str, ...],
    *,
    required_headers: tuple[str, ...],
    ssl_context: SSLContext | None,
) -> str | None:
    for url in candidate_urls:
        try:
            payload = _fetch_text(url, ssl_context=ssl_context, headers={"User-Agent": "Mozilla/5.0"})
        except (HTTPError, URLError, TimeoutError, OSError):
            continue
        header_line = payload.splitlines()[0] if payload.splitlines() else ""
        header_line_normalized = header_line.lstrip("\ufeff").lower()
        if all(header.lower() in header_line_normalized for header in required_headers):
            return payload
    return None


def _player_name_from_row(row: Mapping[str, Any]) -> str | None:
    preferred_name = _as_str(
        row.get("Player")
        or row.get("Name")
        or row.get("player_name")
        or row.get("name")
        or row.get("fielder_name")
        or row.get("entity_name")
    )
    if preferred_name:
        return _normalize_last_first_name(preferred_name)

    last_first_name = _as_str(row.get("last_name, first_name"))
    if last_first_name:
        return _normalize_last_first_name(last_first_name)
    return None


def _normalize_last_first_name(name: str) -> str:
    stripped = name.strip()
    if "," not in stripped:
        return stripped
    last, first = stripped.split(",", 1)
    reordered = f"{first.strip()} {last.strip()}".strip()
    return " ".join(reordered.split())


def _fetch_handedness_splits(
    player_id: int,
    group: str,
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
) -> dict[str, dict[str, float]]:
    for season in seasons:
        splits_by_code: dict[str, dict[str, float]] = {}
        for split_code in ("vl", "vr"):
            payload = _fetch_json(
                f"{mlb_stats_api}/people/{player_id}/stats?stats=statSplits&group={group}&season={season}&sitCodes={split_code}",
                ssl_context=ssl_context,
            )
            stats = payload.get("stats", [])
            if not isinstance(stats, list) or not stats:
                continue
            first_stats = stats[0]
            if not isinstance(first_stats, Mapping):
                continue
            splits = first_stats.get("splits", [])
            if not isinstance(splits, list) or not splits:
                continue
            aggregated = aggregate_split_stats(group, splits)
            if aggregated:
                splits_by_code[split_code] = aggregated
        if splits_by_code:
            return splits_by_code
    return {}


def _fetch_situation_splits(
    player_id: int,
    group: str,
    *,
    codes: tuple[str, ...],
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
) -> dict[str, dict[str, float]]:
    for season in seasons:
        splits_by_code: dict[str, dict[str, float]] = {}
        for split_code in codes:
            payload = _fetch_json(
                f"{mlb_stats_api}/people/{player_id}/stats?stats=statSplits&group={group}&season={season}&sitCodes={split_code}",
                ssl_context=ssl_context,
            )
            stats = payload.get("stats", [])
            if not isinstance(stats, list) or not stats:
                continue
            first_stats = stats[0]
            if not isinstance(first_stats, Mapping):
                continue
            splits = first_stats.get("splits", [])
            if not isinstance(splits, list) or not splits:
                continue
            aggregated = aggregate_split_stats(group, splits)
            if aggregated:
                splits_by_code[split_code] = aggregated
        if splits_by_code:
            return splits_by_code
    return {}


def _fetch_days_on_roster(
    player_id: int,
    group: str,
    *,
    seasons: tuple[int, int],
    ssl_context: SSLContext | None,
    mlb_stats_api: str,
) -> int | None:
    for season in seasons:
        payload = _fetch_json(
            f"{mlb_stats_api}/people/{player_id}/stats?stats=gameLog&group={group}&season={season}",
            ssl_context=ssl_context,
        )
        stats = payload.get("stats", [])
        if not isinstance(stats, list) or not stats:
            continue
        first_stats = stats[0]
        if not isinstance(first_stats, Mapping):
            continue
        splits = first_stats.get("splits", [])
        if not isinstance(splits, list) or not splits:
            continue
        roster_days = game_log_days_on_roster(splits)
        if roster_days is not None:
            return roster_days
    return None


def _nested_str(payload: Mapping[str, Any], key: str, nested_key: str) -> str | None:
    nested = payload.get(key)
    if not isinstance(nested, Mapping):
        return None
    return _as_str(nested.get(nested_key))


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            try:
                return int(float(cleaned))
            except ValueError:
                return None
    return None


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _percentage(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _as_float(numerator)
    denominator_value = _as_float(denominator)
    if numerator_value is None or denominator_value in (None, 0.0):
        return None
    return round((numerator_value / denominator_value) * 100.0, 3)


def _as_percentage_string(value: Any) -> float | None:
    numeric = _as_float(value)
    if numeric is None:
        return None
    return round(numeric * 100.0 if numeric <= 1.0 else numeric, 3)


def _pick_mapping_float(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in mapping:
            value = _as_float(mapping.get(key))
            if value is not None:
                return value
    return None


def _pick_mapping_percentage(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in mapping:
            value = _as_percentage_string(mapping.get(key))
            if value is not None:
                return value
    return None


def _weighted_arsenal_metric(arsenal: Mapping[str, Mapping[str, Any]], *keys: str) -> float | None:
    total_percentage = 0.0
    weighted_value = 0.0
    for stat_line in arsenal.values():
        if not isinstance(stat_line, Mapping):
            continue
        percentage = _as_float(stat_line.get("percentage"))
        if percentage is None or percentage <= 0:
            continue
        metric_value = _pick_mapping_float(stat_line, *keys)
        if metric_value is None:
            continue
        weighted_value += percentage * metric_value
        total_percentage += percentage
    if total_percentage <= 0:
        return None
    return round(weighted_value / total_percentage, 3)


def _format_decimal(value: float) -> str:
    return f"{value:.3f}"


def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _normalized_name(value: str) -> str:
    return " ".join(value.lower().split())