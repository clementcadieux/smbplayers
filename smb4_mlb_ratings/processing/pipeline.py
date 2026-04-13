from __future__ import annotations

from ..engine import rate_players as _rate_players
from ..models import PlayerInput, RatingOutput


def process_players(players: list[PlayerInput | dict], trim_final_traits: bool = True) -> list[RatingOutput]:
    return _rate_players(players, trim_final_traits=trim_final_traits)


def rate_players(players: list[PlayerInput | dict], trim_final_traits: bool = True) -> list[RatingOutput]:
    return process_players(players, trim_final_traits=trim_final_traits)
