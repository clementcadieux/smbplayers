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

PITCHER_ROLE_OVERRIDES: dict[str, str] = {}


@dataclass(slots=True)
class RosterSlot:
    position_group: str
    slot_type: str
    player: RatingOutput
    is_injured_list: bool = False

    def to_dict(self, *, compact_player: bool = False) -> dict[str, object]:
        return {
            "position_group": self.position_group,
            "slot_type": self.slot_type,
            "is_injured_list": self.is_injured_list,
            "player": _player_reference(self.player) if compact_player else self.player.to_dict(),
        }


def _player_key(player: RatingOutput) -> str:
    if isinstance(player.player_id, str) and player.player_id:
        return player.player_id
    team = (player.team or "UNK").upper()
    return f"{team}:{player.name}"


def _player_reference(player: RatingOutput) -> dict[str, object]:
    return {
        "player_key": _player_key(player),
        "player_id": player.player_id,
        "name": player.name,
        "team": player.team,
        "role": player.role,
        "primary_position": player.primary_position,
    }


def _selection_key(player: RatingOutput) -> str:
    return _player_key(player)


def _position_values(player: RatingOutput) -> list[str]:
    positions: list[str] = []
    for position in (player.primary_position, player.secondary_position):
        if isinstance(position, str) and position:
            positions.append(position.upper())
    if isinstance(player.secondary_positions, list):
        for position in player.secondary_positions:
            if isinstance(position, str) and position:
                positions.append(position.upper())
    # Preserve insertion order while removing duplicates.
    return list(dict.fromkeys(positions))


def _injury_status_from_metadata(player: RatingOutput) -> bool:
    if player.on_il is True:
        return True
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


def _projected_ip_value(player: RatingOutput) -> float:
    return float(player.projected_ip or 0.0)


def _pitcher_rank_key(player: RatingOutput) -> tuple[float, float, int, str]:
    return (
        -_overall_value(player),
        -_projected_ip_value(player),
        _age_value(player),
        player.name,
    )


def _age_value(player: RatingOutput) -> int:
    return int(player.age) if player.age is not None else 999


def _player_sort_key(player: RatingOutput, injured_list: set[str]) -> tuple[float, bool, int, int, str]:
    return (
        -_overall_value(player),
        -_projected_playing_time(player),
        _age_value(player),
        player.name,
    )


def _pitcher_bucket(player: RatingOutput) -> str | None:
    override = PITCHER_ROLE_OVERRIDES.get(player.name.lower())
    if override is not None:
        return override

    metadata = player.metadata if isinstance(player.metadata, dict) else {}
    for key in ("pitching_role", "projected_role", "roster_role", "depth_chart_role"):
        value = metadata.get(key)
        if not isinstance(value, str):
            continue
        normalized = value.lower()
        for hint, bucket in PITCHER_ROLE_HINTS.items():
            if hint in normalized:
                return bucket
    projected_ip = float(player.projected_ip or 0.0)
    if projected_ip >= 120:
        return "SP"
    # Treat injured-list starters with meaningful workloads as SP so IL does not
    # collapse them into bullpen buckets during roster selection.
    if bool(player.on_il) and projected_ip >= 100:
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
    if not groups and player.role == "two_way" and float(player.projected_pa or 0.0) > 0.0:
        # Two-way pitchers with no fielding position (e.g., DH profile) still need hitter eligibility.
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
    selected_keys: set[str],
    injured_list: set[str],
) -> list[RosterSlot]:
    slots: list[RosterSlot] = []
    for player in ranked_group:
        player_key = _selection_key(player)
        if player_key in selected_keys:
            continue
        selected_keys.add(player_key)
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


def _fill_group_slots_from_pool(
    slots: list[RosterSlot],
    *,
    target_count: int,
    position_group: str,
    slot_prefix: str,
    pool: list[RatingOutput],
    selected_keys: set[str],
    injured_list: set[str],
) -> None:
    for player in pool:
        if len(slots) >= target_count:
            return
        player_key = _selection_key(player)
        if player_key in selected_keys:
            continue
        selected_keys.add(player_key)
        slots.append(
            RosterSlot(
                position_group=position_group,
                slot_type=f"{slot_prefix}{len(slots) + 1}",
                player=player,
                is_injured_list=_is_injured(player, injured_list),
            )
        )


def _pick_starting_pitchers(
    pitchers: list[RatingOutput],
    *,
    count: int,
    selected_keys: set[str],
    injured_list: set[str],
) -> list[RosterSlot]:
    starter_candidates = sorted(
        [player for player in pitchers if _pitcher_bucket(player) == "SP"],
        key=_pitcher_rank_key,
    )
    fallback_candidates = sorted(
        [player for player in pitchers if _pitcher_bucket(player) != "SP"],
        key=_pitcher_rank_key,
    )

    ordered = starter_candidates + fallback_candidates
    slots: list[RosterSlot] = []
    for player in ordered:
        if len(slots) >= count:
            break
        player_key = _selection_key(player)
        if player_key in selected_keys:
            continue
        selected_keys.add(player_key)
        slots.append(
            RosterSlot(
                position_group="SP",
                slot_type=f"sp{len(slots) + 1}",
                player=player,
                is_injured_list=_is_injured(player, injured_list),
            )
        )
    return slots


def _pick_relievers(
    pitchers: list[RatingOutput],
    *,
    count: int,
    selected_keys: set[str],
    injured_list: set[str],
) -> list[RosterSlot]:
    remaining = [player for player in pitchers if _selection_key(player) not in selected_keys]
    rp_first = sorted(
        [player for player in remaining if _pitcher_bucket(player) == "RP"],
        key=_pitcher_rank_key,
    )
    fallback = sorted(
        [player for player in remaining if _pitcher_bucket(player) != "RP"],
        key=_pitcher_rank_key,
    )

    ordered = rp_first + fallback
    slots: list[RosterSlot] = []
    for player in ordered:
        if len(slots) >= count:
            break
        player_key = _selection_key(player)
        if player_key in selected_keys:
            continue
        selected_keys.add(player_key)
        slots.append(
            RosterSlot(
                position_group="RP",
                slot_type=f"rp{len(slots) + 1}",
                player=player,
                is_injured_list=_is_injured(player, injured_list),
            )
        )
    return slots


def select_roster(
    players: list[RatingOutput],
    injured_list: set[str] | None = None,
    *,
    target_team: str | None = None,
) -> list[RosterSlot]:
    injured = injured_list or set()
    if target_team is not None:
        normalized_team = target_team.upper()
        invalid_players = [player.name for player in players if not isinstance(player.team, str) or player.team.upper() != normalized_team]
        if invalid_players:
            invalid_text = ", ".join(sorted(invalid_players))
            raise ValueError(f"Roster selection for {normalized_team} received players without a matching team: {invalid_text}")
    ranked = rank_players_by_role(players, injured)
    selected_keys: set[str] = set()
    roster: list[RosterSlot] = []

    all_pitchers = sorted(
        [player for player in players if player.role in {"pitcher", "two_way"}],
        key=lambda player: _player_sort_key(player, injured),
    )

    sp_slots = _pick_starting_pitchers(
        all_pitchers,
        count=4,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    rp_slots = _pick_relievers(
        all_pitchers,
        count=5,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    c_slots = _select_group_slots(ranked["C"], 2, "C", "c", selected_keys, injured)
    if_slots = _select_group_slots(ranked["IF"], 5, "IF", "if", selected_keys, injured)
    of_slots = _select_group_slots(ranked["OF"], 4, "OF", "of", selected_keys, injured)

    # Backfill undersubscribed groups from the same role pool to preserve 9P/13H shape.
    all_hitters = sorted(
        [player for player in players if player.role in {"hitter", "two_way"}],
        key=lambda player: _player_sort_key(player, injured),
    )

    _fill_group_slots_from_pool(
        sp_slots,
        target_count=4,
        position_group="SP",
        slot_prefix="sp",
        pool=all_pitchers,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    _fill_group_slots_from_pool(
        rp_slots,
        target_count=5,
        position_group="RP",
        slot_prefix="rp",
        pool=all_pitchers,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    _fill_group_slots_from_pool(
        c_slots,
        target_count=2,
        position_group="C",
        slot_prefix="c",
        pool=all_hitters,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    _fill_group_slots_from_pool(
        if_slots,
        target_count=5,
        position_group="IF",
        slot_prefix="if",
        pool=all_hitters,
        selected_keys=selected_keys,
        injured_list=injured,
    )
    _fill_group_slots_from_pool(
        of_slots,
        target_count=4,
        position_group="OF",
        slot_prefix="of",
        pool=all_hitters,
        selected_keys=selected_keys,
        injured_list=injured,
    )

    roster.extend(sp_slots)
    roster.extend(rp_slots)
    roster.extend(c_slots)
    roster.extend(if_slots)
    roster.extend(of_slots)

    flex_candidates: list[tuple[str, str, RatingOutput]] = []
    flex_candidate_keys: set[str] = set()
    for group_name, slot_type in (("C", "flex_c"), ("IF", "flex_if"), ("OF", "flex_of")):
        for player in ranked[group_name]:
            player_key = _selection_key(player)
            if player_key in selected_keys or player_key in flex_candidate_keys:
                continue
            flex_candidate_keys.add(player_key)
            flex_candidates.append((group_name, slot_type, player))
            break

    if len(flex_candidates) < 2:
        for player in all_hitters:
            player_key = _selection_key(player)
            if player_key in selected_keys or player_key in flex_candidate_keys:
                continue
            flex_candidate_keys.add(player_key)
            flex_candidates.append(("IF", "flex_if", player))
            if len(flex_candidates) >= 2:
                break

    chosen_flex = sorted(
        flex_candidates,
        key=lambda item: (
            -_overall_value(item[2]),
            -_projected_playing_time(item[2]),
            _age_value(item[2]),
            item[2].name,
        ),
    )[:2]

    for index, (group_name, slot_type, player) in enumerate(chosen_flex, start=1):
        selected_keys.add(_selection_key(player))
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


def roster_payload_for_team(
    team: str | None,
    players: list[RatingOutput],
    injured_list: set[str] | None = None,
    *,
    include_full_players: bool = True,
    compact_roster_players: bool = False,
) -> dict[str, object]:
    roster = select_roster(players, injured_list=injured_list, target_team=team)
    payload: dict[str, object] = {
        "team": team,
        "recommended_roster": [slot.to_dict(compact_player=compact_roster_players) for slot in roster],
    }
    sorted_players = sorted(players, key=lambda item: item.name)
    if include_full_players:
        payload["players"] = [player.to_dict() for player in sorted_players]
    else:
        payload["player_refs"] = [_player_reference(player) for player in sorted_players]
    return payload


def build_rank_output(
    players: list[RatingOutput],
    injured_list: set[str] | None = None,
    *,
    compact: bool = False,
) -> dict[str, object]:
    grouped: dict[str | None, list[RatingOutput]] = {}
    for player in players:
        grouped.setdefault(player.team, []).append(player)
    return {
        "teams": [
            roster_payload_for_team(
                team,
                grouped[team],
                injured_list=injured_list,
                include_full_players=not compact,
                compact_roster_players=compact,
            )
            for team in sorted(grouped, key=lambda team_name: team_name or "")
        ]
    }