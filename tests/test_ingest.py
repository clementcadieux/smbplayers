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
                    "BF": 701,
                    "BB": 58,
                    "SO": 192,
                    "HR": 19,
                    "H": 149,
                    "IP": "184.2",
                    "Pitches": 2875,
                    "Strikes": 1896,
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
                    "PA": 600,
                    "ISO": 0.190,
                    "OBP": 0.330,
                    "Barrel %": 14.4,
                    "Avg Exit Velocity": 92.8,
                    "Sprint Speed": 29.1,
                    "K %": 24.0,
                    "Contact %": 73.2,
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
                    "BF": 684,
                    "BB": 54,
                    "SO": 205,
                    "HR": 18,
                    "H": 141,
                    "IP": "181.1",
                    "Pitches": 2798,
                    "Strikes": 1855,
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
        self.assertAlmostEqual(hitter["metrics"]["position_difficulty"]["current"], 0.82)
        self.assertEqual(hitter["metadata"]["source_player_id"], "100")

        self.assertEqual(pitcher["role"], "pitcher")
        self.assertEqual(pitcher["primary_position"], "P")
        self.assertAlmostEqual(pitcher["metrics"]["avg_fastball_velocity"]["current"], 96.3)
        self.assertIn("tracked_pitches", pitcher["samples"])
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

    def test_baseball_reference_manifest_builds_result_based_input(self) -> None:
        manifest = load_manifest(self.root / "br_manifest.json")
        players = ingest_from_manifest(manifest)
        self.assertEqual(len(players), 2)

        hitter = next(player for player in players if player["name"] == "BR Hitter")
        pitcher = next(player for player in players if player["name"] == "BR Pitcher")

        self.assertEqual(hitter["metadata"]["source"], "baseball_reference")
        self.assertAlmostEqual(hitter["metrics"]["iso"]["current"], 0.23)
        self.assertAlmostEqual(hitter["metrics"]["adjusted_obp"]["current"], 0.352)
        self.assertIn("contact_rate", hitter["metadata"]["ingest"]["estimated_metrics"]["current"])

        self.assertEqual(pitcher["metadata"]["source"], "baseball_reference")
        self.assertAlmostEqual(pitcher["metrics"]["walk_rate"]["current"], 58 / 701, places=6)
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
        self.assertIn("baseball_reference:contact_rate", hitter["metadata"]["ingest"]["estimated_metrics"]["current"])
        self.assertIn("baseball_savant:fielding", hitter["metadata"]["ingest"]["missing_files"]["current"])

        self.assertEqual(pitcher["metadata"]["source"], "mixed")
        self.assertAlmostEqual(pitcher["metrics"]["walk_rate"]["current"], 54 / 684, places=6)
        self.assertAlmostEqual(pitcher["metrics"]["avg_fastball_velocity"]["current"], 97.1)
        self.assertAlmostEqual(pitcher["metrics"]["swinging_strike_rate"]["current"], 0.144)
        self.assertIn("baseball_reference:running", pitcher["metadata"]["ingest"]["missing_files"]["current"])


if __name__ == "__main__":
    unittest.main()