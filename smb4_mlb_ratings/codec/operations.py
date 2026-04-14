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


def _team_slot_sort_key(slot_type: str) -> tuple[int, str, int]:
    normalized = slot_type.lower()
    if normalized.startswith("sp"):
        prefix_rank = 0
        suffix = normalized[2:]
    elif normalized.startswith("rp"):
        prefix_rank = 1
        suffix = normalized[2:]
    elif normalized.startswith("c"):
        prefix_rank = 2
        suffix = normalized[1:]
    elif normalized.startswith("if"):
        prefix_rank = 3
        suffix = normalized[2:]
    elif normalized.startswith("of"):
        prefix_rank = 4
        suffix = normalized[2:]
    elif normalized.startswith("flex"):
        prefix_rank = 5
        suffix = normalized[4:]
    else:
        prefix_rank = 9
        suffix = normalized

    try:
        numeric_suffix = int(suffix)
    except ValueError:
        numeric_suffix = 999
    return prefix_rank, normalized, numeric_suffix


def build_encoder_operation_plan(codec_import_payload: dict[str, Any]) -> dict[str, Any]:
    payload = _ensure_object(codec_import_payload, "root")
    records = _ensure_list(payload.get("records") or [], "records")

    league_folder = payload.get("league_folder")
    if not isinstance(league_folder, str) or not league_folder.strip():
        raise ValueError("Codec import payload must include non-empty league_folder")

    team_operations: list[dict[str, Any]] = []
    free_agent_operations: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        record_obj = _ensure_object(record, f"records[{index}]")
        target_pool = _string(record_obj.get("target_pool"))
        player_id = _string(record_obj.get("player_id"))
        player_name = _string(record_obj.get("player_name"))
        if not player_id:
            raise ValueError(f"records[{index}] is missing player_id")
        if not player_name:
            player_name = f"player_{player_id}"

        base_operation = {
            "player": {
                "player_id": player_id,
                "player_name": player_name,
                "role": _string(record_obj.get("role")) or None,
            },
            "attributes": record_obj.get("attributes") if isinstance(record_obj.get("attributes"), dict) else None,
            "attribute_source": _string(record_obj.get("attribute_source")) or None,
        }

        if target_pool == "team":
            team = _string(record_obj.get("team")).upper()
            slot_type = _string(record_obj.get("slot_type"))
            if not team or not slot_type:
                raise ValueError(f"records[{index}] with target_pool=team requires team and slot_type")
            operation = {
                "operation_type": "upsert_team_slot",
                "operation_id": f"team:{team}:{slot_type}:{player_id}",
                "target": {
                    "pool": "team",
                    "team": team,
                    "slot_type": slot_type,
                    "position_group": _string(record_obj.get("position_group")) or None,
                },
                **base_operation,
            }
            team_operations.append(operation)
            continue

        if target_pool == "free_agent":
            operation = {
                "operation_type": "upsert_free_agent",
                "operation_id": f"free_agent:{player_id}",
                "target": {
                    "pool": "free_agent",
                },
                **base_operation,
            }
            free_agent_operations.append(operation)
            continue

        raise ValueError(f"records[{index}] has unsupported target_pool: {target_pool}")

    team_operations.sort(
        key=lambda item: (
            _string(item["target"].get("team")),
            _team_slot_sort_key(_string(item["target"].get("slot_type"))),
            _string(item["player"].get("player_id")),
        )
    )
    free_agent_operations.sort(
        key=lambda item: (
            _string(item["player"].get("player_name")).lower(),
            _string(item["player"].get("player_id")),
        )
    )

    operations = team_operations + free_agent_operations
    return {
        "plan_version": "v1",
        "codec_version": _string(payload.get("codec_version")) or "v1",
        "league_folder": league_folder,
        "source": {
            "league_roster": _string(_ensure_object(payload.get("source") or {}, "source").get("league_roster")) or None,
            "team_reports": _string(_ensure_object(payload.get("source") or {}, "source").get("team_reports")) or None,
            "codec_import": _string(_ensure_object(payload.get("source") or {}, "source").get("bridge_payload")) or None,
        },
        "stats": {
            "team_operations": len(team_operations),
            "free_agent_operations": len(free_agent_operations),
            "total_operations": len(operations),
        },
        "operations": operations,
        "warnings": [str(item) for item in _ensure_list(payload.get("warnings") or [], "warnings")],
    }


def build_encoder_operation_plan_from_file(codec_import_path: Path, output_path: Path) -> dict[str, Any]:
    payload = json.loads(codec_import_path.read_text(encoding="utf-8"))
    operation_plan = build_encoder_operation_plan(payload)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(operation_plan, indent=2), encoding="utf-8")
    return operation_plan
