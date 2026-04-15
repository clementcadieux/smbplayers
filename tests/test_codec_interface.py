from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.codec import build_codec_import_payload


class CodecInterfaceTests(unittest.TestCase):
    def test_build_codec_import_payload_from_bridge(self) -> None:
        bridge_payload = {
            "league_folder": "C:/game/league",
            "source": {
                "league_roster": "export/league_roster.json",
                "team_reports": "team_reports",
            },
            "teams": [
                {
                    "team": "TOR",
                    "roster": [
                        {
                            "slot_type": "if1",
                            "position_group": "IF",
                            "player_id": "101",
                            "player_name": "Rostered",
                            "role": "hitter",
                            "attributes": {"contact": 70},
                            "attribute_source": "TOR_hitters.csv",
                        }
                    ],
                }
            ],
            "free_agents": [
                {
                    "player_id": "202",
                    "name": "Free Agent",
                    "team": "TOR",
                    "role_hint": "pitcher",
                    "attributes": {"velocity": 80},
                    "attribute_source": "TOR_pitchers.csv",
                }
            ],
            "warnings": [],
        }

        payload = build_codec_import_payload(bridge_payload)

        self.assertEqual(payload["codec_version"], "v1")
        self.assertEqual(payload["stats"]["team_records"], 1)
        self.assertEqual(payload["stats"]["free_agent_records"], 1)
        self.assertEqual(payload["stats"]["total_records"], 2)
        self.assertEqual(payload["records"][0]["target_pool"], "team")
        self.assertEqual(payload["records"][1]["target_pool"], "free_agent")

    def test_build_codec_import_payload_rejects_duplicate_ids(self) -> None:
        bridge_payload = {
            "league_folder": "C:/game/league",
            "source": {
                "league_roster": "export/league_roster.json",
                "team_reports": "team_reports",
            },
            "teams": [
                {
                    "team": "TOR",
                    "roster": [
                        {
                            "slot_type": "if1",
                            "position_group": "IF",
                            "player_id": "101",
                            "player_name": "Rostered",
                            "role": "hitter",
                            "attributes": {},
                            "attribute_source": "TOR_hitters.csv",
                        }
                    ],
                }
            ],
            "free_agents": [
                {
                    "player_id": "101",
                    "name": "Also Free Agent",
                    "team": "TOR",
                    "role_hint": "hitter",
                    "attributes": {},
                    "attribute_source": "TOR_hitters.csv",
                }
            ],
            "warnings": [],
        }

        with self.assertRaisesRegex(ValueError, "duplicate player_id"):
            build_codec_import_payload(bridge_payload)

    def test_cli_build_codec_interface_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            bridge_path = root / "league_bridge.json"
            output_path = root / "codec_import.json"
            override_folder = root / "custom_league"
            override_folder.mkdir(parents=True, exist_ok=True)

            bridge_path.write_text(
                json.dumps(
                    {
                        "league_folder": "C:/game/league",
                        "source": {
                            "league_roster": "export/league_roster.json",
                            "team_reports": "team_reports",
                        },
                        "teams": [
                            {
                                "team": "TOR",
                                "roster": [
                                    {
                                        "slot_type": "if1",
                                        "position_group": "IF",
                                        "player_id": "101",
                                        "player_name": "Rostered",
                                        "role": "hitter",
                                        "attributes": {"contact": 70},
                                        "attribute_source": "TOR_hitters.csv",
                                    }
                                ],
                            }
                        ],
                        "free_agents": [],
                        "warnings": ["example warning"],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = main(
                [
                    "build-codec-interface",
                    str(bridge_path),
                    str(output_path),
                    "--league-folder",
                    str(override_folder),
                ]
            )

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["league_folder"], str(override_folder))
            self.assertEqual(payload["stats"]["total_records"], 1)
            self.assertEqual(payload["warnings"], ["example warning"])


if __name__ == "__main__":
    unittest.main()
