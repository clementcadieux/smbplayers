from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.generation import HITTER_COLUMNS, PITCHER_COLUMNS
from smb4_mlb_ratings.models import RatingOutput


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _read_csv_rows(self, path: Path) -> tuple[list[str], list[dict[str, str]]]:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            rows = list(reader)
        return fieldnames, rows

    def test_generate_output_uses_required_csv_headers(self) -> None:
        input_path = self.root / "ratings.json"
        output_dir = self.root / "reports"
        input_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Test Hitter",
                        "role": "hitter",
                        "team": "TOR",
                        "primary_position": "CF",
                        "secondary_positions": ["LF", "RF"],
                        "ratings": {
                            "contact": 82,
                            "power": 74,
                            "speed": 79,
                            "fielding": 77,
                            "arm": 70,
                        },
                        "percentiles": {"contact": 81.2},
                        "overall_numeric": 80,
                        "overall_grade": "B+",
                        "confidence": "high",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [
                            {
                                "name": "Bad Ball Hitter",
                                "chemistry_type": "Disciplined",
                                "polarity": "positive",
                                "confidence": "high",
                                "reason": "test",
                            },
                            {
                                "name": "Stealer",
                                "chemistry_type": "Competitive",
                                "polarity": "positive",
                                "confidence": "medium",
                                "reason": "test",
                            },
                        ],
                        "recommended_personalities": [],
                        "metadata": {"bats": "R", "throws": "R"},
                    },
                    {
                        "name": "Test Pitcher",
                        "role": "pitcher",
                        "team": "TOR",
                        "primary_position": "SP",
                        "ratings": {
                            "velocity": 88,
                            "junk": 91,
                            "accuracy": 84,
                            "contact": 24,
                            "power": 18,
                            "speed": 45,
                            "fielding": 52,
                            "arm": 77,
                        },
                        "percentiles": {"velocity": 90.0},
                        "overall_numeric": 86,
                        "overall_grade": "A-",
                        "confidence": "high",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [
                            {
                                "name": "Elite 4F",
                                "chemistry_type": "Crafty",
                                "polarity": "positive",
                                "confidence": "high",
                                "reason": "test",
                            }
                        ],
                        "recommended_personalities": [],
                        "recommended_pitches": ["4F", "SL", "CH"],
                        "metadata": {"bats": "L", "throws": "R"},
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        result = main(["generate", str(input_path), str(output_dir)])

        self.assertEqual(result, 0)

        hitter_headers, hitter_rows = self._read_csv_rows(output_dir / "TOR_hitters.csv")
        pitcher_headers, pitcher_rows = self._read_csv_rows(output_dir / "TOR_pitchers.csv")

        self.assertEqual(hitter_headers, HITTER_COLUMNS)
        self.assertEqual(pitcher_headers, PITCHER_COLUMNS)
        self.assertEqual(len(hitter_rows), 1)
        self.assertEqual(len(pitcher_rows), 1)

    def test_generate_output_populates_required_fields_for_hitter_and_pitcher(self) -> None:
        hitter = RatingOutput.from_dict(
            {
                "name": "Test Hitter",
                "role": "hitter",
                "team": "TOR",
                "primary_position": "CF",
                "secondary_positions": ["LF", "RF"],
                "ratings": {
                    "contact": 82,
                    "power": 74,
                    "speed": 79,
                    "fielding": 77,
                    "arm": 70,
                },
                "percentiles": {"contact": 81.2},
                "overall_numeric": 80,
                "overall_grade": "B+",
                "confidence": "high",
                "review_flags": [],
                "suggested_traits": [],
                "assigned_traits": [
                    {
                        "name": "Bad Ball Hitter",
                        "chemistry_type": "Disciplined",
                        "polarity": "positive",
                        "confidence": "high",
                        "reason": "test",
                    }
                ],
                "recommended_personalities": [],
                "metadata": {"bats": "R", "throws": "R"},
            }
        )
        pitcher = RatingOutput.from_dict(
            {
                "name": "Test Pitcher",
                "role": "pitcher",
                "team": "TOR",
                "primary_position": "SP",
                "ratings": {
                    "velocity": 88,
                    "junk": 91,
                    "accuracy": 84,
                    "contact": 24,
                    "power": 18,
                    "speed": 45,
                    "fielding": 52,
                    "arm": 77,
                },
                "percentiles": {"velocity": 90.0},
                "overall_numeric": 86,
                "overall_grade": "A-",
                "confidence": "high",
                "review_flags": [],
                "suggested_traits": [],
                "assigned_traits": [
                    {
                        "name": "Elite 4F",
                        "chemistry_type": "Crafty",
                        "polarity": "positive",
                        "confidence": "high",
                        "reason": "test",
                    }
                ],
                "recommended_personalities": [],
                "recommended_pitches": ["4F", "SL", "CH"],
                "metadata": {"bats": "L", "throws": "R"},
            }
        )

        input_path = self.root / "ratings.json"
        output_dir = self.root / "reports"
        input_path.write_text(json.dumps([hitter.to_dict(), pitcher.to_dict()], indent=2), encoding="utf-8")

        result = main(["generate", str(input_path), str(output_dir)])

        self.assertEqual(result, 0)

        _, hitter_rows = self._read_csv_rows(output_dir / "TOR_hitters.csv")
        _, pitcher_rows = self._read_csv_rows(output_dir / "TOR_pitchers.csv")

        self.assertEqual(hitter_rows[0]["Name"], "Test Hitter")
        self.assertEqual(hitter_rows[0]["Throw Hand"], "R")
        self.assertEqual(hitter_rows[0]["Bat Hand"], "R")
        self.assertEqual(hitter_rows[0]["Primary Position"], "CF")
        self.assertEqual(hitter_rows[0]["Secondary Positions"], "LF, RF")
        self.assertEqual(hitter_rows[0]["Letter Grade"], "B+")
        self.assertEqual(hitter_rows[0]["Trait 1"], "Bad Ball Hitter")
        self.assertEqual(hitter_rows[0]["Trait 2"], "")

        self.assertEqual(pitcher_rows[0]["Name"], "Test Pitcher")
        self.assertEqual(pitcher_rows[0]["Throw Hand"], "R")
        self.assertEqual(pitcher_rows[0]["Bat Hand"], "L")
        self.assertEqual(pitcher_rows[0]["Arsenal"], "4F, SL, CH")
        self.assertEqual(pitcher_rows[0]["Letter Grade"], "A-")
        self.assertEqual(pitcher_rows[0]["Velocity"], "88")
        self.assertEqual(pitcher_rows[0]["Junk"], "91")
        self.assertEqual(pitcher_rows[0]["Accuracy"], "84")
        self.assertEqual(pitcher_rows[0]["Trait 1"], "Elite 4F")
        self.assertEqual(pitcher_rows[0]["Trait 2"], "")

    def test_cli_generate_creates_team_csv_files(self) -> None:
        input_path = self.root / "ratings.json"
        output_dir = self.root / "reports"
        input_path.write_text(
            json.dumps(
                [
                    {
                        "name": "Test Hitter",
                        "role": "hitter",
                        "team": "TOR",
                        "primary_position": "CF",
                        "ratings": {
                            "contact": 82,
                            "power": 74,
                            "speed": 79,
                            "fielding": 77,
                            "arm": 70,
                        },
                        "percentiles": {"contact": 81.2},
                        "overall_numeric": 80,
                        "overall_grade": "B+",
                        "confidence": "high",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [],
                        "recommended_personalities": [],
                        "metadata": {"bats": "R", "throws": "R"},
                    },
                    {
                        "name": "Test Pitcher",
                        "role": "pitcher",
                        "team": "NYY",
                        "primary_position": "P",
                        "ratings": {
                            "velocity": 78,
                            "junk": 75,
                            "accuracy": 81,
                            "contact": 30,
                            "power": 22,
                            "speed": 50,
                            "fielding": 44,
                            "arm": 72,
                        },
                        "percentiles": {"velocity": 70.1},
                        "overall_numeric": 76,
                        "overall_grade": "B",
                        "confidence": "medium",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [],
                        "recommended_personalities": [],
                        "recommended_pitches": ["4F", "CH"],
                        "metadata": {"bats": "L", "throws": "R"},
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        result = main(["generate", str(input_path), str(output_dir)])

        self.assertEqual(result, 0)
        self.assertTrue((output_dir / "TOR_hitters.csv").exists())
        self.assertTrue((output_dir / "TOR_pitchers.csv").exists())
        self.assertTrue((output_dir / "NYY_hitters.csv").exists())
        self.assertTrue((output_dir / "NYY_pitchers.csv").exists())

    def test_two_way_player_only_appears_in_pitcher_output_with_batting_attributes(self) -> None:
        hitter = RatingOutput.from_dict(
            {
                "name": "Corner Bat",
                "role": "hitter",
                "team": "LAA",
                "primary_position": "RF",
                "ratings": {
                    "contact": 72,
                    "power": 76,
                    "speed": 62,
                    "fielding": 58,
                    "arm": 64,
                },
                "percentiles": {"contact": 64.0},
                "overall_numeric": 74,
                "overall_grade": "B",
                "confidence": "high",
                "review_flags": [],
                "suggested_traits": [],
                "assigned_traits": [],
                "recommended_personalities": [],
                "metadata": {"bats": "L", "throws": "L"},
            }
        )
        two_way = RatingOutput.from_dict(
            {
                "name": "Two-Way Ace",
                "role": "two_way",
                "team": "LAA",
                "primary_position": "DH",
                "ratings": {
                    "velocity": 96,
                    "junk": 92,
                    "accuracy": 88,
                    "contact": 78,
                    "power": 82,
                    "speed": 69,
                    "fielding": 57,
                    "arm": 71,
                },
                "percentiles": {"velocity": 95.0, "contact": 75.0},
                "overall_numeric": 93,
                "overall_grade": "A+",
                "confidence": "high",
                "review_flags": [],
                "suggested_traits": [],
                "assigned_traits": [],
                "recommended_personalities": [],
                "recommended_pitches": ["4F", "SL", "CH"],
                "metadata": {"bats": "L", "throws": "R"},
            }
        )

        input_path = self.root / "ratings_two_way.json"
        output_dir = self.root / "reports_two_way"
        input_path.write_text(json.dumps([hitter.to_dict(), two_way.to_dict()], indent=2), encoding="utf-8")

        result = main(["generate", str(input_path), str(output_dir)])

        self.assertEqual(result, 0)

        _, hitter_rows = self._read_csv_rows(output_dir / "LAA_hitters.csv")
        _, pitcher_rows = self._read_csv_rows(output_dir / "LAA_pitchers.csv")

        self.assertEqual([row["Name"] for row in hitter_rows], ["Corner Bat"])
        self.assertIn("Two-Way Ace", [row["Name"] for row in pitcher_rows])

        two_way_pitcher_row = next(row for row in pitcher_rows if row["Name"] == "Two-Way Ace")
        self.assertEqual(two_way_pitcher_row["Velocity"], "96")
        self.assertEqual(two_way_pitcher_row["Junk"], "92")
        self.assertEqual(two_way_pitcher_row["Accuracy"], "88")
        self.assertEqual(two_way_pitcher_row["Contact"], "78")
        self.assertEqual(two_way_pitcher_row["Power"], "82")
        self.assertEqual(two_way_pitcher_row["Speed"], "69")
