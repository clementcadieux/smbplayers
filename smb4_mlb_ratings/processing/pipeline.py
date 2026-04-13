from __future__ import annotations

from ..engine import _rate_players_core
from ..models import PlayerInput, RatingOutput


def process_players(players: list[PlayerInput | dict], trim_final_traits: bool = True) -> list[RatingOutput]:
    return _rate_players_core(players, trim_final_traits=trim_final_traits)
