from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


REFERENCE_PATH = Path(__file__).resolve().parent.parent / "smb4_player_reference.json"
DEFAULT_PITCH_SLOT_LIMIT = 4
DEFAULT_PITCH_MAPPINGS = {
    "ff": {"mlb_name": "Four-Seam Fastball", "smb4_name": "4-Seam Fastball", "merge_target": None},
    "si": {"mlb_name": "Sinker", "smb4_name": "2-Seam Fastball", "merge_target": None},
    "fc": {"mlb_name": "Cutter", "smb4_name": "Cut Fastball", "merge_target": None},
    "sl": {"mlb_name": "Slider", "smb4_name": "Slider", "merge_target": None},
    "cu": {"mlb_name": "Curveball", "smb4_name": "Curveball", "merge_target": None},
    "ch": {"mlb_name": "Changeup", "smb4_name": "Changeup", "merge_target": None},
    "fs": {"mlb_name": "Splitter", "smb4_name": "Forkball", "merge_target": None},
    "sv": {"mlb_name": "Sweeper", "smb4_name": None, "merge_target": "Slider"},
    "kn": {"mlb_name": "Knuckleball", "smb4_name": None, "merge_target": None},
}


@dataclass(frozen=True, slots=True)
class PitchMapping:
    mlb_name: str
    smb4_name: str | None
    merge_target: str | None


def load_pitch_selector_config() -> tuple[int, dict[str, PitchMapping]]:
    slot_limit = DEFAULT_PITCH_SLOT_LIMIT
    raw_mappings = DEFAULT_PITCH_MAPPINGS
    try:
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        payload = {}

    raw_slot_limit = payload.get("pitch_slot_limit")
    if raw_slot_limit is not None:
        try:
            slot_limit = max(1, int(raw_slot_limit))
        except (TypeError, ValueError):
            slot_limit = DEFAULT_PITCH_SLOT_LIMIT

    configured_mappings = payload.get("pitch_mappings")
    if isinstance(configured_mappings, dict) and configured_mappings:
        raw_mappings = configured_mappings

    mappings: dict[str, PitchMapping] = {}
    for pitch_code, raw_mapping in raw_mappings.items():
        if not isinstance(raw_mapping, dict):
            continue
        mappings[str(pitch_code).lower()] = PitchMapping(
            mlb_name=str(raw_mapping.get("mlb_name", pitch_code)),
            smb4_name=str(raw_mapping["smb4_name"]) if raw_mapping.get("smb4_name") is not None else None,
            merge_target=str(raw_mapping["merge_target"]) if raw_mapping.get("merge_target") is not None else None,
        )
    return slot_limit, mappings


PITCH_SLOT_LIMIT, PITCH_MAPPINGS = load_pitch_selector_config()


def select_pitch_mix(pitch_mix: dict[str, float]) -> list[str]:
    merged_usage: dict[str, float] = defaultdict(float)
    for raw_pitch_code, raw_usage in pitch_mix.items():
        try:
            usage = float(raw_usage)
        except (TypeError, ValueError):
            continue
        if usage <= 0:
            continue
        pitch_code = str(raw_pitch_code).lower()
        mapping = PITCH_MAPPINGS.get(pitch_code)
        if mapping is None:
            continue
        target_pitch = mapping.smb4_name or mapping.merge_target
        if not target_pitch:
            continue
        merged_usage[target_pitch] += usage
    ordered = sorted(merged_usage.items(), key=lambda item: (-item[1], item[0]))
    return [pitch_name for pitch_name, _ in ordered[:PITCH_SLOT_LIMIT]]