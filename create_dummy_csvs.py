#!/usr/bin/env python3
"""
Create minimal dummy CSV files for all 30 teams to enable ingest to run.
"""

from pathlib import Path

EXPORT_DIR = Path(__file__).parent / "export"
EXPORT_DIR.mkdir(exist_ok=True)

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


def create_bref_hitters_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Baseball Reference hitters CSV."""
    content = """Name,Pos,G,PA,AB,R,H,2B,3B,HR,RBI,BB,K,SB,CS,BA,OBP,SLG
Player One,C,100,400,350,50,100,20,2,15,60,30,50,2,1,0.286,0.350,0.480
Player Two,1B,120,500,450,70,140,25,1,25,90,35,60,3,2,0.311,0.370,0.540
Player Three,2B,110,450,400,60,120,22,3,10,50,35,55,8,3,0.300,0.360,0.430
"""
    filepath.write_text(content, encoding="utf-8")


def create_bref_pitchers_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Baseball Reference pitchers CSV."""
    content = """Name,Pos,G,GS,IP,H,R,ER,BB,K,ERA,FIP
Pitcher One,P,30,28,180.0,160,70,60,50,150,3.00,3.20
Pitcher Two,P,40,0,80.0,70,25,20,25,70,2.25,2.50
Pitcher Three,P,35,25,140.0,130,60,50,40,120,3.21,3.40
"""
    filepath.write_text(content, encoding="utf-8")


def create_roster_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Savant roster CSV."""
    content = f"""Name,Team,Position
Player One,{team_abbrev},C
Player Two,{team_abbrev},1B
Player Three,{team_abbrev},2B
Pitcher One,{team_abbrev},P
Pitcher Two,{team_abbrev},P
Pitcher Three,{team_abbrev},P
"""
    filepath.write_text(content, encoding="utf-8")


def create_savant_hitters_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Savant hitters CSV."""
    content = """player_name,team,position,avg_exit_velo,max_exit_velo
Player One,{},C,85.5,95.2
Player Two,{},1B,87.2,98.1
Player Three,{},2B,84.1,92.3
""".format(team_abbrev, team_abbrev, team_abbrev)
    filepath.write_text(content, encoding="utf-8")


def create_savant_pitchers_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Savant pitchers CSV."""
    content = """player_name,team,pitch_type,avg_velo,max_velo
Pitcher One,{},FF,92.5,96.1
Pitcher One,{},SL,84.2,86.5
Pitcher Two,{},FF,93.2,97.0
Pitcher Two,{},CH,85.1,87.3
Pitcher Three,{},FF,91.8,95.5
Pitcher Three,{},CB,78.5,81.2
""".format(
        team_abbrev,
        team_abbrev,
        team_abbrev,
        team_abbrev,
        team_abbrev,
        team_abbrev,
    )
    filepath.write_text(content, encoding="utf-8")


def create_savant_fielding_csv(filepath: Path, team_abbrev: str) -> None:
    """Create dummy Savant fielding CSV."""
    content = f"""player_name,team,position,fielding_runs
Player One,{team_abbrev},C,2.5
Player Two,{team_abbrev},1B,1.2
Player Three,{team_abbrev},2B,3.1
"""
    filepath.write_text(content, encoding="utf-8")


def main() -> None:
    """Create all dummy CSV files for all teams and years."""
    for team_abbrev, team_name in TEAMS.items():
        print(f"Creating CSVs for {team_abbrev} ({team_name})... ", end="", flush=True)

        # 2026 files
        create_bref_hitters_csv(
            EXPORT_DIR / f"{team_name}_live_bref_hitters_2026.csv", team_abbrev
        )
        create_bref_pitchers_csv(
            EXPORT_DIR / f"{team_name}_live_bref_pitchers_2026.csv", team_abbrev
        )
        create_roster_csv(
            EXPORT_DIR / f"{team_name}_live_roster_2026.csv", team_abbrev
        )
        create_savant_hitters_csv(
            EXPORT_DIR / f"{team_name}_live_savant_hitters_2026.csv", team_abbrev
        )
        create_savant_pitchers_csv(
            EXPORT_DIR / f"{team_name}_live_savant_pitchers_2026.csv", team_abbrev
        )
        create_savant_fielding_csv(
            EXPORT_DIR / f"{team_name}_live_savant_fielding_2026.csv", team_abbrev
        )

        # 2025 files (same structure)
        create_bref_hitters_csv(
            EXPORT_DIR / f"{team_name}_live_bref_hitters_2025.csv", team_abbrev
        )
        create_bref_pitchers_csv(
            EXPORT_DIR / f"{team_name}_live_bref_pitchers_2025.csv", team_abbrev
        )
        create_savant_hitters_csv(
            EXPORT_DIR / f"{team_name}_live_savant_hitters_2025.csv", team_abbrev
        )
        create_savant_pitchers_csv(
            EXPORT_DIR / f"{team_name}_live_savant_pitchers_2025.csv", team_abbrev
        )
        create_savant_fielding_csv(
            EXPORT_DIR / f"{team_name}_live_savant_fielding_2025.csv", team_abbrev
        )

        print("✓")

    print(f"\nCreated {len(TEAMS) * 11} CSV files in {EXPORT_DIR}")


if __name__ == "__main__":
    main()
