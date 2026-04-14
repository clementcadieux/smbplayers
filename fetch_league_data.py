#!/usr/bin/env python3
"""
League-wide data ingestion: fetch from external sources and create CSVs for all 30 teams.
"""

import ssl
import sys
from pathlib import Path

from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
    build_baseball_reference_pitcher_rows,
    build_mixed_source_manifest,
    build_roster_rows,
    build_savant_fielding_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
    fetch_team_players,
)
from smb4_mlb_ratings.cli import write_csv, write_json


PROJECT_ROOT = Path(__file__).resolve().parent
EXPORT_DIR = PROJECT_ROOT / "export"
RAW_EXPORT_DIR = EXPORT_DIR / "raw"

# MLB team IDs and abbreviations
TEAMS = {
    110: ("BAL", "orioles"),       # Baltimore Orioles
    111: ("BOS", "redsox"),        # Boston Red Sox
    147: ("NYY", "yankees"),       # New York Yankees
    139: ("TB", "rays"),           # Tampa Bay Rays
    141: ("TOR", "bluejays"),      # Toronto Blue Jays
    145: ("CWS", "whitesox"),      # Chicago White Sox
    114: ("CLE", "guardians"),     # Cleveland Guardians
    116: ("DET", "tigers"),        # Detroit Tigers
    118: ("KC", "royals"),         # Kansas City Royals
    142: ("MIN", "twins"),         # Minnesota Twins
    117: ("HOU", "astros"),        # Houston Astros
    108: ("LAA", "angels"),        # Los Angeles Angels
    133: ("OAK", "athletics"),     # Oakland Athletics
    136: ("SEA", "mariners"),      # Seattle Mariners
    140: ("TEX", "rangers"),       # Texas Rangers
    144: ("ATL", "braves"),        # Atlanta Braves
    146: ("MIA", "marlins"),       # Miami Marlins
    121: ("NYM", "mets"),          # New York Mets
    143: ("PHI", "phillies"),      # Philadelphia Phillies
    120: ("WSH", "nationals"),     # Washington Nationals
    112: ("CHC", "cubs"),          # Chicago Cubs
    113: ("CIN", "reds"),          # Cincinnati Reds
    158: ("MIL", "brewers"),       # Milwaukee Brewers
    134: ("PIT", "pirates"),       # Pittsburgh Pirates
    138: ("STL", "cardinals"),     # St. Louis Cardinals
    109: ("ARI", "diamondbacks"),  # Arizona Diamondbacks
    115: ("COL", "rockies"),       # Colorado Rockies
    119: ("LAD", "dodgers"),       # Los Angeles Dodgers
    135: ("SD", "padres"),         # San Diego Padres
    137: ("SF", "giants"),         # San Francisco Giants
}

ROSTER_SEASON = 2026
CURRENT_STAT_SEASON = 2026
PREVIOUS_STAT_SEASON = 2025


def ingest_team(team_id: int, team_abbrev: str, team_name: str, insecure_ssl: bool = False) -> bool:
    """Fetch and ingest data for one team. Returns True if successful."""
    print(f"  Fetching {team_abbrev} ({team_name})...", end=" ", flush=True)

    ssl_context = None
    if insecure_ssl:
        ssl_context = ssl._create_unverified_context()

    try:
        team_export_dir = RAW_EXPORT_DIR / team_abbrev
        team_export_dir.mkdir(parents=True, exist_ok=True)

        # Fetch current season players
        current_players = fetch_team_players(
            team_id,
            team_abbreviation=team_abbrev,
            roster_season=ROSTER_SEASON,
            primary_stat_season=CURRENT_STAT_SEASON,
            fallback_stat_season=CURRENT_STAT_SEASON,
            ssl_context=ssl_context,
            min_players=1,  # Allow any number of players for ingestion
        )

        # Fetch previous season players
        previous_players = fetch_team_players(
            team_id,
            team_abbreviation=team_abbrev,
            roster_season=ROSTER_SEASON,
            primary_stat_season=PREVIOUS_STAT_SEASON,
            fallback_stat_season=PREVIOUS_STAT_SEASON,
            ssl_context=ssl_context,
            min_players=1,
        )

        # Define output paths
        roster_file = team_export_dir / f"{team_name}_live_roster_{ROSTER_SEASON}.csv"
        current_savant_hitters = team_export_dir / f"{team_name}_live_savant_hitters_{CURRENT_STAT_SEASON}.csv"
        current_savant_pitchers = team_export_dir / f"{team_name}_live_savant_pitchers_{CURRENT_STAT_SEASON}.csv"
        current_savant_fielding = team_export_dir / f"{team_name}_live_savant_fielding_{CURRENT_STAT_SEASON}.csv"
        current_bref_hitters = team_export_dir / f"{team_name}_live_bref_hitters_{CURRENT_STAT_SEASON}.csv"
        current_bref_pitchers = team_export_dir / f"{team_name}_live_bref_pitchers_{CURRENT_STAT_SEASON}.csv"

        previous_savant_hitters = team_export_dir / f"{team_name}_live_savant_hitters_{PREVIOUS_STAT_SEASON}.csv"
        previous_savant_pitchers = team_export_dir / f"{team_name}_live_savant_pitchers_{PREVIOUS_STAT_SEASON}.csv"
        previous_savant_fielding = team_export_dir / f"{team_name}_live_savant_fielding_{PREVIOUS_STAT_SEASON}.csv"
        previous_bref_hitters = team_export_dir / f"{team_name}_live_bref_hitters_{PREVIOUS_STAT_SEASON}.csv"
        previous_bref_pitchers = team_export_dir / f"{team_name}_live_bref_pitchers_{PREVIOUS_STAT_SEASON}.csv"

        # Write CSVs
        write_csv(roster_file, build_roster_rows(current_players, team_abbreviation=team_abbrev))
        write_csv(
            current_savant_hitters,
            build_savant_hitter_rows(current_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            current_savant_pitchers,
            build_savant_pitcher_rows(current_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            current_savant_fielding,
            build_savant_fielding_rows(
                current_players,
                team_abbreviation=team_abbrev,
                season=CURRENT_STAT_SEASON,
                ssl_context=ssl_context,
            ),
        )
        write_csv(
            current_bref_hitters,
            build_baseball_reference_hitter_rows(current_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            current_bref_pitchers,
            build_baseball_reference_pitcher_rows(current_players, team_abbreviation=team_abbrev),
        )

        write_csv(
            previous_savant_hitters,
            build_savant_hitter_rows(previous_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            previous_savant_pitchers,
            build_savant_pitcher_rows(previous_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            previous_savant_fielding,
            build_savant_fielding_rows(
                previous_players,
                team_abbreviation=team_abbrev,
                season=PREVIOUS_STAT_SEASON,
                ssl_context=ssl_context,
            ),
        )
        write_csv(
            previous_bref_hitters,
            build_baseball_reference_hitter_rows(previous_players, team_abbreviation=team_abbrev),
        )
        write_csv(
            previous_bref_pitchers,
            build_baseball_reference_pitcher_rows(previous_players, team_abbreviation=team_abbrev),
        )

        print(f"✓ ({len(current_players) + len(previous_players)} total players)")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def main() -> None:
    """Fetch and ingest data for all 30 MLB teams."""
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    print("League-wide data ingestion")
    print("=" * 60)

    processed = 0
    failed = []

    for team_id, (team_abbrev, team_name) in TEAMS.items():
        if ingest_team(team_id, team_abbrev, team_name):
            processed += 1
        else:
            failed.append((team_abbrev, team_name))

    print("=" * 60)
    print(f"Ingestion complete: {processed}/30 teams")
    print(f"Created CSV files in: {RAW_EXPORT_DIR}")

    if failed:
        print(f"\nFailed teams ({len(failed)}):")
        for team_abbrev, team_name in failed:
            print(f"  {team_abbrev} ({team_name})")


if __name__ == "__main__":
    main()
