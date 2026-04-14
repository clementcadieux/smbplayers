from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path


DEFAULT_LEAGUE_FOLDER = Path("C:/Users/cadie/AppData/Local/Metalhead/Super Mega Baseball 4/76561198054354622")


@dataclass(slots=True)
class TeamReportRecord:
    player_id: str
    name: str
    team: str
    source_file: str
    role_hint: str
    attributes: dict[str, object]


@dataclass(slots=True)
class BaseRosterSlot:
    team: str
    slot_type: str
    position_group: str
    player_id: str
    player_name: str | None
    role: str | None


def resolve_league_folder(league_folder_override: Path | None = None) -> Path:
    if league_folder_override is None:
        return DEFAULT_LEAGUE_FOLDER
    return league_folder_override


def _normalize_header(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _normalize_id(value: object) -> str:
    text = str(value).strip()
    if not text:
        return ""
    return text


def _coerce_cell(value: str) -> object:
    text = value.strip()
    if text == "":
        return ""
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return text


def _extract_player_id(row: dict[str, str], source_file: Path, row_number: int) -> str:
    for key, value in row.items():
        if _normalize_header(key) == "player_id":
            player_id = _normalize_id(value)
            if not player_id:
                raise ValueError(f"{source_file.name}:{row_number} has an empty player_id")
            return player_id
    raise ValueError(
        f"{source_file.name} is missing required player_id column; regenerate team_reports with player IDs before running bridge"
    )


def _extract_name(row: dict[str, str]) -> str:
    for key, value in row.items():
        if _normalize_header(key) == "name":
            return str(value).strip()
    return ""


def load_team_reports(team_reports_dir: Path) -> dict[str, TeamReportRecord]:
    records: dict[str, TeamReportRecord] = {}
    duplicates: dict[str, list[str]] = {}

    report_files = sorted(team_reports_dir.glob("*_hitters.csv")) + sorted(team_reports_dir.glob("*_pitchers.csv"))
    if not report_files:
        raise ValueError(f"No team report CSV files found in {team_reports_dir}")

    for report_file in report_files:
        suffix = report_file.stem.split("_", 1)[-1]
        role_hint = "hitter" if suffix == "hitters" else "pitcher"
        team_code = report_file.name.split("_", 1)[0].upper()
        with report_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                continue
            for row_number, row in enumerate(reader, start=2):
                player_id = _extract_player_id(row, report_file, row_number)
                attributes = {
                    _normalize_header(str(key)): _coerce_cell(str(value))
                    for key, value in row.items()
                    if key is not None
                }
                record = TeamReportRecord(
                    player_id=player_id,
                    name=_extract_name(row),
                    team=team_code,
                    source_file=report_file.name,
                    role_hint=role_hint,
                    attributes=attributes,
                )
                if player_id in records:
                    duplicates.setdefault(player_id, [records[player_id].source_file]).append(report_file.name)
                    continue
                records[player_id] = record

    if duplicates:
        duplicate_text = "; ".join(f"{player_id}: {', '.join(files)}" for player_id, files in sorted(duplicates.items()))
        raise ValueError(f"Duplicate player_id values found in team_reports: {duplicate_text}")

    return records


def load_base_roster_slots(league_roster_path: Path) -> tuple[list[BaseRosterSlot], set[str]]:
    payload = json.loads(league_roster_path.read_text(encoding="utf-8"))
    teams = payload.get("teams") if isinstance(payload, dict) else None
    if not isinstance(teams, list):
        raise ValueError("league_roster payload must include a teams array")

    slots: list[BaseRosterSlot] = []
    selected_player_ids: set[str] = set()
    duplicate_assignments: list[str] = []

    for team_entry in teams:
        if not isinstance(team_entry, dict):
            continue
        team = str(team_entry.get("team") or "").upper().strip()
        roster = team_entry.get("recommended_roster")
        if not team or not isinstance(roster, list):
            continue
        for item in roster:
            if not isinstance(item, dict):
                continue
            player = item.get("player")
            if not isinstance(player, dict):
                continue
            player_id = _normalize_id(player.get("player_id"))
            if not player_id:
                raise ValueError(f"Roster slot for team {team} is missing player.player_id")
            if player_id in selected_player_ids:
                duplicate_assignments.append(player_id)
            selected_player_ids.add(player_id)
            slots.append(
                BaseRosterSlot(
                    team=team,
                    slot_type=str(item.get("slot_type") or ""),
                    position_group=str(item.get("position_group") or ""),
                    player_id=player_id,
                    player_name=str(player.get("name") or "") or None,
                    role=str(player.get("role") or "") or None,
                )
            )

    if duplicate_assignments:
        duplicates = ", ".join(sorted(set(duplicate_assignments)))
        raise ValueError(f"Duplicate player_id assignments found in base roster: {duplicates}")

    return slots, selected_player_ids


def build_roster_attribute_bridge(
    league_roster_path: Path,
    team_reports_dir: Path,
    *,
    league_folder_override: Path | None = None,
) -> dict[str, object]:
    slots, selected_player_ids = load_base_roster_slots(league_roster_path)
    team_records = load_team_reports(team_reports_dir)
    warnings: list[str] = []

    teams_payload: dict[str, list[dict[str, object]]] = {}
    for slot in slots:
        record = team_records.get(slot.player_id)
        if record is None:
            warnings.append(
                f"Missing team_reports attributes for rostered player_id {slot.player_id} ({slot.player_name or 'unknown'}) on {slot.team}"
            )
        team_slot_payload = {
            "slot_type": slot.slot_type,
            "position_group": slot.position_group,
            "player_id": slot.player_id,
            "player_name": slot.player_name,
            "role": slot.role,
            "attributes": record.attributes if record is not None else None,
            "attribute_source": record.source_file if record is not None else None,
        }
        teams_payload.setdefault(slot.team, []).append(team_slot_payload)

    free_agent_records = [
        record
        for player_id, record in sorted(team_records.items(), key=lambda item: (item[1].team, item[1].name, item[0]))
        if player_id not in selected_player_ids
    ]

    return {
        "league_folder": str(resolve_league_folder(league_folder_override)),
        "source": {
            "league_roster": str(league_roster_path),
            "team_reports": str(team_reports_dir),
        },
        "teams": [
            {
                "team": team,
                "roster": roster,
            }
            for team, roster in sorted(teams_payload.items())
        ],
        "free_agents": [
            {
                "player_id": record.player_id,
                "name": record.name,
                "team": record.team,
                "role_hint": record.role_hint,
                "attributes": record.attributes,
                "attribute_source": record.source_file,
            }
            for record in free_agent_records
        ],
        "warnings": warnings,
    }
