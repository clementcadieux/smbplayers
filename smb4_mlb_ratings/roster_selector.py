from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .models import RatingOutput


INFIELD_POSITIONS = frozenset({"1B", "2B", "3B", "SS", "IF"})
OUTFIELD_POSITIONS = frozenset({"LF", "CF", "RF", "OF"})
PITCHER_ROLE_HINTS = {
    "sp": "SP",
    "starter": "SP",
    "starting": "SP",
    "rotation": "SP",
    "rp": "RP",
    "reliever": "RP",
    "relief": "RP",
    "bullpen": "RP",
    "closer": "RP",
    "setup": "RP",
}


@dataclass(slots=True)
class RosterSlot:
    position_group: str
    slot_type: str
    player: RatingOutput
    is_injured_list: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "position_group": self.position_group,
            "slot_type": self.slot_type,
            "is_injured_list": self.is_injured_list,
            "player": self.player.to_dict(),
        }


def _position_values(player: RatingOutput) -> list[str]:
    return [position.upper() for position in (player.primary_position, player.secondary_position) if isinstance(position, str) and position]


def _injury_status_from_metadata(player: RatingOutput) -> bool:
    metadata = player.metadata if isinstance(player.metadata, dict) else {}
    for key in ("injured_list", "injured", "on_il"):
        if metadata.get(key) is True:
            return True
    status = metadata.get("status")
    if isinstance(status, str):
        normalized = status.lower()
        if normalized == "il" or "injured" in normalized:
            return True
    return False


def _is_injured(player: RatingOutput, injured_list: set[str]) -> bool:
    return player.name in injured_list or _injury_status_from_metadata(player)


def _projected_playing_time(player: RatingOutput) -> float:
    if player.role in {"pitcher", "two_way"}:
        return float(player.projected_ip or 0.0)
    return float(player.projected_pa or 0.0)


def _overall_value(player: RatingOutput) -> int:
    return int(player.overall_numeric or 0)


def _age_value(player: RatingOutput) -> int:
    return int(player.age) if player.age is not None else 999


def _player_sort_key(player: RatingOutput, injured_list: set[str]) -> tuple[float, bool, int, int, str]:
    return (
        -_projected_playing_time(player),
        _is_injured(player, injured_list),
        _age_value(player),
        -_overall_value(player),
        player.name,
    )


def _pitcher_bucket(player: RatingOutput) -> str | None:
    metadata = player.metadata if isinstance(player.metadata, dict) else {}
    for key in ("pitching_role", "projected_role", "roster_role", "depth_chart_role"):
        value = metadata.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.lower()
        for hint, bucket in PITCHER_ROLE_HINTS.items():
            if hint in normalized:
                return bucket
    if player.projected_ip is not None and player.projected_ip >= 80:
        return "SP"
    if player.role == "pitcher":
        return "RP"
    return None


def _eligible_hitter_groups(player: RatingOutput) -> set[str]:
    positions = set(_position_values(player))
    groups: set[str] = set()
    if "C" in positions:
        groups.add("C")
    if positions & INFIELD_POSITIONS:
        groups.add("IF")
    if positions & OUTFIELD_POSITIONS:
        groups.add("OF")
    return groups


def rank_players_by_role(players: list[RatingOutput], injured_list: set[str] | None = None) -> dict[str, list[RatingOutput]]:
    injured = injured_list or set()
    ranked = {"SP": [], "RP": [], "C": [], "IF": [], "OF": []}

    for player in players:
        if player.role in {"pitcher", "two_way"}:
            bucket = _pitcher_bucket(player)
            if bucket is not None:
                ranked[bucket].append(player)
        if player.role in {"hitter", "two_way"}:
            for group in _eligible_hitter_groups(player):
                ranked[group].append(player)

    for group, group_players in ranked.items():
        ranked[group] = sorted(group_players, key=lambda player: _player_sort_key(player, injured))
    return ranked


def _select_group_slots(
    ranked_group: list[RatingOutput],
    count: int,
    position_group: str,
    slot_prefix: str,
    selected_names: set[str],
    injured_list: set[str],
) -> list[RosterSlot]:
    slots: list[RosterSlot] = []
    for player in ranked_group:
        if player.name in selected_names:
            continue
        selected_names.add(player.name)
        slots.append(
            RosterSlot(
                position_group=position_group,
                slot_type=f"{slot_prefix}{len(slots) + 1}",
                player=player,
                is_injured_list=_is_injured(player, injured_list),
            )
        )
        if len(slots) == count:
            break
    return slots


def select_roster(players: list[RatingOutput], injured_list: set[str] | None = None) -> list[RosterSlot]:
    injured = injured_list or set()
    ranked = rank_players_by_role(players, injured)
    selected_names: set[str] = set()
    roster: list[RosterSlot] = []

    roster.extend(_select_group_slots(ranked["SP"], 4, "SP", "sp", selected_names, injured))
    roster.extend(_select_group_slots(ranked["RP"], 5, "RP", "rp", selected_names, injured))
    roster.extend(_select_group_slots(ranked["C"], 2, "C", "c", selected_names, injured))
    roster.extend(_select_group_slots(ranked["IF"], 5, "IF", "if", selected_names, injured))
    roster.extend(_select_group_slots(ranked["OF"], 4, "OF", "of", selected_names, injured))

    flex_candidates: list[tuple[str, str, RatingOutput]] = []
    for group_name, slot_type in (("C", "flex_c"), ("IF", "flex_if"), ("OF", "flex_of")):
        for player in ranked[group_name]:
            if player.name in selected_names:
                continue
            flex_candidates.append((group_name, slot_type, player))
            break

    chosen_flex = sorted(
        flex_candidates,
        key=lambda item: (
            -_overall_value(item[2]),
            -_projected_playing_time(item[2]),
            _is_injured(item[2], injured),
            _age_value(item[2]),
            item[2].name,
        ),
    )[:2]

    for index, (group_name, slot_type, player) in enumerate(chosen_flex, start=1):
        selected_names.add(player.name)
        roster.append(
            RosterSlot(
                position_group=group_name,
                slot_type=f"{slot_type}{index}",
                player=player,
                is_injured_list=_is_injured(player, injured),
            )
        )

    return roster


def load_ratings(path: Path) -> list[RatingOutput]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [RatingOutput.from_dict(item) for item in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("players"), list):
            return [RatingOutput.from_dict(item) for item in payload["players"]]
        if isinstance(payload.get("ratings"), list):
            return [RatingOutput.from_dict(item) for item in payload["ratings"]]
    raise ValueError("Ratings JSON must be an array or an object with a 'players' or 'ratings' array")


def roster_payload_for_team(team: str | None, players: list[RatingOutput], injured_list: set[str] | None = None) -> dict[str, object]:
    roster = select_roster(players, injured_list=injured_list)
    return {
        "team": team,
        "players": [player.to_dict() for player in sorted(players, key=lambda item: item.name)],
        "recommended_roster": [slot.to_dict() for slot in roster],
    }


def build_rank_output(players: list[RatingOutput], injured_list: set[str] | None = None) -> dict[str, object]:
    grouped: dict[str | None, list[RatingOutput]] = {}
    for player in players:
        grouped.setdefault(player.team, []).append(player)
    return {
        "teams": [
            roster_payload_for_team(team, grouped[team], injured_list=injured_list)
            for team in sorted(grouped, key=lambda team_name: team_name or "")
        ]
    }