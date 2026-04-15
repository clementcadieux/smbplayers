"""
Decoder: read a SMB4 .sav file and return a canonical snapshot dict.

The output schema matches what ``build_canonical_snapshot_payload`` produces,
so the existing ``build-dry-run-report --current-snapshot`` workflow works
without modification.

This replaces the PowerShell path previously used to produce
``decoded_league_snapshot.sample.json``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .db_mappings import (
    INT_TO_ARM_ANGLE,
    INT_TO_BATTING_HAND,
    INT_TO_CHEMISTRY,
    INT_TO_PITCH_ROLE,
    INT_TO_POSITION,
    INT_TO_THROWING_HAND,
    OPTION_KEYS,
    TRAIT_ID_TO_NAME,
    all_pitch_option_keys,
)
from .sav_io import sav_to_temp_sqlite


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

_SELECT_TEAMS_SQL = "SELECT GUID, teamName FROM t_teams"

_SELECT_PLAYERS_SQL = """
    SELECT
        p.GUID                          AS player_guid,
        vbpi.firstName                  AS first_name,
        vbpi.lastName                   AS last_name,
        p.power                         AS power,
        p.contact                       AS contact,
        p.speed                         AS speed,
        p.fielding                      AS fielding,
        p.arm                           AS arm,
        p.velocity                      AS velocity,
        p.junk                          AS junk,
        p.accuracy                      AS accuracy,
        vbpi.primaryPosition            AS primary_position_int,
        pitch_pos.optionValue           AS pitch_position_int,
        sec_pos.optionValue             AS secondary_position_int,
        batting.optionValue             AS batting_int,
        throwing.optionValue            AS throwing_int,
        chemistry.optionValue           AS chemistry_int,
        arm_angle.optionValue           AS arm_angle_int,
        four_seam.optionValue           AS four_seam,
        two_seam.optionValue            AS two_seam,
        screwball.optionValue           AS screwball,
        changeup.optionValue            AS changeup,
        fork.optionValue                AS fork,
        curveball.optionValue           AS curveball,
        slider.optionValue              AS slider,
        cutter.optionValue              AS cutter
    FROM t_baseball_players p
    INNER JOIN t_baseball_player_local_ids lid
           ON lid.GUID = p.GUID
    INNER JOIN v_baseball_player_info vbpi
           ON vbpi.baseballPlayerGUID = lid.GUID
    INNER JOIN t_baseball_player_options batting
           ON batting.baseballPlayerLocalID = lid.localID AND batting.optionKey = 5
    INNER JOIN t_baseball_player_options throwing
           ON throwing.baseballPlayerLocalID = lid.localID AND throwing.optionKey = 4
    LEFT  JOIN t_baseball_player_options chemistry
           ON chemistry.baseballPlayerLocalID = lid.localID AND chemistry.optionKey = 107
    LEFT  JOIN t_baseball_player_options arm_angle
           ON arm_angle.baseballPlayerLocalID = lid.localID AND arm_angle.optionKey = 49
    LEFT  JOIN t_baseball_player_options sec_pos
           ON sec_pos.baseballPlayerLocalID = lid.localID AND sec_pos.optionKey = 55
    LEFT  JOIN t_baseball_player_options pitch_pos
           ON pitch_pos.baseballPlayerLocalID = lid.localID AND pitch_pos.optionKey = 57
    LEFT  JOIN t_baseball_player_options four_seam
           ON four_seam.baseballPlayerLocalID = lid.localID AND four_seam.optionKey = 58
    LEFT  JOIN t_baseball_player_options two_seam
           ON two_seam.baseballPlayerLocalID = lid.localID AND two_seam.optionKey = 59
    LEFT  JOIN t_baseball_player_options screwball
           ON screwball.baseballPlayerLocalID = lid.localID AND screwball.optionKey = 60
    LEFT  JOIN t_baseball_player_options changeup
           ON changeup.baseballPlayerLocalID = lid.localID AND changeup.optionKey = 61
    LEFT  JOIN t_baseball_player_options fork
           ON fork.baseballPlayerLocalID = lid.localID AND fork.optionKey = 62
    LEFT  JOIN t_baseball_player_options curveball
           ON curveball.baseballPlayerLocalID = lid.localID AND curveball.optionKey = 63
    LEFT  JOIN t_baseball_player_options slider
           ON slider.baseballPlayerLocalID = lid.localID AND slider.optionKey = 64
    LEFT  JOIN t_baseball_player_options cutter
           ON cutter.baseballPlayerLocalID = lid.localID AND cutter.optionKey = 65
    WHERE p.teamGUID = ?
    ORDER BY vbpi.lastName, vbpi.firstName
"""

_SELECT_TRAITS_SQL = """
    SELECT t.trait, t.subType
      FROM t_baseball_player_traits t
      JOIN t_baseball_player_local_ids lid ON lid.localID = t.baseballPlayerLocalID
     WHERE lid.GUID = ?
"""

_SELECT_FREE_AGENTS_SQL = """
    SELECT
        p.GUID                          AS player_guid,
        vbpi.firstName                  AS first_name,
        vbpi.lastName                   AS last_name,
        p.power                         AS power,
        p.contact                       AS contact,
        p.speed                         AS speed,
        p.fielding                      AS fielding,
        p.arm                           AS arm,
        p.velocity                      AS velocity,
        p.junk                          AS junk,
        p.accuracy                      AS accuracy,
        vbpi.primaryPosition            AS primary_position_int,
        pitch_pos.optionValue           AS pitch_position_int,
        sec_pos.optionValue             AS secondary_position_int,
        batting.optionValue             AS batting_int,
        throwing.optionValue            AS throwing_int,
        chemistry.optionValue           AS chemistry_int,
        arm_angle.optionValue           AS arm_angle_int,
        four_seam.optionValue           AS four_seam,
        two_seam.optionValue            AS two_seam,
        screwball.optionValue           AS screwball,
        changeup.optionValue            AS changeup,
        fork.optionValue                AS fork,
        curveball.optionValue           AS curveball,
        slider.optionValue              AS slider,
        cutter.optionValue              AS cutter
    FROM t_baseball_players p
    INNER JOIN t_baseball_player_local_ids lid
           ON lid.GUID = p.GUID
    INNER JOIN v_baseball_player_info vbpi
           ON vbpi.baseballPlayerGUID = lid.GUID
    INNER JOIN t_baseball_player_options batting
           ON batting.baseballPlayerLocalID = lid.localID AND batting.optionKey = 5
    INNER JOIN t_baseball_player_options throwing
           ON throwing.baseballPlayerLocalID = lid.localID AND throwing.optionKey = 4
    LEFT  JOIN t_baseball_player_options chemistry
           ON chemistry.baseballPlayerLocalID = lid.localID AND chemistry.optionKey = 107
    LEFT  JOIN t_baseball_player_options arm_angle
           ON arm_angle.baseballPlayerLocalID = lid.localID AND arm_angle.optionKey = 49
    LEFT  JOIN t_baseball_player_options sec_pos
           ON sec_pos.baseballPlayerLocalID = lid.localID AND sec_pos.optionKey = 55
    LEFT  JOIN t_baseball_player_options pitch_pos
           ON pitch_pos.baseballPlayerLocalID = lid.localID AND pitch_pos.optionKey = 57
    LEFT  JOIN t_baseball_player_options four_seam
           ON four_seam.baseballPlayerLocalID = lid.localID AND four_seam.optionKey = 58
    LEFT  JOIN t_baseball_player_options two_seam
           ON two_seam.baseballPlayerLocalID = lid.localID AND two_seam.optionKey = 59
    LEFT  JOIN t_baseball_player_options screwball
           ON screwball.baseballPlayerLocalID = lid.localID AND screwball.optionKey = 60
    LEFT  JOIN t_baseball_player_options changeup
           ON changeup.baseballPlayerLocalID = lid.localID AND changeup.optionKey = 61
    LEFT  JOIN t_baseball_player_options fork
           ON fork.baseballPlayerLocalID = lid.localID AND fork.optionKey = 62
    LEFT  JOIN t_baseball_player_options curveball
           ON curveball.baseballPlayerLocalID = lid.localID AND curveball.optionKey = 63
    LEFT  JOIN t_baseball_player_options slider
           ON slider.baseballPlayerLocalID = lid.localID AND slider.optionKey = 64
    LEFT  JOIN t_baseball_player_options cutter
           ON cutter.baseballPlayerLocalID = lid.localID AND cutter.optionKey = 65
    WHERE p.teamGUID IS NULL OR p.teamGUID = x'00000000000000000000000000000000'
    ORDER BY vbpi.lastName, vbpi.firstName
"""

# ---------------------------------------------------------------------------
# Row → dict helpers
# ---------------------------------------------------------------------------

_PITCH_OPTION_KEYS = [
    (OPTION_KEYS["FOUR_SEAM"],  "four_seam",  "4-Seam Fastball"),
    (OPTION_KEYS["TWO_SEAM"],   "two_seam",   "2-Seam Fastball"),
    (OPTION_KEYS["SCREWBALL"],  "screwball",  "Screwball"),
    (OPTION_KEYS["CHANGEUP"],   "changeup",   "Changeup"),
    (OPTION_KEYS["FORK"],       "fork",       "Forkball"),
    (OPTION_KEYS["CURVEBALL"],  "curveball",  "Curveball"),
    (OPTION_KEYS["SLIDER"],     "slider",     "Slider"),
    (OPTION_KEYS["CUTTER"],     "cutter",     "Cut Fastball"),
]


def _guid_to_hex(blob: Any) -> str:
    if isinstance(blob, bytes):
        return blob.hex().upper()
    return str(blob)


def _row_to_attributes(row: sqlite3.Row, conn: sqlite3.Connection, team_guid_blob: bytes | None = None) -> dict[str, Any]:
    """Convert a player SELECT row into the attributes dict used in the snapshot."""
    primary_int = row["primary_position_int"] or 0
    pitch_pos_int = row["pitch_position_int"]
    secondary_int = row["secondary_position_int"] or 0

    if primary_int == 1 and pitch_pos_int:
        position = INT_TO_PITCH_ROLE.get(int(pitch_pos_int), "P")
    else:
        position = INT_TO_POSITION.get(int(primary_int), "")

    secondary_position = INT_TO_POSITION.get(int(secondary_int), "") if secondary_int else ""

    bat = INT_TO_BATTING_HAND.get(int(row["batting_int"] or 1), "R")
    throw = INT_TO_THROWING_HAND.get(int(row["throwing_int"] or 1), "R")
    chemistry = INT_TO_CHEMISTRY.get(int(row["chemistry_int"] or 0), "Competitive")
    arm_angle = INT_TO_ARM_ANGLE.get(int(row["arm_angle_int"] or 2), "Mid")

    arsenal = [
        name for _, col, name in _PITCH_OPTION_KEYS
        if (row[col] or 0) == 1
    ]

    # Traits
    guid_blob = bytes(row["player_guid"])
    trait_rows = conn.execute(_SELECT_TRAITS_SQL, (guid_blob,)).fetchall()
    traits: list[str] = []
    for tr in trait_rows:
        display = TRAIT_ID_TO_NAME.get((int(tr["trait"]), int(tr["subType"])))
        if display:
            traits.append(display)

    attrs: dict[str, Any] = {
        "power":    row["power"],
        "contact":  row["contact"],
        "speed":    row["speed"],
        "fielding": row["fielding"],
        "arm":      row["arm"],
        "velocity": row["velocity"],
        "junk":     row["junk"],
        "accuracy": row["accuracy"],
        "position": position,
        "secondary_position": secondary_position,
        "bat_hand":   bat,
        "throw_hand": throw,
        "chemistry":  chemistry,
        "arm_angle":  arm_angle,
        "arsenal":    ", ".join(arsenal),
    }
    if traits:
        attrs["trait_1"] = traits[0] if len(traits) > 0 else "--"
        attrs["trait_2"] = traits[1] if len(traits) > 1 else "--"

    return attrs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def decode_sav(sav_path: Path) -> dict[str, Any]:
    """
    Decompress *sav_path* and read all players into a canonical snapshot dict.

    The returned dict has the schema:
    ::

        {
            "schema_version": "v1",
            "teams": [
                {
                    "team": "<abbreviation>",
                    "roster": [
                        {
                            "slot_type": "<slot>",
                            "player_id": "<guid_hex>",
                            "player_name": "<name>",
                            "role": "<SP|RP|CP|hitter|...>",
                            "attributes": { ... }
                        },
                        ...
                    ]
                },
                ...
            ],
            "free_agents": [
                {
                    "player_id": "<guid_hex>",
                    "name": "<name>",
                    "role_hint": "<role>",
                    "attributes": { ... }
                },
                ...
            ]
        }

    The schema is compatible with ``build_canonical_snapshot_payload`` output
    so the existing ``--current-snapshot`` diff workflow works unchanged.
    """
    tmp_path, _db_bytes = sav_to_temp_sqlite(sav_path)
    try:
        conn = sqlite3.connect(str(tmp_path))
        conn.row_factory = sqlite3.Row
        try:
            teams: list[dict[str, Any]] = []
            team_rows = conn.execute(_SELECT_TEAMS_SQL).fetchall()

            for team_row in team_rows:
                team_guid_blob = bytes(team_row["GUID"])
                team_name = str(team_row["teamName"] or "")

                player_rows = conn.execute(_SELECT_PLAYERS_SQL, (team_guid_blob,)).fetchall()
                roster: list[dict[str, Any]] = []
                for idx, pr in enumerate(player_rows, start=1):
                    attrs = _row_to_attributes(pr, conn, team_guid_blob)
                    position = attrs.get("position", "")
                    from .db_mappings import is_pitcher_role
                    role = position if is_pitcher_role(position) else "hitter"
                    full_name = f"{pr['first_name']} {pr['last_name']}".strip()
                    # Slot type derived heuristically from role + index
                    slot_prefix = "sp" if position == "SP" else ("rp" if position in ("RP", "CP") else "pos")
                    slot_type = f"{slot_prefix}{idx}"
                    roster.append({
                        "slot_type": slot_type,
                        "player_id": _guid_to_hex(pr["player_guid"]),
                        "player_name": full_name,
                        "role": role,
                        "attributes": attrs,
                    })

                teams.append({"team": team_name, "roster": roster})

            # Free agents
            free_agents: list[dict[str, Any]] = []
            fa_rows = conn.execute(_SELECT_FREE_AGENTS_SQL).fetchall()
            for pr in fa_rows:
                attrs = _row_to_attributes(pr, conn)
                position = attrs.get("position", "")
                from .db_mappings import is_pitcher_role
                role_hint = position if is_pitcher_role(position) else "hitter"
                full_name = f"{pr['first_name']} {pr['last_name']}".strip()
                free_agents.append({
                    "player_id": _guid_to_hex(pr["player_guid"]),
                    "name": full_name,
                    "role_hint": role_hint,
                    "attributes": attrs,
                })

        finally:
            conn.close()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    return {
        "schema_version": "v1",
        "teams": teams,
        "free_agents": free_agents,
    }


def decode_sav_to_file(sav_path: Path, output_path: Path) -> dict[str, Any]:
    """Decode *sav_path* and write canonical snapshot JSON to *output_path*."""
    snapshot = decode_sav(sav_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return snapshot
