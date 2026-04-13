from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.generation import generate_player_report
from smb4_mlb_ratings.models import RatingOutput


class GenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_generate_player_report_contains_required_sections(self) -> None:
        player = RatingOutput.from_dict(
            {
                "name": "Test Hitter",
                "role": "hitter",
                "team": "TOR",
                "primary_position": "CF",
                "ratings": {"contact": 82},
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
                "recommended_personalities": [
                    {
                        "chemistry_type": "Disciplined",
                        "score": 72.5,
                        "personal_score": 80.0,
                        "team_score": 60.0,
                        "reason": "test",
                    }
                ],
                "metadata": {},
            }
        )

        report = generate_player_report(player)

        self.assertIn("## Ratings", report)
        self.assertIn("## Assigned Traits", report)
        self.assertIn("## Recommended Personalities", report)
        self.assertIn("## Review Flags", report)

    def test_cli_generate_creates_team_markdown_files(self) -> None:
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
                        "ratings": {"contact": 82},
                        "percentiles": {"contact": 81.2},
                        "overall_numeric": 80,
                        "overall_grade": "B+",
                        "confidence": "high",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [],
                        "recommended_personalities": [],
                        "metadata": {},
                    },
                    {
                        "name": "Test Pitcher",
                        "role": "pitcher",
                        "team": "NYY",
                        "primary_position": "P",
                        "ratings": {"velocity": 78},
                        "percentiles": {"velocity": 70.1},
                        "overall_numeric": 76,
                        "overall_grade": "B",
                        "confidence": "medium",
                        "review_flags": [],
                        "suggested_traits": [],
                        "assigned_traits": [],
                        "recommended_personalities": [],
                        "metadata": {},
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )

        result = main(["generate", str(input_path), str(output_dir)])

        self.assertEqual(result, 0)
        self.assertTrue((output_dir / "TOR.md").exists())
        self.assertTrue((output_dir / "NYY.md").exists())
