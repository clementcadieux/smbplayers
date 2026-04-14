from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.codec import build_dry_run_patch_preview


class CodecDryRunTests(unittest.TestCase):
    def test_build_dry_run_patch_preview_groups_by_file_target(self) -> None:
        encoder_plan = {
            "plan_version": "v1",
            "codec_version": "v1",
            "league_folder": "C:/game/league",
            "source": {
                "codec_import": "export/codec_import.json",
                "league_roster": "export/league_roster.json",
                "team_reports": "team_reports",
            },
            "operations": [
                {
                    "operation_type": "upsert_team_slot",
                    "operation_id": "team:TOR:sp1:101",
                    "target": {
                        "pool": "team",
                        "team": "TOR",
                        "slot_type": "sp1",
                        "position_group": "SP",
                    },
                    "player": {
                        "player_id": "101",
                        "player_name": "Starter A",
                        "role": "pitcher",
                    },
                    "attributes": {"velocity": 90, "junk": 70},
                    "attribute_source": "TOR_pitchers.csv",
                },
                {
                    "operation_type": "upsert_free_agent",
                    "operation_id": "free_agent:201",
                    "target": {
                        "pool": "free_agent",
                    },
                    "player": {
                        "player_id": "201",
                        "player_name": "Free Agent",
                        "role": "hitter",
                    },
                    "attributes": {"contact": 80},
                    "attribute_source": "TOR_hitters.csv",
                },
            ],
            "warnings": ["sample warning"],
        }

        report = build_dry_run_patch_preview(encoder_plan)

        self.assertEqual(report["mode"], "dry_run")
        self.assertFalse(report["writes_binary_data"])
        self.assertEqual(report["summary"]["total_operations"], 2)
        self.assertEqual(report["summary"]["files_touched"], 2)
        self.assertEqual(report["summary"]["teams_touched"], 1)
        self.assertEqual(report["warnings"], ["sample warning"])

        file_targets = [item["file_target"] for item in report["files"]]
        self.assertIn("league_data/teams/TOR/roster.bin", file_targets)
        self.assertIn("league_data/free_agents.bin", file_targets)

    def test_build_dry_run_patch_preview_rejects_unknown_operation_type(self) -> None:
        encoder_plan = {
            "plan_version": "v1",
            "codec_version": "v1",
            "league_folder": "C:/game/league",
            "source": {},
            "operations": [
                {
                    "operation_type": "delete_player",
                    "operation_id": "bad:1",
                    "target": {},
                    "player": {
                        "player_id": "1",
                        "player_name": "Bad",
                    },
                }
            ],
            "warnings": [],
        }

        with self.assertRaisesRegex(ValueError, "unsupported operation_type"):
            build_dry_run_patch_preview(encoder_plan)

    def test_build_dry_run_patch_preview_with_current_snapshot_adds_concrete_diffs(self) -> None:
        encoder_plan = {
            "plan_version": "v1",
            "codec_version": "v1",
            "league_folder": "C:/game/league",
            "source": {},
            "operations": [
                {
                    "operation_type": "upsert_team_slot",
                    "operation_id": "team:TOR:sp1:101",
                    "target": {
                        "pool": "team",
                        "team": "TOR",
                        "slot_type": "sp1",
                        "position_group": "SP",
                    },
                    "player": {
                        "player_id": "101",
                        "player_name": "Starter A",
                        "role": "pitcher",
                    },
                    "attributes": {"velocity": 90, "junk": 70},
                    "attribute_source": "TOR_pitchers.csv",
                },
                {
                    "operation_type": "upsert_free_agent",
                    "operation_id": "free_agent:201",
                    "target": {
                        "pool": "free_agent",
                    },
                    "player": {
                        "player_id": "201",
                        "player_name": "Free Agent",
                        "role": "hitter",
                    },
                    "attributes": {"contact": 80},
                    "attribute_source": "TOR_hitters.csv",
                },
            ],
            "warnings": [],
        }
        current_snapshot = {
            "teams": [
                {
                    "team": "TOR",
                    "roster": [
                        {
                            "slot_type": "sp1",
                            "player_id": "101",
                            "player_name": "Starter A",
                            "role": "pitcher",
                            "attributes": {"velocity": 80, "junk": 70},
                        }
                    ],
                }
            ],
            "free_agents": [
                {
                    "player_id": "201",
                    "name": "Free Agent",
                    "role_hint": "hitter",
                    "attributes": {"contact": 80},
                }
            ],
        }

        report = build_dry_run_patch_preview(encoder_plan, current_snapshot_payload=current_snapshot)

        self.assertEqual(report["summary"]["concrete_before_states"], 2)
        self.assertEqual(report["summary"]["missing_before_states"], 0)
        self.assertEqual(report["summary"]["changed_operations"], 1)
        all_operations = [op for file_entry in report["files"] for op in file_entry["operations"]]
        starter_operation = next(op for op in all_operations if op["operation_id"] == "team:TOR:sp1:101")
        self.assertIsInstance(starter_operation["before_state"], dict)
        self.assertTrue(starter_operation["diff"]["has_changes"])
        self.assertEqual(starter_operation["diff"]["attribute_changes"][0]["key"], "velocity")

    def test_cli_build_dry_run_report_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            plan_path = root / "encoder_plan.json"
            output_path = root / "dry_run_report.json"

            plan_path.write_text(
                json.dumps(
                    {
                        "plan_version": "v1",
                        "codec_version": "v1",
                        "league_folder": "C:/game/league",
                        "source": {
                            "codec_import": "export/codec_import.json",
                            "league_roster": "export/league_roster.json",
                            "team_reports": "team_reports",
                        },
                        "operations": [
                            {
                                "operation_type": "upsert_team_slot",
                                "operation_id": "team:TOR:sp1:101",
                                "target": {
                                    "pool": "team",
                                    "team": "TOR",
                                    "slot_type": "sp1",
                                    "position_group": "SP",
                                },
                                "player": {
                                    "player_id": "101",
                                    "player_name": "Starter A",
                                    "role": "pitcher",
                                },
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

            result = main(["build-dry-run-report", str(plan_path), str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["total_operations"], 1)
            self.assertEqual(payload["files"][0]["operation_count"], 1)

    def test_cli_build_dry_run_report_with_current_snapshot_writes_concrete_before_states(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            plan_path = root / "encoder_plan.json"
            snapshot_path = root / "current_snapshot.json"
            output_path = root / "dry_run_report.json"

            plan_path.write_text(
                json.dumps(
                    {
                        "plan_version": "v1",
                        "codec_version": "v1",
                        "league_folder": "C:/game/league",
                        "source": {},
                        "operations": [
                            {
                                "operation_type": "upsert_team_slot",
                                "operation_id": "team:TOR:sp1:101",
                                "target": {
                                    "pool": "team",
                                    "team": "TOR",
                                    "slot_type": "sp1",
                                    "position_group": "SP",
                                },
                                "player": {
                                    "player_id": "101",
                                    "player_name": "Starter A",
                                    "role": "pitcher",
                                },
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
            snapshot_path.write_text(
                json.dumps(
                    {
                        "teams": [
                            {
                                "team": "TOR",
                                "roster": [
                                    {
                                        "slot_type": "sp1",
                                        "player_id": "101",
                                        "player_name": "Starter A",
                                        "role": "pitcher",
                                        "attributes": {"velocity": 80},
                                    }
                                ],
                            }
                        ],
                        "free_agents": [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            result = main(
                [
                    "build-dry-run-report",
                    str(plan_path),
                    str(output_path),
                    "--current-snapshot",
                    str(snapshot_path),
                ]
            )

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"]["concrete_before_states"], 1)
            self.assertEqual(payload["summary"]["changed_operations"], 1)


if __name__ == "__main__":
    unittest.main()
