from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CodecImportRecord:
    player_id: str
    player_name: str
    target_pool: str
    team: str | None
    slot_type: str | None
    position_group: str | None
    role: str | None
    attributes: dict[str, Any] | None
    attribute_source: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "target_pool": self.target_pool,
            "team": self.team,
            "slot_type": self.slot_type,
            "position_group": self.position_group,
            "role": self.role,
            "attributes": self.attributes,
            "attribute_source": self.attribute_source,
        }


def _normalize_player_id(value: object) -> str:
    player_id = str(value or "").strip()
    if not player_id:
        raise ValueError("Codec interface payload requires non-empty player_id values")
    return player_id


def _normalize_player_name(value: object, player_id: str) -> str:
    name = str(value or "").strip()
    if name:
        return name
    return f"player_{player_id}"


def _ensure_object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Expected object at {path}")
    return value


def _ensure_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Expected array at {path}")
    return value


def _record_from_team_roster(team: str, roster_item: dict[str, Any]) -> CodecImportRecord:
    player_id = _normalize_player_id(roster_item.get("player_id"))
    player_name = _normalize_player_name(roster_item.get("player_name"), player_id)
    return CodecImportRecord(
        player_id=player_id,
        player_name=player_name,
        target_pool="team",
        team=team,
        slot_type=str(roster_item.get("slot_type") or "") or None,
        position_group=str(roster_item.get("position_group") or "") or None,
        role=str(roster_item.get("role") or "") or None,
        attributes=roster_item.get("attributes") if isinstance(roster_item.get("attributes"), dict) else None,
        attribute_source=str(roster_item.get("attribute_source") or "") or None,
    )


def _record_from_free_agent(free_agent_item: dict[str, Any]) -> CodecImportRecord:
    player_id = _normalize_player_id(free_agent_item.get("player_id"))
    player_name = _normalize_player_name(free_agent_item.get("name"), player_id)
    return CodecImportRecord(
        player_id=player_id,
        player_name=player_name,
        target_pool="free_agent",
        team=None,
        slot_type=None,
        position_group=None,
        role=str(free_agent_item.get("role_hint") or "") or None,
        attributes=free_agent_item.get("attributes") if isinstance(free_agent_item.get("attributes"), dict) else None,
        attribute_source=str(free_agent_item.get("attribute_source") or "") or None,
    )


def load_bridge_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _ensure_object(payload, "root")


def build_codec_import_payload(
    bridge_payload: dict[str, Any],
    *,
    league_folder_override: Path | None = None,
) -> dict[str, Any]:
    source = _ensure_object(bridge_payload.get("source") or {}, "source")
    teams = _ensure_list(bridge_payload.get("teams") or [], "teams")
    free_agents = _ensure_list(bridge_payload.get("free_agents") or [], "free_agents")
    warnings = _ensure_list(bridge_payload.get("warnings") or [], "warnings")

    records: list[CodecImportRecord] = []
    seen_player_ids: set[str] = set()
    duplicate_ids: set[str] = set()

    for team_item in teams:
        team_obj = _ensure_object(team_item, "teams[]")
        team = str(team_obj.get("team") or "").strip().upper()
        if not team:
            raise ValueError("Each teams[] item must include a non-empty team code")
        roster = _ensure_list(team_obj.get("roster") or [], f"teams[{team}].roster")
        for roster_item in roster:
            roster_obj = _ensure_object(roster_item, f"teams[{team}].roster[]")
            record = _record_from_team_roster(team, roster_obj)
            if record.player_id in seen_player_ids:
                duplicate_ids.add(record.player_id)
            seen_player_ids.add(record.player_id)
            records.append(record)

    for free_agent_item in free_agents:
        free_agent_obj = _ensure_object(free_agent_item, "free_agents[]")
        record = _record_from_free_agent(free_agent_obj)
        if record.player_id in seen_player_ids:
            duplicate_ids.add(record.player_id)
        seen_player_ids.add(record.player_id)
        records.append(record)

    if duplicate_ids:
        duplicate_text = ", ".join(sorted(duplicate_ids))
        raise ValueError(f"Bridge payload contains duplicate player_id assignments across team/free agent pools: {duplicate_text}")

    league_folder_value: object
    if league_folder_override is not None:
        league_folder_value = str(league_folder_override)
    else:
        league_folder_value = bridge_payload.get("league_folder")
    if not isinstance(league_folder_value, str) or not league_folder_value.strip():
        raise ValueError("Bridge payload must include league_folder or provide override")

    return {
        "codec_version": "v1",
        "league_folder": league_folder_value,
        "source": {
            "bridge_payload": str(source.get("league_roster") or ""),
            "league_roster": str(source.get("league_roster") or ""),
            "team_reports": str(source.get("team_reports") or ""),
        },
        "stats": {
            "team_records": sum(1 for item in records if item.target_pool == "team"),
            "free_agent_records": sum(1 for item in records if item.target_pool == "free_agent"),
            "total_records": len(records),
            "team_count": len(teams),
        },
        "records": [item.to_dict() for item in records],
        "warnings": [str(item) for item in warnings],
    }


def build_codec_import_from_file(
    bridge_payload_path: Path,
    output_path: Path,
    *,
    league_folder_override: Path | None = None,
) -> dict[str, Any]:
    bridge_payload = load_bridge_payload(bridge_payload_path)
    codec_payload = build_codec_import_payload(bridge_payload, league_folder_override=league_folder_override)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(codec_payload, indent=2), encoding="utf-8")
    return codec_payload
