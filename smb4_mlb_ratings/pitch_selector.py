from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .reference import load_pitch_selector_config as load_reference_pitch_selector_config


@dataclass(frozen=True, slots=True)
class PitchMapping:
    mlb_name: str
    smb4_name: str | None
    merge_target: str | None


def load_pitch_selector_config() -> tuple[int, dict[str, PitchMapping]]:
    slot_limit, raw_mappings = load_reference_pitch_selector_config()

    mappings: dict[str, PitchMapping] = {}
    for pitch_code, raw_mapping in raw_mappings.items():
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