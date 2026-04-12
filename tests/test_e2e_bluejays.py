from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.cli import main

try:
    import pytest
except ImportError:
    pytest = None

if pytest is not None:
    pytestmark = pytest.mark.integration


class BlueJaysPipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.exports = self.root / "exports"
        self.output = self.root / "output"
        self.exports.mkdir(parents=True, exist_ok=True)
        self.output.mkdir(parents=True, exist_ok=True)
        self.players = self._build_player_specs()
        self._write_fixture_files()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_blue_jays_full_pipeline(self) -> None:
        normalized_path = self.output / "tor_normalized.json"
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
                "--normalized-output",
                str(normalized_path),
                "--structured-output",
                str(structured_path),
            ]
        )
        self.assertEqual(ingest_rate_result, 0)

        rank_result = main(["rank", str(ratings_path), str(roster_path)])
        self.assertEqual(rank_result, 0)

        normalized_payload = json.loads(normalized_path.read_text(encoding="utf-8"))
        normalized_players = normalized_payload["players"]
        self.assertEqual(len(normalized_players), len(self.players))
        self.assertTrue(all(player["team"] == "TOR" for player in normalized_players))
        self.assertTrue(all(player["name"] and player["primary_position"] for player in normalized_players))
        self.assertTrue(all(player["samples"] for player in normalized_players))
        self.assertTrue(all(player["metrics"] for player in normalized_players))

        ratings_payload = json.loads(ratings_path.read_text(encoding="utf-8"))
        self.assertEqual(len(ratings_payload), len(self.players))
        self.assertTrue(all(player["team"] == "TOR" for player in ratings_payload))
        self.assertTrue(all(1 <= player["overall_numeric"] <= 99 for player in ratings_payload if player["overall_numeric"] is not None))

        structured_team_path = structured_path / "AL" / "East" / "TOR.json"
        self.assertTrue(structured_team_path.exists())
        structured_team_payload = json.loads(structured_team_path.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(player["name"] for player in structured_team_payload["players"]),
            sorted(player["name"] for player in ratings_payload),
        )
        index_payload = json.loads((structured_path / "index.json").read_text(encoding="utf-8"))
        self.assertEqual(index_payload["AL"]["East"][0]["team"], "TOR")

        roster_payload = json.loads(roster_path.read_text(encoding="utf-8"))
        team_roster = roster_payload["teams"][0]
        self.assertEqual(team_roster["team"], "TOR")
        roster_slots = team_roster["recommended_roster"]
        self.assertEqual(len(roster_slots), 22)
        self.assertEqual(sum(slot["slot_type"].startswith("sp") for slot in roster_slots), 4)
        self.assertEqual(sum(slot["slot_type"].startswith("rp") for slot in roster_slots), 5)
        self.assertEqual(sum(slot["slot_type"].startswith("if") for slot in roster_slots), 5)
        self.assertEqual(sum(slot["slot_type"].startswith("of") for slot in roster_slots), 4)
        self.assertEqual(sum(slot["slot_type"].startswith("c") for slot in roster_slots), 2)
        self.assertEqual(sum(slot["slot_type"].startswith("flex_") for slot in roster_slots), 2)

        catcher_slots = [slot for slot in roster_slots if slot["slot_type"].startswith("c") and not slot["slot_type"].startswith("flex_")]
        self.assertEqual([slot["player"]["name"] for slot in catcher_slots], ["Catcher Prospect", "Catcher Veteran"])

        flex_names = {slot["player"]["name"] for slot in roster_slots if slot["slot_type"].startswith("flex_")}
        self.assertEqual(flex_names, {"Sixth Infielder", "Fifth Outfielder"})

        structured_flex_names = {
            slot["player"]["name"]
            for slot in structured_team_payload["recommended_roster"]
            if slot["slot_type"].startswith("flex_")
        }
        self.assertEqual(structured_flex_names, flex_names)

    def _write_csv(self, path: Path, rows: list[dict[str, object]]) -> None:
        if not rows:
            raise ValueError("CSV fixtures require at least one row")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row)

    def _write_fixture_files(self) -> None:
        self._write_csv(self.exports / "bluejays_roster_2025.csv", self._roster_rows())
        self._write_csv(self.exports / "bluejays_savant_hitters_2025.csv", self._savant_hitter_rows())
        self._write_csv(self.exports / "bluejays_savant_pitchers_2025.csv", self._savant_pitcher_rows())
        self._write_csv(self.exports / "bluejays_savant_running_2025.csv", self._running_rows())
        self._write_csv(self.exports / "bluejays_bref_hitters_2025.csv", self._bref_hitter_rows())
        self._write_csv(self.exports / "bluejays_bref_pitchers_2025.csv", self._bref_pitcher_rows())

        manifest = {
            "source": "mixed",
            "seasons": {
                "current": {
                    "year": 2025,
                    "sources": {
                        "baseball_reference": {
                            "files": {
                                "hitters": "bluejays_bref_hitters_2025.csv",
                                "pitchers": "bluejays_bref_pitchers_2025.csv",
                            }
                        },
                        "baseball_savant": {
                            "files": {
                                "roster": "bluejays_roster_2025.csv",
                                "hitters": "bluejays_savant_hitters_2025.csv",
                                "pitchers": "bluejays_savant_pitchers_2025.csv",
                                "running": "bluejays_savant_running_2025.csv",
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
                "team": "TOR",
                "age": player["age"],
                "position": player["position"],
                "bats": player["bats"],
                "throws": player["throws"],
            }
            for player in self.players
        ]

    def _savant_hitter_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "hitter":
                continue
            pa = player["pa"]
            average = player["avg"]
            obp = player["obp"]
            slugging = player["slg"]
            hits = round(pa * average)
            walks = round(pa * 0.09)
            hit_by_pitch = 4
            strikeouts = round(pa * player["k_rate"])
            doubles = max(18, round(pa * 0.05))
            triples = 2 if player["position"] in {"CF", "RF"} else 1
            home_runs = player["hr"]
            stolen_bases = player["sb"]
            caught_stealing = max(1, round(stolen_bases * 0.18))
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": "TOR",
                    "position": player["position"],
                    "PA": pa,
                    "ISO": player["iso"],
                    "HR": home_runs,
                    "Barrel %": player["barrel_rate"] * 100,
                    "SLG": slugging,
                    "AVG": average,
                    "OBP": obp,
                    "K %": player["k_rate"] * 100,
                    "Contact %": player["contact_rate"] * 100,
                    "Two Strike Contact %": player["two_strike_contact"] * 100,
                    "Avg Exit Velocity": player["exit_velocity"],
                    "2B": doubles,
                    "3B": triples,
                    "SB": stolen_bases,
                    "CS": caught_stealing,
                    "BB": walks,
                    "HBP": hit_by_pitch,
                    "H": hits,
                    "Sprint Speed": player["sprint_speed"],
                }
            )
        return rows

    def _bref_hitter_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "hitter":
                continue
            pa = player["pa"]
            at_bats = max(pa - round(pa * 0.1), 1)
            hits = round(at_bats * player["avg"])
            doubles = max(18, round(pa * 0.05))
            triples = 2 if player["position"] in {"CF", "RF"} else 1
            home_runs = player["hr"]
            walks = round(pa * 0.09)
            strikeouts = round(pa * player["k_rate"])
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": "TOR",
                    "position": player["position"],
                    "PA": pa,
                    "AB": at_bats,
                    "H": hits,
                    "2B": doubles,
                    "3B": triples,
                    "HR": home_runs,
                    "BB": walks,
                    "SO": strikeouts,
                    "HBP": 4,
                    "SB": player["sb"],
                    "CS": max(1, round(player["sb"] * 0.18)),
                    "BA": player["avg"],
                    "OBP": player["obp"],
                    "SLG": player["slg"],
                    "BsR": round((player["sprint_speed"] - 24.0) * 0.8, 2),
                }
            )
        return rows

    def _running_rows(self) -> list[dict[str, object]]:
        return [
            {
                "player_id": player["player_id"],
                "player_name": player["name"],
                "Sprint Speed": player["sprint_speed"],
                "Baserunning Value": round((player["sprint_speed"] - 24.0) * 0.7, 2),
                "Baserunning Opportunities": max(player["pa"] - 100, 80),
            }
            for player in self.players
            if player["type"] == "hitter"
        ]

    def _savant_pitcher_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "pitcher":
                continue
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": "TOR",
                    "position": "P",
                    "BF": player["bf"],
                    "Pitches": round(player["bf"] * 4.05),
                    "Avg Fastball Velocity": player["fbv"],
                    "Peak Fastball Velocity": player["fbv"] + 2.0,
                    "FF %": player["fastball_usage"] * 100,
                    "SwStr %": player["swstr"] * 100,
                    "Chase %": player["chase"] * 100,
                    "BB %": player["bb_rate"] * 100,
                    "Strike %": player["strike_pct"] * 100,
                    "Zone %": player["zone_pct"] * 100,
                    "First Pitch Strike %": player["fps"] * 100,
                    "Horizontal Break": player["hbreak"],
                    "Induced Vertical Break": player["ivb"],
                    "Hard Hit %": player["hard_hit"] * 100,
                    "SL %": player["slider_usage"] * 100,
                    "CH %": player["change_usage"] * 100,
                    "CU %": player["curve_usage"] * 100,
                }
            )
        return rows

    def _bref_pitcher_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for player in self.players:
            if player["type"] != "pitcher":
                continue
            rows.append(
                {
                    "player_id": player["player_id"],
                    "player_name": player["name"],
                    "team": "TOR",
                    "position": "P",
                    "BF": player["bf"],
                    "BB": round(player["bf"] * player["bb_rate"]),
                    "SO": round(player["bf"] * player["k_rate"]),
                    "HR": max(4, round(player["bf"] * 0.02)),
                    "H": max(40, round(player["bf"] * 0.22)),
                    "IP": player["ip"],
                    "Pitches": round(player["bf"] * 4.05),
                    "Strikes": round(player["bf"] * 4.05 * player["strike_pct"]),
                }
            )
        return rows

    def _build_player_specs(self) -> list[dict[str, object]]:
        return [
            {"player_id": 1001, "name": "Catcher Prospect", "type": "hitter", "position": "C", "age": 24, "bats": "R", "throws": "R", "pa": 420, "avg": 0.268, "obp": 0.335, "slg": 0.455, "iso": 0.187, "hr": 19, "sb": 3, "k_rate": 0.19, "contact_rate": 0.79, "two_strike_contact": 0.67, "barrel_rate": 0.095, "exit_velocity": 89.8, "sprint_speed": 25.4},
            {"player_id": 1002, "name": "Catcher Veteran", "type": "hitter", "position": "C", "age": 31, "bats": "L", "throws": "R", "pa": 420, "avg": 0.262, "obp": 0.328, "slg": 0.441, "iso": 0.179, "hr": 17, "sb": 2, "k_rate": 0.20, "contact_rate": 0.78, "two_strike_contact": 0.65, "barrel_rate": 0.089, "exit_velocity": 89.1, "sprint_speed": 25.0},
            {"player_id": 1003, "name": "Third Catcher", "type": "hitter", "position": "C", "age": 29, "bats": "R", "throws": "R", "pa": 240, "avg": 0.231, "obp": 0.298, "slg": 0.372, "iso": 0.141, "hr": 9, "sb": 1, "k_rate": 0.24, "contact_rate": 0.72, "two_strike_contact": 0.58, "barrel_rate": 0.061, "exit_velocity": 86.8, "sprint_speed": 24.1},
            {"player_id": 1101, "name": "First Base Regular", "type": "hitter", "position": "1B", "age": 27, "bats": "L", "throws": "R", "pa": 595, "avg": 0.279, "obp": 0.354, "slg": 0.503, "iso": 0.224, "hr": 27, "sb": 4, "k_rate": 0.21, "contact_rate": 0.77, "two_strike_contact": 0.63, "barrel_rate": 0.111, "exit_velocity": 91.4, "sprint_speed": 25.6},
            {"player_id": 1102, "name": "Second Base Regular", "type": "hitter", "position": "2B", "age": 26, "bats": "R", "throws": "R", "pa": 560, "avg": 0.284, "obp": 0.348, "slg": 0.472, "iso": 0.188, "hr": 18, "sb": 14, "k_rate": 0.18, "contact_rate": 0.81, "two_strike_contact": 0.69, "barrel_rate": 0.084, "exit_velocity": 88.7, "sprint_speed": 27.8},
            {"player_id": 1103, "name": "Third Base Regular", "type": "hitter", "position": "3B", "age": 29, "bats": "R", "throws": "R", "pa": 548, "avg": 0.271, "obp": 0.341, "slg": 0.486, "iso": 0.215, "hr": 24, "sb": 5, "k_rate": 0.22, "contact_rate": 0.76, "two_strike_contact": 0.62, "barrel_rate": 0.102, "exit_velocity": 90.5, "sprint_speed": 26.1},
            {"player_id": 1104, "name": "Shortstop Regular", "type": "hitter", "position": "SS", "age": 25, "bats": "L", "throws": "R", "pa": 610, "avg": 0.287, "obp": 0.357, "slg": 0.478, "iso": 0.191, "hr": 21, "sb": 22, "k_rate": 0.17, "contact_rate": 0.83, "two_strike_contact": 0.71, "barrel_rate": 0.082, "exit_velocity": 88.3, "sprint_speed": 28.6},
            {"player_id": 1105, "name": "Utility Infielder", "type": "hitter", "position": "IF", "age": 28, "bats": "R", "throws": "R", "pa": 430, "avg": 0.259, "obp": 0.326, "slg": 0.421, "iso": 0.162, "hr": 14, "sb": 9, "k_rate": 0.20, "contact_rate": 0.78, "two_strike_contact": 0.64, "barrel_rate": 0.071, "exit_velocity": 87.9, "sprint_speed": 27.0},
            {"player_id": 1106, "name": "Sixth Infielder", "type": "hitter", "position": "SS", "age": 23, "bats": "L", "throws": "R", "pa": 330, "avg": 0.291, "obp": 0.364, "slg": 0.505, "iso": 0.214, "hr": 15, "sb": 18, "k_rate": 0.16, "contact_rate": 0.84, "two_strike_contact": 0.72, "barrel_rate": 0.101, "exit_velocity": 90.2, "sprint_speed": 28.9},
            {"player_id": 1201, "name": "Left Field Regular", "type": "hitter", "position": "LF", "age": 27, "bats": "R", "throws": "R", "pa": 570, "avg": 0.276, "obp": 0.345, "slg": 0.492, "iso": 0.216, "hr": 25, "sb": 11, "k_rate": 0.21, "contact_rate": 0.77, "two_strike_contact": 0.63, "barrel_rate": 0.108, "exit_velocity": 91.0, "sprint_speed": 27.2},
            {"player_id": 1202, "name": "Center Field Regular", "type": "hitter", "position": "CF", "age": 24, "bats": "L", "throws": "R", "pa": 602, "avg": 0.283, "obp": 0.351, "slg": 0.481, "iso": 0.198, "hr": 20, "sb": 24, "k_rate": 0.18, "contact_rate": 0.82, "two_strike_contact": 0.70, "barrel_rate": 0.087, "exit_velocity": 89.0, "sprint_speed": 29.1},
            {"player_id": 1203, "name": "Right Field Regular", "type": "hitter", "position": "RF", "age": 28, "bats": "R", "throws": "R", "pa": 556, "avg": 0.274, "obp": 0.343, "slg": 0.488, "iso": 0.214, "hr": 23, "sb": 10, "k_rate": 0.20, "contact_rate": 0.79, "two_strike_contact": 0.65, "barrel_rate": 0.099, "exit_velocity": 90.7, "sprint_speed": 27.4},
            {"player_id": 1204, "name": "Fourth Outfielder", "type": "hitter", "position": "OF", "age": 26, "bats": "L", "throws": "L", "pa": 410, "avg": 0.267, "obp": 0.333, "slg": 0.436, "iso": 0.169, "hr": 14, "sb": 12, "k_rate": 0.19, "contact_rate": 0.80, "two_strike_contact": 0.66, "barrel_rate": 0.074, "exit_velocity": 88.1, "sprint_speed": 28.0},
            {"player_id": 1205, "name": "Fifth Outfielder", "type": "hitter", "position": "RF", "age": 25, "bats": "R", "throws": "R", "pa": 315, "avg": 0.286, "obp": 0.358, "slg": 0.514, "iso": 0.228, "hr": 16, "sb": 16, "k_rate": 0.17, "contact_rate": 0.83, "two_strike_contact": 0.70, "barrel_rate": 0.106, "exit_velocity": 90.8, "sprint_speed": 28.7},
            {"player_id": 2001, "name": "Starter Ace", "type": "pitcher", "position": "P", "age": 28, "bats": "R", "throws": "R", "bf": 760, "ip": "185.0", "fbv": 96.8, "fastball_usage": 0.49, "swstr": 0.145, "chase": 0.335, "bb_rate": 0.062, "k_rate": 0.283, "strike_pct": 0.662, "zone_pct": 0.502, "fps": 0.634, "hbreak": 15.1, "ivb": 17.5, "hard_hit": 0.318, "slider_usage": 0.24, "change_usage": 0.13, "curve_usage": 0.08},
            {"player_id": 2002, "name": "Starter Two", "type": "pitcher", "position": "P", "age": 30, "bats": "L", "throws": "L", "bf": 720, "ip": "176.0", "fbv": 95.7, "fastball_usage": 0.47, "swstr": 0.136, "chase": 0.322, "bb_rate": 0.068, "k_rate": 0.269, "strike_pct": 0.651, "zone_pct": 0.493, "fps": 0.621, "hbreak": 14.6, "ivb": 17.1, "hard_hit": 0.327, "slider_usage": 0.22, "change_usage": 0.15, "curve_usage": 0.09},
            {"player_id": 2003, "name": "Starter Three", "type": "pitcher", "position": "P", "age": 26, "bats": "R", "throws": "R", "bf": 690, "ip": "168.1", "fbv": 95.1, "fastball_usage": 0.46, "swstr": 0.129, "chase": 0.315, "bb_rate": 0.071, "k_rate": 0.255, "strike_pct": 0.646, "zone_pct": 0.487, "fps": 0.615, "hbreak": 14.2, "ivb": 16.9, "hard_hit": 0.333, "slider_usage": 0.21, "change_usage": 0.14, "curve_usage": 0.1},
            {"player_id": 2004, "name": "Starter Four", "type": "pitcher", "position": "P", "age": 24, "bats": "R", "throws": "R", "bf": 650, "ip": "160.0", "fbv": 94.6, "fastball_usage": 0.45, "swstr": 0.121, "chase": 0.304, "bb_rate": 0.074, "k_rate": 0.241, "strike_pct": 0.639, "zone_pct": 0.481, "fps": 0.607, "hbreak": 13.8, "ivb": 16.5, "hard_hit": 0.341, "slider_usage": 0.2, "change_usage": 0.14, "curve_usage": 0.1},
            {"player_id": 2101, "name": "Reliever One", "type": "pitcher", "position": "P", "age": 29, "bats": "R", "throws": "R", "bf": 260, "ip": "62.0", "fbv": 97.4, "fastball_usage": 0.55, "swstr": 0.161, "chase": 0.349, "bb_rate": 0.083, "k_rate": 0.312, "strike_pct": 0.652, "zone_pct": 0.482, "fps": 0.626, "hbreak": 15.0, "ivb": 18.0, "hard_hit": 0.31, "slider_usage": 0.26, "change_usage": 0.07, "curve_usage": 0.04},
            {"player_id": 2102, "name": "Reliever Two", "type": "pitcher", "position": "P", "age": 27, "bats": "L", "throws": "L", "bf": 245, "ip": "59.1", "fbv": 96.9, "fastball_usage": 0.54, "swstr": 0.154, "chase": 0.342, "bb_rate": 0.081, "k_rate": 0.301, "strike_pct": 0.648, "zone_pct": 0.479, "fps": 0.619, "hbreak": 14.7, "ivb": 17.6, "hard_hit": 0.316, "slider_usage": 0.24, "change_usage": 0.09, "curve_usage": 0.05},
            {"player_id": 2103, "name": "Reliever Three", "type": "pitcher", "position": "P", "age": 31, "bats": "R", "throws": "R", "bf": 232, "ip": "56.2", "fbv": 96.1, "fastball_usage": 0.52, "swstr": 0.148, "chase": 0.334, "bb_rate": 0.079, "k_rate": 0.289, "strike_pct": 0.646, "zone_pct": 0.476, "fps": 0.615, "hbreak": 14.3, "ivb": 17.1, "hard_hit": 0.322, "slider_usage": 0.23, "change_usage": 0.1, "curve_usage": 0.05},
            {"player_id": 2104, "name": "Reliever Four", "type": "pitcher", "position": "P", "age": 25, "bats": "R", "throws": "R", "bf": 218, "ip": "53.0", "fbv": 95.8, "fastball_usage": 0.51, "swstr": 0.143, "chase": 0.329, "bb_rate": 0.076, "k_rate": 0.278, "strike_pct": 0.642, "zone_pct": 0.472, "fps": 0.611, "hbreak": 14.0, "ivb": 16.8, "hard_hit": 0.328, "slider_usage": 0.22, "change_usage": 0.1, "curve_usage": 0.06},
            {"player_id": 2105, "name": "Reliever Five", "type": "pitcher", "position": "P", "age": 28, "bats": "L", "throws": "L", "bf": 205, "ip": "50.1", "fbv": 95.3, "fastball_usage": 0.5, "swstr": 0.138, "chase": 0.321, "bb_rate": 0.074, "k_rate": 0.266, "strike_pct": 0.639, "zone_pct": 0.469, "fps": 0.605, "hbreak": 13.7, "ivb": 16.4, "hard_hit": 0.334, "slider_usage": 0.21, "change_usage": 0.11, "curve_usage": 0.06},
        ]


if __name__ == "__main__":
    unittest.main()