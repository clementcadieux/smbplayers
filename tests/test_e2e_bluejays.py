from __future__ import annotations

import csv
import json
import re
import ssl
import tempfile
import unittest
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from smb4_mlb_ratings.cli import main

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:
    pytest = None

if pytest is not None:
    pytestmark = pytest.mark.integration


TEAM_ID = 141
TEAM_ABBREVIATION = "TOR"
ROSTER_SEASON = 2026
PRIMARY_STAT_SEASON = 2025
FALLBACK_STAT_SEASON = 2026
MLB_STATS_API = "https://statsapi.mlb.com/api/v1"
BASEBALL_SAVANT = "https://baseballsavant.mlb.com"
INFIELD_POSITIONS = {"1B", "2B", "3B", "SS", "IF"}
OUTFIELD_POSITIONS = {"LF", "CF", "RF", "OF"}
ELITE_PITCH_SPECS = {
    "4F": {
        "metric_key": "pitch_quality_4f",
        "column": "Pitch Quality 4F",
        "arsenal_codes": ("FF",),
        "savant_codes": ("FF",),
        "kind": "fastball",
        "velocity_baseline": 90.0,
    },
    "2F": {
        "metric_key": "pitch_quality_2f",
        "column": "Pitch Quality 2F",
        "arsenal_codes": ("SI", "FT"),
        "savant_codes": ("SI", "FT"),
        "kind": "fastball",
        "velocity_baseline": 89.0,
    },
    "CF": {
        "metric_key": "pitch_quality_cf",
        "column": "Pitch Quality CF",
        "arsenal_codes": ("FC",),
        "savant_codes": ("FC",),
        "kind": "fastball",
        "velocity_baseline": 87.0,
    },
    "CB": {
        "metric_key": "pitch_quality_cb",
        "column": "Pitch Quality CB",
        "arsenal_codes": ("CU", "KC"),
        "savant_codes": ("CU", "KC"),
        "kind": "secondary",
        "target_gap": 15.0,
    },
    "CH": {
        "metric_key": "pitch_quality_ch",
        "column": "Pitch Quality CH",
        "arsenal_codes": ("CH",),
        "savant_codes": ("CH",),
        "kind": "secondary",
        "target_gap": 9.0,
    },
    "FK": {
        "metric_key": "pitch_quality_fk",
        "column": "Pitch Quality FK",
        "arsenal_codes": ("FS", "FO"),
        "savant_codes": ("FS", "FO"),
        "kind": "secondary",
        "target_gap": 10.0,
    },
    "SL": {
        "metric_key": "pitch_quality_sl",
        "column": "Pitch Quality SL",
        "arsenal_codes": ("SL", "SV"),
        "savant_codes": ("SL", "SV"),
        "kind": "secondary",
        "target_gap": 11.0,
    },
    "SB": {
        "metric_key": "pitch_quality_sb",
        "column": "Pitch Quality SB",
        "arsenal_codes": ("SC",),
        "savant_codes": ("SC",),
        "kind": "secondary",
        "target_gap": 13.0,
    },
}


class BlueJaysPipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.exports = self.root / "exports"
        self.output = self.root / "output"
        self.exports.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        # The configured Python environment cannot validate the MLB Stats API
        # certificate chain, so the live integration test uses an explicit SSL context.
        self.ssl_context = ssl._create_unverified_context()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_blue_jays_full_pipeline(self) -> None:
        try:
            self.players = self._fetch_blue_jays_players()
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            self.skipTest(f"Live MLB Stats API unavailable: {error}")

        self._write_fixture_files()

        normalized_path = self.output / "tor_normalized.json"
        filtered_normalized_path = self.output / "tor_filtered_normalized.json"
        ratings_path = self.output / "tor_ratings.json"
        structured_path = self.output / "tor_structured"
        roster_path = self.output / "tor_roster.json"
        manifest_path = self.exports / "bluejays_manifest.json"

        ingest_result = main(["ingest", str(manifest_path), str(normalized_path)])
        self.assertEqual(ingest_result, 0)

        ingest_rate_result = main(
            [
                "ingest-rate",
                str(manifest_path),
                str(ratings_path),
                "--team",
                TEAM_ABBREVIATION,
                "--normalized-output",
                str(filtered_normalized_path),
                "--structured-output",
                str(structured_path),
            ]
        )
        self.assertEqual(ingest_rate_result, 0)

        rank_result = main(["rank", str(ratings_path), str(roster_path)])
        self.assertEqual(rank_result, 0)

        expected_names = sorted(str(player["name"]) for player in self.players)
        inactive_name = str(self._inactive_player()["name"])
        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        normalized_players = normalized_payload["players"]
        self.assertEqual(len(normalized_players), len(self.players) + 1)
        inactive_player = next(player for player in normalized_players if player["name"] == inactive_name)
        self.assertFalse(inactive_player["active"])
        self.assertEqual(inactive_player["team"], "NYY")
        self.assertTrue(all(player["name"] and player["primary_position"] for player in normalized_players))
        self.assertTrue(all(player["samples"] for player in normalized_players))
        self.assertTrue(all(player["metrics"] for player in normalized_players))

        filtered_normalized_payload = json.loads(filtered_normalized_path.read_text(encoding="utf-8"))
        filtered_normalized_players = filtered_normalized_payload["players"]
        self.assertEqual(len(filtered_normalized_players), len(self.players))
        self.assertTrue(all(player["team"] == "TOR" for player in filtered_normalized_players))
        self.assertTrue(all(player["metadata"]["source"] == "mixed" for player in filtered_normalized_players))
        self.assertEqual(sorted(player["name"] for player in filtered_normalized_players), expected_names)
        self.assertNotIn(inactive_name, {player["name"] for player in filtered_normalized_players})

        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(ratings_payload), len(self.players))
        self.assertTrue(all(player["team"] == "TOR" for player in ratings_payload))
        self.assertTrue(all(1 <= player["overall_numeric"] <= 99 for player in ratings_payload if player["overall_numeric"] is not None))
        self.assertEqual(sorted(player["name"] for player in ratings_payload), expected_names)
        self.assertNotIn(inactive_name, {player["name"] for player in ratings_payload})
        pitcher_outputs = [player for player in ratings_payload if player["role"] in {"pitcher", "two_way"}]
        self.assertTrue(any(player["recommended_pitches"] for player in pitcher_outputs))
        injured_players = {
            player["name"]
            for player in ratings_payload
            if isinstance(player.get("metadata"), dict) and isinstance(player["metadata"].get("status"), str) and "injured" in player["metadata"]["status"].lower()
        }
        self.assertTrue(injured_players)

        structured_team_path = structured_path / "AL" / "East" / "TOR.json"
        self.assertTrue(structured_team_path.exists())
        structured_team_payload = json.loads(structured_team_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(player["name"] for player in structured_team_payload["players"]),
            sorted(player["name"] for player in ratings_payload),
        )
        self.assertNotIn(inactive_name, {player["name"] for player in structured_team_payload["players"]})
        index_payload = json.loads((structured_path / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index_payload["AL"]["East"][0]["team"], "TOR")

        roster_payload = json.loads(roster_path.read_text(encoding="utf-8"))
        team_roster = roster_payload["teams"][0]
        self.assertEqual(team_roster["team"], "TOR")
        roster_slots = team_roster["recommended_roster"]
        expected_counts = self._expected_roster_counts(structured_team_payload["players"])
        self.assertEqual(len(roster_slots), expected_counts["total"])
        self.assertEqual(sum(slot["slot_type"].startswith("sp") for slot in roster_slots), expected_counts["SP"])
        self.assertEqual(sum(slot["slot_type"].startswith("rp") for slot in roster_slots), expected_counts["RP"])
        self.assertEqual(sum(slot["slot_type"].startswith("if") for slot in roster_slots), expected_counts["IF"])
        self.assertEqual(sum(slot["slot_type"].startswith("of") for slot in roster_slots), expected_counts["OF"])
        self.assertEqual(sum(slot["slot_type"].startswith("c") for slot in roster_slots), expected_counts["C"])
        self.assertEqual(sum(slot["slot_type"].startswith("flex_") for slot in roster_slots), expected_counts["Flex"])

        for prefix in ("sp", "rp", "c", "if", "of"):
            grouped_slots = [slot for slot in roster_slots if slot["slot_type"].startswith(prefix) and not slot["slot_type"].startswith("flex_")]
            ordered_keys = [self._output_sort_key(slot["player"]) for slot in grouped_slots]
            self.assertEqual(ordered_keys, sorted(ordered_keys))

        flex_names = {slot["player"]["name"] for slot in roster_slots if slot["slot_type"].startswith("flex_")}
        expected_flex_names = self._expected_flex_names(structured_team_payload["players"])
        self.assertEqual(flex_names, expected_flex_names)

        structured_flex_names = {
            slot["player"]["name"]
            for slot in structured_team_payload["recommended_roster"]
            if slot["slot_type"].startswith("flex_")
        }
        self.assertEqual(structured_flex_names, flex_names)
        self.assertNotIn(inactive_name, {slot["player"]["name"] for slot in roster_slots})
        injured_slots = [slot for slot in roster_slots if slot["is_injured_list"]]
        self.assertTrue(injured_slots)
        self.assertTrue(all(slot["player"]["name"] in injured_players for slot in injured_slots))

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            raise ValueError("CSV fixtures require at least one row")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_fixture_files(self) -> None:
        self._write_csv(self.exports / "bluejays_roster_2026.csv", self._roster_rows())
        self._write_csv(self.exports / "bluejays_savant_hitters_2025.csv", self._savant_hitter_rows())
        self._write_csv(self.exports / "bluejays_savant_pitchers_2025.csv", self._savant_pitcher_rows())
        self._write_csv(self.exports / "bluejays_bref_hitters_2025.csv", self._bref_hitter_rows())
        self._write_csv(self.exports / "bluejays_bref_pitchers_2025.csv", self._bref_pitcher_rows())

        manifest = {
            "source": "mixed",
            "roster_filter": {"team": TEAM_ABBREVIATION, "year": ROSTER_SEASON},
            "seasons": {
                "current": {
                    "year": ROSTER_SEASON,
                    "sources": {
                        "baseball_reference": {
                            "files": {
                                "hitters": "bluejays_bref_hitters_2025.csv",
                                "pitchers": "bluejays_bref_pitchers_2025.csv",
                            }
                        },
                        "baseball_savant": {
                            "files": {
                                "roster": "bluejays_roster_2026.csv",
                                "hitters": "bluejays_savant_hitters_2025.csv",
                                "pitchers": "bluejays_savant_pitchers_2025.csv",
                            }
                        },
                    },
                }
            },
        }
        (self.exports / "bluejays_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _roster_rows(self) -> list[dict[str, object]]:
        return [
            {
                "player_id": player["player_id"],
                "player_name": player["name"],
                "team": TEAM_ABBREVIATION,
                "status": player["status"],
                "status_code": player["status_code"],
                "age": player["age"],
                "position": player["position"],
                "bats": player["bats"],
                "throws": player["throws"],
            }
            for player in self.players
        ]

    def _bref_hitter_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players + [self._inactive_player()]:
            if player["type"] != "hitter":
                continue
            hitting_splits = player.get("hitting_handedness_splits") if isinstance(player.get("hitting_handedness_splits"), dict) else {}
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": player.get("team", TEAM_ABBREVIATION),
                    "position": player["position"],
                    "Days On Roster": player.get("days_on_roster"),
                    "PA": player["plate_appearances"],
                    "AB": player["at_bats"],
                    "H": player["hits"],
                    "2B": player["doubles"],
                    "3B": player["triples"],
                    "HR": player["home_runs"],
                    "BB": player["walks"],
                    "SO": player["strikeouts"],
                    "HBP": player["hit_by_pitch"],
                    "SB": player["stolen_bases"],
                    "CS": player["caught_stealing"],
                    "BA": player["avg"],
                    "OBP": player["obp"],
                    "SLG": player["slg"],
                    "Contact vs LHP Minus RHP": self._hitter_contact_platoon_delta(hitting_splits),
                    "Power vs LHP Minus RHP": self._hitter_power_platoon_delta(hitting_splits),
                }
            )
        return rows

    def _savant_hitter_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players + [self._inactive_player()]:
            if player["type"] != "hitter":
                continue
            advanced = player.get("advanced_hitting") if isinstance(player.get("advanced_hitting"), dict) else {}
            hitting_splits = player.get("hitting_handedness_splits") if isinstance(player.get("hitting_handedness_splits"), dict) else {}
            total_swings = self._as_int(advanced.get("totalSwings"))
            swing_and_misses = self._as_int(advanced.get("swingAndMisses"))
            contact_pct = None
            if total_swings not in (None, 0) and swing_and_misses is not None:
                contact_pct = round((1.0 - (swing_and_misses / total_swings)) * 100.0, 3)
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": player.get("team", TEAM_ABBREVIATION),
                    "position": player["position"],
                    "Days On Roster": player.get("days_on_roster"),
                    "PA": player["plate_appearances"],
                    "ISO": self._as_str(advanced.get("iso")) or self._format_decimal(float(player["slg"]) - float(player["avg"])),
                    "HR": player["home_runs"],
                    "SLG": player["slg"],
                    "AVG": player["avg"],
                    "OBP": player["obp"],
                    "K %": self._percentage(player["strikeouts"], player["plate_appearances"]),
                    "Contact %": contact_pct,
                    "2B": player["doubles"],
                    "3B": player["triples"],
                    "SB": player["stolen_bases"],
                    "CS": player["caught_stealing"],
                    "BB": player["walks"],
                    "HBP": player["hit_by_pitch"],
                    "H": player["hits"],
                    "Contact vs LHP Minus RHP": self._hitter_contact_platoon_delta(hitting_splits),
                    "Power vs LHP Minus RHP": self._hitter_power_platoon_delta(hitting_splits),
                }
            )
        return rows

    def _inactive_player(self) -> dict[str, object]:
        return {
            "player_id": 999001,
            "name": "Synthetic Traded Blue Jay",
            "team": "NYY",
            "type": "hitter",
            "position": "LF",
            "age": 29,
            "bats": "L",
            "throws": "R",
            "plate_appearances": 320,
            "at_bats": 290,
            "hits": 77,
            "doubles": 15,
            "triples": 1,
            "home_runs": 11,
            "walks": 24,
            "strikeouts": 68,
            "hit_by_pitch": 3,
            "stolen_bases": 5,
            "caught_stealing": 2,
            "avg": "0.266",
            "obp": "0.327",
            "slg": "0.438",
        }

    def _bref_pitcher_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "pitcher":
                continue
            pitching_splits = player.get("pitching_handedness_splits") if isinstance(player.get("pitching_handedness_splits"), dict) else {}
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": TEAM_ABBREVIATION,
                    "position": "P",
                    "Days On Roster": player.get("days_on_roster"),
                    "BF": player["batters_faced"],
                    "BB": player["walks"],
                    "SO": player["strikeouts"],
                    "HR": player["home_runs"],
                    "H": player["hits"],
                    "IP": player["innings_pitched"],
                    "Pitches": player["number_of_pitches"],
                    "Strikes": player["strikes"],
                    "Same Handed Pitching": self._pitcher_handedness_score(player, pitching_splits, split_type="same"),
                    "Same Handed Pitching Gap": self._pitcher_handedness_gap(player, pitching_splits, split_type="same"),
                    "Opposite Handed Pitching": self._pitcher_handedness_score(player, pitching_splits, split_type="opposite"),
                    "Opposite Handed Pitching Gap": self._pitcher_handedness_gap(player, pitching_splits, split_type="opposite"),
                }
            )
        return rows

    def _savant_pitcher_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "pitcher":
                continue
            advanced = player.get("advanced_pitching") if isinstance(player.get("advanced_pitching"), dict) else {}
            arsenal = player.get("pitch_arsenal") if isinstance(player.get("pitch_arsenal"), dict) else {}
            pitching_splits = player.get("pitching_handedness_splits") if isinstance(player.get("pitching_handedness_splits"), dict) else {}
            savant_pitch_details = player.get("savant_pitch_details") if isinstance(player.get("savant_pitch_details"), dict) else {}
            pitch_quality = self._derived_pitch_quality_metrics(arsenal, savant_pitch_details)
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": TEAM_ABBREVIATION,
                    "position": "P",
                    "Days On Roster": player.get("days_on_roster"),
                    "BF": player["batters_faced"],
                    "Pitches": player["number_of_pitches"],
                    "Avg Fastball Velocity": self._fastball_velocity(arsenal, mode="average"),
                    "Peak Fastball Velocity": self._fastball_velocity(arsenal, mode="peak"),
                    "FF %": self._arsenal_percentage(arsenal, "FF"),
                    "FT %": self._arsenal_percentage(arsenal, "FT"),
                    "SI %": self._arsenal_percentage(arsenal, "SI"),
                    "FC %": self._arsenal_percentage(arsenal, "FC"),
                    "SL %": self._arsenal_percentage(arsenal, "SL"),
                    "CU %": self._arsenal_percentage(arsenal, "CU"),
                    "CH %": self._arsenal_percentage(arsenal, "CH"),
                    "FS %": self._arsenal_percentage(arsenal, "FS"),
                    "FO %": self._arsenal_percentage(arsenal, "FO"),
                    "SC %": self._arsenal_percentage(arsenal, "SC"),
                    "SV %": self._arsenal_percentage(arsenal, "SV"),
                    "SwStr %": self._as_percentage_string(advanced.get("whiffPercentage")),
                    "BB %": self._percentage(player["walks"], player["batters_faced"]),
                    "Strike %": self._as_percentage_string(player.get("strike_percentage")),
                    **{
                        spec["column"]: pitch_quality.get(spec["metric_key"])
                        for spec in ELITE_PITCH_SPECS.values()
                    },
                    "Same Handed Pitching": self._pitcher_handedness_score(player, pitching_splits, split_type="same"),
                    "Same Handed Pitching Gap": self._pitcher_handedness_gap(player, pitching_splits, split_type="same"),
                    "Opposite Handed Pitching": self._pitcher_handedness_score(player, pitching_splits, split_type="opposite"),
                    "Opposite Handed Pitching Gap": self._pitcher_handedness_gap(player, pitching_splits, split_type="opposite"),
                }
            )
        return rows

    def _fetch_blue_jays_players(self) -> list[dict[str, Any]]:
        roster_payload = self._fetch_json(f"{MLB_STATS_API}/teams/{TEAM_ID}/roster?rosterType=40Man&season={ROSTER_SEASON}")
        roster_entries = roster_payload.get("roster", [])
        if not isinstance(roster_entries, list):
            return []

        players: list[dict[str, Any]] = []

        for roster_entry in roster_entries:
            if not isinstance(roster_entry, dict):
                continue
            person_summary = roster_entry.get("person", {})
            if not isinstance(person_summary, dict):
                continue
            player_id = self._as_int(person_summary.get("id"))
            if player_id is None:
                continue

            person_payload = self._fetch_json(f"{MLB_STATS_API}/people/{player_id}")
            people = person_payload.get("people", [])
            if not isinstance(people, list) or not people:
                continue
            person = people[0]
            if not isinstance(person, dict):
                continue

            roster_position = roster_entry.get("position", {})
            if not isinstance(roster_position, dict):
                roster_position = {}
            primary_position = person.get("primaryPosition", {})
            if not isinstance(primary_position, dict):
                primary_position = {}
            status_payload = roster_entry.get("status", {})
            if not isinstance(status_payload, dict):
                status_payload = {}
            status = self._as_str(status_payload.get("description")) or "Active"
            if status != "Active" and "injured" not in status.lower():
                continue

            position = self._as_str(roster_position.get("abbreviation")) or self._as_str(primary_position.get("abbreviation"))
            position_type = self._as_str(roster_position.get("type"))
            if position_type == "Pitcher" or position == "P":
                stat_group = "pitching"
                player_type = "pitcher"
            else:
                stat_group = "hitting"
                player_type = "hitter"

            stats = self._fetch_stats(player_id, stat_group)
            if stats is None:
                continue
            advanced_stats = self._fetch_stats(player_id, stat_group, stats_type="seasonAdvanced") or {}
            handedness_splits = self._fetch_handedness_splits(player_id, stat_group)

            base_player = {
                "player_id": player_id,
                "name": self._as_str(person.get("fullName")) or self._as_str(person_summary.get("fullName")),
                "type": player_type,
                "position": position,
                "status": status,
                "status_code": self._as_str(status_payload.get("code")) or "A",
                "age": self._as_int(person.get("currentAge")),
                "bats": self._nested_str(person, "batSide", "code"),
                "throws": self._nested_str(person, "pitchHand", "code"),
                "days_on_roster": self._fetch_days_on_roster(player_id, stat_group),
            }
            if player_type == "hitter":
                plate_appearances = self._as_int(stats.get("plateAppearances")) or 0
                if plate_appearances == 0:
                    continue
                base_player.update(
                    {
                        "plate_appearances": plate_appearances,
                        "at_bats": self._as_int(stats.get("atBats")) or 0,
                        "hits": self._as_int(stats.get("hits")) or 0,
                        "doubles": self._as_int(stats.get("doubles")) or 0,
                        "triples": self._as_int(stats.get("triples")) or 0,
                        "home_runs": self._as_int(stats.get("homeRuns")) or 0,
                        "walks": self._as_int(stats.get("baseOnBalls")) or 0,
                        "strikeouts": self._as_int(stats.get("strikeOuts")) or 0,
                        "hit_by_pitch": self._as_int(stats.get("hitByPitch")) or 0,
                        "stolen_bases": self._as_int(stats.get("stolenBases")) or 0,
                        "caught_stealing": self._as_int(stats.get("caughtStealing")) or 0,
                        "avg": self._as_str(stats.get("avg")) or "0.000",
                        "obp": self._as_str(stats.get("obp")) or "0.000",
                        "slg": self._as_str(stats.get("slg")) or "0.000",
                        "advanced_hitting": advanced_stats,
                        "hitting_handedness_splits": handedness_splits,
                    }
                )
            else:
                pitch_arsenal = self._fetch_pitch_arsenal(player_id)
                batters_faced = self._as_int(stats.get("battersFaced")) or 0
                if batters_faced == 0:
                    continue
                base_player.update(
                    {
                        "batters_faced": batters_faced,
                        "walks": self._as_int(stats.get("baseOnBalls")) or 0,
                        "strikeouts": self._as_int(stats.get("strikeOuts")) or 0,
                        "home_runs": self._as_int(stats.get("homeRuns")) or 0,
                        "hits": self._as_int(stats.get("hits")) or 0,
                        "innings_pitched": self._as_str(stats.get("inningsPitched")) or "0.0",
                        "number_of_pitches": self._as_int(stats.get("numberOfPitches")) or 0,
                        "strikes": self._as_int(stats.get("strikes")) or 0,
                        "strike_percentage": self._as_str(stats.get("strikePercentage")) or self._as_str(advanced_stats.get("strikePercentage")),
                        "advanced_pitching": advanced_stats,
                        "pitching_handedness_splits": handedness_splits,
                        "savant_pitch_details": self._fetch_savant_pitch_details(player_id),
                        "pitch_arsenal": pitch_arsenal,
                    }
                )
            players.append(base_player)

        if len(players) < 22:
            self.fail(f"Expected enough real Blue Jays players for a full roster, found {len(players)}")
        return sorted(players, key=lambda player: (player["type"], player["name"]))

    def _fetch_json(self, url: str) -> dict[str, Any]:
        with urlopen(url, timeout=30, context=self.ssl_context) as response:
            return json.load(response)

    def _fetch_text(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        request = Request(url, headers=headers or {})
        with urlopen(request, timeout=30, context=self.ssl_context) as response:
            return response.read().decode("utf-8", errors="replace")

    def _fetch_stats(self, player_id: int, group: str, *, stats_type: str = "season") -> dict[str, Any] | None:
        for season in (PRIMARY_STAT_SEASON, FALLBACK_STAT_SEASON):
            payload = self._fetch_json(f"{MLB_STATS_API}/people/{player_id}/stats?stats={stats_type}&group={group}&season={season}")
            stats = payload.get("stats", [])
            if not isinstance(stats, list) or not stats:
                continue
            first_stats = stats[0]
            if not isinstance(first_stats, dict):
                continue
            splits = first_stats.get("splits", [])
            if not isinstance(splits, list) or not splits:
                continue
            first_split = splits[0]
            if not isinstance(first_split, dict):
                continue
            stat_line = first_split.get("stat", {})
            if isinstance(stat_line, dict):
                return stat_line
        return None

    def _fetch_pitch_arsenal(self, player_id: int) -> dict[str, dict[str, Any]]:
        for season in (PRIMARY_STAT_SEASON, FALLBACK_STAT_SEASON):
            payload = self._fetch_json(f"{MLB_STATS_API}/people/{player_id}/stats?stats=pitchArsenal&group=pitching&season={season}")
            stats = payload.get("stats", [])
            if not isinstance(stats, list) or not stats:
                continue
            first_stats = stats[0]
            if not isinstance(first_stats, dict):
                continue
            splits = first_stats.get("splits", [])
            if not isinstance(splits, list) or not splits:
                continue
            arsenal: dict[str, dict[str, Any]] = {}
            for split in splits:
                if not isinstance(split, dict):
                    continue
                stat_line = split.get("stat", {})
                if not isinstance(stat_line, dict):
                    continue
                pitch_type = stat_line.get("type", {})
                if not isinstance(pitch_type, dict):
                    continue
                pitch_code = self._as_str(pitch_type.get("code"))
                if not pitch_code:
                    continue
                arsenal[pitch_code.upper()] = stat_line
            if arsenal:
                return arsenal
        return {}

    def _fetch_savant_pitch_details(self, player_id: int) -> dict[str, dict[str, float]]:
        try:
            payload = self._fetch_text(
                f"{BASEBALL_SAVANT}/player-services/statcast-pitches-breakdown?playerId={player_id}&position=1&pitchBreakdown=pitches",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": f"{BASEBALL_SAVANT}/",
                    "Accept": "application/json,text/plain,*/*",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
        except (HTTPError, URLError, TimeoutError, OSError):
            return {}

        match = re.search(r"window\.serverVals\.pitchDetails\s*=\s*(\[.*?\]);", payload, re.DOTALL)
        if not match:
            return {}
        try:
            raw_rows = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        if not isinstance(raw_rows, list):
            return {}

        details: dict[str, dict[str, float]] = {}
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            pitch_code = self._as_str(row.get("api_pitch_type"))
            if not pitch_code:
                continue
            details[pitch_code.upper()] = {
                "xba": self._as_float(row.get("xba")) or 0.0,
                "xwoba": self._as_float(row.get("xwoba")) or 0.0,
                "xslg": self._as_float(row.get("xslg")) or 0.0,
                "hard_hit_percent": self._as_float(row.get("hard_hit_percent")) or 0.0,
                "brl_percent": self._as_float(row.get("brl_percent")) or 0.0,
                "swings": self._as_float(row.get("swings")) or 0.0,
                "misses": self._as_float(row.get("misses")) or 0.0,
                "release_speed": self._as_float(row.get("release_speed")) or 0.0,
                "pitches": self._as_float(row.get("pitches")) or 0.0,
                "total_pitches": self._as_float(row.get("total_pitches")) or 0.0,
            }
        return details

    def _fetch_handedness_splits(self, player_id: int, group: str) -> dict[str, dict[str, float]]:
        for season in (PRIMARY_STAT_SEASON, FALLBACK_STAT_SEASON):
            splits_by_code: dict[str, dict[str, float]] = {}
            for split_code in ("vl", "vr"):
                payload = self._fetch_json(
                    f"{MLB_STATS_API}/people/{player_id}/stats?stats=statSplits&group={group}&season={season}&sitCodes={split_code}"
                )
                stats = payload.get("stats", [])
                if not isinstance(stats, list) or not stats:
                    continue
                first_stats = stats[0]
                if not isinstance(first_stats, dict):
                    continue
                splits = first_stats.get("splits", [])
                if not isinstance(splits, list) or not splits:
                    continue
                aggregated = self._aggregate_split_stats(group, splits)
                if aggregated:
                    splits_by_code[split_code] = aggregated
            if splits_by_code:
                return splits_by_code
        return {}

    def _aggregate_split_stats(self, group: str, splits: list[dict[str, Any]]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for split in splits:
            if not isinstance(split, dict):
                continue
            stat_line = split.get("stat", {})
            if not isinstance(stat_line, dict):
                continue
            for key in (
                "hits",
                "atBats",
                "baseOnBalls",
                "hitByPitch",
                "sacFlies",
                "totalBases",
                "strikeOuts",
                "plateAppearances",
                "battersFaced",
            ):
                value = self._as_float(stat_line.get(key))
                if value is not None:
                    totals[key] += value

        if group == "hitting":
            at_bats = totals.get("atBats", 0.0)
            plate_appearances = totals.get("plateAppearances", 0.0)
            hits = totals.get("hits", 0.0)
            total_bases = totals.get("totalBases", 0.0)
            walks = totals.get("baseOnBalls", 0.0)
            hit_by_pitch = totals.get("hitByPitch", 0.0)
            sac_flies = totals.get("sacFlies", 0.0)
            strikeouts = totals.get("strikeOuts", 0.0)
            avg = self._ratio(hits, at_bats)
            obp = self._ratio(hits + walks + hit_by_pitch, at_bats + walks + hit_by_pitch + sac_flies)
            slg = self._ratio(total_bases, at_bats)
            iso = None if avg is None or slg is None else max(slg - avg, 0.0)
            strikeout_rate = self._ratio(strikeouts, plate_appearances)
            return {
                "avg": avg or 0.0,
                "obp": obp or 0.0,
                "slg": slg or 0.0,
                "iso": iso or 0.0,
                "strikeout_rate": strikeout_rate or 0.0,
            }

        if group == "pitching":
            at_bats = totals.get("atBats", 0.0)
            batters_faced = totals.get("battersFaced", 0.0)
            hits = totals.get("hits", 0.0)
            total_bases = totals.get("totalBases", 0.0)
            walks = totals.get("baseOnBalls", 0.0)
            hit_by_pitch = totals.get("hitByPitch", 0.0)
            sac_flies = totals.get("sacFlies", 0.0)
            strikeouts = totals.get("strikeOuts", 0.0)
            avg = self._ratio(hits, at_bats)
            obp = self._ratio(hits + walks + hit_by_pitch, at_bats + walks + hit_by_pitch + sac_flies)
            slg = self._ratio(total_bases, at_bats)
            ops = None if obp is None or slg is None else obp + slg
            strikeout_rate = self._ratio(strikeouts, batters_faced)
            return {
                "avg": avg or 0.0,
                "obp": obp or 0.0,
                "slg": slg or 0.0,
                "ops": ops or 0.0,
                "strikeout_rate": strikeout_rate or 0.0,
            }
        return {}

    def _hitter_contact_platoon_delta(self, splits: dict[str, dict[str, float]]) -> float | None:
        vs_left = splits.get("vl") if isinstance(splits.get("vl"), dict) else None
        vs_right = splits.get("vr") if isinstance(splits.get("vr"), dict) else None
        if not isinstance(vs_left, dict) or not isinstance(vs_right, dict):
            return None
        avg_delta = (vs_left.get("avg", 0.0) - vs_right.get("avg", 0.0)) * 1000.0
        strikeout_delta = (vs_right.get("strikeout_rate", 0.0) - vs_left.get("strikeout_rate", 0.0)) * 100.0
        return round(avg_delta + strikeout_delta, 3)

    def _hitter_power_platoon_delta(self, splits: dict[str, dict[str, float]]) -> float | None:
        vs_left = splits.get("vl") if isinstance(splits.get("vl"), dict) else None
        vs_right = splits.get("vr") if isinstance(splits.get("vr"), dict) else None
        if not isinstance(vs_left, dict) or not isinstance(vs_right, dict):
            return None
        return round((vs_left.get("iso", 0.0) - vs_right.get("iso", 0.0)) * 1000.0, 3)

    def _pitcher_handedness_score(
        self,
        player: dict[str, Any],
        splits: dict[str, dict[str, float]],
        *,
        split_type: str,
    ) -> float | None:
        throws = self._as_str(player.get("throws"))
        if throws == "L":
            key = "vl" if split_type == "same" else "vr"
        elif throws == "R":
            key = "vr" if split_type == "same" else "vl"
        else:
            return None
        split = splits.get(key) if isinstance(splits.get(key), dict) else None
        if not isinstance(split, dict):
            return None
        ops = split.get("ops", 0.0)
        strikeout_rate = split.get("strikeout_rate", 0.0)
        score = 100.0 - max((ops - 0.5) * 200.0, 0.0) + (strikeout_rate * 100.0 * 0.25)
        return round(max(0.0, min(99.0, score)), 3)

    def _pitcher_handedness_gap(
        self,
        player: dict[str, Any],
        splits: dict[str, dict[str, float]],
        *,
        split_type: str,
    ) -> float | None:
        same_score = self._pitcher_handedness_score(player, splits, split_type="same")
        opposite_score = self._pitcher_handedness_score(player, splits, split_type="opposite")
        if same_score is None or opposite_score is None:
            return None
        if split_type == "same":
            return round(same_score - opposite_score, 3)
        if split_type == "opposite":
            return round(opposite_score - same_score, 3)
        return None

    def _derived_pitch_quality_metrics(
        self,
        arsenal: dict[str, dict[str, Any]],
        savant_pitch_details: dict[str, dict[str, float]] | None = None,
    ) -> dict[str, float | None]:
        fastball_velocity = self._fastball_velocity(arsenal, mode="average") or 0.0
        primary_fastball_usage = max(
            (
                self._arsenal_percentage_for_codes(arsenal, spec["arsenal_codes"]) or 0.0
                for spec in ELITE_PITCH_SPECS.values()
                if spec["kind"] == "fastball"
            ),
            default=0.0,
        )
        metrics: dict[str, float | None] = {}
        for spec in ELITE_PITCH_SPECS.values():
            metric_key = str(spec["metric_key"])
            if spec["kind"] == "fastball":
                metrics[metric_key] = self._pitch_quality_fastball_family(
                    arsenal,
                    savant_pitch_details or {},
                    arsenal_codes=tuple(spec["arsenal_codes"]),
                    savant_codes=tuple(spec["savant_codes"]),
                    primary_fastball_usage=primary_fastball_usage,
                    velocity_baseline=float(spec["velocity_baseline"]),
                )
                continue
            metrics[metric_key] = self._pitch_quality_secondary_family(
                arsenal,
                savant_pitch_details or {},
                arsenal_codes=tuple(spec["arsenal_codes"]),
                savant_codes=tuple(spec["savant_codes"]),
                fastball_velocity=fastball_velocity,
                primary_fastball_usage=primary_fastball_usage,
                target_gap=float(spec["target_gap"]),
            )
        return metrics

    def _pitch_quality_fastball_family(
        self,
        arsenal: dict[str, dict[str, Any]],
        savant_pitch_details: dict[str, dict[str, float]],
        *,
        arsenal_codes: tuple[str, ...],
        savant_codes: tuple[str, ...],
        primary_fastball_usage: float,
        velocity_baseline: float,
    ) -> float | None:
        usage = self._arsenal_percentage_for_codes(arsenal, arsenal_codes)
        velocity = self._pitch_average_speed_for_codes(arsenal, arsenal_codes)
        if usage is None or velocity is None:
            return None
        quality_score = self._family_savant_pitch_quality_score(savant_pitch_details, savant_codes)
        fallback_quality = max((velocity - velocity_baseline) * 5.0, 0.0)
        score = (quality_score * 0.8) + (fallback_quality * 0.2)
        score += self._pitch_usage_modifier(usage, primary_fastball_usage)
        if primary_fastball_usage and usage >= primary_fastball_usage * 0.9:
            score += 3.0
        return round(max(0.0, min(99.0, score)), 3)

    def _pitch_quality_secondary_family(
        self,
        arsenal: dict[str, dict[str, Any]],
        savant_pitch_details: dict[str, dict[str, float]],
        *,
        arsenal_codes: tuple[str, ...],
        savant_codes: tuple[str, ...],
        fastball_velocity: float,
        primary_fastball_usage: float,
        target_gap: float,
    ) -> float | None:
        usage = self._arsenal_percentage_for_codes(arsenal, arsenal_codes)
        velocity = self._pitch_average_speed_for_codes(arsenal, arsenal_codes)
        if usage is None or velocity is None or fastball_velocity <= 0:
            return None
        velocity_gap = fastball_velocity - velocity
        gap_bonus = max(18.0 - abs(velocity_gap - target_gap) * 2.0, 0.0)
        quality_score = self._family_savant_pitch_quality_score(savant_pitch_details, savant_codes)
        fallback_quality = 22.0 + gap_bonus
        score = (quality_score * 0.8) + (fallback_quality * 0.2)
        score += self._pitch_usage_modifier(usage, primary_fastball_usage)
        return round(max(0.0, min(99.0, score)), 3)

    def _family_savant_pitch_quality_score(
        self,
        savant_pitch_details: dict[str, dict[str, float]],
        pitch_codes: tuple[str, ...],
    ) -> float:
        weighted_score = 0.0
        total_weight = 0.0
        for pitch_code in pitch_codes:
            pitch_detail = savant_pitch_details.get(pitch_code)
            if not isinstance(pitch_detail, dict):
                continue
            weight = pitch_detail.get("pitches", 0.0) or 1.0
            weighted_score += self._savant_pitch_quality_score(pitch_detail, pitch_code=pitch_code) * weight
            total_weight += weight
        if total_weight <= 0:
            return 0.0
        return weighted_score / total_weight

    def _savant_pitch_quality_score(self, pitch_detail: dict[str, float] | None, *, pitch_code: str) -> float:
        if not isinstance(pitch_detail, dict):
            return 0.0
        xwoba = pitch_detail.get("xwoba", 0.0)
        xba = pitch_detail.get("xba", 0.0)
        xslg = pitch_detail.get("xslg", 0.0)
        hard_hit_percent = pitch_detail.get("hard_hit_percent", 0.0)
        barrel_percent = pitch_detail.get("brl_percent", 0.0)
        swings = pitch_detail.get("swings", 0.0)
        misses = pitch_detail.get("misses", 0.0)
        whiff_percent = (misses / swings) * 100.0 if swings > 0 else 0.0
        release_speed = pitch_detail.get("release_speed", 0.0)

        score = 0.0
        score += self._bounded_score(0.420 - xwoba, 0.220) * 35.0
        score += self._bounded_score(0.300 - xba, 0.160) * 15.0
        score += self._bounded_score(0.650 - xslg, 0.350) * 20.0
        score += self._bounded_score(whiff_percent - 15.0, 30.0) * 15.0
        score += self._bounded_score(55.0 - hard_hit_percent, 35.0) * 10.0
        score += self._bounded_score(12.0 - barrel_percent, 10.0) * 5.0
        if pitch_code == "FF":
            score += self._bounded_score(release_speed - 92.0, 6.0) * 8.0
        return max(0.0, min(99.0, score))

    def _pitch_usage_modifier(self, usage: float, primary_fastball_usage: float) -> float:
        modifier = self._bounded_score(usage - 8.0, 24.0) * 6.0
        if primary_fastball_usage > 0:
            if usage >= primary_fastball_usage:
                modifier += 10.0
            elif usage >= primary_fastball_usage * 0.75:
                modifier += 6.0
            elif usage >= primary_fastball_usage * 0.5:
                modifier += 3.0
        return modifier

    def _bounded_score(self, value: float, scale: float) -> float:
        if scale <= 0:
            return 0.0
        return max(0.0, min(1.0, value / scale))

    def _pitch_average_speed_for_codes(self, arsenal: dict[str, dict[str, Any]], pitch_codes: tuple[str, ...]) -> float | None:
        weighted_velocity = 0.0
        total_percentage = 0.0
        for pitch_code in pitch_codes:
            stat_line = arsenal.get(pitch_code)
            if not isinstance(stat_line, dict):
                continue
            percentage = self._as_float(stat_line.get("percentage"))
            velocity = self._as_float(stat_line.get("averageSpeed"))
            if percentage is None or velocity is None:
                continue
            weighted_velocity += percentage * velocity
            total_percentage += percentage
        if total_percentage <= 0:
            return None
        return round(weighted_velocity / total_percentage, 3)

    def _ratio(self, numerator: float, denominator: float) -> float | None:
        if denominator == 0:
            return None
        return numerator / denominator

    def _fetch_days_on_roster(self, player_id: int, group: str) -> int | None:
        for season in (PRIMARY_STAT_SEASON, FALLBACK_STAT_SEASON):
            payload = self._fetch_json(f"{MLB_STATS_API}/people/{player_id}/stats?stats=gameLog&group={group}&season={season}")
            stats = payload.get("stats", [])
            if not isinstance(stats, list) or not stats:
                continue
            first_stats = stats[0]
            if not isinstance(first_stats, dict):
                continue
            splits = first_stats.get("splits", [])
            if not isinstance(splits, list) or not splits:
                continue
            dates = [self._parse_date(split.get("date")) for split in splits if isinstance(split, dict)]
            dates = [game_date for game_date in dates if game_date is not None]
            if not dates:
                continue
            return (max(dates) - min(dates)).days + 1
        return None

    def _arsenal_percentage(self, arsenal: dict[str, dict[str, Any]], pitch_code: str) -> float | None:
        stat_line = arsenal.get(pitch_code)
        if not isinstance(stat_line, dict):
            return None
        raw_percentage = self._as_float(stat_line.get("percentage"))
        if raw_percentage is None:
            return None
        return round(raw_percentage * 100.0, 3)

    def _arsenal_percentage_for_codes(self, arsenal: dict[str, dict[str, Any]], pitch_codes: tuple[str, ...]) -> float | None:
        total_percentage = 0.0
        found_code = False
        for pitch_code in pitch_codes:
            stat_line = arsenal.get(pitch_code)
            if not isinstance(stat_line, dict):
                continue
            raw_percentage = self._as_float(stat_line.get("percentage"))
            if raw_percentage is None:
                continue
            total_percentage += raw_percentage
            found_code = True
        if not found_code:
            return None
        return round(total_percentage * 100.0, 3)

    def _fastball_velocity(self, arsenal: dict[str, dict[str, Any]], *, mode: str) -> float | None:
        fastball_codes = ("FF", "SI", "FC")
        if mode == "peak":
            velocities = [
                velocity
                for code in fastball_codes
                if code in arsenal and (velocity := self._as_float(arsenal[code].get("averageSpeed"))) is not None
            ]
            return round(max(velocities), 3) if velocities else None

        weighted_velocity = 0.0
        total_percentage = 0.0
        for code in fastball_codes:
            stat_line = arsenal.get(code)
            if not isinstance(stat_line, dict):
                continue
            percentage = self._as_float(stat_line.get("percentage"))
            velocity = self._as_float(stat_line.get("averageSpeed"))
            if percentage is None or velocity is None:
                continue
            weighted_velocity += percentage * velocity
            total_percentage += percentage
        if total_percentage <= 0:
            return None
        return round(weighted_velocity / total_percentage, 3)

    def _output_sort_key(self, player: dict[str, Any]) -> tuple[float, int, int, str]:
        projected_ip = player.get("projected_ip")
        projected_pa = player.get("projected_pa")
        if self._as_float(projected_ip) is not None:
            playing_time = self._as_float(projected_ip) or 0.0
        else:
            playing_time = self._as_float(projected_pa) or 0.0
        age = self._as_int(player.get("age")) or 999
        overall = self._as_int(player.get("overall_numeric")) or 0
        return (-playing_time, age, -overall, str(player.get("name") or ""))

    def _expected_flex_names(self, players: list[dict[str, Any]]) -> set[str]:
        grouped = {"SP": [], "RP": [], "C": [], "IF": [], "OF": []}
        for player in players:
            role = player.get("role")
            primary_position = player.get("primary_position")
            secondary_position = player.get("secondary_position")
            positions = {position for position in (primary_position, secondary_position) if isinstance(position, str) and position}
            if role in {"pitcher", "two_way"}:
                projected_ip = self._as_float(player.get("projected_ip")) or 0.0
                grouped["SP" if projected_ip >= 80 else "RP"].append(player)
            if role in {"hitter", "two_way"}:
                if "C" in positions:
                    grouped["C"].append(player)
                if positions & INFIELD_POSITIONS:
                    grouped["IF"].append(player)
                if positions & OUTFIELD_POSITIONS:
                    grouped["OF"].append(player)

        for group_name in grouped:
            grouped[group_name] = sorted(grouped[group_name], key=self._output_sort_key)

        selected_names = set()
        for group_name, count in (("SP", 4), ("RP", 5), ("C", 2), ("IF", 5), ("OF", 4)):
            picked_count = 0
            for player in grouped[group_name]:
                if player["name"] in selected_names:
                    continue
                selected_names.add(player["name"])
                picked_count += 1
                if picked_count >= count:
                    break

        flex_candidates: list[tuple[str, dict[str, Any]]] = []
        for group_name in ("C", "IF", "OF"):
            for player in grouped[group_name]:
                if player["name"] in selected_names:
                    continue
                flex_candidates.append((group_name, player))
                break

        chosen = sorted(
            flex_candidates,
            key=lambda item: (
                -(self._as_int(item[1].get("overall_numeric")) or 0),
                self._output_sort_key(item[1]),
            ),
        )[:2]
        return {player["name"] for _, player in chosen}

    def _expected_roster_counts(self, players: list[dict[str, Any]]) -> dict[str, int]:
        grouped = {"SP": [], "RP": [], "C": [], "IF": [], "OF": []}
        for player in players:
            role = player.get("role")
            primary_position = player.get("primary_position")
            secondary_position = player.get("secondary_position")
            positions = {position for position in (primary_position, secondary_position) if isinstance(position, str) and position}
            if role in {"pitcher", "two_way"}:
                projected_ip = self._as_float(player.get("projected_ip")) or 0.0
                grouped["SP" if projected_ip >= 80 else "RP"].append(player)
            if role in {"hitter", "two_way"}:
                if "C" in positions:
                    grouped["C"].append(player)
                if positions & INFIELD_POSITIONS:
                    grouped["IF"].append(player)
                if positions & OUTFIELD_POSITIONS:
                    grouped["OF"].append(player)

        for group_name in grouped:
            grouped[group_name] = sorted(grouped[group_name], key=self._output_sort_key)

        selected_names = set()
        counts = {"SP": 0, "RP": 0, "C": 0, "IF": 0, "OF": 0, "Flex": 0}
        for group_name, count in (("SP", 4), ("RP", 5), ("C", 2), ("IF", 5), ("OF", 4)):
            picked_count = 0
            for player in grouped[group_name]:
                if player["name"] in selected_names:
                    continue
                selected_names.add(player["name"])
                picked_count += 1
                if picked_count >= count:
                    break
            counts[group_name] = picked_count

        flex_candidates: list[tuple[str, dict[str, Any]]] = []
        for group_name in ("C", "IF", "OF"):
            for player in grouped[group_name]:
                if player["name"] in selected_names:
                    continue
                flex_candidates.append((group_name, player))
                break

        chosen = sorted(
            flex_candidates,
            key=lambda item: (
                -(self._as_int(item[1].get("overall_numeric")) or 0),
                self._output_sort_key(item[1]),
            ),
        )[:2]
        counts["Flex"] = len(chosen)
        counts["total"] = counts["SP"] + counts["RP"] + counts["C"] + counts["IF"] + counts["OF"] + counts["Flex"]
        return counts

    def _nested_str(self, payload: dict[str, Any], key: str, nested_key: str) -> str | None:
        nested = payload.get(key)
        if not isinstance(nested, dict):
            return None
        return self._as_str(nested.get(nested_key))

    def _as_int(self, value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                return int(cleaned)
            except ValueError:
                try:
                    return int(float(cleaned))
                except ValueError:
                    return None
        return None

    def _as_float(self, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _percentage(self, numerator: Any, denominator: Any) -> float | None:
        numerator_value = self._as_float(numerator)
        denominator_value = self._as_float(denominator)
        if numerator_value is None or denominator_value in (None, 0.0):
            return None
        return round((numerator_value / denominator_value) * 100.0, 3)

    def _as_percentage_string(self, value: Any) -> float | None:
        numeric = self._as_float(value)
        if numeric is None:
            return None
        return round(numeric * 100.0 if numeric <= 1.0 else numeric, 3)

    def _format_decimal(self, value: float) -> str:
        return f"{value:.3f}"

    def _as_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)

    def _parse_date(self, value: Any) -> date | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    def test_pitch_quality_derivation_boosts_prominent_secondary_pitch(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.36, "count": 360, "totalPitches": 1000, "averageSpeed": 95.0, "type": {"code": "FF"}},
            "SL": {"percentage": 0.34, "count": 340, "totalPitches": 1000, "averageSpeed": 84.0, "type": {"code": "SL"}},
            "CH": {"percentage": 0.12, "count": 120, "totalPitches": 1000, "averageSpeed": 86.5, "type": {"code": "CH"}},
        }
        savant_pitch_details = {
            "FF": {"xwoba": 0.305, "xba": 0.235, "xslg": 0.420, "hard_hit_percent": 37.0, "brl_percent": 7.0, "swings": 220.0, "misses": 45.0, "release_speed": 95.0},
            "SL": {"xwoba": 0.215, "xba": 0.170, "xslg": 0.280, "hard_hit_percent": 24.0, "brl_percent": 3.0, "swings": 190.0, "misses": 78.0, "release_speed": 84.0},
            "CH": {"xwoba": 0.290, "xba": 0.220, "xslg": 0.410, "hard_hit_percent": 34.0, "brl_percent": 6.0, "swings": 80.0, "misses": 20.0, "release_speed": 86.5},
        }

        metrics = self._derived_pitch_quality_metrics(arsenal, savant_pitch_details)

        self.assertIsNotNone(metrics["pitch_quality_4f"])
        self.assertIsNotNone(metrics["pitch_quality_sl"])
        self.assertGreater(metrics["pitch_quality_sl"], 65.0)
        self.assertGreater(metrics["pitch_quality_sl"], metrics["pitch_quality_ch"] or 0.0)

    def test_pitch_quality_derivation_supports_all_smb_pitch_families(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.22, "count": 220, "totalPitches": 1000, "averageSpeed": 95.5, "type": {"code": "FF"}},
            "SI": {"percentage": 0.16, "count": 160, "totalPitches": 1000, "averageSpeed": 94.0, "type": {"code": "SI"}},
            "FC": {"percentage": 0.11, "count": 110, "totalPitches": 1000, "averageSpeed": 90.5, "type": {"code": "FC"}},
            "CU": {"percentage": 0.10, "count": 100, "totalPitches": 1000, "averageSpeed": 80.0, "type": {"code": "CU"}},
            "CH": {"percentage": 0.12, "count": 120, "totalPitches": 1000, "averageSpeed": 85.8, "type": {"code": "CH"}},
            "FS": {"percentage": 0.10, "count": 100, "totalPitches": 1000, "averageSpeed": 84.7, "type": {"code": "FS"}},
            "SV": {"percentage": 0.11, "count": 110, "totalPitches": 1000, "averageSpeed": 83.4, "type": {"code": "SV"}},
            "SC": {"percentage": 0.08, "count": 80, "totalPitches": 1000, "averageSpeed": 81.6, "type": {"code": "SC"}},
        }
        savant_pitch_details = {
            "FF": {"xwoba": 0.245, "xba": 0.190, "xslg": 0.320, "hard_hit_percent": 28.0, "brl_percent": 4.0, "swings": 140.0, "misses": 38.0, "release_speed": 95.5, "pitches": 220.0},
            "SI": {"xwoba": 0.255, "xba": 0.205, "xslg": 0.340, "hard_hit_percent": 30.0, "brl_percent": 4.5, "swings": 95.0, "misses": 22.0, "release_speed": 94.0, "pitches": 160.0},
            "FC": {"xwoba": 0.235, "xba": 0.185, "xslg": 0.305, "hard_hit_percent": 26.0, "brl_percent": 3.5, "swings": 88.0, "misses": 27.0, "release_speed": 90.5, "pitches": 110.0},
            "CU": {"xwoba": 0.210, "xba": 0.165, "xslg": 0.270, "hard_hit_percent": 23.0, "brl_percent": 2.5, "swings": 82.0, "misses": 34.0, "release_speed": 80.0, "pitches": 100.0},
            "CH": {"xwoba": 0.225, "xba": 0.175, "xslg": 0.290, "hard_hit_percent": 25.0, "brl_percent": 3.0, "swings": 96.0, "misses": 36.0, "release_speed": 85.8, "pitches": 120.0},
            "FS": {"xwoba": 0.205, "xba": 0.160, "xslg": 0.255, "hard_hit_percent": 22.0, "brl_percent": 2.0, "swings": 78.0, "misses": 31.0, "release_speed": 84.7, "pitches": 100.0},
            "SV": {"xwoba": 0.215, "xba": 0.168, "xslg": 0.275, "hard_hit_percent": 24.0, "brl_percent": 2.8, "swings": 89.0, "misses": 35.0, "release_speed": 83.4, "pitches": 110.0},
            "SC": {"xwoba": 0.220, "xba": 0.172, "xslg": 0.285, "hard_hit_percent": 24.5, "brl_percent": 2.7, "swings": 62.0, "misses": 22.0, "release_speed": 81.6, "pitches": 80.0},
        }

        metrics = self._derived_pitch_quality_metrics(arsenal, savant_pitch_details)

        for spec in ELITE_PITCH_SPECS.values():
            self.assertIsNotNone(metrics[str(spec["metric_key"])])

    def test_pitch_quality_derivation_prioritizes_quality_over_usage(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.45, "count": 450, "totalPitches": 1000, "averageSpeed": 95.0, "type": {"code": "FF"}},
            "SL": {"percentage": 0.30, "count": 300, "totalPitches": 1000, "averageSpeed": 84.5, "type": {"code": "SL"}},
            "CH": {"percentage": 0.22, "count": 220, "totalPitches": 1000, "averageSpeed": 86.0, "type": {"code": "CH"}},
        }
        savant_pitch_details = {
            "SL": {"xwoba": 0.195, "xba": 0.145, "xslg": 0.240, "hard_hit_percent": 20.0, "brl_percent": 2.0, "swings": 210.0, "misses": 92.0, "release_speed": 84.5},
            "CH": {"xwoba": 0.330, "xba": 0.255, "xslg": 0.500, "hard_hit_percent": 42.0, "brl_percent": 9.0, "swings": 160.0, "misses": 32.0, "release_speed": 86.0},
        }

        metrics = self._derived_pitch_quality_metrics(arsenal, savant_pitch_details)

        self.assertGreater(metrics["pitch_quality_sl"], metrics["pitch_quality_ch"] or 0.0)

    def test_pitch_quality_derivation_handles_missing_arsenal_data(self) -> None:
        metrics = self._derived_pitch_quality_metrics({})

        self.assertEqual(
            metrics,
            {
                "pitch_quality_4f": None,
                "pitch_quality_2f": None,
                "pitch_quality_cf": None,
                "pitch_quality_cb": None,
                "pitch_quality_ch": None,
                "pitch_quality_fk": None,
                "pitch_quality_sl": None,
                "pitch_quality_sb": None,
            },
        )


if __name__ == "__main__":
    unittest.main()