from __future__ import annotations

from .core import _rate_players_core
from ..models import PlayerInput, RatingOutput


def process_players(
    players: list[PlayerInput | dict],
    trim_final_traits: bool = True,
    config_path: str | None = None,
) -> list[RatingOutput]:
    return _rate_players_core(players, trim_final_traits=trim_final_traits, config_path=config_path)
