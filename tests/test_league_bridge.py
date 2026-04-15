from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.league_bridge import DEFAULT_LEAGUE_FOLDER, build_roster_attribute_bridge


class LeagueBridgeTests(unittest.TestCase):
    def test_build_bridge_uses_base_roster_and_derives_free_agents(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            roster_path = root / "league_roster.json"
            reports_dir = root / "team_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            roster_path.write_text(
                json.dumps(
                    {
                        "teams": [
                            {
                                "team": "TOR",
                                "recommended_roster": [
                                    {
                                        "position_group": "IF",
                                        "slot_type": "if1",
                                        "player": {
                                            "player_id": "101",
                                            "name": "Rostered Player",
                                            "role": "hitter",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (reports_dir / "TOR_hitters.csv").write_text(
                "player_id,Name,Contact,Power\n"
                "101,Rostered Player,70,60\n"
                "202,Extra Player,80,75\n",
                encoding="utf-8",
            )
            (reports_dir / "TOR_pitchers.csv").write_text(
                "player_id,Name,Velocity,Junk,Accuracy\n"
                "303,TOR Pitcher,65,64,63\n",
                encoding="utf-8",
            )

            payload = build_roster_attribute_bridge(roster_path, reports_dir)

            self.assertEqual(payload["league_folder"], str(DEFAULT_LEAGUE_FOLDER))
            self.assertEqual(payload["teams"][0]["team"], "TOR")
            self.assertEqual(len(payload["teams"][0]["roster"]), 1)
            roster_slot = payload["teams"][0]["roster"][0]
            self.assertEqual(roster_slot["player_id"], "101")
            self.assertIsInstance(roster_slot["attributes"], dict)
            self.assertEqual({item["player_id"] for item in payload["free_agents"]}, {"202", "303"})

    def test_team_report_requires_player_id_column(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            roster_path = root / "league_roster.json"
            reports_dir = root / "team_reports"
            reports_dir.mkdir(parents=True, exist_ok=True)

            roster_path.write_text(
                json.dumps(
                    {
                        "teams": [
                            {
                                "team": "TOR",
                                "recommended_roster": [
                                    {
                                        "position_group": "IF",
                                        "slot_type": "if1",
                                        "player": {
                                            "player_id": "101",
                                            "name": "Rostered Player",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (reports_dir / "TOR_hitters.csv").write_text("Name,Contact,Power\nRostered Player,70,60\n", encoding="utf-8")
            (reports_dir / "TOR_pitchers.csv").write_text("player_id,Name\n999,Pitcher\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "missing required player_id column"):
                build_roster_attribute_bridge(roster_path, reports_dir)

    def test_cli_bridge_supports_league_folder_override(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            roster_path = root / "league_roster.json"
            reports_dir = root / "team_reports"
            output_path = root / "bridge.json"
            override_path = root / "league_root"
            override_path.mkdir(parents=True, exist_ok=True)
            reports_dir.mkdir(parents=True, exist_ok=True)

            roster_path.write_text(
                json.dumps(
                    {
                        "teams": [
                            {
                                "team": "TOR",
                                "recommended_roster": [
                                    {
                                        "position_group": "IF",
                                        "slot_type": "if1",
                                        "player": {
                                            "player_id": "101",
                                            "name": "Rostered Player",
                                            "role": "hitter",
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (reports_dir / "TOR_hitters.csv").write_text(
                "player_id,Name,Contact,Power\n"
                "101,Rostered Player,70,60\n",
                encoding="utf-8",
            )
            (reports_dir / "TOR_pitchers.csv").write_text("player_id,Name\n999,Pitcher\n", encoding="utf-8")

            result = main(
                [
                    "build-roster-bridge",
                    str(roster_path),
                    str(reports_dir),
                    str(output_path),
                    "--league-folder",
                    str(override_path),
                ]
            )

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["league_folder"], str(override_path))


if __name__ == "__main__":
    unittest.main()
