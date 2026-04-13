from __future__ import annotations

import csv
import json
import ssl
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from smb4_mlb_ratings.cli import main
from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
    build_baseball_reference_pitcher_rows,
    build_mixed_source_manifest,
    build_roster_rows,
    build_savant_fielding_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
    fetch_team_players,
)

try:
    import pytest  # type: ignore[import-not-found]
except ImportError:
    pytest = None

if pytest is not None:
    pytestmark = pytest.mark.integration


TEAM_ID = 141
TEAM_ABBREVIATION = "TOR"
TIGERS_TEAM_ID = 116
TIGERS_TEAM_ABBREVIATION = "DET"
ROSTER_SEASON = 2026
CURRENT_STAT_SEASON = 2026
PREVIOUS_STAT_SEASON = 2025
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
            self.players = fetch_team_players(
                TEAM_ID,
                team_abbreviation=TEAM_ABBREVIATION,
                roster_season=ROSTER_SEASON,
                primary_stat_season=CURRENT_STAT_SEASON,
                fallback_stat_season=CURRENT_STAT_SEASON,
                ssl_context=self.ssl_context,
                min_players=22,
            )
            previous_players = fetch_team_players(
                TEAM_ID,
                team_abbreviation=TEAM_ABBREVIATION,
                roster_season=ROSTER_SEASON,
                primary_stat_season=PREVIOUS_STAT_SEASON,
                fallback_stat_season=PREVIOUS_STAT_SEASON,
                ssl_context=self.ssl_context,
                min_players=22,
            )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            self.skipTest(f"Live MLB Stats API unavailable: {error}")

        manifest_path = self._write_fixture_files(
            self.players,
            previous_players,
            team_abbreviation=TEAM_ABBREVIATION,
            file_prefix="bluejays",
            include_inactive=True,
        )

        normalized_path = self.output / "tor_normalized.json"
        filtered_normalized_path = self.output / "tor_filtered_normalized.json"
        ratings_path = self.output / "tor_ratings.json"
        structured_path = self.output / "tor_structured"
        roster_path = self.output / "tor_roster.json"
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

        expected_names = self._expected_live_output_names(self.players, previous_players)
        expected_name_set = set(expected_names)
        fallback_only_names = self._expected_roster_only_fallback_names(self.players, previous_players)
        inactive_name = str(self._inactive_player()["name"])
        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        normalized_players = normalized_payload["players"]
        normalized_names = {str(player["name"]) for player in normalized_players}
        self.assertTrue(expected_name_set.issubset(normalized_names))
        self.assertIn(inactive_name, normalized_names)
        inactive_player = next(player for player in normalized_players if player["name"] == inactive_name)
        self.assertFalse(inactive_player["active"])
        self.assertEqual(inactive_player["team"], "NYY")
        self.assertTrue(all(player["name"] and player["primary_position"] for player in normalized_players))
        self.assertTrue(all(player["samples"] for player in normalized_players))
        self.assertTrue(all(player["metrics"] for player in normalized_players))

        filtered_normalized_payload = json.loads(filtered_normalized_path.read_text(encoding="utf-8"))
        filtered_normalized_players = filtered_normalized_payload["players"]
        self.assertTrue(all(player["team"] == "TOR" for player in filtered_normalized_players))
        self.assertTrue(all(player["metadata"]["source"] == "mixed" for player in filtered_normalized_players))
        self.assertTrue({player["name"] for player in filtered_normalized_players}.issubset(expected_name_set))
        self.assertTrue(fallback_only_names.issubset({player["name"] for player in filtered_normalized_players}))
        self.assertNotIn(inactive_name, {player["name"] for player in filtered_normalized_players})

        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertTrue(all(player["team"] == "TOR" for player in ratings_payload))
        self.assertTrue(all(1 <= player["overall_numeric"] <= 99 for player in ratings_payload if player["overall_numeric"] is not None))
        self.assertEqual(
            sorted(player["name"] for player in ratings_payload),
            sorted(player["name"] for player in filtered_normalized_players),
        )
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
            self.assertEqual(len(grouped_slots), len({slot["player"]["name"] for slot in grouped_slots}))

        flex_names = {slot["player"]["name"] for slot in roster_slots if slot["slot_type"].startswith("flex_")}
        self.assertEqual(len(flex_names), expected_counts["Flex"])

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

    def test_detroit_tigers_ingest_rate_pipeline(self) -> None:
        try:
            players = fetch_team_players(
                TIGERS_TEAM_ID,
                team_abbreviation=TIGERS_TEAM_ABBREVIATION,
                roster_season=ROSTER_SEASON,
                primary_stat_season=CURRENT_STAT_SEASON,
                fallback_stat_season=CURRENT_STAT_SEASON,
                ssl_context=self.ssl_context,
                min_players=22,
            )
            previous_players = fetch_team_players(
                TIGERS_TEAM_ID,
                team_abbreviation=TIGERS_TEAM_ABBREVIATION,
                roster_season=ROSTER_SEASON,
                primary_stat_season=PREVIOUS_STAT_SEASON,
                fallback_stat_season=PREVIOUS_STAT_SEASON,
                ssl_context=self.ssl_context,
                min_players=22,
            )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            self.skipTest(f"Live MLB Stats API unavailable: {error}")

        manifest_path = self._write_fixture_files(
            players,
            previous_players,
            team_abbreviation=TIGERS_TEAM_ABBREVIATION,
            file_prefix="tigers",
            include_inactive=False,
        )

        filtered_normalized_path = self.output / "det_filtered_normalized.json"
        ratings_path = self.output / "det_ratings.json"

        ingest_rate_result = main(
            [
                "ingest-rate",
                str(manifest_path),
                str(ratings_path),
                "--team",
                TIGERS_TEAM_ABBREVIATION,
                "--normalized-output",
                str(filtered_normalized_path),
            ]
        )
        self.assertEqual(ingest_rate_result, 0)

        normalized_payload = json.loads(filtered_normalized_path.read_text(encoding="utf-8"))
        normalized_players = normalized_payload["players"]
        self.assertTrue(normalized_players)
        self.assertTrue(all(player["team"] == TIGERS_TEAM_ABBREVIATION for player in normalized_players))

        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertTrue(ratings_payload)
        self.assertTrue(all(player["team"] == TIGERS_TEAM_ABBREVIATION for player in ratings_payload))
        self.assertTrue(all(1 <= player["overall_numeric"] <= 99 for player in ratings_payload if player["overall_numeric"] is not None))

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            raise ValueError("CSV fixtures require at least one row")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_fixture_files(
        self,
        current_players: list[dict[str, object]],
        previous_players: list[dict[str, object]],
        *,
        team_abbreviation: str,
        file_prefix: str,
        include_inactive: bool,
    ) -> Path:
        inactive_players = [self._inactive_player()] if include_inactive else []
        roster_file = self.exports / f"{file_prefix}_roster_2026.csv"
        current_savant_hitters_file = self.exports / f"{file_prefix}_savant_hitters_2026.csv"
        current_savant_pitchers_file = self.exports / f"{file_prefix}_savant_pitchers_2026.csv"
        current_savant_fielding_file = self.exports / f"{file_prefix}_savant_fielding_2026.csv"
        current_baseball_reference_hitters_file = self.exports / f"{file_prefix}_bref_hitters_2026.csv"
        current_baseball_reference_pitchers_file = self.exports / f"{file_prefix}_bref_pitchers_2026.csv"
        previous_savant_hitters_file = self.exports / f"{file_prefix}_savant_hitters_2025.csv"
        previous_savant_pitchers_file = self.exports / f"{file_prefix}_savant_pitchers_2025.csv"
        previous_savant_fielding_file = self.exports / f"{file_prefix}_savant_fielding_2025.csv"
        previous_baseball_reference_hitters_file = self.exports / f"{file_prefix}_bref_hitters_2025.csv"
        previous_baseball_reference_pitchers_file = self.exports / f"{file_prefix}_bref_pitchers_2025.csv"
        manifest_path = self.exports / f"{file_prefix}_manifest.json"

        self._write_csv(
            roster_file,
            build_roster_rows(current_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            current_savant_hitters_file,
            build_savant_hitter_rows(current_players, team_abbreviation=team_abbreviation, extra_players=inactive_players),
        )
        self._write_csv(
            current_savant_pitchers_file,
            build_savant_pitcher_rows(current_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            current_savant_fielding_file,
            build_savant_fielding_rows(current_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            current_baseball_reference_hitters_file,
            build_baseball_reference_hitter_rows(
                current_players,
                team_abbreviation=team_abbreviation,
                extra_players=inactive_players,
            ),
        )
        self._write_csv(
            current_baseball_reference_pitchers_file,
            build_baseball_reference_pitcher_rows(current_players, team_abbreviation=team_abbreviation),
        )

        self._write_csv(
            previous_savant_hitters_file,
            build_savant_hitter_rows(previous_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            previous_savant_pitchers_file,
            build_savant_pitcher_rows(previous_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            previous_savant_fielding_file,
            build_savant_fielding_rows(previous_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            previous_baseball_reference_hitters_file,
            build_baseball_reference_hitter_rows(previous_players, team_abbreviation=team_abbreviation),
        )
        self._write_csv(
            previous_baseball_reference_pitchers_file,
            build_baseball_reference_pitcher_rows(previous_players, team_abbreviation=team_abbreviation),
        )
        manifest = build_mixed_source_manifest(
            team_abbreviation=team_abbreviation,
            roster_season=ROSTER_SEASON,
            current_year=CURRENT_STAT_SEASON,
            roster_file=roster_file.name,
            savant_hitters_file=current_savant_hitters_file.name,
            savant_pitchers_file=current_savant_pitchers_file.name,
            savant_fielding_file=current_savant_fielding_file.name,
            baseball_reference_hitters_file=current_baseball_reference_hitters_file.name,
            baseball_reference_pitchers_file=current_baseball_reference_pitchers_file.name,
            previous_year=PREVIOUS_STAT_SEASON,
            previous_savant_hitters_file=previous_savant_hitters_file.name,
            previous_savant_pitchers_file=previous_savant_pitchers_file.name,
            previous_savant_fielding_file=previous_savant_fielding_file.name,
            previous_baseball_reference_hitters_file=previous_baseball_reference_hitters_file.name,
            previous_baseball_reference_pitchers_file=previous_baseball_reference_pitchers_file.name,
        )
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return manifest_path

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

    def _expected_live_output_names(
        self,
        current_players: list[dict[str, Any]],
        previous_players: list[dict[str, Any]],
    ) -> list[str]:
        previous_by_name = {str(player.get("name") or ""): player for player in previous_players}
        expected_names: list[str] = []
        for player in current_players:
            name = str(player.get("name") or "")
            if not name:
                continue
            if self._has_live_sample(player) or self._has_live_sample(previous_by_name.get(name, {})):
                expected_names.append(name)
        return sorted(expected_names)

    def _expected_roster_only_fallback_names(
        self,
        current_players: list[dict[str, Any]],
        previous_players: list[dict[str, Any]],
    ) -> set[str]:
        previous_by_name = {str(player.get("name") or ""): player for player in previous_players}
        fallback_names: set[str] = set()
        for player in current_players:
            name = str(player.get("name") or "")
            if not name:
                continue
            if self._has_live_sample(player):
                continue
            if self._has_live_sample(previous_by_name.get(name, {})):
                fallback_names.add(name)
        return fallback_names

    def _has_live_sample(self, player: dict[str, Any]) -> bool:
        player_type = player.get("type") or player.get("role")
        if player_type == "pitcher":
            return (self._as_int(player.get("batters_faced")) or 0) > 0
        if player_type == "hitter":
            return (self._as_int(player.get("plate_appearances")) or 0) > 0
        return ((self._as_int(player.get("batters_faced")) or 0) > 0) or ((self._as_int(player.get("plate_appearances")) or 0) > 0)

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

    def _as_str(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return str(value)


if __name__ == "__main__":
    unittest.main()