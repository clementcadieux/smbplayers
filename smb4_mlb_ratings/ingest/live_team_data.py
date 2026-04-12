from __future__ import annotations

import csv
import io
import json
import re
from ssl import SSLContext
from typing import Any, Iterable, Mapping
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .live_metrics import (
    aggregate_split_stats,
    derive_hitter_situational_metrics,
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


def parse_savant_statcast_summary(payload: str, *, season: int) -> dict[str, float]:
    match = re.search(r"statcast:\s*(\[.*?\]),\s*statcastArrayString:", payload, re.DOTALL)
    if not match:
        return {}
    try:
        rows = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    if not isinstance(rows, list):
        return {}

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _as_int(row.get("year")) != season:
            continue
        zone_contact_pct = _as_float(row.get("iz_contact_percent"))
        out_of_zone_contact_pct = _as_float(row.get("oz_contact_percent"))
        if zone_contact_pct is None or out_of_zone_contact_pct is None:
            return {}
        return {
            "zone_contact_pct": zone_contact_pct,
            "out_of_zone_contact_pct": out_of_zone_contact_pct,
        }
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
        advanced = player.get("advanced_hitting") if isinstance(player.get("advanced_hitting"), Mapping) else {}
        hitting_splits = player.get("hitting_handedness_splits") if isinstance(player.get("hitting_handedness_splits"), Mapping) else {}
        savant_hitting_summary = player.get("savant_hitting_summary") if isinstance(player.get("savant_hitting_summary"), Mapping) else {}
        situational_hitting_metrics = player.get("situational_hitting_metrics") if isinstance(player.get("situational_hitting_metrics"), Mapping) else {}
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
                "z_contact_pct": savant_hitting_summary.get("zone_contact_pct"),
                "o_contact_pct": savant_hitting_summary.get("out_of_zone_contact_pct"),
                "first_pitch_hitting": situational_hitting_metrics.get("first_pitch_hitting"),
                "risp_hitting": situational_hitting_metrics.get("risp_hitting"),
                "pressure_hitting": situational_hitting_metrics.get("pressure_hitting"),
                "late_game_hitting": situational_hitting_metrics.get("late_game_hitting"),
                "trailing_bases_empty_hitting": situational_hitting_metrics.get("trailing_bases_empty_hitting"),
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
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
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
    return rows


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


def build_fangraphs_fielding_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
    season: int,
    ssl_context: SSLContext | None = None,
    fangraphs: str = DEFAULT_FANGRAPHS,
    csv_payload: str | None = None,
) -> list[dict[str, object]]:
    payload = csv_payload
    if payload is None:
        payload = _fetch_fangraphs_fielding_csv(season=season, ssl_context=ssl_context, fangraphs=fangraphs)
    if not payload:
        return []

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


def build_baseball_reference_pitcher_rows(
    players: Iterable[Mapping[str, Any]],
    *,
    team_abbreviation: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player in players:
        if player.get("type") != "pitcher":
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
        advanced = player.get("advanced_pitching") if isinstance(player.get("advanced_pitching"), Mapping) else {}
        arsenal_data = player.get("pitch_arsenal") if isinstance(player.get("pitch_arsenal"), Mapping) else {}
        pitching_splits = player.get("pitching_handedness_splits") if isinstance(player.get("pitching_handedness_splits"), Mapping) else {}
        situational_pitching_metrics = player.get("situational_pitching_metrics") if isinstance(player.get("situational_pitching_metrics"), Mapping) else {}
        savant_pitch_details = player.get("savant_pitch_details") if isinstance(player.get("savant_pitch_details"), Mapping) else {}
        pitch_quality = derive_pitch_quality_metrics(arsenal_data, savant_pitch_details)
        throws = _as_str(player.get("throws"))
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
                "BB %": _percentage(player.get("walks"), player.get("batters_faced")),
                "Strike %": _as_percentage_string(player.get("strike_percentage")),
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
    fangraphs_fielding_file: str | None = None,
    baseball_reference_hitters_file: str,
    baseball_reference_pitchers_file: str,
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
    if fangraphs_fielding_file:
        sources["fangraphs"] = {"files": {"fielding": fangraphs_fielding_file}}

    return {
        "source": "mixed",
        "roster_filter": {"team": team_abbreviation, "year": roster_season},
        "seasons": {
            "current": {
                "year": roster_season,
                "sources": sources,
            }
        },
    }


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
    if status != "Active" and "injured" not in status.lower():
        return None

    position = _as_str(roster_position.get("abbreviation")) or _as_str(primary_position.get("abbreviation"))
    position_type = _as_str(roster_position.get("type"))
    if position_type == "Pitcher" or position == "P":
        stat_group = "pitching"
        player_type = "pitcher"
    else:
        stat_group = "hitting"
        player_type = "hitter"

    stats = _fetch_stats(player_id, stat_group, seasons=seasons, ssl_context=ssl_context, mlb_stats_api=mlb_stats_api)
    if stats is None:
        return None
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

    base_player: dict[str, Any] = {
        "player_id": player_id,
        "name": _as_str(person.get("fullName")) or _as_str(person_summary.get("fullName")),
        "team": team_abbreviation,
        "type": player_type,
        "position": position,
        "status": status,
        "status_code": _as_str(status_payload.get("code")) or "A",
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

    if player_type == "hitter":
        savant_hitting_summary = _fetch_savant_hitter_summary(
            player_id,
            season=seasons[0],
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
        plate_appearances = _as_int(stats.get("plateAppearances")) or 0
        if plate_appearances == 0:
            return None
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
        return None
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