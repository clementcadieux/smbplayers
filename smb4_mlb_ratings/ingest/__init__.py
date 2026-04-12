from __future__ import annotations

from pathlib import Path
from typing import Any

from .baseball_reference import ingest_from_manifest as ingest_from_baseball_reference_manifest
from .savant import IngestManifest, RosterFilter, SeasonInputs, ingest_from_manifest as ingest_from_savant_manifest, load_manifest


SAVANT_TOOL_METRICS = frozenset(
	{
		"barrel_rate",
		"avg_exit_velocity",
		"two_strike_contact_rate",
		"sprint_speed",
		"oaa",
		"arm_strength",
		"catcher_throw_value",
		"outfield_arm_runs",
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


def _normalized_name(value: str) -> str:
	return " ".join(value.lower().split())


def _clone_manifest_for_source(manifest: IngestManifest, source_name: str) -> IngestManifest:
	seasons: dict[str, SeasonInputs] = {}
	for season_key, season_inputs in manifest.seasons.items():
		files = season_inputs.source_files.get(source_name, {})
		if not files:
			continue
		seasons[season_key] = SeasonInputs(year=season_inputs.year, files=files)
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
	name = player.get("name")
	if not isinstance(name, str) or not name.strip():
		raise ValueError("Merged player record is missing a valid name")
	return ("name", _normalized_name(name))


def _union_season_values(
	preferred_values: dict[str, Any],
	fallback_values: dict[str, Any],
) -> dict[str, Any]:
	merged: dict[str, Any] = {}
	for season_key in set(preferred_values) | set(fallback_values):
		if season_key in preferred_values:
			merged[season_key] = preferred_values[season_key]
		elif season_key in fallback_values:
			merged[season_key] = fallback_values[season_key]
	return dict(sorted(merged.items()))


def _merge_metric_map(
	baseball_reference: dict[str, dict[str, Any]],
	savant: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
	merged: dict[str, dict[str, Any]] = {}
	for metric_name in sorted(set(baseball_reference) | set(savant)):
		preferred = savant if metric_name in SAVANT_TOOL_METRICS else baseball_reference
		fallback = baseball_reference if metric_name in SAVANT_TOOL_METRICS else savant
		merged_values = _union_season_values(preferred.get(metric_name, {}), fallback.get(metric_name, {}))
		if merged_values:
			merged[metric_name] = merged_values
	return merged


def _merge_sample_map(
	baseball_reference: dict[str, dict[str, Any]],
	savant: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
	merged: dict[str, dict[str, Any]] = {}
	for sample_name in sorted(set(baseball_reference) | set(savant)):
		preferred = savant if sample_name in SAVANT_SAMPLE_KEYS else baseball_reference
		fallback = baseball_reference if sample_name in SAVANT_SAMPLE_KEYS else savant
		merged_values = _union_season_values(preferred.get(sample_name, {}), fallback.get(sample_name, {}))
		if merged_values:
			merged[sample_name] = merged_values
	return merged


def _merge_ingest_metadata(
	baseball_reference: dict[str, Any],
	savant: dict[str, Any],
) -> dict[str, Any]:
	merged_estimated: dict[str, set[str]] = {}
	merged_missing: dict[str, set[str]] = {}
	for source_name, metadata in (("baseball_reference", baseball_reference), ("baseball_savant", savant)):
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
) -> dict[str, Any]:
	if baseball_reference is None and savant is None:
		raise ValueError("Cannot merge two missing player records")
	if baseball_reference is None:
		baseball_reference = {}
	if savant is None:
		savant = {}

	br_metadata = baseball_reference.get("metadata", {}) if isinstance(baseball_reference.get("metadata"), dict) else {}
	sv_metadata = savant.get("metadata", {}) if isinstance(savant.get("metadata"), dict) else {}
	br_role = baseball_reference.get("role")
	sv_role = savant.get("role")
	roles = {role for role in (br_role, sv_role) if isinstance(role, str) and role}
	if "two_way" in roles or roles == {"hitter", "pitcher"}:
		role = "two_way"
	elif "pitcher" in roles:
		role = "pitcher"
	else:
		role = "hitter"

	metrics = _merge_metric_map(
		baseball_reference.get("metrics", {}) if isinstance(baseball_reference.get("metrics"), dict) else {},
		savant.get("metrics", {}) if isinstance(savant.get("metrics"), dict) else {},
	)
	samples = _merge_sample_map(
		baseball_reference.get("samples", {}) if isinstance(baseball_reference.get("samples"), dict) else {},
		savant.get("samples", {}) if isinstance(savant.get("samples"), dict) else {},
	)
	merged_years = {}
	for metadata in (br_metadata, sv_metadata):
		years = metadata.get("source_years", {}) if isinstance(metadata, dict) else {}
		if isinstance(years, dict):
			for season_key, value in years.items():
				merged_years[season_key] = value

	merged_source_player_id = None
	for metadata in (sv_metadata, br_metadata):
		source_player_id = metadata.get("source_player_id") if isinstance(metadata, dict) else None
		if isinstance(source_player_id, str) and source_player_id:
			merged_source_player_id = source_player_id
			break

	merged_status = None
	merged_status_code = None
	merged_on_il = None
	for metadata in (sv_metadata, br_metadata):
		status = metadata.get("status") if isinstance(metadata, dict) else None
		status_code = metadata.get("status_code") if isinstance(metadata, dict) else None
		on_il = metadata.get("on_il") if isinstance(metadata, dict) else None
		if merged_status is None and isinstance(status, str) and status:
			merged_status = status
		if merged_status_code is None and isinstance(status_code, str) and status_code:
			merged_status_code = status_code
		if merged_on_il is None and isinstance(on_il, bool):
			merged_on_il = on_il

	metadata = {
		"source": "mixed",
		"source_components": [source for source, payload in (("baseball_reference", baseball_reference), ("baseball_savant", savant)) if payload],
		"source_player_ids": {
			source: payload_metadata.get("source_player_id")
			for source, payload_metadata in (("baseball_reference", br_metadata), ("baseball_savant", sv_metadata))
			if isinstance(payload_metadata.get("source_player_id"), str)
		},
		"source_years": dict(sorted(merged_years.items())),
		"ingest": _merge_ingest_metadata(br_metadata, sv_metadata),
		"source_details": {
			"baseball_reference": br_metadata,
			"baseball_savant": sv_metadata,
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
	active = bool(baseball_reference.get("active", True)) and bool(savant.get("active", True))
	pitch_mix = savant.get("pitch_mix", {}) if isinstance(savant.get("pitch_mix"), dict) else {}

	merged_player = {
		"name": baseball_reference.get("name") or savant.get("name"),
		"role": role,
		"active": active,
		"team": baseball_reference.get("team") or savant.get("team"),
		"age": baseball_reference.get("age") if baseball_reference.get("age") is not None else savant.get("age"),
		"primary_position": baseball_reference.get("primary_position") or savant.get("primary_position"),
		"secondary_position": baseball_reference.get("secondary_position") or savant.get("secondary_position"),
		"bats": baseball_reference.get("bats") or savant.get("bats"),
		"throws": baseball_reference.get("throws") or savant.get("throws"),
		"metrics": metrics,
		"samples": samples,
		"metadata": metadata,
	}
	if pitch_mix:
		merged_player["pitch_mix"] = {str(key): float(value) for key, value in sorted(pitch_mix.items())}
	return merged_player


def _ingest_from_mixed_manifest(manifest: IngestManifest) -> list[dict[str, Any]]:
	baseball_reference_manifest = _clone_manifest_for_source(manifest, "baseball_reference")
	savant_manifest = _clone_manifest_for_source(manifest, "baseball_savant")
	baseball_reference_players = ingest_from_baseball_reference_manifest(baseball_reference_manifest)
	savant_players = ingest_from_savant_manifest(savant_manifest)

	baseball_reference_by_key = {_player_merge_key(player): player for player in baseball_reference_players}
	savant_by_key = {_player_merge_key(player): player for player in savant_players}
	merged_players = [
		_merge_player_records(baseball_reference_by_key.get(key), savant_by_key.get(key))
		for key in sorted(set(baseball_reference_by_key) | set(savant_by_key))
	]
	merged_players.sort(key=lambda item: (item["role"], item["name"]))
	return merged_players


def ingest_from_manifest(manifest: IngestManifest | Path) -> list[dict]:
	manifest_obj = load_manifest(manifest) if isinstance(manifest, Path) else manifest
	if manifest_obj.source == "baseball_savant":
		return ingest_from_savant_manifest(manifest_obj)
	if manifest_obj.source == "baseball_reference":
		return ingest_from_baseball_reference_manifest(manifest_obj)
	if manifest_obj.source == "mixed":
		return _ingest_from_mixed_manifest(manifest_obj)
	raise ValueError(f"Unsupported ingest source '{manifest_obj.source}'")


__all__ = ["IngestManifest", "RosterFilter", "load_manifest", "ingest_from_manifest"]