#!/usr/bin/env python3
"""Regenerate TOR/DET combined report with updated roster.

Phases
------
1. ingest     – Fetch live roster/stats from Baseball Savant and Baseball Reference and
                write raw CSV exports to examples/exports/.
2. aggregate  – Read the CSVs via the manifest, merge all sources, and write a
                normalized player JSON for each team.
3. process    – Rate each team's normalized JSON and write a rated player JSON.
4. generate   – Merge both rated JSONs into a single combined report.

Usage
-----
Run all phases (default):
    python -m smb4_mlb_ratings.generation.regenerate_tor_det_report

Skip ingestion (reuse existing CSVs):
    python -m smb4_mlb_ratings.generation.regenerate_tor_det_report --skip-ingest

Skip ingestion and aggregation (reuse existing normalized JSON):
    python -m smb4_mlb_ratings.generation.regenerate_tor_det_report --skip-aggregate
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
    build_baseball_reference_pitcher_rows,
    build_roster_rows,
    build_savant_fielding_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
    fetch_team_players,
)


CURRENT_STAT_SEASON = 2026
PREVIOUS_STAT_SEASON = 2025
ROSTER_SEASON = 2026
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPORT_ROOT = PROJECT_ROOT / "examples" / "exports"


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(str(key))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def refresh_team_live_exports(*, team_id: int, team_abbreviation: str, file_prefix: str) -> None:
    ssl_context = None
    current_players = fetch_team_players(
        team_id,
        team_abbreviation=team_abbreviation,
        roster_season=ROSTER_SEASON,
        primary_stat_season=CURRENT_STAT_SEASON,
        fallback_stat_season=CURRENT_STAT_SEASON,
        ssl_context=ssl_context,
        min_players=22,
    )
    previous_players = fetch_team_players(
        team_id,
        team_abbreviation=team_abbreviation,
        roster_season=ROSTER_SEASON,
        primary_stat_season=PREVIOUS_STAT_SEASON,
        fallback_stat_season=PREVIOUS_STAT_SEASON,
        ssl_context=ssl_context,
        min_players=22,
    )

    write_csv(EXPORT_ROOT / f"{file_prefix}_live_roster_2026.csv", build_roster_rows(current_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_hitters_2026.csv", build_savant_hitter_rows(current_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_pitchers_2026.csv", build_savant_pitcher_rows(current_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_fielding_2026.csv", build_savant_fielding_rows(current_players, team_abbreviation=team_abbreviation, season=CURRENT_STAT_SEASON, ssl_context=ssl_context))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_bref_hitters_2026.csv", build_baseball_reference_hitter_rows(current_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_bref_pitchers_2026.csv", build_baseball_reference_pitcher_rows(current_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_hitters_2025.csv", build_savant_hitter_rows(previous_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_pitchers_2025.csv", build_savant_pitcher_rows(previous_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_savant_fielding_2025.csv", build_savant_fielding_rows(previous_players, team_abbreviation=team_abbreviation, season=PREVIOUS_STAT_SEASON, ssl_context=ssl_context))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_bref_hitters_2025.csv", build_baseball_reference_hitter_rows(previous_players, team_abbreviation=team_abbreviation))
    write_csv(EXPORT_ROOT / f"{file_prefix}_live_bref_pitchers_2025.csv", build_baseball_reference_pitcher_rows(previous_players, team_abbreviation=team_abbreviation))

def _cli(*args: str) -> None:
    """Run a smb4_mlb_ratings CLI command and exit on failure."""
    cmd = [sys.executable, "-m", "smb4_mlb_ratings.cli", *args]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Command failed: {' '.join(args)}\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    skip_group = parser.add_mutually_exclusive_group()
    skip_group.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip Phase 1: reuse the existing CSV exports and start from aggregation.",
    )
    skip_group.add_argument(
        "--skip-aggregate",
        action="store_true",
        help="Skip Phases 1–2: reuse existing normalized JSON and start from processing.",
    )
    args = parser.parse_args()

    # ── Phase 1: Ingest ──────────────────────────────────────────────────────
    if not args.skip_ingest and not args.skip_aggregate:
        print("Phase 1 – Ingest: refreshing live CSV exports...")
        refresh_team_live_exports(team_id=141, team_abbreviation="TOR", file_prefix="bluejays")
        print("  ✓ Blue Jays CSV exports written")
        refresh_team_live_exports(team_id=116, team_abbreviation="DET", file_prefix="tigers")
        print("  ✓ Tigers CSV exports written")
    else:
        print("Phase 1 – Ingest: skipped (reusing existing CSV exports)")

    # ── Phase 2: Aggregate ───────────────────────────────────────────────────
    if not args.skip_aggregate:
        print("Phase 2 – Aggregate: normalizing source CSVs into player JSON...")
        _cli(
            "aggregate",
            str(EXPORT_ROOT / "bluejays_live_manifest.json"),
            str(EXPORT_ROOT / "bluejays_live_normalized.json"),
        )
        print("  ✓ bluejays_live_normalized.json written")
        _cli(
            "aggregate",
            str(EXPORT_ROOT / "tigers_live_manifest.json"),
            str(EXPORT_ROOT / "tigers_live_normalized.json"),
        )
        print("  ✓ tigers_live_normalized.json written")
    else:
        print("Phase 2 – Aggregate: skipped (reusing existing normalized JSON)")

    # ── Phase 3: Process ─────────────────────────────────────────────────────
    print("Phase 3 – Process: rating normalized players...")
    _cli(
        "process",
        str(EXPORT_ROOT / "bluejays_live_normalized.json"),
        str(EXPORT_ROOT / "bluejays_live_ratings_new.json"),
        "--team", "TOR",
    )
    print("  ✓ bluejays_live_ratings_new.json written")
    _cli(
        "process",
        str(EXPORT_ROOT / "tigers_live_normalized.json"),
        str(EXPORT_ROOT / "tigers_live_ratings_new.json"),
        "--team", "DET",
    )
    print("  ✓ tigers_live_ratings_new.json written")

    # ── Phase 4: Generate ────────────────────────────────────────────────────
    print("Phase 4 – Generate: merging into combined report...")
    with (EXPORT_ROOT / "bluejays_live_ratings_new.json").open() as f:
        tor_data = json.load(f)
    with (EXPORT_ROOT / "tigers_live_ratings_new.json").open() as f:
        det_data = json.load(f)

    tor_players = tor_data if isinstance(tor_data, list) else tor_data.get("players", [])
    det_players = det_data if isinstance(det_data, list) else det_data.get("players", [])
    combined = tor_players + det_players

    with (EXPORT_ROOT / "tor_det_combined_report.json").open("w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2)

    print(f"  ✓ tor_det_combined_report.json written")
    print(f"\nDone. {len(combined)} total players (Blue Jays: {len(tor_players)}, Tigers: {len(det_players)})")


if __name__ == "__main__":
    main()
