"""
Tests for the SMB4 .sav codec: sav_io, encoder, decoder, and CLI integration.

A synthetic .sav fixture is built programmatically for each test:
  1. Create an in-memory SQLite DB with the required schema.
  2. Save to a temp .sqlite file.
  3. Compress with zlib (matching SMB4's DEFLATE format) to produce a .sav.

No real save files are required.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zlib
from pathlib import Path

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.codec.decoder import decode_sav
from smb4_mlb_ratings.codec.encoder import apply_encoder_plan
from smb4_mlb_ratings.codec.sav_io import compress_sav, decompress_sav


# ──────────────────────────────────────────────────────────────────────────────
# Fixture constants
# ──────────────────────────────────────────────────────────────────────────────

# 16-byte GUID blobs used in fixtures (arbitrary non-zero values)
_TEAM_GUID   = b"\x01" * 16
_PLAYER_GUID = b"\x02" * 16

# DDL for all tables and views required by the codec.
# v_baseball_player_info is backed by a simple t_player_names table.
_DDL = """
CREATE TABLE t_teams (
    GUID     BLOB PRIMARY KEY,
    teamName TEXT NOT NULL
);

CREATE TABLE t_baseball_players (
    GUID       BLOB    PRIMARY KEY,
    power      INTEGER NOT NULL DEFAULT 50,
    contact    INTEGER NOT NULL DEFAULT 50,
    speed      INTEGER NOT NULL DEFAULT 50,
    fielding   INTEGER NOT NULL DEFAULT 50,
    arm        INTEGER NOT NULL DEFAULT 50,
    velocity   INTEGER NOT NULL DEFAULT 50,
    junk       INTEGER NOT NULL DEFAULT 50,
    accuracy   INTEGER NOT NULL DEFAULT 50,
    teamGUID   BLOB
);

CREATE TABLE t_baseball_player_local_ids (
    localID INTEGER PRIMARY KEY AUTOINCREMENT,
    GUID    BLOB    NOT NULL UNIQUE
);

CREATE TABLE t_baseball_player_options (
    baseballPlayerLocalID INTEGER NOT NULL,
    optionKey             INTEGER NOT NULL,
    optionValue           INTEGER NOT NULL DEFAULT 0,
    optionType            INTEGER NOT NULL DEFAULT 0,
    UNIQUE(baseballPlayerLocalID, optionKey)
);

CREATE TABLE t_baseball_player_traits (
    baseballPlayerLocalID INTEGER NOT NULL,
    trait                 INTEGER NOT NULL,
    subType               INTEGER NOT NULL
);

CREATE TABLE t_player_names (
    GUID            BLOB PRIMARY KEY,
    firstName       TEXT,
    lastName        TEXT,
    primaryPosition INTEGER DEFAULT 2,
    pitcherRole     INTEGER DEFAULT 0
);

CREATE VIEW v_baseball_player_info AS
    SELECT firstName,
           lastName,
           primaryPosition,
           pitcherRole,
           GUID AS baseballPlayerGUID
      FROM t_player_names;
"""


# ──────────────────────────────────────────────────────────────────────────────
# Fixture builder
# ──────────────────────────────────────────────────────────────────────────────

def _make_sav_fixture(tmp_dir: Path, *, with_player: bool = True) -> Path:
    """
    Build a minimal SQLite database, optionally insert one rostered player, then
    DEFLATE-compress it as *tmp_dir/test.sav* and return that path.
    """
    db_path = tmp_dir / "fixture.sqlite"

    conn = sqlite3.connect(str(db_path))
    conn.executescript(_DDL)

    if with_player:
        conn.execute(
            "INSERT INTO t_teams (GUID, teamName) VALUES (?, ?)",
            (_TEAM_GUID, "Test Team"),
        )

        conn.execute(
            "INSERT INTO t_baseball_player_local_ids (GUID) VALUES (?)",
            (_PLAYER_GUID,),
        )
        local_id = conn.execute(
            "SELECT localID FROM t_baseball_player_local_ids WHERE GUID = ?",
            (_PLAYER_GUID,),
        ).fetchone()[0]

        conn.execute(
            "INSERT INTO t_baseball_players "
            "(GUID, power, contact, speed, fielding, arm, velocity, junk, accuracy, teamGUID) "
            "VALUES (?, 70, 65, 60, 55, 50, 0, 0, 0, ?)",
            (_PLAYER_GUID, _TEAM_GUID),
        )

        conn.execute(
            "INSERT INTO t_player_names (GUID, firstName, lastName, primaryPosition, pitcherRole) "
            "VALUES (?, ?, ?, ?, ?)",
            (_PLAYER_GUID, "Test", "Player", 2, 0),  # primaryPosition 2 = C
        )

        # Required INNER JOINs in the decoder: THROWING_HAND (key=4) and BATTING_HAND (key=5)
        for opt_key, opt_val in [(4, 1), (5, 1)]:  # 1 = Right
            conn.execute(
                "INSERT INTO t_baseball_player_options "
                "(baseballPlayerLocalID, optionKey, optionValue, optionType) "
                "VALUES (?, ?, ?, 0)",
                (local_id, opt_key, opt_val),
            )

        conn.commit()

    conn.close()

    db_bytes = db_path.read_bytes()
    sav_path = tmp_dir / "test.sav"
    sav_path.write_bytes(zlib.compress(db_bytes))
    return sav_path


def _minimal_encoder_plan(player_name: str = "Test Player") -> dict:
    return {
        "plan_version": "v1",
        "operations": [
            {
                "operation_id": "team:XX:pos1:test",
                "operation_type": "upsert_team_slot",
                "player": {
                    "player_id": "0",
                    "player_name": player_name,
                    "role": "hitter",
                },
                "target": {"position_group": "C"},
                "attributes": {
                    "power":    80,
                    "contact":  75,
                    "speed":    60,
                    "fielding": 70,
                    "arm":      65,
                    "bat_hand":  "R",
                    "throw_hand": "R",
                    "primary_position": "C",
                },
            }
        ],
    }


# ──────────────────────────────────────────────────────────────────────────────
# sav_io tests
# ──────────────────────────────────────────────────────────────────────────────

class SavIOTests(unittest.TestCase):
    def test_decompress_recompress_roundtrip(self):
        """decompress_sav → compress_sav preserves the SQLite byte content."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=False)

            db_bytes = decompress_sav(sav_path)
            # SQLite magic header check
            self.assertTrue(
                db_bytes.startswith(b"SQLite format 3"),
                "Decompressed bytes should start with SQLite magic header",
            )

            out_path = tmp_dir / "roundtrip.sav"
            compress_sav(db_bytes, out_path)
            db_bytes_2 = decompress_sav(out_path)

            self.assertEqual(db_bytes, db_bytes_2)

    def test_decompress_sav_rejects_non_deflate(self):
        """decompress_sav raises ValueError when the first byte is not 0x78."""
        with tempfile.TemporaryDirectory() as tmp:
            bad_sav = Path(tmp) / "bad.sav"
            bad_sav.write_bytes(b"\xFF\xFE Not a zlib stream")
            with self.assertRaises(ValueError):
                decompress_sav(bad_sav)

    def test_decompress_empty_file_raises(self):
        """decompress_sav raises ValueError (not IndexError) on an empty file."""
        with tempfile.TemporaryDirectory() as tmp:
            empty = Path(tmp) / "empty.sav"
            empty.write_bytes(b"")
            with self.assertRaises(ValueError):
                decompress_sav(empty)


# ──────────────────────────────────────────────────────────────────────────────
# Encoder tests
# ──────────────────────────────────────────────────────────────────────────────

class EncoderTests(unittest.TestCase):
    def test_encoder_skips_unknown_player(self):
        """An op whose player_id and name don't exist in the DB is skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=False)

            plan = {
                "plan_version": "v1",
                "operations": [
                    {
                        "operation_id": "team:XX:sp1:9999",
                        "operation_type": "upsert_team_slot",
                        "player": {
                            "player_id": "9999999",
                            "player_name": "Nobody Exists",
                            "role": "pitcher",
                        },
                        "target": {"position_group": "SP"},
                        "attributes": {"velocity": 90, "junk": 70, "arsenal": "4-Seam Fastball"},
                    }
                ],
            }

            result = apply_encoder_plan(plan, sav_path, dry_run=True)

            self.assertEqual(result.skipped, 1)
            self.assertEqual(result.applied, 0)
            self.assertGreaterEqual(len(result.warnings), 1)

    def test_encoder_applies_to_known_player_by_name(self):
        """An op matching by player name is applied and returns applied=1."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=True)

            result = apply_encoder_plan(_minimal_encoder_plan("Test Player"), sav_path, dry_run=True)

            self.assertEqual(result.applied, 1)
            self.assertEqual(result.skipped, 0)

    def test_encoder_dry_run_does_not_modify_sav(self):
        """dry_run=True leaves the .sav file unchanged."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=True)
            original_bytes = sav_path.read_bytes()

            apply_encoder_plan(_minimal_encoder_plan("Test Player"), sav_path, dry_run=True)

            self.assertEqual(original_bytes, sav_path.read_bytes())

    def test_encoder_result_to_dict_has_expected_keys(self):
        """EncoderResult.to_dict() includes applied, skipped, total, warnings."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=True)

            result = apply_encoder_plan(_minimal_encoder_plan("Test Player"), sav_path, dry_run=True)
            d = result.to_dict()

            self.assertIn("applied", d)
            self.assertIn("skipped", d)
            self.assertIn("total", d)
            self.assertIn("warnings", d)
            self.assertEqual(d["total"], d["applied"] + d["skipped"])


# ──────────────────────────────────────────────────────────────────────────────
# Decoder tests
# ──────────────────────────────────────────────────────────────────────────────

class DecoderTests(unittest.TestCase):
    def test_decoder_returns_canonical_top_level_keys(self):
        """decode_sav returns a dict with schema_version, teams, free_agents."""
        with tempfile.TemporaryDirectory() as tmp:
            sav_path = _make_sav_fixture(Path(tmp), with_player=True)
            result = decode_sav(sav_path)

            self.assertIn("schema_version", result)
            self.assertIn("teams", result)
            self.assertIn("free_agents", result)
            self.assertEqual(result["schema_version"], "v1")

    def test_decoder_reads_team_and_player(self):
        """decode_sav returns the fixture team with one rostered player."""
        with tempfile.TemporaryDirectory() as tmp:
            sav_path = _make_sav_fixture(Path(tmp), with_player=True)
            result = decode_sav(sav_path)

            self.assertEqual(len(result["teams"]), 1)
            team = result["teams"][0]
            self.assertEqual(team["team"], "Test Team")
            self.assertEqual(len(team["roster"]), 1)

            entry = team["roster"][0]
            self.assertIn("player_name", entry)
            self.assertIn("attributes", entry)
            self.assertEqual(entry["player_name"], "Test Player")

    def test_decoder_player_attributes_match_fixture(self):
        """Decoded power/contact values match what was inserted in the fixture."""
        with tempfile.TemporaryDirectory() as tmp:
            sav_path = _make_sav_fixture(Path(tmp), with_player=True)
            result = decode_sav(sav_path)

            attrs = result["teams"][0]["roster"][0]["attributes"]
            self.assertEqual(attrs["power"],   70)
            self.assertEqual(attrs["contact"], 65)
            self.assertEqual(attrs["speed"],   60)
            self.assertEqual(attrs["fielding"], 55)

    def test_decoder_empty_sav_has_no_teams_or_free_agents(self):
        """A .sav with no rows produces empty teams and free_agents lists."""
        with tempfile.TemporaryDirectory() as tmp:
            sav_path = _make_sav_fixture(Path(tmp), with_player=False)
            result = decode_sav(sav_path)

            self.assertEqual(result["teams"], [])
            self.assertEqual(result["free_agents"], [])


# ──────────────────────────────────────────────────────────────────────────────
# CLI integration tests
# ──────────────────────────────────────────────────────────────────────────────

class CLIIntegrationTests(unittest.TestCase):
    def test_cli_decode_sav_writes_json_output(self):
        """decode-sav subcommand writes a valid JSON snapshot to the output path."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=True)
            out_path = tmp_dir / "decoded.json"

            try:
                main(["decode-sav", str(sav_path), str(out_path)])
            except SystemExit as exc:
                self.assertEqual(exc.code, 0, f"CLI exited with non-zero code {exc.code}")

            self.assertTrue(out_path.exists(), "Output JSON was not created")
            data = json.loads(out_path.read_text(encoding="utf-8"))
            self.assertIn("schema_version", data)
            self.assertIn("teams", data)

    def test_cli_encode_sav_dry_run_exits_zero(self):
        """encode-sav --dry-run exits zero given a valid plan and .sav fixture."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            sav_path = _make_sav_fixture(tmp_dir, with_player=True)
            plan_path = tmp_dir / "plan.json"
            plan_path.write_text(
                json.dumps(_minimal_encoder_plan("Test Player")), encoding="utf-8"
            )

            try:
                main(["encode-sav", str(plan_path), str(sav_path), "--dry-run"])
            except SystemExit as exc:
                self.assertEqual(exc.code, 0, f"CLI exited with non-zero code {exc.code}")


if __name__ == "__main__":
    unittest.main()
