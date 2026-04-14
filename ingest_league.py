#!/usr/bin/env python3
"""
League-wide ingestion script.
Processes all 30 MLB teams by creating individual manifests and orchestrating ingestion.
"""

import json
import tempfile
from pathlib import Path
from smb4_mlb_ratings.aggregation import aggregate_from_manifest, load_manifest

TEAMS = {
    "BAL": "orioles",
    "BOS": "redsox",
    "NYY": "yankees",
    "TB": "rays",
    "TOR": "bluejays",
    "CWS": "whitesox",
    "CLE": "guardians",
    "DET": "tigers",
    "KC": "royals",
    "MIN": "twins",
    "HOU": "astros",
    "LAA": "angels",
    "OAK": "athletics",
    "SEA": "mariners",
    "TEX": "rangers",
    "ATL": "braves",
    "MIA": "marlins",
    "NYM": "mets",
    "PHI": "phillies",
    "WSH": "nationals",
    "CHC": "cubs",
    "CIN": "reds",
    "MIL": "brewers",
    "PIT": "pirates",
    "STL": "cardinals",
    "ARI": "diamondbacks",
    "COL": "rockies",
    "LAD": "dodgers",
    "SD": "padres",
    "SF": "giants",
}

EXPORT_DIR = Path(__file__).parent / "export"
RAW_EXPORT_DIR = EXPORT_DIR / "raw"
PROJECT_ROOT = Path(__file__).parent


def build_team_manifest(team_abbrev: str, team_name: str) -> dict:
    """Build a manifest for a single team."""
    # Use absolute paths so they work regardless of where the manifest file is
    team_export_dir = (RAW_EXPORT_DIR / team_abbrev).resolve()
    
    return {
        "source": "mixed",
        "roster_filter": {
            "team": team_abbrev,
            "year": 2026
        },
        "seasons": {
            "current": {
                "year": 2026,
                "sources": {
                    "baseball_reference": {
                        "files": {
                            "hitters": str(team_export_dir / f"{team_name}_live_bref_hitters_2026.csv"),
                            "pitchers": str(team_export_dir / f"{team_name}_live_bref_pitchers_2026.csv")
                        }
                    },
                    "baseball_savant": {
                        "files": {
                            "roster": str(team_export_dir / f"{team_name}_live_roster_2026.csv"),
                            "hitters": str(team_export_dir / f"{team_name}_live_savant_hitters_2026.csv"),
                            "pitchers": str(team_export_dir / f"{team_name}_live_savant_pitchers_2026.csv"),
                            "fielding": str(team_export_dir / f"{team_name}_live_savant_fielding_2026.csv")
                        }
                    }
                }
            },
            "previous": {
                "year": 2025,
                "sources": {
                    "baseball_reference": {
                        "files": {
                            "hitters": str(team_export_dir / f"{team_name}_live_bref_hitters_2025.csv"),
                            "pitchers": str(team_export_dir / f"{team_name}_live_bref_pitchers_2025.csv")
                        }
                    },
                    "baseball_savant": {
                        "files": {
                            "hitters": str(team_export_dir / f"{team_name}_live_savant_hitters_2025.csv"),
                            "pitchers": str(team_export_dir / f"{team_name}_live_savant_pitchers_2025.csv"),
                            "fielding": str(team_export_dir / f"{team_name}_live_savant_fielding_2025.csv")
                        }
                    }
                }
            }
        }
    }


def ingest_league() -> None:
    """Ingest all 30 teams and combine results."""
    all_players = []
    processed_teams = []
    failed_teams = []

    for team_abbrev, team_name in TEAMS.items():
        print(f"Processing {team_abbrev} ({team_name})...", end=" ", flush=True)
        
        try:
            # Build manifest
            manifest_dict = build_team_manifest(team_abbrev, team_name)
            
            # Write to temp file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(manifest_dict, f)
                temp_manifest_path = Path(f.name)
            
            try:
                # Load manifest from temp file
                manifest_obj = load_manifest(temp_manifest_path)
                
                # Aggregate players
                players = aggregate_from_manifest(manifest_obj)
                
                all_players.extend(players)
                processed_teams.append(team_abbrev)
                print(f"✓ ({len(players)} players)")
            finally:
                # Clean up temp file
                temp_manifest_path.unlink(missing_ok=True)
            
        except Exception as e:
            print(f"✗ Error: {e}")
            failed_teams.append((team_abbrev, str(e)))

    # Write combined output
    output_path = EXPORT_DIR / "league_normalized.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"players": all_players}, indent=2),
        encoding="utf-8"
    )
    
    # Summary
    print(f"\n{'='*60}")
    print(f"League ingestion complete!")
    print(f"Processed: {len(processed_teams)}/30 teams")
    print(f"Total players: {len(all_players)}")
    print(f"Output: {output_path}")
    
    if failed_teams:
        print(f"\nFailed teams ({len(failed_teams)}):")
        for team_abbrev, error in failed_teams:
            print(f"  {team_abbrev}: {error}")


if __name__ == "__main__":
    ingest_league()
