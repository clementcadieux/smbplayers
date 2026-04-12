from __future__ import annotations

import csv
import json
import ssl
import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

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
INFIELD_POSITIONS = {"1B", "2B", "3B", "SS", "IF"}
OUTFIELD_POSITIONS = {"LF", "CF", "RF", "OF"}


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
                }
            )
        return rows

    def _savant_hitter_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players + [self._inactive_player()]:
            if player["type"] != "hitter":
                continue
            advanced = player.get("advanced_hitting") if isinstance(player.get("advanced_hitting"), dict) else {}
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
                    "SI %": self._arsenal_percentage(arsenal, "SI"),
                    "FC %": self._arsenal_percentage(arsenal, "FC"),
                    "SL %": self._arsenal_percentage(arsenal, "SL"),
                    "CU %": self._arsenal_percentage(arsenal, "CU"),
                    "CH %": self._arsenal_percentage(arsenal, "CH"),
                    "FS %": self._arsenal_percentage(arsenal, "FS"),
                    "SV %": self._arsenal_percentage(arsenal, "SV"),
                    "SwStr %": self._as_percentage_string(advanced.get("whiffPercentage")),
                    "BB %": self._percentage(player["walks"], player["batters_faced"]),
                    "Strike %": self._as_percentage_string(player.get("strike_percentage")),
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


if __name__ == "__main__":
    unittest.main()