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


def _team_file_target(team: str) -> str:
    return f"league_data/teams/{team}/roster.bin"


def _free_agent_file_target() -> str:
    return "league_data/free_agents.bin"


def build_dry_run_patch_preview(encoder_plan_payload: dict[str, Any]) -> dict[str, Any]:
    payload = _ensure_object(encoder_plan_payload, "root")
    operations = _ensure_list(payload.get("operations") or [], "operations")
    warnings = [str(item) for item in _ensure_list(payload.get("warnings") or [], "warnings")]

    league_folder = _string(payload.get("league_folder"))
    if not league_folder:
        raise ValueError("Encoder plan payload must include non-empty league_folder")

    files: dict[str, dict[str, Any]] = {}
    teams_touched: set[str] = set()

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
            "notes": [
                "This is a dry-run preview only.",
                "No SMB4 league files were modified.",
            ],
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
        },
        "files": sorted_files,
        "warnings": warnings,
    }


def build_dry_run_patch_preview_from_file(encoder_plan_path: Path, output_path: Path) -> dict[str, Any]:
    payload = json.loads(encoder_plan_path.read_text(encoding="utf-8"))
    report = build_dry_run_patch_preview(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
