from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import rate_players
from .ingest import ingest_from_manifest, load_manifest
from .output import write_structured_output


def load_players(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("players"), list):
        return data["players"]
    raise ValueError("Input JSON must be a player array or an object with a 'players' array")


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_rate(input_path: Path, output_path: Path) -> int:
    players = load_players(input_path)
    outputs = rate_players(players)
    write_json(output_path, [output.to_dict() for output in outputs])
    return 0


def run_ingest(manifest_path: Path, output_path: Path) -> int:
    manifest = load_manifest(manifest_path)
    players = ingest_from_manifest(manifest)
    write_json(output_path, {"players": players})
    return 0


def run_ingest_rate(
    manifest_path: Path,
    output_path: Path | None,
    normalized_output_path: Path | None,
    structured_output_path: Path | None,
) -> int:
    manifest = load_manifest(manifest_path)
    players = ingest_from_manifest(manifest)
    if normalized_output_path is not None:
        write_json(normalized_output_path, {"players": players})
    outputs = rate_players(players)
    if output_path is not None:
        write_json(output_path, [output.to_dict() for output in outputs])
    if structured_output_path is not None:
        write_structured_output(outputs, structured_output_path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert MLB data into SMB4-ready inputs and ratings")
    subparsers = parser.add_subparsers(dest="command")

    rate_parser = subparsers.add_parser("rate", help="Rate an existing normalized player JSON file")
    rate_parser.add_argument("input", type=Path, help="Normalized player JSON file")
    rate_parser.add_argument("output", type=Path, help="Output ratings JSON file")

    ingest_parser = subparsers.add_parser("ingest", help="Normalize supported source files into engine input JSON")
    ingest_parser.add_argument("manifest", type=Path, help="Ingestion manifest JSON file")
    ingest_parser.add_argument("output", type=Path, help="Output normalized player JSON file")

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) == 2 and not args[0].startswith("-") and not args[1].startswith("-"):
        return run_rate(Path(args[0]), Path(args[1]))

    parser = build_parser()
    namespace = parser.parse_args(args)
    if namespace.command == "rate":
        return run_rate(namespace.input, namespace.output)
    if namespace.command == "ingest":
        return run_ingest(namespace.manifest, namespace.output)
    if namespace.command == "ingest-rate":
        if namespace.output is None and namespace.structured_output is None:
            parser.error("ingest-rate requires either an output file or --structured-output")
        return run_ingest_rate(
            namespace.manifest,
            namespace.output,
            namespace.normalized_output,
            namespace.structured_output,
        )

    parser.print_help(sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())