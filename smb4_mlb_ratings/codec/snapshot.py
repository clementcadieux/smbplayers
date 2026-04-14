from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _ensure_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object at {path}")
    return value


def _ensure_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Expected array at {path}")
    return value


def _string(value: object) -> str:
    return str(value or "").strip()


def _read_json_file(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return json.loads(path.read_text(encoding="utf-8-sig"))


def _first_non_empty(obj: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = _string(obj.get(key))
        if value:
            return value
    return ""


def _normalize_player_entry(item: dict[str, Any], *, path: str) -> dict[str, Any]:
    player_obj = item.get("player") if isinstance(item.get("player"), dict) else item
    player = _ensure_object(player_obj, path)

    player_id = _first_non_empty(player, "player_id", "id", "mlbam_id", "statsapi_id")
    if not player_id:
        raise ValueError(f"Missing player_id at {path}")

    player_name = _first_non_empty(player, "player_name", "name")
    role = _first_non_empty(player, "role", "role_hint") or None
    attributes = None
    if isinstance(item.get("attributes"), dict):
        attributes = item.get("attributes")
    elif isinstance(player.get("attributes"), dict):
        attributes = player.get("attributes")
    elif isinstance(player.get("ratings"), dict):
        attributes = player.get("ratings")

    return {
        "player_id": player_id,
        "player_name": player_name,
        "role": role,
        "attributes": attributes,
    }


def _normalize_team_roster_entries(team_code: str, team_obj: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    roster = team_obj.get("roster")
    if not isinstance(roster, list):
        roster = team_obj.get("players")
    if not isinstance(roster, list):
        roster = team_obj.get("slots")
    roster_entries = _ensure_list(roster or [], f"{path}.roster")

    normalized: list[dict[str, Any]] = []
    for index, roster_entry in enumerate(roster_entries):
        entry = _ensure_object(roster_entry, f"{path}.roster[{index}]")
        slot_type = _first_non_empty(entry, "slot_type", "slot", "roster_slot")
        if not slot_type:
            raise ValueError(f"Missing slot_type for {team_code} at {path}.roster[{index}]")
        player = _normalize_player_entry(entry, path=f"{path}.roster[{index}]")
        player["slot_type"] = slot_type
        normalized.append(player)
    return normalized


def _normalize_teams_from_array(teams: list[Any], *, path: str) -> list[dict[str, Any]]:
    normalized_teams: list[dict[str, Any]] = []
    for index, team_item in enumerate(teams):
        team_obj = _ensure_object(team_item, f"{path}[{index}]")
        team_code = _first_non_empty(team_obj, "team", "team_code", "abbreviation").upper()
        if not team_code:
            raise ValueError(f"Missing team code at {path}[{index}]")
        roster = _normalize_team_roster_entries(team_code, team_obj, path=f"{path}[{index}]")
        normalized_teams.append(
            {
                "team": team_code,
                "roster": roster,
            }
        )
    return normalized_teams


def _normalize_teams_from_object(rosters: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    normalized_teams: list[dict[str, Any]] = []
    for team_code_raw, team_payload in sorted(rosters.items()):
        team_code = _string(team_code_raw).upper()
        team_obj = _ensure_object(team_payload, f"{path}.{team_code}")

        if isinstance(team_obj.get("roster"), list) or isinstance(team_obj.get("players"), list) or isinstance(team_obj.get("slots"), list):
            roster = _normalize_team_roster_entries(team_code, team_obj, path=f"{path}.{team_code}")
        else:
            roster = []
            for slot_key, slot_payload in sorted(team_obj.items()):
                slot_obj = _ensure_object(slot_payload, f"{path}.{team_code}.{slot_key}")
                normalized = _normalize_player_entry(slot_obj, path=f"{path}.{team_code}.{slot_key}")
                normalized["slot_type"] = _string(slot_key)
                roster.append(normalized)

        normalized_teams.append(
            {
                "team": team_code,
                "roster": roster,
            }
        )
    return normalized_teams


def _normalize_free_agents(payload: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    free_agents_obj = payload.get("free_agents")
    if not isinstance(free_agents_obj, list):
        free_agents_obj = payload.get("freeAgents")
    free_agents = _ensure_list(free_agents_obj or [], path)

    normalized: list[dict[str, Any]] = []
    for index, free_agent in enumerate(free_agents):
        item = _ensure_object(free_agent, f"{path}[{index}]")
        player = _normalize_player_entry(item, path=f"{path}[{index}]")
        normalized.append(
            {
                "player_id": player["player_id"],
                "name": player["player_name"],
                "role_hint": player["role"],
                "attributes": player["attributes"],
            }
        )
    return normalized


def build_canonical_snapshot_payload(decoded_payload: dict[str, Any]) -> dict[str, Any]:
    payload = _ensure_object(decoded_payload, "decoded_payload")

    teams_value = payload.get("teams")
    if isinstance(teams_value, list):
        teams = _normalize_teams_from_array(teams_value, path="teams")
    else:
        rosters_value = payload.get("rosters")
        if not isinstance(rosters_value, dict):
            rosters_value = payload.get("team_rosters") if isinstance(payload.get("team_rosters"), dict) else {}
        teams = _normalize_teams_from_object(rosters_value, path="rosters")

    free_agents = _normalize_free_agents(payload, path="free_agents")

    return {
        "schema_version": "v1",
        "teams": teams,
        "free_agents": free_agents,
    }


def build_canonical_snapshot_from_file(decoded_snapshot_path: Path, output_path: Path) -> dict[str, Any]:
    payload = _read_json_file(decoded_snapshot_path)
    canonical = build_canonical_snapshot_payload(_ensure_object(payload, "decoded_payload"))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(canonical, indent=2), encoding="utf-8")
    return canonical


def load_canonical_snapshot_from_decoded(decoded_snapshot_path: Path) -> dict[str, Any]:
    payload = _read_json_file(decoded_snapshot_path)
    return build_canonical_snapshot_payload(_ensure_object(payload, "decoded_payload"))
