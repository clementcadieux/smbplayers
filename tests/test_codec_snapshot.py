from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.codec import build_canonical_snapshot_payload


class CodecSnapshotTests(unittest.TestCase):
    def test_build_canonical_snapshot_payload_from_teams_shape(self) -> None:
        decoded_payload = {
            "teams": [
                {
                    "team": "TOR",
                    "roster": [
                        {
                            "slot_type": "sp1",
                            "player": {
                                "player_id": "101",
                                "name": "Starter A",
                                "role": "pitcher",
                                "ratings": {"velocity": 90},
                            },
                        }
                    ],
                }
            ],
            "free_agents": [
                {
                    "player": {
                        "player_id": "201",
                        "name": "Free Agent",
                        "role": "hitter",
                        "ratings": {"contact": 80},
                    }
                }
            ],
        }

        canonical = build_canonical_snapshot_payload(decoded_payload)

        self.assertEqual(canonical["schema_version"], "v1")
        self.assertEqual(canonical["teams"][0]["team"], "TOR")
        self.assertEqual(canonical["teams"][0]["roster"][0]["slot_type"], "sp1")
        self.assertEqual(canonical["teams"][0]["roster"][0]["attributes"]["velocity"], 90)
        self.assertEqual(canonical["free_agents"][0]["player_id"], "201")

    def test_build_canonical_snapshot_payload_from_rosters_object_shape(self) -> None:
        decoded_payload = {
            "rosters": {
                "TOR": {
                    "sp1": {
                        "player_id": "101",
                        "player_name": "Starter A",
                        "role": "pitcher",
                        "attributes": {"velocity": 90},
                    }
                }
            },
            "freeAgents": [
                {
                    "player_id": "201",
                    "name": "Free Agent",
                    "role_hint": "hitter",
                    "attributes": {"contact": 80},
                }
            ],
        }

        canonical = build_canonical_snapshot_payload(decoded_payload)

        self.assertEqual(canonical["teams"][0]["team"], "TOR")
        self.assertEqual(canonical["teams"][0]["roster"][0]["slot_type"], "sp1")
        self.assertEqual(canonical["free_agents"][0]["name"], "Free Agent")

    def test_cli_build_canonical_snapshot_writes_output(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            decoded_path = root / "decoded_snapshot.json"
            output_path = root / "canonical_snapshot.json"

            decoded_path.write_text(
                json.dumps(
                    {
                        "teams": [
                            {
                                "team": "TOR",
                                "roster": [
                                    {
                                        "slot_type": "sp1",
                                        "player": {
                                            "player_id": "101",
                                            "name": "Starter A",
                                            "role": "pitcher",
                                            "ratings": {"velocity": 90},
                                        },
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

            result = main(["build-canonical-snapshot", str(decoded_path), str(output_path)])

            self.assertEqual(result, 0)
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "v1")
            self.assertEqual(payload["teams"][0]["team"], "TOR")


if __name__ == "__main__":
    unittest.main()
