from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from ..models import RatingOutput


HITTER_COLUMNS = [
    "Name",
    "Throw Hand",
    "Bat Hand",
    "Primary Position",
    "Secondary Positions",
    "Letter Grade",
    "Contact",
    "Power",
    "Speed",
    "Fielding",
    "Arm",
    "Trait 1",
    "Trait 2",
]

PITCHER_COLUMNS = [
    "Name",
    "Throw Hand",
    "Bat Hand",
    "Arsenal",
    "Letter Grade",
    "Velocity",
    "Junk",
    "Accuracy",
    "Trait 1",
    "Trait 2",
    "Contact",
    "Power",
    "Speed",
    "Fielding",
    "Arm",
]

PITCHER_ROLES = {"pitcher", "sp", "rp"}


def _clean_text(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value)


def _metadata_lookup(metadata: Mapping[str, object], dotted_key: str) -> object | None:
    current: object = metadata
    for key in dotted_key.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _metadata_text(metadata: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = _metadata_lookup(metadata, key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_throw_hand(player: RatingOutput) -> str:
    if isinstance(player.throws, str) and player.throws.strip():
        return player.throws.strip()
    metadata = player.metadata if isinstance(player.metadata, Mapping) else {}
    return _metadata_text(metadata, "throws", "throw_hand", "ingest.throws")


def _extract_bat_hand(player: RatingOutput) -> str:
    if isinstance(player.bats, str) and player.bats.strip():
        return player.bats.strip()
    metadata = player.metadata if isinstance(player.metadata, Mapping) else {}
    return _metadata_text(metadata, "bats", "bat_hand", "ingest.bats")


def _rating_value(player: RatingOutput, key: str) -> int:
    value = player.ratings.get(key)
    if value is None:
        return 0
    return int(value)


def _trait_name(player: RatingOutput, index: int) -> str:
    if index < len(player.assigned_traits):
        return _clean_text(player.assigned_traits[index].name)
    return ""


def _join_values(values: list[str]) -> str:
    return ", ".join(item.strip() for item in values if isinstance(item, str) and item.strip())


def _is_pitcher(player: RatingOutput) -> bool:
    role = _clean_text(player.role).lower()
    if role in PITCHER_ROLES:
        return True
    if player.recommended_pitches:
        return True
    return any(key in player.ratings for key in ("velocity", "junk", "accuracy"))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def build_hitter_row(player: RatingOutput) -> dict[str, object]:
    secondary_positions = player.secondary_positions
    if not secondary_positions and player.secondary_position:
        secondary_positions = [player.secondary_position]
    return {
        "Name": _clean_text(player.name),
        "Throw Hand": _extract_throw_hand(player),
        "Bat Hand": _extract_bat_hand(player),
        "Primary Position": _clean_text(player.primary_position),
        "Secondary Positions": _join_values(secondary_positions),
        "Letter Grade": _clean_text(player.overall_grade),
        "Contact": _rating_value(player, "contact"),
        "Power": _rating_value(player, "power"),
        "Speed": _rating_value(player, "speed"),
        "Fielding": _rating_value(player, "fielding"),
        "Arm": _rating_value(player, "arm"),
        "Trait 1": _trait_name(player, 0),
        "Trait 2": _trait_name(player, 1),
    }


def build_pitcher_row(player: RatingOutput) -> dict[str, object]:
    return {
        "Name": _clean_text(player.name),
        "Throw Hand": _extract_throw_hand(player),
        "Bat Hand": _extract_bat_hand(player),
        "Arsenal": _join_values(player.recommended_pitches),
        "Letter Grade": _clean_text(player.overall_grade),
        "Velocity": _rating_value(player, "velocity"),
        "Junk": _rating_value(player, "junk"),
        "Accuracy": _rating_value(player, "accuracy"),
        "Trait 1": _trait_name(player, 0),
        "Trait 2": _trait_name(player, 1),
        "Contact": _rating_value(player, "contact"),
        "Power": _rating_value(player, "power"),
        "Speed": _rating_value(player, "speed"),
        "Fielding": _rating_value(player, "fielding"),
        "Arm": _rating_value(player, "arm"),
    }


def generate_output(ratings: list[RatingOutput], output_path: Path) -> None:
    output_path.mkdir(parents=True, exist_ok=True)

    players_by_team: dict[str, list[RatingOutput]] = defaultdict(list)
    for player in ratings:
        team = _clean_text(player.team, default="UNASSIGNED") or "UNASSIGNED"
        players_by_team[team].append(player)

    for team, players in sorted(players_by_team.items()):
        sorted_players = sorted(players, key=lambda player: (player.overall_numeric or 0, player.name), reverse=True)
        pitcher_rows = [build_pitcher_row(player) for player in sorted_players if _is_pitcher(player)]
        hitter_rows = [build_hitter_row(player) for player in sorted_players if not _is_pitcher(player)]

        _write_csv(output_path / f"{team}_hitters.csv", HITTER_COLUMNS, hitter_rows)
        _write_csv(output_path / f"{team}_pitchers.csv", PITCHER_COLUMNS, pitcher_rows)

__all__ = ["generate_output", "build_hitter_row", "build_pitcher_row", "HITTER_COLUMNS", "PITCHER_COLUMNS"]
