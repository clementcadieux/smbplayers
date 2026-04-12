from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.ingest import ingest_from_manifest, load_manifest


class IngestFrameworkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self._write_fixture_files()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            raise ValueError("CSV fixtures require at least one row")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_fixture_files(self) -> None:
        self._write_csv(
            self.root / "roster_2025.csv",
            [
                {
                    "player_id": 100,
                    "player_name": "Test Hitter",
                    "team": "NYM",
                    "age": 27,
                    "position": "CF",
                    "bats": "R",
                    "throws": "R",
                },
                {
                    "player_id": 200,
                    "player_name": "Test Pitcher",
                    "team": "LAD",
                    "age": 30,
                    "position": "P",
                    "bats": "L",
                    "throws": "L",
                },
            ],
        )
        self._write_csv(
            self.root / "hitters_2025.csv",
            [
                {
                    "player_id": 100,
                    "player_name": "Test Hitter",
                    "team": "NYM",
                    "position": "CF",
                    "Days On Roster": 154,
                    "PA": 620,
                    "ISO": 0.215,
                    "HR": 31,
                    "Barrel %": 11.2,
                    "SLG": 0.512,
                    "AVG": 0.287,
                    "OBP": 0.361,
                    "K %": 21.4,
                    "Contact %": 77.8,
                    "Two Strike Contact %": 63.1,
                    "Avg Exit Velocity": 91.2,
                    "2B": 34,
                    "3B": 6,
                    "SB": 21,
                    "CS": 5,
                    "BB": 54,
                    "HBP": 7,
                    "H": 162,
                    "Sprint Speed": 28.6,
                    "First Pitch Hitting": 81,
                    "Pressure Hitting": 77,
                    "O-Contact %": 71,
                }
            ],
        )
        self._write_csv(
            self.root / "hitters_2024.csv",
            [
                {
                    "player_id": 100,
                    "player_name": "Test Hitter",
                    "team": "NYM",
                    "position": "CF",
                    "Days On Roster": 149,
                    "PA": 590,
                    "ISO": 0.201,
                    "HR": 26,
                    "Barrel %": 10.1,
                    "SLG": 0.488,
                    "AVG": 0.276,
                    "OBP": 0.347,
                    "K %": 22.8,
                    "Contact %": 76.0,
                    "Two Strike Contact %": 61.5,
                    "Avg Exit Velocity": 90.4,
                    "2B": 31,
                    "3B": 4,
                    "SB": 17,
                    "CS": 6,
                    "BB": 50,
                    "HBP": 5,
                    "H": 149,
                    "Sprint Speed": 28.4,
                }
            ],
        )
        self._write_csv(
            self.root / "fielding_2025.csv",
            [
                {
                    "player_id": 100,
                    "player_name": "Test Hitter",
                    "team": "NYM",
                    "position": "CF",
                    "Defensive Innings": 1115,
                    "OAA": 8,
                    "DRS": 6,
                    "UZR": 4.1,
                    "Dive Recovery": 72,
                    "Fielding %": 0.992,
                    "Arm Strength": 89.4,
                    "Outfield Arm Runs": 2.9,
                }
            ],
        )
        self._write_csv(
            self.root / "running_2025.csv",
            [
                {
                    "player_id": 100,
                    "player_name": "Test Hitter",
                    "Sprint Speed": 28.6,
                    "Baserunning Value": 4.8,
                    "Baserunning Opportunities": 153,
                }
            ],
        )
        self._write_csv(
            self.root / "pitchers_2025.csv",
            [
                {
                    "player_id": 200,
                    "player_name": "Test Pitcher",
                    "team": "LAD",
                    "position": "P",
                    "Days On Roster": 176,
                    "BF": 712,
                    "Pitches": 2810,
                    "Avg Fastball Velocity": 96.3,
                    "Peak Fastball Velocity": 99.1,
                    "FF %": 48.0,
                    "SwStr %": 13.9,
                    "Chase %": 32.4,
                    "BB %": 6.9,
                    "Strike %": 65.4,
                    "Zone %": 49.8,
                    "First Pitch Strike %": 62.1,
                    "Horizontal Break": 15.2,
                    "Induced Vertical Break": 17.8,
                    "Hard Hit %": 34.0,
                    "SL %": 27.0,
                    "CH %": 15.0,
                    "CU %": 10.0,
                    "Pressure Pitching": 78,
                    "Runners On Pitching": 74,
                    "First Pitch Pitching": 73,
                    "Running Game Control": 68,
                    "Same Handed Pitching": 72,
                    "Same Handed Pitching Gap": 14,
                    "Opposite Handed Pitching": 58,
                    "Opposite Handed Pitching Gap": -14,
                    "Pitch Quality 4F": 80,
                    "Pitch Quality 2F": 76,
                    "Pitch Quality CF": 74,
                    "Pitch Quality FK": 82,
                    "Pitch Quality SB": 71,
                    "Secondary Field Positions": "OF",
                }
            ],
        )

        manifest = {
            "source": "baseball_savant",
            "seasons": {
                "current": {
                    "year": 2025,
                    "files": {
                        "roster": "roster_2025.csv",
                        "hitters": "hitters_2025.csv",
                        "pitchers": "pitchers_2025.csv",
                        "fielding": "fielding_2025.csv",
                        "running": "running_2025.csv",
                    },
                },
                "previous": {
                    "year": 2024,
                    "files": {
                        "hitters": "hitters_2024.csv",
                    },
                },
            },
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        self._write_csv(
            self.root / "br_roster_2025.csv",
            [
                {
                    "player_id": 300,
                    "player_name": "BR Hitter",
                    "team": "SEA",
                    "age": 28,
                    "position": "RF",
                    "bats": "L",
                    "throws": "R",
                },
                {
                    "player_id": 400,
                    "player_name": "BR Pitcher",
                    "team": "CHC",
                    "age": 31,
                    "position": "P",
                    "bats": "R",
                    "throws": "R",
                },
            ],
        )
        self._write_csv(
            self.root / "br_hitters_2025.csv",
            [
                {
                    "player_id": 300,
                    "player_name": "BR Hitter",
                    "team": "SEA",
                    "position": "RF",
                    "Days On Roster": 158,
                    "PA": 645,
                    "AB": 585,
                    "H": 170,
                    "2B": 38,
                    "3B": 3,
                    "HR": 29,
                    "BB": 52,
                    "SO": 118,
                    "HBP": 6,
                    "SB": 14,
                    "CS": 4,
                    "BA": 0.291,
                    "OBP": 0.352,
                    "SLG": 0.521,
                    "BsR": 3.7,
                    "Pinch Hitting": 67,
                }
            ],
        )
        self._write_csv(
            self.root / "br_pitchers_2025.csv",
            [
                {
                    "player_id": 400,
                    "player_name": "BR Pitcher",
                    "team": "CHC",
                    "position": "P",
                    "Days On Roster": 172,
                    "BF": 701,
                    "BB": 58,
                    "SO": 192,
                    "HR": 19,
                    "H": 149,
                    "IP": "184.2",
                    "Pitches": 2875,
                    "Strikes": 1896,
                    "Pressure Pitching": 71,
                    "Same Handed Pitching": 69,
                    "Same Handed Pitching Gap": 11,
                    "Opposite Handed Pitching": 58,
                    "Opposite Handed Pitching Gap": -11,
                }
            ],
        )
        self._write_csv(
            self.root / "br_fielding_2025.csv",
            [
                {
                    "player_id": 300,
                    "player_name": "BR Hitter",
                    "team": "SEA",
                    "position": "RF",
                    "Defensive Innings": 1092,
                    "DRS": 7,
                    "UZR": 5.2,
                    "PO": 201,
                    "A": 9,
                    "E": 2,
                }
            ],
        )

        br_manifest = {
            "source": "baseball_reference",
            "seasons": {
                "current": {
                    "year": 2025,
                    "files": {
                        "roster": "br_roster_2025.csv",
                        "hitters": "br_hitters_2025.csv",
                        "pitchers": "br_pitchers_2025.csv",
                        "fielding": "br_fielding_2025.csv",
                    },
                }
            },
        }
        (self.root / "br_manifest.json").write_text(json.dumps(br_manifest, indent=2), encoding="utf-8")

        self._write_csv(
            self.root / "mixed_savant_hitters_2025.csv",
            [
                {
                    "player_id": 500,
                    "player_name": "Merge Hitter",
                    "team": "ATL",
                    "position": "LF",
                    "Days On Roster": 141,
                    "PA": 600,
                    "ISO": 0.190,
                    "OBP": 0.330,
                    "Barrel %": 14.4,
                    "Avg Exit Velocity": 92.8,
                    "Sprint Speed": 29.1,
                    "K %": 24.0,
                    "Contact %": 73.2,
                    "First Pitch Hitting": 79,
                    "O-Contact %": 69,
                }
            ],
        )
        self._write_csv(
            self.root / "mixed_savant_pitchers_2025.csv",
            [
                {
                    "player_id": 600,
                    "player_name": "Merge Pitcher",
                    "team": "BOS",
                    "position": "P",
                    "Days On Roster": 168,
                    "BF": 680,
                    "Pitches": 2750,
                    "Avg Fastball Velocity": 97.1,
                    "Peak Fastball Velocity": 99.4,
                    "FF %": 52.0,
                    "SwStr %": 14.4,
                    "Chase %": 33.1,
                    "Zone %": 50.2,
                    "First Pitch Strike %": 63.0,
                    "Horizontal Break": 14.8,
                    "Induced Vertical Break": 17.2,
                    "Hard Hit %": 32.0,
                    "SL %": 28.0,
                    "CH %": 12.0,
                    "Pitch Quality 4F": 77,
                    "Pitch Quality FK": 83,
                    "Running Game Control": 66,
                    "Secondary Field Positions": "OF",
                }
            ],
        )
        self._write_csv(
            self.root / "mixed_running_2025.csv",
            [
                {
                    "player_id": 500,
                    "player_name": "Merge Hitter",
                    "Sprint Speed": 29.1,
                    "Baserunning Opportunities": 150,
                }
            ],
        )
        self._write_csv(
            self.root / "mixed_br_hitters_2025.csv",
            [
                {
                    "player_id": 500,
                    "player_name": "Merge Hitter",
                    "team": "ATL",
                    "position": "LF",
                    "Days On Roster": 150,
                    "PA": 612,
                    "AB": 560,
                    "H": 158,
                    "2B": 35,
                    "3B": 2,
                    "HR": 27,
                    "BB": 48,
                    "SO": 121,
                    "HBP": 4,
                    "SB": 16,
                    "CS": 3,
                    "BA": 0.282,
                    "OBP": 0.347,
                    "SLG": 0.498,
                    "BsR": 4.2,
                    "Bunt Value": 70,
                }
            ],
        )
        self._write_csv(
            self.root / "mixed_br_pitchers_2025.csv",
            [
                {
                    "player_id": 600,
                    "player_name": "Merge Pitcher",
                    "team": "BOS",
                    "position": "P",
                    "Days On Roster": 171,
                    "BF": 684,
                    "BB": 54,
                    "SO": 205,
                    "HR": 18,
                    "H": 141,
                    "IP": "181.1",
                    "Pitches": 2798,
                    "Strikes": 1855,
                    "Pressure Pitching": 69,
                }
            ],
        )

        mixed_manifest = {
            "source": "mixed",
            "seasons": {
                "current": {
                    "year": 2025,
                    "sources": {
                        "baseball_reference": {
                            "files": {
                                "hitters": "mixed_br_hitters_2025.csv",
                                "pitchers": "mixed_br_pitchers_2025.csv",
                            }
                        },
                        "baseball_savant": {
                            "files": {
                                "hitters": "mixed_savant_hitters_2025.csv",
                                "pitchers": "mixed_savant_pitchers_2025.csv",
                                "running": "mixed_running_2025.csv",
                            }
                        },
                    },
                }
            },
        }
        (self.root / "mixed_manifest.json").write_text(json.dumps(mixed_manifest, indent=2), encoding="utf-8")

    def test_ingest_from_manifest_builds_engine_input(self) -> None:
        manifest = load_manifest(self.root / "manifest.json")
        players = ingest_from_manifest(manifest)
        self.assertEqual(len(players), 2)

        hitter = next(player for player in players if player["name"] == "Test Hitter")
        pitcher = next(player for player in players if player["name"] == "Test Pitcher")

        self.assertEqual(hitter["role"], "hitter")
        self.assertEqual(hitter["primary_position"], "CF")
        self.assertIn("current", hitter["metrics"]["iso"])
        self.assertIn("previous", hitter["metrics"]["iso"])
        self.assertAlmostEqual(hitter["samples"]["weighted_pa"]["current"], 620.0)
        self.assertEqual(hitter["days_on_roster"]["current"], 154.0)
        self.assertAlmostEqual(hitter["metrics"]["position_difficulty"]["current"], 0.82)
        self.assertEqual(hitter["metadata"]["source_player_id"], "100")
        self.assertEqual(hitter["trait_metrics"]["first_pitch_hitting"]["current"], 81.0)
        self.assertEqual(hitter["trait_metrics"]["pressure_hitting"]["current"], 77.0)
        self.assertEqual(hitter["trait_metrics"]["out_of_zone_contact_pct"]["current"], 71.0)
        self.assertEqual(hitter["trait_metrics"]["dive_recovery"]["current"], 72.0)

        self.assertEqual(pitcher["role"], "pitcher")
        self.assertEqual(pitcher["primary_position"], "P")
        self.assertAlmostEqual(pitcher["metrics"]["avg_fastball_velocity"]["current"], 96.3)
        self.assertEqual(pitcher["days_on_roster"]["current"], 176.0)
        self.assertIn("tracked_pitches", pitcher["samples"])
        self.assertAlmostEqual(pitcher["pitch_mix"]["ff"], 0.48)
        self.assertAlmostEqual(pitcher["pitch_mix"]["sl"], 0.27)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_4f"]["current"], 80.0)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_2f"]["current"], 76.0)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_cf"]["current"], 74.0)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_fk"]["current"], 82.0)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_sb"]["current"], 71.0)
        self.assertEqual(pitcher["trait_metrics"]["steal_suppression"]["current"], 68.0)
        self.assertEqual(pitcher["trait_metrics"]["same_handed_pitching_gap"]["current"], 14.0)
        self.assertEqual(pitcher["trait_metrics"]["opposite_handed_pitching_gap"]["current"], -14.0)
        self.assertEqual(pitcher["trait_lists"]["secondary_field_positions"], ["OF"])
        self.assertIn("arsenal_diversity", pitcher["metadata"]["ingest"]["estimated_metrics"]["current"])

    def test_cli_ingest_and_legacy_rate_flow(self) -> None:
        normalized_path = self.root / "normalized.json"
        ratings_path = self.root / "ratings.json"

        result = main(["ingest", str(self.root / "manifest.json"), str(normalized_path)])
        self.assertEqual(result, 0)
        payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["players"]), 2)

        legacy_result = main([str(normalized_path), str(ratings_path)])
        self.assertEqual(legacy_result, 0)
        ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(ratings), 2)
        self.assertEqual(sorted(item["name"] for item in ratings), ["Test Hitter", "Test Pitcher"])

    def test_cli_ingest_rate_writes_optional_normalized_output(self) -> None:
        normalized_path = self.root / "normalized_from_ingest_rate.json"
        ratings_path = self.root / "ratings_from_ingest_rate.json"

        result = main(
            [
                "ingest-rate",
                str(self.root / "manifest.json"),
                str(ratings_path),
                "--normalized-output",
                str(normalized_path),
            ]
        )
        self.assertEqual(result, 0)
        self.assertTrue(normalized_path.exists())
        self.assertTrue(ratings_path.exists())

        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(normalized_payload["players"]), 2)
        self.assertEqual(len(ratings_payload), 2)

    def test_ingest_marks_current_wrong_team_players_inactive_when_roster_filter_present(self) -> None:
        roster_path = self.root / "filtered_roster_2025.csv"
        hitters_path = self.root / "filtered_hitters_2025.csv"
        manifest_path = self.root / "filtered_manifest.json"

        self._write_csv(
            roster_path,
            [
                {
                    "player_id": 700,
                    "player_name": "Target Team Hitter",
                    "team": "NYM",
                    "age": 25,
                    "position": "CF",
                    "bats": "R",
                    "throws": "R",
                }
            ],
        )
        self._write_csv(
            hitters_path,
            [
                {
                    "player_id": 700,
                    "player_name": "Target Team Hitter",
                    "team": "NYM",
                    "position": "CF",
                    "PA": 510,
                    "ISO": 0.180,
                    "HR": 21,
                    "Barrel %": 9.8,
                    "SLG": 0.472,
                    "AVG": 0.277,
                    "OBP": 0.340,
                    "K %": 20.1,
                    "Contact %": 79.1,
                    "Two Strike Contact %": 63.0,
                    "Avg Exit Velocity": 89.4,
                    "2B": 28,
                    "3B": 3,
                    "SB": 14,
                    "CS": 4,
                    "BB": 41,
                    "HBP": 3,
                    "H": 138,
                    "Sprint Speed": 28.2,
                },
                {
                    "player_id": 701,
                    "player_name": "Traded Hitter",
                    "team": "PHI",
                    "position": "RF",
                    "PA": 480,
                    "ISO": 0.195,
                    "HR": 24,
                    "Barrel %": 10.4,
                    "SLG": 0.481,
                    "AVG": 0.271,
                    "OBP": 0.336,
                    "K %": 22.0,
                    "Contact %": 76.0,
                    "Two Strike Contact %": 60.2,
                    "Avg Exit Velocity": 90.1,
                    "2B": 30,
                    "3B": 2,
                    "SB": 8,
                    "CS": 2,
                    "BB": 39,
                    "HBP": 2,
                    "H": 126,
                    "Sprint Speed": 27.9,
                },
            ],
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "baseball_savant",
                    "roster_filter": {"team": "NYM", "year": 2025},
                    "seasons": {
                        "current": {
                            "year": 2025,
                            "files": {
                                "roster": "filtered_roster_2025.csv",
                                "hitters": "filtered_hitters_2025.csv",
                            },
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        players = ingest_from_manifest(load_manifest(manifest_path))

        active_player = next(player for player in players if player["name"] == "Target Team Hitter")
        inactive_player = next(player for player in players if player["name"] == "Traded Hitter")
        self.assertTrue(active_player["active"])
        self.assertFalse(inactive_player["active"])
        self.assertEqual(inactive_player["team"], "PHI")

    def test_cli_rate_team_filter_excludes_other_teams(self) -> None:
        normalized_path = self.root / "filtered_players.json"
        ratings_path = self.root / "filtered_ratings.json"
        normalized_path.write_text(
            json.dumps(
                {
                    "players": [
                        {
                            "name": "Keep Me",
                            "role": "hitter",
                            "active": True,
                            "team": "NYM",
                            "primary_position": "CF",
                            "metrics": {
                                "iso": {"current": 0.190},
                                "hr_per_pa": {"current": 0.040},
                                "barrel_rate": {"current": 0.100},
                                "slugging": {"current": 0.470},
                                "avg_exit_velocity": {"current": 90.0},
                                "strikeout_rate": {"current": 0.210},
                                "contact_rate": {"current": 0.780},
                                "batting_average": {"current": 0.270},
                                "adjusted_obp": {"current": 0.340},
                                "two_strike_contact_rate": {"current": 0.620},
                            },
                            "samples": {"weighted_pa": {"current": 500}},
                            "metadata": {},
                        },
                        {
                            "name": "Drop Me",
                            "role": "hitter",
                            "active": True,
                            "team": "ATL",
                            "primary_position": "RF",
                            "metrics": {
                                "iso": {"current": 0.180},
                                "hr_per_pa": {"current": 0.038},
                                "barrel_rate": {"current": 0.090},
                                "slugging": {"current": 0.450},
                                "avg_exit_velocity": {"current": 89.0},
                                "strikeout_rate": {"current": 0.220},
                                "contact_rate": {"current": 0.760},
                                "batting_average": {"current": 0.265},
                                "adjusted_obp": {"current": 0.332},
                                "two_strike_contact_rate": {"current": 0.610},
                            },
                            "samples": {"weighted_pa": {"current": 480}},
                            "metadata": {},
                        },
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = main(["rate", str(normalized_path), str(ratings_path), "--team", "nym"])

        self.assertEqual(result, 0)
        ratings = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in ratings], ["Keep Me"])

    def test_ingest_preserves_roster_status_metadata(self) -> None:
        roster_path = self.root / "status_roster_2025.csv"
        hitters_path = self.root / "status_hitters_2025.csv"
        manifest_path = self.root / "status_manifest.json"

        self._write_csv(
            roster_path,
            [
                {
                    "player_id": 710,
                    "player_name": "Injured Hitter",
                    "team": "NYM",
                    "status": "Injured 10-Day",
                    "status_code": "D10",
                    "age": 28,
                    "position": "LF",
                    "bats": "L",
                    "throws": "R",
                }
            ],
        )
        self._write_csv(
            hitters_path,
            [
                {
                    "player_id": 710,
                    "player_name": "Injured Hitter",
                    "team": "NYM",
                    "position": "LF",
                    "PA": 420,
                    "ISO": 0.172,
                    "HR": 18,
                    "Barrel %": 8.9,
                    "SLG": 0.441,
                    "AVG": 0.266,
                    "OBP": 0.329,
                    "K %": 21.0,
                    "Contact %": 77.4,
                    "Two Strike Contact %": 61.8,
                    "Avg Exit Velocity": 89.1,
                    "2B": 24,
                    "3B": 2,
                    "SB": 6,
                    "CS": 2,
                    "BB": 35,
                    "HBP": 2,
                    "H": 111,
                    "Sprint Speed": 27.5,
                }
            ],
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "baseball_savant",
                    "seasons": {
                        "current": {
                            "year": 2025,
                            "files": {
                                "roster": "status_roster_2025.csv",
                                "hitters": "status_hitters_2025.csv",
                            },
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        players = ingest_from_manifest(load_manifest(manifest_path))

        player = players[0]
        self.assertEqual(player["metadata"]["status"], "Injured 10-Day")
        self.assertEqual(player["metadata"]["status_code"], "D10")
        self.assertTrue(player["metadata"]["on_il"])

    def test_ingest_flags_injury_shortened_season_from_volume_threshold(self) -> None:
        roster_path = self.root / "injury_roster_2025.csv"
        hitters_path = self.root / "injury_hitters_2025.csv"
        manifest_path = self.root / "injury_manifest.json"

        self._write_csv(
            roster_path,
            [
                {"player_id": 800, "player_name": "Healthy One", "team": "NYM", "age": 27, "position": "CF", "bats": "R", "throws": "R"},
                {"player_id": 801, "player_name": "Healthy Two", "team": "NYM", "age": 29, "position": "RF", "bats": "L", "throws": "R"},
                {"player_id": 802, "player_name": "Short Season", "team": "NYM", "age": 25, "position": "LF", "bats": "L", "throws": "R"},
            ],
        )
        self._write_csv(
            hitters_path,
            [
                {"player_id": 800, "player_name": "Healthy One", "team": "NYM", "position": "CF", "PA": 640, "ISO": 0.185, "HR": 24, "Barrel %": 9.5, "SLG": 0.470, "AVG": 0.276, "OBP": 0.344, "K %": 20.4, "Contact %": 78.2, "Two Strike Contact %": 62.5, "Avg Exit Velocity": 90.1, "2B": 30, "3B": 4, "SB": 12, "CS": 3, "BB": 50, "HBP": 4, "H": 160, "Sprint Speed": 28.0},
                {"player_id": 801, "player_name": "Healthy Two", "team": "NYM", "position": "RF", "PA": 600, "ISO": 0.175, "HR": 22, "Barrel %": 8.8, "SLG": 0.455, "AVG": 0.271, "OBP": 0.338, "K %": 21.0, "Contact %": 77.0, "Two Strike Contact %": 61.7, "Avg Exit Velocity": 89.7, "2B": 29, "3B": 2, "SB": 9, "CS": 2, "BB": 46, "HBP": 3, "H": 151, "Sprint Speed": 27.6},
                {"player_id": 802, "player_name": "Short Season", "team": "NYM", "position": "LF", "PA": 120, "ISO": 0.180, "HR": 8, "Barrel %": 9.0, "SLG": 0.460, "AVG": 0.274, "OBP": 0.340, "K %": 20.8, "Contact %": 77.8, "Two Strike Contact %": 62.2, "Avg Exit Velocity": 89.9, "2B": 10, "3B": 1, "SB": 4, "CS": 1, "BB": 12, "HBP": 1, "H": 31, "Sprint Speed": 27.8},
            ],
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "baseball_savant",
                    "seasons": {
                        "current": {
                            "year": 2025,
                            "files": {
                                "roster": "injury_roster_2025.csv",
                                "hitters": "injury_hitters_2025.csv",
                            },
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        players = ingest_from_manifest(load_manifest(manifest_path))

        shortened = next(player for player in players if player["name"] == "Short Season")
        healthy = next(player for player in players if player["name"] == "Healthy One")
        self.assertTrue(shortened["metadata"]["ingest"]["injury_shortened"]["current"])
        self.assertEqual(healthy["metadata"]["ingest"]["injury_shortened"], {})

    def test_baseball_reference_manifest_builds_result_based_input(self) -> None:
        manifest = load_manifest(self.root / "br_manifest.json")
        players = ingest_from_manifest(manifest)
        self.assertEqual(len(players), 2)

        hitter = next(player for player in players if player["name"] == "BR Hitter")
        pitcher = next(player for player in players if player["name"] == "BR Pitcher")

        self.assertEqual(hitter["metadata"]["source"], "baseball_reference")
        self.assertEqual(hitter["days_on_roster"]["current"], 158.0)
        self.assertAlmostEqual(hitter["metrics"]["iso"]["current"], 0.23)
        self.assertAlmostEqual(hitter["metrics"]["adjusted_obp"]["current"], 0.352)
        self.assertEqual(hitter["trait_metrics"]["pinch_hitting"]["current"], 67.0)
        self.assertIn("contact_rate", hitter["metadata"]["ingest"]["estimated_metrics"]["current"])

        self.assertEqual(pitcher["metadata"]["source"], "baseball_reference")
        self.assertEqual(pitcher["days_on_roster"]["current"], 172.0)
        self.assertAlmostEqual(pitcher["metrics"]["walk_rate"]["current"], 58 / 701, places=6)
        self.assertEqual(pitcher["trait_metrics"]["pressure_pitching"]["current"], 71.0)
        self.assertEqual(pitcher["trait_metrics"]["same_handed_pitching"]["current"], 69.0)
        self.assertEqual(pitcher["trait_metrics"]["same_handed_pitching_gap"]["current"], 11.0)
        self.assertEqual(pitcher["trait_metrics"]["opposite_handed_pitching_gap"]["current"], -11.0)
        self.assertIn("stuff_metric", pitcher["metadata"]["ingest"]["estimated_metrics"]["current"])
        self.assertIn("running", pitcher["metadata"]["ingest"]["missing_files"]["current"])

    def test_mixed_manifest_prefers_br_outcomes_and_savant_tools(self) -> None:
        manifest = load_manifest(self.root / "mixed_manifest.json")
        players = ingest_from_manifest(manifest)
        self.assertEqual(len(players), 2)

        hitter = next(player for player in players if player["name"] == "Merge Hitter")
        pitcher = next(player for player in players if player["name"] == "Merge Pitcher")

        self.assertEqual(hitter["metadata"]["source"], "mixed")
        self.assertEqual(sorted(hitter["metadata"]["source_components"]), ["baseball_reference", "baseball_savant"])
        self.assertAlmostEqual(hitter["metrics"]["iso"]["current"], 0.216)
        self.assertAlmostEqual(hitter["metrics"]["adjusted_obp"]["current"], 0.347)
        self.assertAlmostEqual(hitter["metrics"]["barrel_rate"]["current"], 0.144)
        self.assertAlmostEqual(hitter["metrics"]["avg_exit_velocity"]["current"], 92.8)
        self.assertAlmostEqual(hitter["metrics"]["sprint_speed"]["current"], 29.1)
        self.assertEqual(hitter["days_on_roster"]["current"], 141.0)
        self.assertEqual(hitter["trait_metrics"]["first_pitch_hitting"]["current"], 79.0)
        self.assertEqual(hitter["trait_metrics"]["bunt_value"]["current"], 70.0)
        self.assertIn("baseball_reference:contact_rate", hitter["metadata"]["ingest"]["estimated_metrics"]["current"])
        self.assertIn("baseball_savant:fielding", hitter["metadata"]["ingest"]["missing_files"]["current"])

        self.assertEqual(pitcher["metadata"]["source"], "mixed")
        self.assertAlmostEqual(pitcher["metrics"]["walk_rate"]["current"], 54 / 684, places=6)
        self.assertAlmostEqual(pitcher["metrics"]["avg_fastball_velocity"]["current"], 97.1)
        self.assertAlmostEqual(pitcher["metrics"]["swinging_strike_rate"]["current"], 0.144)
        self.assertEqual(pitcher["days_on_roster"]["current"], 168.0)
        self.assertAlmostEqual(pitcher["pitch_mix"]["ff"], 0.565217, places=6)
        self.assertAlmostEqual(pitcher["pitch_mix"]["sl"], 0.304348, places=6)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_4f"]["current"], 77.0)
        self.assertEqual(pitcher["trait_metrics"]["pitch_quality_fk"]["current"], 83.0)
        self.assertEqual(pitcher["trait_metrics"]["pressure_pitching"]["current"], 69.0)
        self.assertEqual(pitcher["trait_lists"]["secondary_field_positions"], ["OF"])
        self.assertIn("baseball_reference:running", pitcher["metadata"]["ingest"]["missing_files"]["current"])


if __name__ == "__main__":
    unittest.main()