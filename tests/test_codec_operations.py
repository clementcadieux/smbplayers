from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.codec import build_encoder_operation_plan


class CodecOperationPlanTests(unittest.TestCase):
    def test_build_encoder_plan_orders_team_slots_then_free_agents(self) -> None:
        codec_import = {
            "codec_version": "v1",
            "league_folder": "C:/game/league",
            "source": {
                "bridge_payload": "export/league_bridge.json",
                "league_roster": "export/league_roster.json",
                "team_reports": "team_reports",
            },
            "records": [
                {
                    "player_id": "202",
                    "player_name": "Zed Free Agent",
                    "target_pool": "free_agent",
                    "team": None,
                    "slot_type": None,
                    "position_group": None,
                    "role": "hitter",
                    "attributes": {"contact": 80},
                    "attribute_source": "TOR_hitters.csv",
                },
                {
                    "player_id": "101",
                    "player_name": "Starter A",
                    "target_pool": "team",
                    "team": "TOR",
                    "slot_type": "sp2",
                    "position_group": "SP",
                    "role": "pitcher",
                    "attributes": {"velocity": 90},
                    "attribute_source": "TOR_pitchers.csv",
                },
                {
                    "player_id": "102",
                    "player_name": "Starter B",
                    "target_pool": "team",
                    "team": "TOR",
                    "slot_type": "sp1",
                    "position_group": "SP",
                    "role": "pitcher",
                    "attributes": {"velocity": 91},
                    "attribute_source": "TOR_pitchers.csv",
                },
                {
                    "player_id": "201",
                    "player_name": "Alpha Free Agent",
                    "target_pool": "free_agent",
                    "team": None,
                    "slot_type": None,
                    "position_group": None,
                    "role": "pitcher",
                    "attributes": {"velocity": 70},
                    "attribute_source": "TOR_pitchers.csv",
                },
            ],
            "warnings": ["example warning"],
        }

        plan = build_encoder_operation_plan(codec_import)

        self.assertEqual(plan["plan_version"], "v1")
        self.assertEqual(plan["stats"]["team_operations"], 2)
        self.assertEqual(plan["stats"]["free_agent_operations"], 2)
        self.assertEqual(plan["stats"]["total_operations"], 4)

        operation_ids = [item["operation_id"] for item in plan["operations"]]
        self.assertEqual(
            operation_ids,
            [
                "team:TOR:sp1:102",
                "team:TOR:sp2:101",
                "free_agent:201",
                "free_agent:202",
            ],
        )

    def test_build_encoder_plan_rejects_invalid_target_pool(self) -> None:
        codec_import = {
            "codec_version": "v1",
            "league_folder": "C:/game/league",
            "source": {
                "bridge_payload": "export/league_bridge.json",
                "league_roster": "export/league_roster.json",
                "team_reports": "team_reports",
            },
            "records": [
                {
                    "player_id": "101",
                    "player_name": "Unknown",
                    "target_pool": "waivers",
                    "team": None,
                    "slot_type": None,
                    "position_group": None,
                    "role": "hitter",
                    "attributes": {},
                    "attribute_source": "TOR_hitters.csv",
                }
            ],
            "warnings": [],
        }

        with self.assertRaisesRegex(ValueError, "unsupported target_pool"):
            build_encoder_operation_plan(codec_import)

    def test_cli_build_encoder_plan_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            codec_import_path = root / "codec_import.json"
            output_path = root / "encoder_plan.json"

            codec_import_path.write_text(
                json.dumps(
                    {
                        "codec_version": "v1",
                        "league_folder": "C:/game/league",
                        "source": {
                            "bridge_payload": "export/league_bridge.json",
                            "league_roster": "export/league_roster.json",
                            "team_reports": "team_reports",
                        },
                        "records": [
                            {
                                "player_id": "101",
                                "player_name": "Starter A",
                                "target_pool": "team",
                                "team": "TOR",
                                "slot_type": "sp1",
                                "position_group": "SP",
                                "role": "pitcher",
                                "attributes": {"velocity": 90},
                                "attribute_source": "TOR_pitchers.csv",
                            }
                        ],
                        "warnings": [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = main(["build-encoder-plan", str(codec_import_path), str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["stats"]["total_operations"], 1)
            self.assertEqual(payload["operations"][0]["operation_id"], "team:TOR:sp1:101")


if __name__ == "__main__":
    unittest.main()
