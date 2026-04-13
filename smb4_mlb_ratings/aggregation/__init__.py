from __future__ import annotations

from pathlib import Path
from typing import Any

from ..ingest.baseball_reference import ingest_from_manifest as aggregate_from_baseball_reference_manifest
from ..ingest.fangraphs import ingest_from_manifest as aggregate_from_fangraphs_manifest
from ..ingest.savant import IngestManifest, ingest_from_manifest as aggregate_from_savant_manifest, load_manifest


SAVANT_TOOL_METRICS = frozenset(
    {
        "barrel_rate",
        "avg_exit_velocity",
        "sprint_speed",
        "oaa",
        "arm_strength",
        "catcher_throw_value",
        "outfield_arm_runs",
        "pop_time",
        "framing_runs",
        "avg_fastball_velocity",
        "peak_fastball_velocity",
        "fastball_usage",
        "swinging_strike_rate",
        "chase_rate",
        "movement_quality",
        "stuff_metric",
        "arsenal_diversity",
        "zone_pct",
        "first_pitch_strike_pct",
    }
)

SAVANT_SAMPLE_KEYS = frozenset({"tracked_fastballs", "tracked_pitches"})
FANGRAPHS_PREFERRED_METRICS = frozenset({"drs", "uzr"})


def _merge_trait_metric_map(
    baseball_reference: dict[str, dict[str, Any]],
    savant: dict[str, dict[str, Any]],
    fangraphs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for metric_name in sorted(set(baseball_reference) | set(savant) | set(fangraphs)):
        merged_values = _union_season_values(
            savant.get(metric_name, {}),
            fangraphs.get(metric_name, {}),
            baseball_reference.get(metric_name, {}),
        )
        if merged_values:
            merged[metric_name] = merged_values
    return merged


def _merge_trait_lists(
    baseball_reference: dict[str, list[Any]],
    savant: dict[str, list[Any]],
    fangraphs: dict[str, list[Any]],
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for list_name in sorted(set(baseball_reference) | set(savant) | set(fangraphs)):
        values: set[str] = set()
        for source_values in (baseball_reference.get(list_name, []), savant.get(list_name, []), fangraphs.get(list_name, [])):
            if isinstance(source_values, list):
                values.update(str(item) for item in source_values if item is not None and str(item))
        if values:
            merged[list_name] = sorted(values)
    return merged


def _normalized_name(value: str) -> str:
    return " ".join(value.lower().split())


def _normalized_field(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.lower().split())


def _clone_manifest_for_source(manifest: IngestManifest, source_name: str) -> IngestManifest:
    seasons = {}
    for season_key, season_inputs in manifest.seasons.items():
        files = season_inputs.source_files.get(source_name, {})
        if not files:
            continue
        seasons[season_key] = season_inputs.__class__(year=season_inputs.year, files=files)
    return IngestManifest(
        source=source_name,
        seasons=seasons,
        manifest_path=manifest.manifest_path,
        roster_filter=manifest.roster_filter,
    )


def _player_merge_key(player: dict[str, Any]) -> tuple[str, str]:
    metadata = player.get("metadata", {})
    if isinstance(metadata, dict):
        source_id = metadata.get("source_player_id")
        if isinstance(source_id, str) and source_id:
            return ("id", source_id)
    if isinstance(player.get("player_id"), str) and player.get("player_id"):
        return ("id", str(player.get("player_id")))
    name = player.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Merged player record is missing a valid name")
    team = _normalized_field(player.get("team"))
    primary_position = _normalized_field(player.get("primary_position"))
    role = _normalized_field(player.get("role"))
    roster_season = ""
    if isinstance(metadata, dict):
        source_years = metadata.get("source_years")
        if isinstance(source_years, dict):
            current = source_years.get("current")
            if current is not None:
                roster_season = str(current)
    composite = f"{_normalized_name(name)}|{team}|{primary_position}|{role}|{roster_season}"
    return ("composite", composite)


def _player_merge_warning_fields(player: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (player.get("age"), player.get("bats"), player.get("throws"))


def _build_source_index(
    players: list[dict[str, Any]],
    *,
    source_name: str,
    warnings_by_key: dict[tuple[str, str], set[str]],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for player in players:
        key = _player_merge_key(player)
        existing = indexed.get(key)
        if existing is None:
            indexed[key] = player
            continue
        if _player_merge_warning_fields(existing) != _player_merge_warning_fields(player):
            warnings_by_key.setdefault(key, set()).add(
                f"Ambiguous {source_name} merge key '{key[0]}:{key[1]}' with conflicting age/bats/throws values."
            )
    return indexed


def _union_season_values(*season_maps: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for season_map in season_maps:
        if not isinstance(season_map, dict):
            continue
        for season_key, value in season_map.items():
            if season_key not in merged:
                merged[season_key] = value
    return dict(sorted(merged.items()))


def _merge_metric_map(
    baseball_reference: dict[str, dict[str, Any]],
    savant: dict[str, dict[str, Any]],
    fangraphs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for metric_name in sorted(set(baseball_reference) | set(savant) | set(fangraphs)):
        if metric_name in SAVANT_TOOL_METRICS:
            merged_values = _union_season_values(
                savant.get(metric_name, {}),
                fangraphs.get(metric_name, {}),
                baseball_reference.get(metric_name, {}),
            )
        elif metric_name in FANGRAPHS_PREFERRED_METRICS:
            merged_values = _union_season_values(
                fangraphs.get(metric_name, {}),
                baseball_reference.get(metric_name, {}),
                savant.get(metric_name, {}),
            )
        else:
            merged_values = _union_season_values(
                baseball_reference.get(metric_name, {}),
                fangraphs.get(metric_name, {}),
                savant.get(metric_name, {}),
            )
        if merged_values:
            merged[metric_name] = merged_values
    return merged


def _merge_sample_map(
    baseball_reference: dict[str, dict[str, Any]],
    savant: dict[str, dict[str, Any]],
    fangraphs: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for sample_name in sorted(set(baseball_reference) | set(savant) | set(fangraphs)):
        if sample_name in SAVANT_SAMPLE_KEYS:
            merged_values = _union_season_values(
                savant.get(sample_name, {}),
                baseball_reference.get(sample_name, {}),
                fangraphs.get(sample_name, {}),
            )
        else:
            merged_values = _union_season_values(
                baseball_reference.get(sample_name, {}),
                fangraphs.get(sample_name, {}),
                savant.get(sample_name, {}),
            )
        if merged_values:
            merged[sample_name] = merged_values
    return merged


def _merge_ingest_metadata(
    baseball_reference: dict[str, Any],
    savant: dict[str, Any],
    fangraphs: dict[str, Any],
) -> dict[str, Any]:
    merged_estimated: dict[str, set[str]] = {}
    merged_missing: dict[str, set[str]] = {}
    for source_name, metadata in (("baseball_reference", baseball_reference), ("baseball_savant", savant), ("fangraphs", fangraphs)):
        ingest = metadata.get("ingest", {}) if isinstance(metadata, dict) else {}
        estimated = ingest.get("estimated_metrics", {}) if isinstance(ingest, dict) else {}
        if isinstance(estimated, dict):
            for season_key, metrics in estimated.items():
                if not isinstance(metrics, list):
                    continue
                merged_estimated.setdefault(season_key, set()).update(f"{source_name}:{metric}" for metric in metrics)
        missing = ingest.get("missing_files", {}) if isinstance(ingest, dict) else {}
        if isinstance(missing, dict):
            for season_key, file_types in missing.items():
                if not isinstance(file_types, list):
                    continue
                merged_missing.setdefault(season_key, set()).update(f"{source_name}:{file_type}" for file_type in file_types)
    return {
        "estimated_metrics": {season: sorted(values) for season, values in sorted(merged_estimated.items()) if values},
        "missing_files": {season: sorted(values) for season, values in sorted(merged_missing.items()) if values},
        "merge_strategy": "baseball_reference outcomes, baseball_savant tools",
    }


def _merge_player_records(
    baseball_reference: dict[str, Any] | None,
    savant: dict[str, Any] | None,
    fangraphs: dict[str, Any] | None,
    merge_warnings: list[str] | None = None,
) -> dict[str, Any]:
    if baseball_reference is None and savant is None and fangraphs is None:
        raise ValueError("Cannot merge missing player records")
    if baseball_reference is None:
        baseball_reference = {}
    if savant is None:
        savant = {}
    if fangraphs is None:
        fangraphs = {}

    br_metadata = baseball_reference.get("metadata", {}) if isinstance(baseball_reference.get("metadata"), dict) else {}
    sv_metadata = savant.get("metadata", {}) if isinstance(savant.get("metadata"), dict) else {}
    fg_metadata = fangraphs.get("metadata", {}) if isinstance(fangraphs.get("metadata"), dict) else {}
    br_role = baseball_reference.get("role")
    sv_role = savant.get("role")
    fg_role = fangraphs.get("role")
    roles = {role for role in (br_role, sv_role, fg_role) if isinstance(role, str) and role}
    if "two_way" in roles or roles == {"hitter", "pitcher"}:
        role = "two_way"
    elif "pitcher" in roles:
        role = "pitcher"
    else:
        role = "hitter"

    metrics = _merge_metric_map(
        baseball_reference.get("metrics", {}) if isinstance(baseball_reference.get("metrics"), dict) else {},
        savant.get("metrics", {}) if isinstance(savant.get("metrics"), dict) else {},
        fangraphs.get("metrics", {}) if isinstance(fangraphs.get("metrics"), dict) else {},
    )
    samples = _merge_sample_map(
        baseball_reference.get("samples", {}) if isinstance(baseball_reference.get("samples"), dict) else {},
        savant.get("samples", {}) if isinstance(savant.get("samples"), dict) else {},
        fangraphs.get("samples", {}) if isinstance(fangraphs.get("samples"), dict) else {},
    )
    trait_metrics = _merge_trait_metric_map(
        baseball_reference.get("trait_metrics", {}) if isinstance(baseball_reference.get("trait_metrics"), dict) else {},
        savant.get("trait_metrics", {}) if isinstance(savant.get("trait_metrics"), dict) else {},
        fangraphs.get("trait_metrics", {}) if isinstance(fangraphs.get("trait_metrics"), dict) else {},
    )
    trait_lists = _merge_trait_lists(
        baseball_reference.get("trait_lists", {}) if isinstance(baseball_reference.get("trait_lists"), dict) else {},
        savant.get("trait_lists", {}) if isinstance(savant.get("trait_lists"), dict) else {},
        fangraphs.get("trait_lists", {}) if isinstance(fangraphs.get("trait_lists"), dict) else {},
    )
    merged_years = {}
    for metadata in (br_metadata, sv_metadata, fg_metadata):
        years = metadata.get("source_years", {}) if isinstance(metadata, dict) else {}
        if isinstance(years, dict):
            for season_key, value in years.items():
                merged_years[season_key] = value

    merged_source_player_id = None
    for metadata in (sv_metadata, fg_metadata, br_metadata):
        source_player_id = metadata.get("source_player_id") if isinstance(metadata, dict) else None
        if isinstance(source_player_id, str) and source_player_id:
            merged_source_player_id = source_player_id
            break

    merged_status = None
    merged_status_code = None
    merged_on_il = None
    merged_mlb_trait_metric_percentiles = None
    merged_mlb_trait_metric_percentile_peer_counts = None
    for metadata in (sv_metadata, fg_metadata, br_metadata):
        status = metadata.get("status") if isinstance(metadata, dict) else None
        status_code = metadata.get("status_code") if isinstance(metadata, dict) else None
        on_il = metadata.get("on_il") if isinstance(metadata, dict) else None
        mlb_trait_metric_percentiles = metadata.get("mlb_trait_metric_percentiles") if isinstance(metadata, dict) else None
        mlb_trait_metric_percentile_peer_counts = metadata.get("mlb_trait_metric_percentile_peer_counts") if isinstance(metadata, dict) else None
        if merged_status is None and isinstance(status, str) and status:
            merged_status = status
        if merged_status_code is None and isinstance(status_code, str) and status_code:
            merged_status_code = status_code
        if merged_on_il is None and isinstance(on_il, bool):
            merged_on_il = on_il
        if merged_mlb_trait_metric_percentiles is None and isinstance(mlb_trait_metric_percentiles, dict):
            merged_mlb_trait_metric_percentiles = {
                str(metric_name): float(value)
                for metric_name, value in mlb_trait_metric_percentiles.items()
                if isinstance(value, (int, float))
            }
        if merged_mlb_trait_metric_percentile_peer_counts is None and isinstance(mlb_trait_metric_percentile_peer_counts, dict):
            merged_mlb_trait_metric_percentile_peer_counts = {
                str(metric_name): int(value)
                for metric_name, value in mlb_trait_metric_percentile_peer_counts.items()
                if isinstance(value, (int, float))
            }

    metadata = {
        "source": "mixed",
        "source_components": [
            source
            for source, payload in (("baseball_reference", baseball_reference), ("baseball_savant", savant), ("fangraphs", fangraphs))
            if payload
        ],
        "source_player_ids": {
            source: payload_metadata.get("source_player_id")
            for source, payload_metadata in (("baseball_reference", br_metadata), ("baseball_savant", sv_metadata), ("fangraphs", fg_metadata))
            if isinstance(payload_metadata.get("source_player_id"), str)
        },
        "source_years": dict(sorted(merged_years.items())),
        "ingest": _merge_ingest_metadata(br_metadata, sv_metadata, fg_metadata),
        "source_details": {
            "baseball_reference": br_metadata,
            "baseball_savant": sv_metadata,
            "fangraphs": fg_metadata,
        },
    }
    if isinstance(merged_source_player_id, str):
        metadata["source_player_id"] = merged_source_player_id
    if isinstance(merged_status, str):
        metadata["status"] = merged_status
    if isinstance(merged_status_code, str):
        metadata["status_code"] = merged_status_code
    if isinstance(merged_on_il, bool):
        metadata["on_il"] = merged_on_il
    if isinstance(merged_mlb_trait_metric_percentiles, dict) and merged_mlb_trait_metric_percentiles:
        metadata["mlb_trait_metric_percentiles"] = dict(sorted(merged_mlb_trait_metric_percentiles.items()))
    if isinstance(merged_mlb_trait_metric_percentile_peer_counts, dict) and merged_mlb_trait_metric_percentile_peer_counts:
        metadata["mlb_trait_metric_percentile_peer_counts"] = dict(sorted(merged_mlb_trait_metric_percentile_peer_counts.items()))
    if merge_warnings:
        metadata["merge_warnings"] = sorted({str(item) for item in merge_warnings if str(item)})
    source_payloads = [payload for payload in (baseball_reference, savant, fangraphs) if payload]
    active = any(bool(payload.get("active", True)) for payload in source_payloads) if source_payloads else True
    days_on_roster = _union_season_values(
        savant.get("days_on_roster", {}) if isinstance(savant.get("days_on_roster"), dict) else {},
        baseball_reference.get("days_on_roster", {}) if isinstance(baseball_reference.get("days_on_roster"), dict) else {},
        fangraphs.get("days_on_roster", {}) if isinstance(fangraphs.get("days_on_roster"), dict) else {},
    )
    positional_games = _union_season_values(
        savant.get("positional_games", {}) if isinstance(savant.get("positional_games"), dict) else {},
        fangraphs.get("positional_games", {}) if isinstance(fangraphs.get("positional_games"), dict) else {},
        baseball_reference.get("positional_games", {}) if isinstance(baseball_reference.get("positional_games"), dict) else {},
    )
    pitch_mix = savant.get("pitch_mix", {}) if isinstance(savant.get("pitch_mix"), dict) else {}

    merged_player = {
        "name": baseball_reference.get("name") or fangraphs.get("name") or savant.get("name"),
        "role": role,
        "player_id": merged_source_player_id,
        "active": active,
        "team": baseball_reference.get("team") or fangraphs.get("team") or savant.get("team"),
        "age": baseball_reference.get("age") if baseball_reference.get("age") is not None else (fangraphs.get("age") if fangraphs.get("age") is not None else savant.get("age")),
        "primary_position": baseball_reference.get("primary_position") or fangraphs.get("primary_position") or savant.get("primary_position"),
        "secondary_position": baseball_reference.get("secondary_position") or fangraphs.get("secondary_position") or savant.get("secondary_position"),
        "bats": baseball_reference.get("bats") or fangraphs.get("bats") or savant.get("bats"),
        "throws": baseball_reference.get("throws") or fangraphs.get("throws") or savant.get("throws"),
        "metrics": metrics,
        "samples": samples,
        "metadata": metadata,
    }
    if trait_metrics:
        merged_player["trait_metrics"] = trait_metrics
    if trait_lists:
        merged_player["trait_lists"] = trait_lists
    if days_on_roster:
        merged_player["days_on_roster"] = {str(key): float(value) for key, value in sorted(days_on_roster.items())}
    if positional_games:
        merged_player["positional_games"] = {str(key): float(value) for key, value in sorted(positional_games.items())}
    if pitch_mix:
        merged_player["pitch_mix"] = {str(key): float(value) for key, value in sorted(pitch_mix.items())}
    return merged_player


def _aggregate_from_mixed_manifest(manifest: IngestManifest) -> list[dict[str, Any]]:
    baseball_reference_manifest = _clone_manifest_for_source(manifest, "baseball_reference")
    savant_manifest = _clone_manifest_for_source(manifest, "baseball_savant")
    fangraphs_manifest = _clone_manifest_for_source(manifest, "fangraphs")
    baseball_reference_players = aggregate_from_baseball_reference_manifest(baseball_reference_manifest)
    savant_players = aggregate_from_savant_manifest(savant_manifest)
    fangraphs_players = aggregate_from_fangraphs_manifest(fangraphs_manifest)

    warnings_by_key: dict[tuple[str, str], set[str]] = {}
    baseball_reference_by_key = _build_source_index(baseball_reference_players, source_name="baseball_reference", warnings_by_key=warnings_by_key)
    savant_by_key = _build_source_index(savant_players, source_name="baseball_savant", warnings_by_key=warnings_by_key)
    fangraphs_by_key = _build_source_index(fangraphs_players, source_name="fangraphs", warnings_by_key=warnings_by_key)
    for key in sorted(set(baseball_reference_by_key) | set(savant_by_key) | set(fangraphs_by_key)):
        records = [
            payload
            for payload in (
                baseball_reference_by_key.get(key),
                savant_by_key.get(key),
                fangraphs_by_key.get(key),
            )
            if payload is not None
        ]
        if len(records) <= 1:
            continue
        field_values = {_player_merge_warning_fields(record) for record in records}
        if len(field_values) > 1:
            warnings_by_key.setdefault(key, set()).add(
                f"Ambiguous cross-source merge key '{key[0]}:{key[1]}' with conflicting age/bats/throws values."
            )
    merged_players = [
        _merge_player_records(
            baseball_reference_by_key.get(key),
            savant_by_key.get(key),
            fangraphs_by_key.get(key),
            merge_warnings=sorted(warnings_by_key.get(key, set())),
        )
        for key in sorted(set(baseball_reference_by_key) | set(savant_by_key) | set(fangraphs_by_key))
    ]
    merged_players.sort(key=lambda item: (item["role"], item["name"]))
    return merged_players


def aggregate_from_manifest(manifest: IngestManifest | Path) -> list[dict[str, Any]]:
    manifest_obj = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    if manifest_obj.source == "baseball_savant":
        return aggregate_from_savant_manifest(manifest_obj)
    if manifest_obj.source == "baseball_reference":
        return aggregate_from_baseball_reference_manifest(manifest_obj)
    if manifest_obj.source == "fangraphs":
        return aggregate_from_fangraphs_manifest(manifest_obj)
    if manifest_obj.source == "mixed":
        return _aggregate_from_mixed_manifest(manifest_obj)
    raise ValueError(f"Unsupported ingest source '{manifest_obj.source}'")


def ingest_from_manifest(manifest: IngestManifest | Path) -> list[dict[str, Any]]:
    # Backward-compatible alias while callers migrate to aggregate_from_manifest.
    return aggregate_from_manifest(manifest)


__all__ = [
    "aggregate_from_manifest",
    "ingest_from_manifest",
    "IngestManifest",
    "load_manifest",
]
