from __future__ import annotations

from pathlib import Path
from typing import Any

# FanGraphs complements Savant by supplying public advanced defensive outputs
# such as DRS/UZR, while Savant remains the preferred source for many tool metrics.
from .savant import (
    IngestManifest,
    PlayerAccumulator,
    _apply_fielding_row,
    _apply_hitter_row,
    _apply_identity,
    _apply_pitcher_row,
    _apply_roster_rows,
    _apply_running_row,
    _ensure_player,
    _finalize_active_status,
    _mark_active_status,
    _read_csv,
    load_manifest,
)


def ingest_from_manifest(manifest: IngestManifest | Path) -> list[dict[str, Any]]:
    manifest_obj = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    if manifest_obj.source != "fangraphs":
        raise ValueError("FanGraphs adapter received a non-FanGraphs manifest")

    players: dict[tuple[str, str], PlayerAccumulator] = {}

    for season_key, season_inputs in manifest_obj.seasons.items():
        roster_path = season_inputs.files.get("roster")
        if roster_path is not None:
            _apply_roster_rows(
                players,
                _read_csv(roster_path),
                source=manifest_obj.source,
                season_key=season_key,
                season_year=season_inputs.year,
                roster_filter=manifest_obj.roster_filter,
            )

        hitters_path = season_inputs.files.get("hitters")
        if hitters_path is not None:
            for row in _read_csv(hitters_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_hitter_row(player, season_key, row)
                player.source_years[season_key] = season_inputs.year or player.source_years.get(season_key) or 0
        else:
            for player in players.values():
                player.note_missing_file(season_key, "hitters")

        pitchers_path = season_inputs.files.get("pitchers")
        if pitchers_path is not None:
            for row in _read_csv(pitchers_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_pitcher_row(player, season_key, row)
                player.source_years[season_key] = season_inputs.year or player.source_years.get(season_key) or 0
        else:
            for player in players.values():
                player.note_missing_file(season_key, "pitchers")

        fielding_path = season_inputs.files.get("fielding")
        if fielding_path is not None:
            for row in _read_csv(fielding_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_fielding_row(player, season_key, row)
                player.source_years[season_key] = season_inputs.year or player.source_years.get(season_key) or 0
        else:
            for player in players.values():
                player.note_missing_file(season_key, "fielding")

        running_path = season_inputs.files.get("running")
        if running_path is not None:
            for row in _read_csv(running_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_identity(player, row)
                _apply_running_row(player, season_key, row)
                player.source_years[season_key] = season_inputs.year or player.source_years.get(season_key) or 0
        else:
            for player in players.values():
                player.note_missing_file(season_key, "running")

    _finalize_active_status(players, roster_filter=manifest_obj.roster_filter)
    normalized = [player.to_player_dict() for player in players.values()]
    normalized.sort(key=lambda item: (item["role"], item["name"]))
    return normalized
