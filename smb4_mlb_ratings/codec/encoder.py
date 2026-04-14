"""
Encoder: apply an encoder_plan.json operation plan to a SMB4 .sav file.

The encoder decompresses the .sav → opens the embedded SQLite DB → executes
UPDATE / UPSERT / DELETE+INSERT statements derived from each operation →
recompresses and overwrites the .sav.

Scope: UPDATE-only.  A player must already exist in the database (identified
by player_id GUID or by name fallback) for their attributes to be written.
Players not found are skipped with a warning in the summary.

Player-ID matching strategy
---------------------------
SMB4 stores players as UUID blobs.  The encoder_plan player_id values are
MLBAM integer IDs, which do not correspond to the game's GUIDs directly.
Two lookup paths are attempted in order:

1. GUID match  – if the DB contains a row in t_baseball_player_local_ids whose
   GUID bytes, when interpreted as a big-endian integer with only the first
   8 bytes, equal the player_id integer, the match succeeds.  This is only
   useful if players were previously imported by this pipeline with a
   predictable GUID scheme.

2. Name match  – if path 1 yields no result, the encoder falls back to a
   case-insensitive full-name search across v_baseball_player_info.  If
   exactly one match is found the GUID is used; if zero or multiple matches
   are found the player is skipped with a warning.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .db_mappings import (
    OPTION_KEYS,
    all_pitch_option_keys,
    arm_angle_to_int,
    batting_hand_to_int,
    chemistry_to_int,
    is_pitcher_role,
    option_type_for_key,
    parse_arsenal,
    pitch_role_to_int,
    position_to_int,
    throwing_hand_to_int,
    trait_name_to_ids,
)
from .sav_io import compress_sav, sav_to_temp_sqlite


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class EncoderResult:
    applied: int = 0
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "skipped": self.skipped,
            "total": self.applied + self.skipped,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

_UPSERT_OPTION_SQL = """
    INSERT INTO t_baseball_player_options
        (baseballPlayerLocalID, optionKey, optionValue, optionType)
    VALUES (
        (SELECT localID FROM t_baseball_player_local_ids WHERE GUID = ?),
        ?, ?, ?
    )
    ON CONFLICT (baseballPlayerLocalID, optionKey)
    DO UPDATE SET optionValue = excluded.optionValue,
                  optionType  = excluded.optionType
"""

_UPDATE_PLAYER_SQL = """
    UPDATE t_baseball_players
       SET power    = ?,
           contact  = ?,
           speed    = ?,
           fielding = ?,
           arm      = ?,
           velocity = ?,
           junk     = ?,
           accuracy = ?
     WHERE GUID = ?
"""

_DELETE_TRAITS_SQL = """
    DELETE FROM t_baseball_player_traits
     WHERE baseballPlayerLocalID = (
         SELECT localID FROM t_baseball_player_local_ids WHERE GUID = ?
     )
"""

_INSERT_TRAIT_SQL = """
    INSERT INTO t_baseball_player_traits (baseballPlayerLocalID, trait, subType)
    VALUES (
        (SELECT localID FROM t_baseball_player_local_ids WHERE GUID = ?),
        ?, ?
    )
"""

_FIND_BY_NAME_SQL = """
    SELECT p.GUID
      FROM t_baseball_players p
      JOIN t_baseball_player_local_ids lid ON lid.GUID = p.GUID
      JOIN v_baseball_player_info vbpi     ON vbpi.baseballPlayerGUID = lid.GUID
     WHERE lower(vbpi.firstName || ' ' || vbpi.lastName) = lower(?)
"""

_FIND_BY_GUID_SQL = """
    SELECT GUID FROM t_baseball_player_local_ids WHERE GUID = ?
"""


# ---------------------------------------------------------------------------
# GUID utilities
# ---------------------------------------------------------------------------


def _player_id_to_guid_blob(player_id: str | int) -> bytes | None:
    """
    Attempt to construct a 16-byte GUID blob from an MLBAM player_id integer.
    The convention used here: first 8 bytes = big-endian player_id integer,
    remaining 8 bytes = 0x00.  This only succeeds if the pipeline previously
    imported this player using the same convention.
    """
    try:
        pid = int(player_id)
    except (TypeError, ValueError):
        return None
    try:
        return pid.to_bytes(8, "big") + b"\x00" * 8
    except OverflowError:
        return None


def _find_player_guid(
    conn: sqlite3.Connection,
    player_id: str,
    player_name: str,
    result: EncoderResult,
) -> bytes | None:
    """
    Return the 16-byte GUID blob for the player, or None if not found.
    Tries GUID-from-player_id first, then name fallback.
    """
    guid_blob = _player_id_to_guid_blob(player_id)

    if guid_blob is not None:
        row = conn.execute(_FIND_BY_GUID_SQL, (guid_blob,)).fetchone()
        if row:
            return guid_blob

    # Name fallback
    rows = conn.execute(_FIND_BY_NAME_SQL, (player_name.strip(),)).fetchall()
    if len(rows) == 1:
        return bytes(rows[0][0])
    if len(rows) == 0:
        result.warnings.append(
            f"Player not found in DB (id={player_id!r}, name={player_name!r}); skipped"
        )
    else:
        result.warnings.append(
            f"Ambiguous name match for {player_name!r} (id={player_id!r}): "
            f"{len(rows)} rows found; skipped"
        )
    return None


# ---------------------------------------------------------------------------
# Per-player attribute application
# ---------------------------------------------------------------------------


def _int_attr(attrs: dict[str, Any], key: str, default: int = 0) -> int:
    val = attrs.get(key, default)
    try:
        return max(0, min(99, int(val)))
    except (TypeError, ValueError):
        return default


def _apply_player(
    conn: sqlite3.Connection,
    guid_blob: bytes,
    attrs: dict[str, Any],
    role: str | None,
    position_group: str | None,
    result: EncoderResult,
) -> bool:
    """
    Write all attributes for one player to the open SQLite connection.
    Returns True on success, False on failure.
    """
    pitcher = is_pitcher_role(position_group or role or "")

    # --- Core rating columns ---
    power    = _int_attr(attrs, "power")
    contact  = _int_attr(attrs, "contact")
    speed    = _int_attr(attrs, "speed")
    fielding = _int_attr(attrs, "fielding")
    arm      = _int_attr(attrs, "arm") if not pitcher else 0
    velocity = _int_attr(attrs, "velocity") if pitcher else 0
    junk     = _int_attr(attrs, "junk") if pitcher else 0
    accuracy = _int_attr(attrs, "accuracy") if pitcher else 0

    cursor = conn.execute(
        _UPDATE_PLAYER_SQL,
        (power, contact, speed, fielding, arm, velocity, junk, accuracy, guid_blob),
    )
    if cursor.rowcount == 0:
        result.warnings.append(
            f"UPDATE t_baseball_players affected 0 rows for GUID "
            f"{guid_blob.hex().upper()!r}"
        )
        return False

    # --- Options ---
    def upsert_option(option_key: int, value: int) -> None:
        conn.execute(
            _UPSERT_OPTION_SQL,
            (guid_blob, option_key, value, option_type_for_key(option_key)),
        )

    upsert_option(OPTION_KEYS["BATTING_HAND"], batting_hand_to_int(attrs.get("bat_hand", "R")))
    upsert_option(OPTION_KEYS["THROWING_HAND"], throwing_hand_to_int(attrs.get("throw_hand", "R")))
    upsert_option(OPTION_KEYS["CHEMISTRY"], chemistry_to_int(attrs.get("personality_type_recommendation", "")))

    arm_angle_str = attrs.get("arm_angle") or attrs.get("angle") or "Mid"
    upsert_option(OPTION_KEYS["ARM_ANGLE"], arm_angle_to_int(arm_angle_str))

    # Primary position + pitch role
    if pitcher:
        upsert_option(OPTION_KEYS["PRIMARY_POSITION"], 1)  # 1 = "P"
        pitch_role = pitch_role_to_int(position_group or role or "")
        if pitch_role:
            upsert_option(OPTION_KEYS["PITCH_POSITION"], pitch_role)
    else:
        primary_pos = attrs.get("primary_position") or position_group or ""
        upsert_option(OPTION_KEYS["PRIMARY_POSITION"], position_to_int(primary_pos))
        secondary_pos = attrs.get("secondary_position") or ""
        upsert_option(OPTION_KEYS["SECONDARY_POSITION"], position_to_int(secondary_pos))

    # Pitch types (all cleared to 0 first, then enabled pitches set to 1)
    arsenal_keys = parse_arsenal(attrs.get("arsenal") or "")
    for pitch_key in all_pitch_option_keys():
        upsert_option(pitch_key, 1 if pitch_key in arsenal_keys else 0)

    # --- Traits ---
    conn.execute(_DELETE_TRAITS_SQL, (guid_blob,))
    for trait_field in ("trait_1", "trait_2"):
        trait_name = attrs.get(trait_field) or ""
        if not trait_name or trait_name == "--":
            continue
        ids = trait_name_to_ids(trait_name)
        if ids is None:
            result.warnings.append(
                f"Unknown trait {trait_name!r} for GUID {guid_blob.hex().upper()!r}; skipped"
            )
            continue
        trait_id, subtype_id = ids
        conn.execute(_INSERT_TRAIT_SQL, (guid_blob, trait_id, subtype_id))

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def apply_encoder_plan(
    plan: dict[str, Any],
    sav_path: Path,
    *,
    dry_run: bool = False,
) -> EncoderResult:
    """
    Apply all operations in *plan* to the SMB4 .sav file at *sav_path*.

    Parameters
    ----------
    plan:
        A dict matching the ``encoder_plan.json`` schema produced by
        ``build_encoder_operation_plan``.
    sav_path:
        Path to the ``*.sav`` league file.  Modified in-place unless
        *dry_run* is True.
    dry_run:
        If True, all DB work is performed on the decompressed temp SQLite
        copy but the modified bytes are **not** written back to *sav_path*.

    Returns
    -------
    EncoderResult
        Summary of applied / skipped counts and any per-player warnings.
    """
    result = EncoderResult()
    operations = plan.get("operations") or []

    tmp_path, _original_bytes = sav_to_temp_sqlite(sav_path)
    try:
        conn = sqlite3.connect(str(tmp_path))
        try:
            for op in operations:
                player_info = op.get("player") or {}
                attrs = op.get("attributes") or {}
                target = op.get("target") or {}

                player_id = str(player_info.get("player_id") or attrs.get("player_id") or "").strip()
                player_name = str(player_info.get("player_name") or attrs.get("name") or "").strip()
                role = str(player_info.get("role") or "").strip() or None
                position_group = str(target.get("position_group") or "").strip() or None

                if not player_id and not player_name:
                    result.warnings.append(f"Operation {op.get('operation_id')!r} has no player_id or name; skipped")
                    result.skipped += 1
                    continue

                guid_blob = _find_player_guid(conn, player_id, player_name, result)
                if guid_blob is None:
                    result.skipped += 1
                    continue

                ok = _apply_player(conn, guid_blob, attrs, role, position_group, result)
                if ok:
                    result.applied += 1
                else:
                    result.skipped += 1

            conn.commit()
        finally:
            conn.close()

        if not dry_run:
            modified_bytes = tmp_path.read_bytes()
            compress_sav(modified_bytes, sav_path)

    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    return result


def apply_encoder_plan_from_file(
    plan_path: Path,
    sav_path: Path,
    *,
    dry_run: bool = False,
) -> EncoderResult:
    """Load *plan_path* as JSON and call :func:`apply_encoder_plan`."""
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return apply_encoder_plan(plan, sav_path, dry_run=dry_run)
