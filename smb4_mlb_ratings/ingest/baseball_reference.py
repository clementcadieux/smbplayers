from __future__ import annotations

from pathlib import Path
from typing import Any

# Baseball Reference result files can carry some of the situational trait columns directly,
# but deeper plate-discipline and batted-ball split gaps may still need Fangraphs-style exports.
# Keep those future source additions aligned to the shared trait metric keys used by issue 31.
# Defensive tool/result split reference for fielding CSVs:
# - https://www.baseballsavant.mlb.com/leaderboard/outs_above_average -> oaa / outs_above_average, innings
# - https://baseballsavant.mlb.com/leaderboard/arm-strength -> arm_strength
# - https://baseballsavant.mlb.com/leaderboard/poptime and https://baseballsavant.mlb.com/catcher_framing -> pop_time, catcher_throw_value, framing_runs
# - https://www.fangraphs.com/leaders/major-league?stats=fld -> drs, uzr exports used by _apply_fielding_row

from .savant import (
    HITTER_TRAIT_METRIC_COLUMNS,
    IngestManifest,
    PITCHER_TRAIT_METRIC_COLUMNS,
    PlayerAccumulator,
    _apply_fielding_row,
    _apply_identity,
    _mark_active_status,
    _apply_roster_rows,
    _as_float,
    _canonical_position,
    _clamp,
    _ensure_player,
    _pick_first,
    _pick_number,
    _row_days_on_roster,
    _row_trait_metrics,
    _read_csv,
    _safe_divide,
    load_manifest,
)


def _apply_hitter_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    player.roles.add("hitter")
    _apply_identity(player, row)
    player.set_days_on_roster(season_key, _row_days_on_roster(row))
    player.set_trait_metrics(season_key, _row_trait_metrics(row, HITTER_TRAIT_METRIC_COLUMNS))

    plate_appearances = _pick_number(row, "pa", "plate_appearances")
    at_bats = _pick_number(row, "ab", "at_bats")
    hits = _pick_number(row, "h", "hits")
    doubles = _pick_number(row, "2b", "doubles")
    triples = _pick_number(row, "3b", "triples")
    home_runs = _pick_number(row, "hr", "home_runs")
    walks = _pick_number(row, "bb", "walks")
    hit_by_pitch = _pick_number(row, "hbp", "hit_by_pitch")
    stolen_bases = _pick_number(row, "sb", "stolen_bases")
    caught_stealing = _pick_number(row, "cs", "caught_stealing")
    strikeouts = _pick_number(row, "so", "k", "strikeouts")

    singles = None
    if hits is not None:
        singles = hits - (doubles or 0) - (triples or 0) - (home_runs or 0)
        singles = max(singles, 0)

    iso = _pick_number(row, "iso", "isolated_power")
    iso_estimated = False
    if iso is None:
        slugging = _pick_number(row, "slg", "slugging", "slugging_pct")
        batting_average = _pick_number(row, "batting_average", "avg", "ba")
        if slugging is not None and batting_average is not None:
            iso = max(slugging - batting_average, 0.0)
            iso_estimated = True

    strikeout_rate = _pick_number(row, "k_pct", "k_percent", "strikeout_rate", "strikeout_pct", rate=True)
    strikeout_rate_estimated = False
    if strikeout_rate is None:
        strikeout_rate = _safe_divide(strikeouts, plate_appearances)
        strikeout_rate_estimated = strikeout_rate is not None

    contact_rate = _pick_number(row, "contact_rate", "contact_pct", "contact_percent", rate=True)
    contact_rate_estimated = False
    if contact_rate is None and strikeout_rate is not None:
        contact_rate = _clamp(1.0 - strikeout_rate, 0.0, 1.0)
        contact_rate_estimated = True

    adjusted_obp = _pick_number(row, "adjusted_obp", "obp", "on_base_pct", "on_base_percentage")
    adjusted_obp_estimated = adjusted_obp is not None and _pick_first(row, "adjusted_obp") is None

    baserunning_value = _pick_number(row, "baserunning_value", "bsr", "rbaser", "baserunning_runs")
    baserunning_value_estimated = False
    if baserunning_value is None and stolen_bases is not None:
        baserunning_value = stolen_bases - ((caught_stealing or 0) * 1.5)
        baserunning_value_estimated = True

    baserunning_opportunities = _pick_number(row, "baserunning_opportunities", "br_opportunities")
    if baserunning_opportunities is None and any(value is not None for value in (singles, walks, hit_by_pitch)):
        baserunning_opportunities = max((singles or 0) + (walks or 0) + (hit_by_pitch or 0), 1)

    steal_attempts = None
    if stolen_bases is not None or caught_stealing is not None:
        steal_attempts = (stolen_bases or 0) + (caught_stealing or 0)

    player.set_metric("iso", season_key, iso, estimated=iso_estimated)
    player.set_metric("hr_per_pa", season_key, _safe_divide(home_runs, plate_appearances), estimated=home_runs is not None and plate_appearances is not None)
    player.set_metric("slugging", season_key, _pick_number(row, "slg", "slugging", "slugging_pct"))
    player.set_metric("strikeout_rate", season_key, strikeout_rate, estimated=strikeout_rate_estimated)
    player.set_metric("contact_rate", season_key, contact_rate, estimated=contact_rate_estimated)
    player.set_metric("batting_average", season_key, _pick_number(row, "batting_average", "avg", "ba"))
    player.set_metric("adjusted_obp", season_key, adjusted_obp, estimated=adjusted_obp_estimated)
    player.set_metric("baserunning_value", season_key, baserunning_value, estimated=baserunning_value_estimated)
    player.set_metric("sb_attempt_rate", season_key, _safe_divide(steal_attempts, baserunning_opportunities or plate_appearances), estimated=steal_attempts is not None)
    player.set_metric("sb_success_rate", season_key, _safe_divide(stolen_bases, steal_attempts), estimated=steal_attempts is not None)
    player.set_metric("triple_double_rate", season_key, _safe_divide((doubles or 0) + (triples or 0), plate_appearances), estimated=doubles is not None or triples is not None)

    player.set_sample("weighted_pa", season_key, plate_appearances)
    player.set_sample("baserunning_opportunities", season_key, baserunning_opportunities)


def _parse_ip_to_outs(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if "." not in cleaned:
        numeric = _as_float(cleaned)
        return numeric * 3 if numeric is not None else None
    innings_part, fraction_part = cleaned.split(".", 1)
    innings = _as_float(innings_part)
    fraction = _as_float(fraction_part)
    if innings is None or fraction is None:
        return None
    return innings * 3 + fraction


def _apply_pitcher_row(player: PlayerAccumulator, season_key: str, row: dict[str, str]) -> None:
    player.roles.add("pitcher")
    _apply_identity(player, row, default_position="P")
    player.set_days_on_roster(season_key, _row_days_on_roster(row))
    player.set_trait_metrics(season_key, _row_trait_metrics(row, PITCHER_TRAIT_METRIC_COLUMNS))

    batters_faced = _pick_number(row, "bf", "tbf", "batters_faced")
    pitches = _pick_number(row, "pitches", "pit", "pitch_count")
    strikes = _pick_number(row, "strikes", "str")
    walks = _pick_number(row, "bb", "walks")
    strikeouts = _pick_number(row, "so", "k", "strikeouts")
    home_runs = _pick_number(row, "hr", "home_runs")
    hits = _pick_number(row, "h", "hits")
    hit_by_pitch = _pick_number(row, "hbp", "hit_by_pitch")

    tracked_pitches = pitches
    tracked_pitches_estimated = False
    if tracked_pitches is None and batters_faced is not None:
        tracked_pitches = batters_faced * 3.85
        tracked_pitches_estimated = True

    walk_rate = _pick_number(row, "walk_rate", "bb_pct", "bb_percent", rate=True)
    walk_rate_estimated = False
    if walk_rate is None:
        walk_rate = _safe_divide(walks, batters_faced)
        walk_rate_estimated = walk_rate is not None

    strike_pct = _pick_number(row, "strike_pct", "strk_pct", rate=True)
    strike_pct_estimated = False
    if strike_pct is None and strikes is not None and tracked_pitches is not None:
        strike_pct = _safe_divide(strikes, tracked_pitches)
        strike_pct_estimated = strike_pct is not None

    strikeout_rate = _pick_number(row, "k_pct", "k_percent", "strikeout_rate", rate=True)
    if strikeout_rate is None:
        strikeout_rate = _safe_divide(strikeouts, batters_faced)

    weak_contact_rate = _pick_number(row, "weak_contact_rate", "weak_pct", rate=True)
    weak_contact_estimated = False
    if weak_contact_rate is None and hits is not None and batters_faced is not None:
        weak_contact_rate = _clamp(1.0 - (hits / batters_faced), 0.0, 1.0)
        weak_contact_estimated = True

    stuff_metric = _pick_number(row, "stuff_metric", "stuff_plus")
    stuff_estimated = False
    if stuff_metric is None and strikeout_rate is not None:
        home_run_rate = _safe_divide(home_runs, batters_faced) or 0.0
        stuff_metric = max((strikeout_rate * 100.0) - (home_run_rate * 120.0), 0.0)
        stuff_estimated = True

    command_error_rate = _pick_number(row, "command_error_rate", "ball_pct", rate=True)
    command_error_estimated = False
    if command_error_rate is None:
        if strike_pct is not None:
            command_error_rate = _clamp(1.0 - strike_pct, 0.0, 1.0)
            command_error_estimated = True
        elif walk_rate is not None:
            command_error_rate = walk_rate
            command_error_estimated = True

    innings_outs = _parse_ip_to_outs(_pick_first(row, "ip", "innings_pitched"))
    defensive_innings = innings_outs / 3.0 if innings_outs is not None else None

    player.set_metric("stuff_metric", season_key, stuff_metric, estimated=stuff_estimated)
    player.set_metric("weak_contact_rate", season_key, weak_contact_rate, estimated=weak_contact_estimated)
    player.set_metric("walk_rate", season_key, walk_rate, estimated=walk_rate_estimated)
    player.set_metric("strike_pct", season_key, strike_pct, estimated=strike_pct_estimated)
    player.set_metric("command_error_rate", season_key, command_error_rate, estimated=command_error_estimated)
    player.set_sample("weighted_bf", season_key, batters_faced)
    player.set_sample("tracked_pitches", season_key, tracked_pitches)
    if tracked_pitches_estimated:
        player.estimated_metrics[season_key].append("tracked_pitches")
    if defensive_innings is not None:
        player.set_sample("defensive_innings", season_key, defensive_innings)


def _should_apply_pitcher_row(player: PlayerAccumulator, row: dict[str, str]) -> bool:
    row_position = _canonical_position(_pick_first(row, "primary_position", "position", "pos", "fielding_position", "mlb_pos"))
    if row_position is not None and row_position != "P":
        return False
    if player.primary_position is not None and player.primary_position != "P" and "pitcher" not in player.roles:
        return False
    return True


def ingest_from_manifest(manifest: IngestManifest | Path) -> list[dict[str, Any]]:
    manifest_obj = load_manifest(manifest) if isinstance(manifest, Path) else manifest
    if manifest_obj.source != "baseball_reference":
        raise ValueError("Baseball Reference adapter received a non-Baseball Reference manifest")

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
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_hitter_row(player, season_key, row)

        pitchers_path = season_inputs.files.get("pitchers")
        if pitchers_path is not None:
            for row in _read_csv(pitchers_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                if not _should_apply_pitcher_row(player, row):
                    continue
                _apply_pitcher_row(player, season_key, row)

        fielding_path = season_inputs.files.get("fielding")
        if fielding_path is not None:
            for row in _read_csv(fielding_path):
                player = _ensure_player(players, row, source=manifest_obj.source)
                if season_inputs.year is not None:
                    player.source_years[season_key] = season_inputs.year
                _mark_active_status(
                    player,
                    row,
                    season_key=season_key,
                    season_year=season_inputs.year,
                    roster_filter=manifest_obj.roster_filter,
                )
                _apply_fielding_row(player, season_key, row)
        else:
            for player in players.values():
                player.note_missing_file(season_key, "fielding")

        if season_inputs.files.get("running") is None:
            for player in players.values():
                player.note_missing_file(season_key, "running")

    outputs = [player.to_player_dict() for player in players.values() if player.roles]
    outputs.sort(key=lambda item: (item["role"], item["name"]))
    return outputs