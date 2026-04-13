#!/usr/bin/env python3
"""Regenerate TOR/DET combined report with updated roster."""
import json
import ssl
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
EXPORT_ROOT = Path("examples/exports")


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
    ssl_context = ssl._create_unverified_context()
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

# Refresh live export inputs first so current reports reflect the latest roster and fallback logic.
print("Refreshing Blue Jays live exports...")
refresh_team_live_exports(team_id=141, team_abbreviation="TOR", file_prefix="bluejays")
print("✓ Blue Jays live exports refreshed")

print("Refreshing Tigers live exports...")
refresh_team_live_exports(team_id=116, team_abbreviation="DET", file_prefix="tigers")
print("✓ Tigers live exports refreshed")

# Run ingest-rate for Blue Jays
print("Ingesting Blue Jays data...")
result = subprocess.run([
    sys.executable, "-m", "smb4_mlb_ratings.cli",
    "ingest-rate",
    "examples/exports/bluejays_live_manifest.json",
    "examples/exports/bluejays_live_ratings_new.json"
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"Blue Jays ingest failed: {result.stderr}")
    sys.exit(1)
print("✓ Blue Jays ingest complete")

# Run ingest-rate for Tigers
print("Ingesting Tigers data...")
result = subprocess.run([
    sys.executable, "-m", "smb4_mlb_ratings.cli",
    "ingest-rate",
    "examples/exports/tigers_live_manifest.json",
    "examples/exports/tigers_live_ratings_new.json"
], capture_output=True, text=True)

if result.returncode != 0:
    print(f"Tigers ingest failed: {result.stderr}")
    sys.exit(1)
print("✓ Tigers ingest complete")

# Load both rating files and combine
with open("examples/exports/bluejays_live_ratings_new.json") as f:
    tor_data = json.load(f)

with open("examples/exports/tigers_live_ratings_new.json") as f:
    det_data = json.load(f)

# Merge players - data is a list directly
tor_players = tor_data if isinstance(tor_data, list) else tor_data.get("players", [])
det_players = det_data if isinstance(det_data, list) else det_data.get("players", [])

combined = tor_players + det_players

# Write combined report
with open("examples/exports/tor_det_combined_report.json", "w") as f:
    json.dump(combined, f, indent=2)

print(f"✓ Combined report written: {len(combined)} total players")
print(f"  - Blue Jays: {len(tor_players)}")
print(f"  - Tigers: {len(det_players)}")
