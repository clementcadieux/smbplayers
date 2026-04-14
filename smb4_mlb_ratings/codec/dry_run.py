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


def _team_file_target(team: str) -> str:
    return f"league_data/teams/{team}/roster.bin"


def _free_agent_file_target() -> str:
    return "league_data/free_agents.bin"


def _normalize_snapshot_player(item: dict[str, Any], *, free_agent: bool = False) -> dict[str, Any]:
    player_id = _string(item.get("player_id"))
    if not player_id:
        raise ValueError("Current snapshot entries must include player_id")
    player_name = _string(item.get("player_name") if not free_agent else item.get("name"))
    role = _string(item.get("role") or item.get("role_hint")) or None
    attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else None
    return {
        "player_id": player_id,
        "player_name": player_name,
        "role": role,
        "attributes": attributes,
    }


def _build_snapshot_index(current_snapshot_payload: dict[str, Any]) -> dict[str, dict[Any, dict[str, Any]]]:
    payload = _ensure_object(current_snapshot_payload, "current_snapshot")
    teams = _ensure_list(payload.get("teams") or [], "current_snapshot.teams")
    free_agents = _ensure_list(payload.get("free_agents") or [], "current_snapshot.free_agents")

    team_slots: dict[tuple[str, str], dict[str, Any]] = {}
    free_agent_players: dict[str, dict[str, Any]] = {}

    for team_item in teams:
        team_obj = _ensure_object(team_item, "current_snapshot.teams[]")
        team_code = _string(team_obj.get("team")).upper()
        if not team_code:
            raise ValueError("Current snapshot team entries must include team")
        roster = _ensure_list(team_obj.get("roster") or [], f"current_snapshot.teams[{team_code}].roster")
        for roster_item in roster:
            roster_obj = _ensure_object(roster_item, f"current_snapshot.teams[{team_code}].roster[]")
            slot_type = _string(roster_obj.get("slot_type"))
            if not slot_type:
                raise ValueError(f"Current snapshot team {team_code} roster entries must include slot_type")
            team_slots[(team_code, slot_type)] = _normalize_snapshot_player(roster_obj)

    for free_agent_item in free_agents:
        free_agent_obj = _ensure_object(free_agent_item, "current_snapshot.free_agents[]")
        normalized = _normalize_snapshot_player(free_agent_obj, free_agent=True)
        free_agent_players[normalized["player_id"]] = normalized

    return {
        "team_slots": team_slots,
        "free_agents": free_agent_players,
    }


def _build_diff(before_state: dict[str, Any], after_state: dict[str, Any]) -> dict[str, Any]:
    changed_fields: list[str] = []
    for field in ("player_id", "player_name", "role"):
        if before_state.get(field) != after_state.get(field):
            changed_fields.append(field)

    before_attrs = before_state.get("attributes") if isinstance(before_state.get("attributes"), dict) else {}
    after_attrs = after_state.get("attributes") if isinstance(after_state.get("attributes"), dict) else {}
    attribute_changes: list[dict[str, Any]] = []
    for key in sorted(set(before_attrs.keys()) | set(after_attrs.keys())):
        before_value = before_attrs.get(key)
        after_value = after_attrs.get(key)
        if before_value != after_value:
            attribute_changes.append(
                {
                    "key": key,
                    "before": before_value,
                    "after": after_value,
                }
            )

    return {
        "has_changes": bool(changed_fields or attribute_changes),
        "changed_fields": changed_fields,
        "attribute_changes": attribute_changes,
    }


def build_dry_run_patch_preview(
    encoder_plan_payload: dict[str, Any],
    *,
    current_snapshot_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _ensure_object(encoder_plan_payload, "root")
    operations = _ensure_list(payload.get("operations") or [], "operations")
    warnings = [str(item) for item in _ensure_list(payload.get("warnings") or [], "warnings")]

    league_folder = _string(payload.get("league_folder"))
    if not league_folder:
        raise ValueError("Encoder plan payload must include non-empty league_folder")

    snapshot_index: dict[str, dict[Any, dict[str, Any]]] | None = None
    if current_snapshot_payload is not None:
        snapshot_index = _build_snapshot_index(current_snapshot_payload)

    files: dict[str, dict[str, Any]] = {}
    teams_touched: set[str] = set()
    concrete_before_count = 0
    missing_before_count = 0
    changed_count = 0

    def _bucket_for(file_target: str) -> dict[str, Any]:
        if file_target not in files:
            files[file_target] = {
                "file_target": file_target,
                "operation_count": 0,
                "operations": [],
            }
        return files[file_target]

    for index, operation in enumerate(operations):
        operation_obj = _ensure_object(operation, f"operations[{index}]")
        operation_type = _string(operation_obj.get("operation_type"))
        operation_id = _string(operation_obj.get("operation_id"))
        target = _ensure_object(operation_obj.get("target") or {}, f"operations[{index}].target")
        player = _ensure_object(operation_obj.get("player") or {}, f"operations[{index}].player")
        attributes = operation_obj.get("attributes") if isinstance(operation_obj.get("attributes"), dict) else None

        if operation_type == "upsert_team_slot":
            team = _string(target.get("team")).upper()
            slot_type = _string(target.get("slot_type"))
            if not team or not slot_type:
                raise ValueError(f"operations[{index}] upsert_team_slot requires team and slot_type")
            teams_touched.add(team)
            file_target = _team_file_target(team)
            target_locator = {
                "pool": "team",
                "team": team,
                "slot_type": slot_type,
                "position_group": _string(target.get("position_group")) or None,
            }
        elif operation_type == "upsert_free_agent":
            file_target = _free_agent_file_target()
            target_locator = {
                "pool": "free_agent",
            }
        else:
            raise ValueError(f"operations[{index}] has unsupported operation_type: {operation_type}")

        preview_item = {
            "operation_id": operation_id,
            "operation_type": operation_type,
            "player_id": _string(player.get("player_id")),
            "player_name": _string(player.get("player_name")),
            "target_locator": target_locator,
            "before_state": "unknown (binary decode not implemented)",
            "after_state_preview": {
                "role": _string(player.get("role")) or None,
                "attribute_source": _string(operation_obj.get("attribute_source")) or None,
                "attribute_keys": sorted(attributes.keys()) if attributes is not None else [],
                "attributes": attributes,
            },
            "diff": None,
            "notes": [
                "This is a dry-run preview only.",
                "No SMB4 league files were modified.",
            ],
        }

        if snapshot_index is not None:
            before_state: dict[str, Any] | None = None
            if operation_type == "upsert_team_slot":
                before_state = snapshot_index["team_slots"].get((target_locator["team"], target_locator["slot_type"]))
            elif operation_type == "upsert_free_agent":
                before_state = snapshot_index["free_agents"].get(preview_item["player_id"])

            if before_state is not None:
                concrete_before_count += 1
                preview_item["before_state"] = before_state
                after_state = {
                    "player_id": preview_item["player_id"],
                    "player_name": preview_item["player_name"],
                    "role": preview_item["after_state_preview"]["role"],
                    "attributes": preview_item["after_state_preview"]["attributes"],
                }
                diff = _build_diff(before_state, after_state)
                preview_item["diff"] = diff
                if diff["has_changes"]:
                    changed_count += 1
            else:
                missing_before_count += 1
                preview_item["before_state"] = "missing in supplied current snapshot"
                preview_item["diff"] = {
                    "has_changes": True,
                    "changed_fields": ["player_assignment"],
                    "attribute_changes": [],
                }

        bucket = _bucket_for(file_target)
        bucket["operation_count"] += 1
        bucket["operations"].append(preview_item)

    sorted_files = [files[key] for key in sorted(files.keys())]

    return {
        "report_version": "v1",
        "mode": "dry_run",
        "writes_binary_data": False,
        "league_folder": league_folder,
        "source": _ensure_object(payload.get("source") or {}, "source"),
        "summary": {
            "total_operations": len(operations),
            "files_touched": len(sorted_files),
            "teams_touched": len(teams_touched),
            "warnings_count": len(warnings),
            "concrete_before_states": concrete_before_count,
            "missing_before_states": missing_before_count,
            "changed_operations": changed_count,
        },
        "files": sorted_files,
        "warnings": warnings,
    }


def build_dry_run_patch_preview_from_file(
    encoder_plan_path: Path,
    output_path: Path,
    *,
    current_snapshot_path: Path | None = None,
) -> dict[str, Any]:
    payload = _read_json_file(encoder_plan_path)
    current_snapshot_payload: dict[str, Any] | None = None
    if current_snapshot_path is not None:
        current_snapshot_payload = _ensure_object(_read_json_file(current_snapshot_path), "current_snapshot")
    report = build_dry_run_patch_preview(payload, current_snapshot_payload=current_snapshot_payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
