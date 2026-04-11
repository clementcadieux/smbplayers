from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.models import RatingOutput
from smb4_mlb_ratings.output import write_structured_output


class StructuredOutputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_write_structured_output_groups_by_league_division_and_team(self) -> None:
        output_dir = self.root / "structured"
        ratings = [
            self._rating("Red Sox 1", "BOS"),
            self._rating("Red Sox 2", "BOS"),
            self._rating("Guardians 1", "CLE"),
            self._rating("Dodgers 1", "LAD"),
            self._rating("Mets 1", "NYM"),
        ]

        write_structured_output(ratings, output_dir)

        bos_payload = json.loads((output_dir / "AL" / "East" / "BOS.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in bos_payload], ["Red Sox 1", "Red Sox 2"])

        cle_payload = json.loads((output_dir / "AL" / "Central" / "CLE.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in cle_payload], ["Guardians 1"])

        lad_payload = json.loads((output_dir / "NL" / "West" / "LAD.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in lad_payload], ["Dodgers 1"])

        index_payload = json.loads((output_dir / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index_payload["AL"]["East"][0]["path"], "AL/East/BOS.json")
        self.assertEqual(index_payload["AL"]["Central"][0]["team"], "CLE")
        self.assertEqual(index_payload["NL"]["West"][0]["team"], "LAD")
        self.assertEqual(index_payload["NL"]["East"][0]["team"], "NYM")

    def test_cli_ingest_rate_can_write_structured_output_only(self) -> None:
        roster_path = self.root / "roster_2025.csv"
        hitters_path = self.root / "hitters_2025.csv"
        pitchers_path = self.root / "pitchers_2025.csv"
        manifest_path = self.root / "manifest.json"
        structured_path = self.root / "team_output"

        roster_path.write_text(
            "player_id,player_name,team,age,position,bats,throws\n"
            "100,Test Hitter,NYM,27,CF,R,R\n"
            "200,Test Pitcher,LAD,30,P,L,L\n",
            encoding="utf-8",
        )
        hitters_path.write_text(
            "player_id,player_name,team,position,PA,ISO,HR,Barrel %,SLG,AVG,OBP,K %,Contact %,Two Strike Contact %,Avg Exit Velocity,2B,3B,SB,CS,BB,HBP,H,Sprint Speed\n"
            "100,Test Hitter,NYM,CF,620,0.215,31,11.2,0.512,0.287,0.361,21.4,77.8,63.1,91.2,34,6,21,5,54,7,162,28.6\n",
            encoding="utf-8",
        )
        pitchers_path.write_text(
            "player_id,player_name,team,position,BF,Pitches,Avg Fastball Velocity,Peak Fastball Velocity,FF %,SwStr %,Chase %,BB %,Strike %,Zone %,First Pitch Strike %,Horizontal Break,Induced Vertical Break,Hard Hit %,SL %,CH %,CU %\n"
            "200,Test Pitcher,LAD,P,712,2810,96.3,99.1,48.0,13.9,32.4,6.9,65.4,49.8,62.1,15.2,17.8,34.0,27.0,15.0,10.0\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "source": "baseball_savant",
                    "seasons": {
                        "current": {
                            "year": 2025,
                            "files": {
                                "roster": "roster_2025.csv",
                                "hitters": "hitters_2025.csv",
                                "pitchers": "pitchers_2025.csv",
                            },
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        result = main([
            "ingest-rate",
            str(manifest_path),
            "--structured-output",
            str(structured_path),
        ])

        self.assertEqual(result, 0)
        self.assertTrue((structured_path / "NL" / "East" / "NYM.json").exists())
        self.assertTrue((structured_path / "NL" / "West" / "LAD.json").exists())
        index_payload = json.loads((structured_path / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index_payload["NL"]["East"][0]["team"], "NYM")
        self.assertEqual(index_payload["NL"]["West"][0]["team"], "LAD")

    def _rating(self, name: str, team: str) -> RatingOutput:
        return RatingOutput(
            name=name,
            role="hitter",
            team=team,
            primary_position="CF",
            ratings={"power": 80},
            percentiles={"power": 75.0},
            overall_numeric=80,
            overall_grade="B+",
            confidence="high",
            review_flags=[],
            suggested_traits=[],
            assigned_traits=[],
            recommended_personalities=[],
        )


if __name__ == "__main__":
    unittest.main()