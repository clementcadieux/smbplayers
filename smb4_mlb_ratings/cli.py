from __future__ import annotations

import argparse
import csv
import json
import ssl
import sys
from pathlib import Path

from .aggregation import aggregate_from_manifest
from .codec import (
    build_canonical_snapshot_from_file,
    build_codec_import_from_file,
    build_dry_run_patch_preview_from_file,
    build_encoder_operation_plan_from_file,
)
from .generation import generate_output
from .ingest import load_manifest
from .league_bridge import build_roster_attribute_bridge
from .ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
    build_baseball_reference_pitcher_rows,
    build_mixed_source_manifest,
    build_roster_rows,
    build_savant_fielding_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
    fetch_team_players,
)
from .models import RatingOutput
from .output import write_structured_output
from .processing import process_players
from .roster_selector import build_rank_output, load_ratings


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BLUE_JAYS_TEAM_ID = 141
BLUE_JAYS_TEAM_ABBREVIATION = "TOR"
BLUE_JAYS_ROSTER_SEASON = 2026
BLUE_JAYS_CURRENT_STAT_SEASON = 2026
BLUE_JAYS_PREVIOUS_STAT_SEASON = 2025



def load_players(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("players"), list):
        return data["players"]
    raise ValueError("Input JSON must be a player array or an object with a 'players' array")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError("CSV output requires at least one row")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            key_text = str(key)
            if key_text not in fieldnames:
                fieldnames.append(key_text)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _normalized_team(team: str | None) -> str | None:
    if not isinstance(team, str):
        return None
    cleaned = team.strip()
    if not cleaned:
        return None
    return cleaned.upper()


def _filter_players_by_team(players: list[dict], team: str | None, *, active_only: bool = False) -> list[dict]:
    normalized_team = _normalized_team(team)
    if normalized_team is None:
        return players
    return [
        player
        for player in players
        if isinstance(player.get("team"), str) and player["team"].strip().upper() == normalized_team
        and (not active_only or bool(player.get("active", True)))
    ]


def run_rate(
    input_path: Path,
    output_path: Path,
    team: str | None = None,
    config_path: Path | None = None,
) -> int:
    players = load_players(input_path)
    players = _filter_players_by_team(players, team, active_only=True)
    outputs = process_players(players, config_path=str(config_path) if config_path is not None else None)
    write_json(output_path, [output.to_dict() for output in outputs])
    return 0


def run_ingest(manifest_path: Path, output_path: Path) -> int:
    manifest = load_manifest(manifest_path)
    players = aggregate_from_manifest(manifest)
    write_json(output_path, {"players": players})
    return 0


def run_aggregate(manifest_path: Path, output_path: Path) -> int:
    return run_ingest(manifest_path, output_path)


def run_process(input_path: Path, output_path: Path, team: str | None = None) -> int:
    return run_rate(input_path, output_path, team=team)


def run_generate(input_path: Path, output_path: Path) -> int:
    ratings = [RatingOutput.from_dict(item) for item in load_players(input_path)]
    generate_output(ratings, output_path)
    return 0


def run_rank(input_path: Path, output_path: Path) -> int:
    ratings = load_ratings(input_path)
    write_json(output_path, build_rank_output(ratings, compact=True))
    return 0


def run_build_roster_bridge(
    league_roster_path: Path,
    team_reports_path: Path,
    output_path: Path,
    league_folder: Path | None = None,
) -> int:
    payload = build_roster_attribute_bridge(
        league_roster_path,
        team_reports_path,
        league_folder_override=league_folder,
    )
    write_json(output_path, payload)
    return 0


def run_build_codec_interface(
    bridge_payload_path: Path,
    output_path: Path,
    league_folder: Path | None = None,
) -> int:
    build_codec_import_from_file(
        bridge_payload_path,
        output_path,
        league_folder_override=league_folder,
    )
    return 0


def run_build_canonical_snapshot(
    decoded_snapshot_path: Path,
    output_path: Path,
) -> int:
    build_canonical_snapshot_from_file(decoded_snapshot_path, output_path)
    return 0


def run_build_encoder_plan(
    codec_import_path: Path,
    output_path: Path,
) -> int:
    build_encoder_operation_plan_from_file(codec_import_path, output_path)
    return 0


def run_build_dry_run_report(
    encoder_plan_path: Path,
    output_path: Path,
    current_snapshot_path: Path | None = None,
    decoded_snapshot_path: Path | None = None,
) -> int:
    build_dry_run_patch_preview_from_file(
        encoder_plan_path,
        output_path,
        current_snapshot_path=current_snapshot_path,
        decoded_snapshot_path=decoded_snapshot_path,
    )
    return 0


def run_ingest_rate(
    manifest_path: Path,
    output_path: Path | None,
    normalized_output_path: Path | None,
    structured_output_path: Path | None,
    team: str | None = None,
    config_path: Path | None = None,
) -> int:
    manifest = load_manifest(manifest_path)
    players = aggregate_from_manifest(manifest)
    players = _filter_players_by_team(players, team, active_only=True)
    if normalized_output_path is not None:
        write_json(normalized_output_path, {"players": players})
    outputs = process_players(players, config_path=str(config_path) if config_path is not None else None)
    if output_path is not None:
        write_json(output_path, [output.to_dict() for output in outputs])
    if structured_output_path is not None:
        write_structured_output(outputs, structured_output_path)
    return 0


def run_refresh_bluejays_example(example_root: Path | None = None, *, insecure_ssl: bool = False) -> int:
    root = example_root if example_root is not None else PROJECT_ROOT / "examples"
    exports = root / "exports"
    structured_output_path = exports / "bluejays_structured_report"
    normalized_output_path = exports / "bluejays_normalized_for_result_example.json"
    roster_output_path = exports / "bluejays_roster_report.json"
    manifest_path = root / "bluejays_mixed_manifest_concrete.json"
    ratings_output_path = root / "bluejays_result_example.json"

    exports.mkdir(parents=True, exist_ok=True)
    ssl_context = None
    if insecure_ssl:
        print("Warning: using insecure SSL mode; certificate verification is disabled.", file=sys.stderr)
        ssl_context = ssl._create_unverified_context()
    current_players = fetch_team_players(
        BLUE_JAYS_TEAM_ID,
        team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION,
        roster_season=BLUE_JAYS_ROSTER_SEASON,
        primary_stat_season=BLUE_JAYS_CURRENT_STAT_SEASON,
        fallback_stat_season=BLUE_JAYS_CURRENT_STAT_SEASON,
        ssl_context=ssl_context,
        min_players=22,
    )
    previous_players = fetch_team_players(
        BLUE_JAYS_TEAM_ID,
        team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION,
        roster_season=BLUE_JAYS_ROSTER_SEASON,
        primary_stat_season=BLUE_JAYS_PREVIOUS_STAT_SEASON,
        fallback_stat_season=BLUE_JAYS_PREVIOUS_STAT_SEASON,
        ssl_context=ssl_context,
        min_players=22,
    )

    roster_file = exports / "bluejays_roster_2026.csv"
    current_savant_hitters_file = exports / "bluejays_live_savant_hitters_2026.csv"
    current_savant_pitchers_file = exports / "bluejays_live_savant_pitchers_2026.csv"
    current_savant_fielding_file = exports / "bluejays_live_savant_fielding_2026.csv"
    current_baseball_reference_hitters_file = exports / "bluejays_live_bref_hitters_2026.csv"
    current_baseball_reference_pitchers_file = exports / "bluejays_live_bref_pitchers_2026.csv"
    previous_savant_hitters_file = exports / "bluejays_live_savant_hitters_2025.csv"
    previous_savant_pitchers_file = exports / "bluejays_live_savant_pitchers_2025.csv"
    previous_savant_fielding_file = exports / "bluejays_live_savant_fielding_2025.csv"
    previous_baseball_reference_hitters_file = exports / "bluejays_live_bref_hitters_2025.csv"
    previous_baseball_reference_pitchers_file = exports / "bluejays_live_bref_pitchers_2025.csv"

    write_csv(roster_file, build_roster_rows(current_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION))
    write_csv(
        current_savant_hitters_file,
        build_savant_hitter_rows(current_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        current_savant_pitchers_file,
        build_savant_pitcher_rows(current_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        current_savant_fielding_file,
        build_savant_fielding_rows(
            current_players,
            team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION,
            season=BLUE_JAYS_CURRENT_STAT_SEASON,
            ssl_context=ssl_context,
        ),
    )
    write_csv(
        current_baseball_reference_hitters_file,
        build_baseball_reference_hitter_rows(current_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        current_baseball_reference_pitchers_file,
        build_baseball_reference_pitcher_rows(current_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )

    write_csv(
        previous_savant_hitters_file,
        build_savant_hitter_rows(previous_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        previous_savant_pitchers_file,
        build_savant_pitcher_rows(previous_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        previous_savant_fielding_file,
        build_savant_fielding_rows(
            previous_players,
            team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION,
            season=BLUE_JAYS_PREVIOUS_STAT_SEASON,
            ssl_context=ssl_context,
        ),
    )
    write_csv(
        previous_baseball_reference_hitters_file,
        build_baseball_reference_hitter_rows(previous_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )
    write_csv(
        previous_baseball_reference_pitchers_file,
        build_baseball_reference_pitcher_rows(previous_players, team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION),
    )

    manifest = build_mixed_source_manifest(
        team_abbreviation=BLUE_JAYS_TEAM_ABBREVIATION,
        roster_season=BLUE_JAYS_ROSTER_SEASON,
        current_year=BLUE_JAYS_CURRENT_STAT_SEASON,
        roster_file=str(roster_file.relative_to(root)).replace("\\", "/"),
        savant_hitters_file=str(current_savant_hitters_file.relative_to(root)).replace("\\", "/"),
        savant_pitchers_file=str(current_savant_pitchers_file.relative_to(root)).replace("\\", "/"),
        savant_fielding_file=str(current_savant_fielding_file.relative_to(root)).replace("\\", "/"),
        baseball_reference_hitters_file=str(current_baseball_reference_hitters_file.relative_to(root)).replace("\\", "/"),
        baseball_reference_pitchers_file=str(current_baseball_reference_pitchers_file.relative_to(root)).replace("\\", "/"),
        previous_year=BLUE_JAYS_PREVIOUS_STAT_SEASON,
        previous_savant_hitters_file=str(previous_savant_hitters_file.relative_to(root)).replace("\\", "/"),
        previous_savant_pitchers_file=str(previous_savant_pitchers_file.relative_to(root)).replace("\\", "/"),
        previous_savant_fielding_file=str(previous_savant_fielding_file.relative_to(root)).replace("\\", "/"),
        previous_baseball_reference_hitters_file=str(previous_baseball_reference_hitters_file.relative_to(root)).replace("\\", "/"),
        previous_baseball_reference_pitchers_file=str(previous_baseball_reference_pitchers_file.relative_to(root)).replace("\\", "/"),
    )
    write_json(manifest_path, manifest)

    ingest_rate_result = run_ingest_rate(
        manifest_path,
        ratings_output_path,
        normalized_output_path,
        structured_output_path,
        team=BLUE_JAYS_TEAM_ABBREVIATION,
    )
    if ingest_rate_result != 0:
        return ingest_rate_result
    return run_rank(ratings_output_path, roster_output_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert MLB data into SMB4-ready inputs and ratings")
    subparsers = parser.add_subparsers(dest="command")

    rate_parser = subparsers.add_parser("rate", help="Rate an existing normalized player JSON file")
    rate_parser.add_argument("input", type=Path, help="Normalized player JSON file")
    rate_parser.add_argument("output", type=Path, help="Output ratings JSON file")
    rate_parser.add_argument("--team", type=str, default=None, help="Optional team abbreviation to filter before rating")
    rate_parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Optional YAML config path to override runtime rating and trait tuning values",
    )

    ingest_parser = subparsers.add_parser("ingest", help="Normalize supported source files into engine input JSON")
    ingest_parser.add_argument("manifest", type=Path, help="Ingestion manifest JSON file")
    ingest_parser.add_argument("output", type=Path, help="Output normalized player JSON file")

    aggregate_parser = subparsers.add_parser("aggregate", help="Aggregate supported source files into normalized player JSON")
    aggregate_parser.add_argument("manifest", type=Path, help="Ingestion manifest JSON file")
    aggregate_parser.add_argument("output", type=Path, help="Output normalized player JSON file")

    process_parser = subparsers.add_parser("process", help="Process a normalized player JSON file into ratings")
    process_parser.add_argument("input", type=Path, help="Normalized player JSON file")
    process_parser.add_argument("output", type=Path, help="Output ratings JSON file")
    process_parser.add_argument("--team", type=str, default=None, help="Optional team abbreviation to filter before rating")

    generate_parser = subparsers.add_parser("generate", help="Generate per-team hitter and pitcher CSV exports from ratings JSON")
    generate_parser.add_argument("input", type=Path, help="Ratings JSON file")
    generate_parser.add_argument("output", type=Path, help="Output directory for team CSV reports")

    rank_parser = subparsers.add_parser("rank", help="Rank rated players into recommended 22-man rosters")
    rank_parser.add_argument("input", type=Path, help="Ratings JSON file")
    rank_parser.add_argument("output", type=Path, help="Output roster JSON file")

    bridge_parser = subparsers.add_parser(
        "build-roster-bridge",
        help="Merge base roster IDs with team_reports attributes and derive free agents",
    )
    bridge_parser.add_argument(
        "league_roster",
        type=Path,
        help="Base roster JSON file (usually export/league_roster.json)",
    )
    bridge_parser.add_argument(
        "team_reports",
        type=Path,
        help="Directory containing *_hitters.csv and *_pitchers.csv reports",
    )
    bridge_parser.add_argument("output", type=Path, help="Output bridge JSON file")
    bridge_parser.add_argument(
        "--league-folder",
        type=Path,
        default=None,
        help="Optional SMB4 league folder override path",
    )

    codec_parser = subparsers.add_parser(
        "build-codec-interface",
        help="Build canonical codec import payload from league bridge JSON",
    )
    codec_parser.add_argument(
        "bridge_payload",
        type=Path,
        help="Roster bridge JSON file (usually export/league_bridge.json)",
    )
    codec_parser.add_argument(
        "output",
        type=Path,
        help="Output codec import payload JSON",
    )
    codec_parser.add_argument(
        "--league-folder",
        type=Path,
        default=None,
        help="Optional SMB4 league folder override path",
    )

    snapshot_parser = subparsers.add_parser(
        "build-canonical-snapshot",
        help="Normalize decoded league snapshot payload into canonical comparator schema",
    )
    snapshot_parser.add_argument(
        "decoded_snapshot",
        type=Path,
        help="Decoded/current league snapshot JSON from decoder output",
    )
    snapshot_parser.add_argument(
        "output",
        type=Path,
        help="Output canonical snapshot JSON",
    )

    encoder_plan_parser = subparsers.add_parser(
        "build-encoder-plan",
        help="Build deterministic encoder operation plan from codec import JSON",
    )
    encoder_plan_parser.add_argument(
        "codec_import",
        type=Path,
        help="Codec import payload JSON (usually export/codec_import.json)",
    )
    encoder_plan_parser.add_argument(
        "output",
        type=Path,
        help="Output encoder operation plan JSON",
    )

    dry_run_parser = subparsers.add_parser(
        "build-dry-run-report",
        help="Build dry-run patch preview report from encoder plan JSON",
    )
    dry_run_parser.add_argument(
        "encoder_plan",
        type=Path,
        help="Encoder operation plan JSON (usually export/encoder_plan.json)",
    )
    dry_run_parser.add_argument(
        "output",
        type=Path,
        help="Output dry-run patch preview JSON",
    )
    dry_run_parser.add_argument(
        "--current-snapshot",
        type=Path,
        default=None,
        help="Optional decoded/current league snapshot JSON used for concrete before/after diffs",
    )
    dry_run_parser.add_argument(
        "--decoded-snapshot",
        type=Path,
        default=None,
        help="Optional raw decoded snapshot JSON; will be normalized to canonical schema before diffing",
    )

    ingest_rate_parser = subparsers.add_parser("ingest-rate", help="Normalize supported source files and rate them")
    ingest_rate_parser.add_argument("manifest", type=Path, help="Ingestion manifest JSON file")
    ingest_rate_parser.add_argument("output", type=Path, nargs="?", default=None, help="Optional output ratings JSON file")
    ingest_rate_parser.add_argument(
        "--normalized-output",
        type=Path,
        default=None,
        help="Optional path to also write normalized player JSON",
    )
    ingest_rate_parser.add_argument(
        "--structured-output",
        type=Path,
        default=None,
        help="Optional directory path for league/division/team JSON output",
    )
    ingest_rate_parser.add_argument("--team", type=str, default=None, help="Optional team abbreviation to filter before rating")
    ingest_rate_parser.add_argument(
        "--config-path",
        type=Path,
        default=None,
        help="Optional YAML config path to override runtime rating and trait tuning values",
    )

    refresh_bluejays_parser = subparsers.add_parser(
        "refresh-bluejays-example",
        help="Fetch the live Blue Jays roster and regenerate the local example artifacts",
    )
    refresh_bluejays_parser.add_argument(
        "--example-root",
        type=Path,
        default=None,
        help="Optional root directory for the Blue Jays example outputs (defaults to the workspace examples folder)",
    )
    refresh_bluejays_parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification for live fetches (not recommended)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) == 2 and not args[0].startswith("-") and not args[1].startswith("-"):
        return run_rate(Path(args[0]), Path(args[1]))

    parser = build_parser()
    namespace = parser.parse_args(args)
    if namespace.command == "rate":
        return run_rate(namespace.input, namespace.output, team=namespace.team, config_path=namespace.config_path)
    if namespace.command == "ingest":
        return run_ingest(namespace.manifest, namespace.output)
    if namespace.command == "aggregate":
        return run_aggregate(namespace.manifest, namespace.output)
    if namespace.command == "process":
        return run_process(namespace.input, namespace.output, team=namespace.team)
    if namespace.command == "generate":
        return run_generate(namespace.input, namespace.output)
    if namespace.command == "rank":
        return run_rank(namespace.input, namespace.output)
    if namespace.command == "build-roster-bridge":
        return run_build_roster_bridge(
            namespace.league_roster,
            namespace.team_reports,
            namespace.output,
            league_folder=namespace.league_folder,
        )
    if namespace.command == "build-codec-interface":
        return run_build_codec_interface(
            namespace.bridge_payload,
            namespace.output,
            league_folder=namespace.league_folder,
        )
    if namespace.command == "build-canonical-snapshot":
        return run_build_canonical_snapshot(
            namespace.decoded_snapshot,
            namespace.output,
        )
    if namespace.command == "build-encoder-plan":
        return run_build_encoder_plan(
            namespace.codec_import,
            namespace.output,
        )
    if namespace.command == "build-dry-run-report":
        return run_build_dry_run_report(
            namespace.encoder_plan,
            namespace.output,
            current_snapshot_path=namespace.current_snapshot,
            decoded_snapshot_path=namespace.decoded_snapshot,
        )
    if namespace.command == "ingest-rate":
        if namespace.output is None and namespace.structured_output is None:
            parser.error("ingest-rate requires either an output file or --structured-output")
        return run_ingest_rate(
            namespace.manifest,
            namespace.output,
            namespace.normalized_output,
            namespace.structured_output,
            namespace.team,
            namespace.config_path,
        )
    if namespace.command == "refresh-bluejays-example":
        return run_refresh_bluejays_example(namespace.example_root, insecure_ssl=namespace.insecure)

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())