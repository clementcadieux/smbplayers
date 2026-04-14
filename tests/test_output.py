from __future__ import annotations

import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        self.assertEqual([item["name"] for item in bos_payload["players"]], ["Red Sox 1", "Red Sox 2"])
        self.assertIn("recommended_roster", bos_payload)

        cle_payload = json.loads((output_dir / "AL" / "Central" / "CLE.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in cle_payload["players"]], ["Guardians 1"])

        lad_payload = json.loads((output_dir / "NL" / "West" / "LAD.json").read_text(encoding="utf-8"))
        self.assertEqual([item["name"] for item in lad_payload["players"]], ["Dodgers 1"])

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

    def test_cli_refresh_bluejays_example_builds_local_live_example_outputs(self) -> None:
        with patch("smb4_mlb_ratings.cli.fetch_team_players", return_value=self._live_bluejays_players()) as fetch_mock:
            result = main([
                "refresh-bluejays-example",
                "--example-root",
                str(self.root),
            ])

        self.assertEqual(result, 0)

        manifest_path = self.root / "bluejays_mixed_manifest_concrete.json"
        normalized_path = self.root / "exports" / "bluejays_normalized_for_result_example.json"
        ratings_path = self.root / "bluejays_result_example.json"
        roster_path = self.root / "exports" / "bluejays_roster_report.json"
        structured_path = self.root / "exports" / "bluejays_structured_report" / "AL" / "East" / "TOR.json"

        self.assertTrue(manifest_path.exists())
        self.assertTrue(normalized_path.exists())
        self.assertTrue(ratings_path.exists())
        self.assertTrue(roster_path.exists())
        self.assertTrue(structured_path.exists())

        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertIn("previous", manifest_payload["seasons"])
        self.assertEqual(manifest_payload["seasons"]["current"]["year"], 2026)
        self.assertEqual(manifest_payload["seasons"]["previous"]["year"], 2025)

        self.assertTrue(fetch_mock.call_count >= 2)
        self.assertIsNone(fetch_mock.call_args_list[0].kwargs.get("ssl_context"))
        self.assertIsNone(fetch_mock.call_args_list[1].kwargs.get("ssl_context"))

        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        hitter = next(player for player in normalized_payload["players"] if player["role"] == "hitter")
        self.assertAlmostEqual(hitter["metrics"]["barrel_rate"]["current"], 0.114)
        self.assertAlmostEqual(hitter["metrics"]["avg_exit_velocity"]["current"], 91.7)
        self.assertAlmostEqual(hitter["metrics"]["sprint_speed"]["current"], 27.7)

        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        rated_hitter = next(player for player in ratings_payload if player["role"] == "hitter")
        review_flags = set(rated_hitter["review_flags"])
        self.assertTrue(all("avg_exit_velocity" not in flag for flag in review_flags))
        self.assertTrue(all("barrel_rate" not in flag for flag in review_flags))
        self.assertTrue(all("sprint_speed" not in flag for flag in review_flags))

    def test_cli_refresh_bluejays_example_insecure_flag_uses_unverified_ssl_context(self) -> None:
        stderr_buffer = io.StringIO()
        with patch("smb4_mlb_ratings.cli.fetch_team_players", return_value=self._live_bluejays_players()) as fetch_mock, patch(
            "sys.stderr", new=stderr_buffer
        ), patch("smb4_mlb_ratings.cli.run_ingest_rate", return_value=0), patch(
            "smb4_mlb_ratings.cli.run_rank", return_value=0
        ):
            result = main([
                "refresh-bluejays-example",
                "--example-root",
                str(self.root),
                "--insecure",
            ])

        self.assertEqual(result, 0)
        self.assertIn("insecure SSL mode", stderr_buffer.getvalue())
        self.assertTrue(fetch_mock.call_count >= 2)
        self.assertIsNotNone(fetch_mock.call_args_list[0].kwargs.get("ssl_context"))
        self.assertIsNotNone(fetch_mock.call_args_list[1].kwargs.get("ssl_context"))

    def _rating(self, name: str, team: str) -> RatingOutput:
        return RatingOutput(
            name=name,
            role="hitter",
            team=team,
            primary_position="CF",
            bats=None,
            throws=None,
            ratings={"power": 80},
            percentiles={"power": 75.0},
            overall_numeric=80,
            overall_grade="B+",
            confidence="high",
            review_flags=[],
            suggested_traits=[],
            assigned_traits=[],
            recommended_personalities=[],
            secondary_position=None,
            age=26,
            projected_pa=500.0,
            projected_ip=None,
            metadata={},
        )

    def _live_bluejays_players(self) -> list[dict[str, object]]:
        return [
            {
                "player_id": 680718,
                "name": "Addison Barger",
                "team": "TOR",
                "type": "hitter",
                "position": "3B",
                "status": "Active",
                "status_code": "A",
                "age": 26,
                "bats": "L",
                "throws": "R",
                "days_on_roster": 167,
                "plate_appearances": 502,
                "at_bats": 460,
                "hits": 112,
                "doubles": 32,
                "triples": 1,
                "home_runs": 21,
                "walks": 36,
                "strikeouts": 121,
                "hit_by_pitch": 3,
                "stolen_bases": 4,
                "caught_stealing": 1,
                "avg": "0.243",
                "obp": "0.301",
                "slg": "0.454",
                "advanced_hitting": {"iso": "0.211", "totalSwings": 700, "swingAndMisses": 182},
                "savant_hitting_summary": {
                    "zone_contact_pct": 82.0,
                    "out_of_zone_contact_pct": 55.6,
                    "avg_exit_velocity": 91.7,
                    "barrel_rate": 11.4,
                    "sprint_speed": 27.7,
                },
                "situational_hitting_metrics": {
                    "first_pitch_hitting": 72.0,
                    "risp_hitting": 76.0,
                    "pressure_hitting": 67.0,
                    "late_game_hitting": 64.0,
                    "trailing_bases_empty_hitting": 61.0,
                },
                "hitting_handedness_splits": {
                    "vl": {"avg": 0.300, "iso": 0.250, "strikeout_rate": 0.18},
                    "vr": {"avg": 0.230, "iso": 0.180, "strikeout_rate": 0.27},
                },
                "fielding_stats": {
                    "innings": "613.1",
                    "fielding": "0.966",
                    "putOuts": 45,
                    "assists": 88,
                    "errors": 5,
                    "outsAboveAverage": 2,
                    "defensiveRunsSaved": 1,
                    "uzr": 0.5,
                    "armStrength": 96.5,
                },
            },
            {
                "player_id": 670102,
                "name": "Bowden Francis",
                "team": "TOR",
                "type": "pitcher",
                "position": "P",
                "status": "Active",
                "status_code": "A",
                "age": 29,
                "bats": "R",
                "throws": "R",
                "days_on_roster": 176,
                "batters_faced": 684,
                "walks": 54,
                "strikeouts": 179,
                "home_runs": 22,
                "hits": 141,
                "innings_pitched": "168.0",
                "number_of_pitches": 2718,
                "strikes": 1764,
                "strike_percentage": "64.9",
                "stolen_bases": 9,
                "caught_stealing": 5,
                "pickoffs": 1,
                "stolenBasePercentage": "64.3",
                "advanced_pitching": {"whiffPercentage": 0.144},
                "situational_pitching_metrics": {
                    "first_pitch_pitching": 78.0,
                    "runners_on_pitching": 73.5,
                    "pressure_pitching": 80.5,
                    "three_ball_accuracy": 58.0,
                    "steal_suppression": 59.2,
                },
                "pitching_handedness_splits": {
                    "vr": {"ops": 0.610, "strikeout_rate": 0.290},
                    "vl": {"ops": 0.740, "strikeout_rate": 0.220},
                },
                "pitch_arsenal": {
                    "FF": {"percentage": 0.56, "averageSpeed": 92.4},
                    "SI": {"percentage": 0.02, "averageSpeed": 91.2},
                    "SL": {"percentage": 0.22, "averageSpeed": 84.5},
                    "CU": {"percentage": 0.14, "averageSpeed": 79.4},
                },
                "savant_pitch_details": {
                    "FF": {"xba": 0.220, "xwoba": 0.300, "xslg": 0.360, "hard_hit_percent": 33.0, "brl_percent": 6.0, "swings": 300.0, "misses": 80.0, "release_speed": 92.4, "pitches": 420.0, "total_pitches": 1000.0},
                    "SL": {"xba": 0.180, "xwoba": 0.240, "xslg": 0.280, "hard_hit_percent": 24.0, "brl_percent": 3.0, "swings": 220.0, "misses": 90.0, "release_speed": 84.5, "pitches": 310.0, "total_pitches": 1000.0},
                },
            },
        ]


if __name__ == "__main__":
    unittest.main()