from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from smb4_mlb_ratings.ingest import live_team_data as live_team_data_module

from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
        fetch_team_players,
    build_baseball_reference_pitcher_rows,
    build_fangraphs_fielding_rows,
    build_mixed_source_manifest,
    build_roster_rows,
    parse_fangraphs_fielding_csv,
    build_savant_fielding_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
    parse_savant_fielding_run_value_csv,
    parse_savant_oaa_csv,
    parse_savant_arm_strength_csv,
    parse_savant_catcher_throwing_csv,
    parse_savant_catcher_framing_csv,
    parse_savant_statcast_summary,
)


class LiveTeamDataTests(unittest.TestCase):
    def test_build_manifest_uses_supplied_file_names(self) -> None:
        manifest = build_mixed_source_manifest(
            team_abbreviation="TOR",
            roster_season=2026,
            roster_file="roster.csv",
            savant_hitters_file="savant_hitters.csv",
            savant_pitchers_file="savant_pitchers.csv",
            savant_fielding_file="savant_fielding.csv",
            baseball_reference_hitters_file="bref_hitters.csv",
            baseball_reference_pitchers_file="bref_pitchers.csv",
        )

        self.assertEqual(manifest["roster_filter"], {"team": "TOR", "year": 2026})
        self.assertEqual(manifest["seasons"]["current"]["sources"]["baseball_savant"]["files"]["roster"], "roster.csv")
        self.assertEqual(manifest["seasons"]["current"]["sources"]["baseball_savant"]["files"]["fielding"], "savant_fielding.csv")
        self.assertEqual(manifest["seasons"]["current"]["sources"]["baseball_reference"]["files"]["pitchers"], "bref_pitchers.csv")

    def test_build_manifest_can_emit_previous_season_sources(self) -> None:
        manifest = build_mixed_source_manifest(
            team_abbreviation="TOR",
            roster_season=2026,
            current_year=2026,
            roster_file="roster_2026.csv",
            savant_hitters_file="savant_hitters_2026.csv",
            savant_pitchers_file="savant_pitchers_2026.csv",
            savant_fielding_file="savant_fielding_2026.csv",
            baseball_reference_hitters_file="bref_hitters_2026.csv",
            baseball_reference_pitchers_file="bref_pitchers_2026.csv",
            previous_year=2025,
            previous_savant_hitters_file="savant_hitters_2025.csv",
            previous_savant_pitchers_file="savant_pitchers_2025.csv",
            previous_savant_fielding_file="savant_fielding_2025.csv",
            previous_baseball_reference_hitters_file="bref_hitters_2025.csv",
            previous_baseball_reference_pitchers_file="bref_pitchers_2025.csv",
        )

        self.assertEqual(manifest["seasons"]["current"]["year"], 2026)
        self.assertEqual(manifest["seasons"]["previous"]["year"], 2025)
        self.assertNotIn("roster", manifest["seasons"]["previous"]["sources"]["baseball_savant"]["files"])
        self.assertEqual(manifest["seasons"]["previous"]["sources"]["baseball_savant"]["files"]["hitters"], "savant_hitters_2025.csv")
        self.assertEqual(manifest["seasons"]["previous"]["sources"]["baseball_reference"]["files"]["pitchers"], "bref_pitchers_2025.csv")

    def test_build_rows_include_derived_live_metrics(self) -> None:
        hitter = {
            "player_id": 1,
            "name": "Test Hitter",
            "team": "TOR",
            "type": "hitter",
            "position": "3B",
            "status": "Active",
            "status_code": "A",
            "age": 27,
            "bats": "R",
            "throws": "R",
            "days_on_roster": 120,
            "plate_appearances": 500,
            "at_bats": 450,
            "hits": 126,
            "doubles": 28,
            "triples": 2,
            "home_runs": 24,
            "walks": 42,
            "strikeouts": 110,
            "hit_by_pitch": 4,
            "stolen_bases": 8,
            "caught_stealing": 2,
            "avg": "0.280",
            "obp": "0.341",
            "slg": "0.502",
            "advanced_hitting": {"iso": "0.222", "totalSwings": 700, "swingAndMisses": 140},
            "savant_hitting_summary": {
                "zone_contact_pct": 88.4,
                "out_of_zone_contact_pct": 61.2,
                "barrel_rate": 12.3,
                "avg_exit_velocity": 91.7,
                "sprint_speed": 28.8,
            },
            "situational_hitting_metrics": {
                "first_pitch_hitting": 72.5,
                "risp_hitting": 76.0,
                "pressure_hitting": 67.0,
                "late_game_hitting": 64.5,
                "trailing_bases_empty_hitting": 68.0,
            },
            "pitch_type_hitting_metrics": {
                "fastball_hitting": 73.2,
                "offspeed_hitting": 66.8,
            },
            "zone_hitting_metrics": {
                "zone_hitting_high": 69.1,
                "zone_hitting_low": 63.4,
                "zone_hitting_inside": 71.2,
                "zone_hitting_outside": 64.0,
            },
            "hitting_handedness_splits": {
                "vl": {"avg": 0.300, "iso": 0.240, "strikeout_rate": 0.18},
                "vr": {"avg": 0.260, "iso": 0.180, "strikeout_rate": 0.24},
            },
            "fielding_stats": {
                "innings": "812.0",
                "fielding": "0.982",
                "putOuts": 120,
                "assists": 200,
                "errors": 6,
            },
        }
        pitcher = {
            "player_id": 2,
            "name": "Test Pitcher",
            "team": "TOR",
            "type": "pitcher",
            "position": "P",
            "status": "Active",
            "status_code": "A",
            "age": 30,
            "bats": "R",
            "throws": "R",
            "days_on_roster": 140,
            "batters_faced": 600,
            "walks": 48,
            "strikeouts": 180,
            "home_runs": 18,
            "hits": 132,
            "era": 2.87,
            "fip": 3.18,
            "whip": 1.06,
            "era_minus": 74.0,
            "fip_minus": 82.0,
            "stolen_bases_allowed": 12,
            "caught_stealing": 7,
            "pickoffs": 3,
            "stolen_base_percentage": "63.2",
            "innings_pitched": "170.2",
            "number_of_pitches": 2600,
            "strikes": 1700,
            "strike_percentage": "65.4",
            "advanced_pitching": {
                "whiffPercentage": 0.294,
                "chasePercentage": 0.321,
                "zonePercentage": 0.486,
                "firstPitchStrikePercentage": 0.617,
            },
            "situational_pitching_metrics": {
                "first_pitch_pitching": 78.0,
                "runners_on_pitching": 73.5,
                "pressure_pitching": 80.5,
                "three_ball_accuracy": 58.0,
                "steal_suppression": 59.2,
            },
            "pitching_handedness_splits": {
                "vr": {"ops": 0.610, "strikeout_rate": 0.290},
                "vl": {"ops": 0.740, "strikeout_rate": 0.220},
            },
            "pitch_arsenal": {
                "FF": {"percentage": 0.42, "averageSpeed": 96.4, "horizontalBreak": 9.0, "inducedVerticalBreak": 16.0},
                "SL": {"percentage": 0.31, "averageSpeed": 86.1, "horizontalBreak": 14.0, "inducedVerticalBreak": 2.0},
                "CH": {"percentage": 0.15, "averageSpeed": 87.4, "horizontalBreak": 13.0, "inducedVerticalBreak": 8.0},
                "CU": {"percentage": 0.12, "averageSpeed": 80.0, "horizontalBreak": 8.0, "inducedVerticalBreak": -10.0},
            },
            "savant_pitch_details": {
                "FF": {"xba": 0.220, "xwoba": 0.300, "xslg": 0.360, "hard_hit_percent": 33.0, "brl_percent": 6.0, "swings": 300.0, "misses": 80.0, "release_speed": 96.4, "pitches": 420.0, "total_pitches": 1000.0},
                "SL": {"xba": 0.180, "xwoba": 0.240, "xslg": 0.280, "hard_hit_percent": 24.0, "brl_percent": 3.0, "swings": 220.0, "misses": 90.0, "release_speed": 86.1, "pitches": 310.0, "total_pitches": 1000.0},
            },
        }

        roster_rows = build_roster_rows([hitter, pitcher], team_abbreviation="TOR")
        bref_hitter_rows = build_baseball_reference_hitter_rows([hitter], team_abbreviation="TOR")
        savant_hitter_rows = build_savant_hitter_rows([hitter], team_abbreviation="TOR")
        savant_fielding_rows = build_savant_fielding_rows([hitter], team_abbreviation="TOR")
        bref_pitcher_rows = build_baseball_reference_pitcher_rows([pitcher], team_abbreviation="TOR")
        savant_pitcher_rows = build_savant_pitcher_rows([pitcher], team_abbreviation="TOR")

        self.assertEqual(len(roster_rows), 2)
        self.assertEqual(bref_hitter_rows[0]["Contact vs LHP Minus RHP"], 46.0)
        self.assertEqual(savant_hitter_rows[0]["Contact %"], 80.0)
        self.assertEqual(savant_hitter_rows[0]["Barrel %"], 12.3)
        self.assertEqual(savant_hitter_rows[0]["Avg Exit Velocity"], 91.7)
        self.assertEqual(savant_hitter_rows[0]["z_contact_pct"], 88.4)
        self.assertEqual(savant_hitter_rows[0]["o_contact_pct"], 61.2)
        self.assertEqual(savant_hitter_rows[0]["Sprint Speed"], 28.8)
        self.assertEqual(savant_hitter_rows[0]["first_pitch_hitting"], 72.5)
        self.assertEqual(savant_hitter_rows[0]["risp_hitting"], 76.0)
        self.assertEqual(savant_hitter_rows[0]["pressure_hitting"], 67.0)
        self.assertEqual(savant_hitter_rows[0]["late_game_hitting"], 64.5)
        self.assertEqual(savant_hitter_rows[0]["trailing_bases_empty_hitting"], 68.0)
        self.assertEqual(savant_hitter_rows[0]["fastball_hitting"], 73.2)
        self.assertEqual(savant_hitter_rows[0]["offspeed_hitting"], 66.8)
        self.assertEqual(savant_hitter_rows[0]["zone_hitting_high"], 69.1)
        self.assertEqual(savant_hitter_rows[0]["zone_hitting_low"], 63.4)
        self.assertEqual(savant_hitter_rows[0]["zone_hitting_inside"], 71.2)
        self.assertEqual(savant_hitter_rows[0]["zone_hitting_outside"], 64.0)
        self.assertEqual(savant_fielding_rows[0]["Defensive Innings"], 812.0)
        self.assertEqual(savant_fielding_rows[0]["Fielding %"], 0.982)
        self.assertEqual(savant_fielding_rows[0]["PO"], 120.0)
        self.assertGreater(bref_pitcher_rows[0]["Same Handed Pitching"], bref_pitcher_rows[0]["Opposite Handed Pitching"])
        self.assertEqual(bref_pitcher_rows[0]["ERA"], 2.87)
        self.assertEqual(bref_pitcher_rows[0]["FIP"], 3.18)
        self.assertEqual(bref_pitcher_rows[0]["WHIP"], 1.06)
        self.assertEqual(bref_pitcher_rows[0]["ERA Minus"], 74.0)
        self.assertEqual(bref_pitcher_rows[0]["FIP Minus"], 82.0)
        self.assertAlmostEqual(bref_pitcher_rows[0]["K %"], 30.0)
        self.assertAlmostEqual(bref_pitcher_rows[0]["BB %"], 8.0, places=3)
        self.assertIn("Pitch Quality SL", savant_pitcher_rows[0])
        self.assertEqual(savant_pitcher_rows[0]["ERA"], 2.87)
        self.assertEqual(savant_pitcher_rows[0]["FIP"], 3.18)
        self.assertEqual(savant_pitcher_rows[0]["WHIP"], 1.06)
        self.assertEqual(savant_pitcher_rows[0]["ERA Minus"], 74.0)
        self.assertEqual(savant_pitcher_rows[0]["FIP Minus"], 82.0)
        self.assertAlmostEqual(savant_pitcher_rows[0]["K %"], 30.0)
        self.assertEqual(savant_pitcher_rows[0]["Strike %"], 65.4)
        self.assertEqual(savant_pitcher_rows[0]["Chase %"], 32.1)
        self.assertEqual(savant_pitcher_rows[0]["Zone %"], 48.6)
        self.assertEqual(savant_pitcher_rows[0]["First Pitch Strike %"], 61.7)
        self.assertAlmostEqual(savant_pitcher_rows[0]["Horizontal Break"], 11.03, places=2)
        self.assertAlmostEqual(savant_pitcher_rows[0]["Induced Vertical Break"], 7.34, places=2)
        self.assertEqual(savant_pitcher_rows[0]["first_pitch_pitching"], 78.0)
        self.assertEqual(savant_pitcher_rows[0]["runners_on_pitching"], 73.5)
        self.assertEqual(savant_pitcher_rows[0]["pressure_pitching"], 80.5)
        self.assertEqual(savant_pitcher_rows[0]["three_ball_accuracy"], 58.0)
        self.assertEqual(savant_pitcher_rows[0]["steal_suppression"], 59.2)

    def test_build_rows_skip_zero_sample_players_but_keep_roster_rows(self) -> None:
        roster_only_hitter = {
            "player_id": 10,
            "name": "Roster Only Hitter",
            "team": "TOR",
            "type": "hitter",
            "position": "LF",
            "status": "Injured 10-Day",
            "status_code": "D10",
            "age": 25,
            "bats": "L",
            "throws": "R",
            "plate_appearances": 0,
        }
        roster_only_pitcher = {
            "player_id": 11,
            "name": "Roster Only Pitcher",
            "team": "TOR",
            "type": "pitcher",
            "position": "P",
            "status": "Injured 60-Day",
            "status_code": "D60",
            "age": 26,
            "bats": "R",
            "throws": "R",
            "batters_faced": 0,
        }

        roster_rows = build_roster_rows([roster_only_hitter, roster_only_pitcher], team_abbreviation="TOR")

        self.assertEqual(len(roster_rows), 2)
        self.assertEqual(build_baseball_reference_hitter_rows([roster_only_hitter], team_abbreviation="TOR"), [])
        self.assertEqual(build_savant_hitter_rows([roster_only_hitter], team_abbreviation="TOR"), [])
        self.assertEqual(build_baseball_reference_pitcher_rows([roster_only_pitcher], team_abbreviation="TOR"), [])
        self.assertEqual(build_savant_pitcher_rows([roster_only_pitcher], team_abbreviation="TOR"), [])

    def test_build_savant_pitcher_rows_includes_two_way_hitter_with_pitching_sample(self) -> None:
        two_way_hitter = {
            "player_id": 660271,
            "name": "Shohei Ohtani",
            "team": "LAD",
            "type": "hitter",
            "position": "TWP",
            "throws": "R",
            "batters_faced": 72,
            "number_of_pitches": 285,
            "walks": 6,
            "advanced_pitching": {
                "whiffPercentage": 0.29,
                "chasePercentage": 0.33,
                "zonePercentage": 0.49,
                "firstPitchStrikePercentage": 0.61,
            },
            "pitch_arsenal": {
                "FF": {"percentage": 0.46, "averageSpeed": 97.2},
                "SL": {"percentage": 0.31, "averageSpeed": 87.8},
                "CH": {"percentage": 0.23, "averageSpeed": 89.1},
            },
        }

        rows = build_savant_pitcher_rows([two_way_hitter], team_abbreviation="LAD")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_name"], "Shohei Ohtani")
        self.assertEqual(rows[0]["position"], "P")
        self.assertEqual(rows[0]["BF"], 72)
        self.assertIsNotNone(rows[0]["Avg Fastball Velocity"])

    def test_fetch_roster_player_two_way_hitter_enriches_pitching_metrics(self) -> None:
        roster_entry = {
            "person": {"id": 660271, "fullName": "Shohei Ohtani"},
            "position": {"abbreviation": "TWP", "type": "Two-Way Player"},
            "status": {"description": "Active", "code": "A"},
        }
        person_payload = {
            "people": [
                {
                    "fullName": "Shohei Ohtani",
                    "currentAge": 31,
                    "primaryPosition": {"abbreviation": "DH"},
                    "batSide": {"code": "L"},
                    "pitchHand": {"code": "R"},
                }
            ]
        }

        def fake_fetch_stats(
            player_id: int,
            group: str,
            *,
            seasons,
            ssl_context,
            mlb_stats_api,
            stats_type: str = "season",
        ):
            if group == "hitting" and stats_type == "season":
                return {
                    "plateAppearances": 90,
                    "atBats": 82,
                    "hits": 24,
                    "doubles": 3,
                    "triples": 0,
                    "homeRuns": 6,
                    "baseOnBalls": 12,
                    "strikeOuts": 23,
                    "hitByPitch": 2,
                    "stolenBases": 0,
                    "caughtStealing": 0,
                    "avg": ".293",
                    "obp": ".398",
                    "slg": ".598",
                }
            if group == "hitting" and stats_type == "seasonAdvanced":
                return {"totalSwings": 120, "swingAndMisses": 34}
            if group == "pitching" and stats_type == "season":
                return {
                    "battersFaced": 72,
                    "baseOnBalls": 6,
                    "strikeOuts": 31,
                    "homeRuns": 4,
                    "hits": 18,
                    "inningsPitched": "17.2",
                    "numberOfPitches": 285,
                    "strikes": 183,
                    "strikePercentage": "64.2",
                    "stolenBases": 1,
                    "caughtStealing": 0,
                    "pickoffs": 0,
                    "stolenBasePercentage": "100.0",
                }
            if group == "pitching" and stats_type == "seasonAdvanced":
                return {"whiffPercentage": 0.29}
            return {}

        with patch.object(live_team_data_module, "_fetch_json", return_value=person_payload), patch.object(
            live_team_data_module, "_fetch_days_on_roster", return_value=19
        ), patch.object(live_team_data_module, "_fetch_stats", side_effect=fake_fetch_stats), patch.object(
            live_team_data_module, "_fetch_handedness_splits", return_value={}
        ), patch.object(live_team_data_module, "_fetch_savant_hitter_summary", return_value={}), patch.object(
            live_team_data_module, "_fetch_savant_hitter_pitch_details", return_value={}
        ), patch.object(live_team_data_module, "_fetch_situation_splits", return_value={}), patch.object(
            live_team_data_module, "_fetch_pitch_arsenal", return_value={"FF": {"percentage": 0.5, "averageSpeed": 97.1}}
        ), patch.object(live_team_data_module, "_fetch_savant_pitch_details", return_value={}):
            player = live_team_data_module._fetch_roster_player(
                roster_entry,
                team_abbreviation="LAD",
                seasons=(2026, 2026),
                ssl_context=None,
                mlb_stats_api="https://statsapi.mlb.com/api/v1",
                baseball_savant="https://baseballsavant.mlb.com",
            )

        self.assertIsNotNone(player)
        assert player is not None
        self.assertEqual(player["type"], "hitter")
        self.assertEqual(player["position"], "TWP")
        self.assertEqual(player.get("batters_faced"), 72)
        self.assertIn("pitch_arsenal", player)
        self.assertIn("FF", player["pitch_arsenal"])

    def test_fetch_roster_player_keeps_injured_pitcher_without_current_sample(self) -> None:
        roster_entry = {
            "person": {"id": 702056, "fullName": "Trey Yesavage"},
            "position": {"abbreviation": "P", "type": "Pitcher"},
            "status": {"description": "Injured 60-Day", "code": "D60"},
        }
        person_payload = {
            "people": [
                {
                    "fullName": "Trey Yesavage",
                    "currentAge": 26,
                    "primaryPosition": {"abbreviation": "P"},
                    "batSide": {"code": "R"},
                    "pitchHand": {"code": "R"},
                }
            ]
        }

        with patch.object(live_team_data_module, "_fetch_json", return_value=person_payload), patch.object(
            live_team_data_module, "_fetch_stats", return_value={"battersFaced": 0}
        ), patch.object(live_team_data_module, "_fetch_days_on_roster", return_value=None):
            player = live_team_data_module._fetch_roster_player(
                roster_entry,
                team_abbreviation="TOR",
                seasons=(2026, 2026),
                ssl_context=None,
                mlb_stats_api="https://statsapi.mlb.com/api/v1",
                baseball_savant="https://baseballsavant.mlb.com",
            )

        self.assertIsNotNone(player)
        assert player is not None
        self.assertEqual(player["name"], "Trey Yesavage")
        self.assertEqual(player["type"], "pitcher")
        self.assertEqual(player["status"], "Injured 60-Day")
        self.assertNotIn("batters_faced", player)

    def test_fetch_roster_player_keeps_rehab_status_without_current_sample(self) -> None:
        roster_entry = {
            "person": {"id": 702057, "fullName": "Rehab Player"},
            "position": {"abbreviation": "LF", "type": "Outfielder"},
            "status": {"description": "Rehab Assignment", "code": "RL"},
        }
        person_payload = {
            "people": [
                {
                    "fullName": "Rehab Player",
                    "currentAge": 24,
                    "primaryPosition": {"abbreviation": "LF"},
                    "batSide": {"code": "L"},
                    "pitchHand": {"code": "R"},
                }
            ]
        }

        with patch.object(live_team_data_module, "_fetch_json", return_value=person_payload), patch.object(
            live_team_data_module, "_fetch_stats", return_value={"plateAppearances": 0}
        ), patch.object(live_team_data_module, "_fetch_days_on_roster", return_value=None):
            player = live_team_data_module._fetch_roster_player(
                roster_entry,
                team_abbreviation="TOR",
                seasons=(2026, 2026),
                ssl_context=None,
                mlb_stats_api="https://statsapi.mlb.com/api/v1",
                baseball_savant="https://baseballsavant.mlb.com",
            )

        self.assertIsNotNone(player)
        assert player is not None
        self.assertEqual(player["status"], "Rehab Assignment")
        self.assertEqual(player["status_code"], "RL")

    def test_fetch_roster_player_tolerates_savant_hitter_summary_http_500(self) -> None:
        roster_entry = {
            "person": {"id": 702058, "fullName": "Summary Failure Hitter"},
            "position": {"abbreviation": "LF", "type": "Outfielder"},
            "status": {"description": "Active", "code": "A"},
        }
        person_payload = {
            "people": [
                {
                    "fullName": "Summary Failure Hitter",
                    "currentAge": 25,
                    "primaryPosition": {"abbreviation": "LF"},
                    "batSide": {"code": "L"},
                    "pitchHand": {"code": "R"},
                }
            ]
        }

        def fake_fetch_stats(
            player_id: int,
            group: str,
            *,
            seasons: tuple[int, int],
            ssl_context,
            mlb_stats_api: str,
            stats_type: str = "season",
        ):
            if stats_type == "seasonAdvanced":
                return {}
            return {
                "plateAppearances": 42,
                "atBats": 39,
                "hits": 10,
                "doubles": 2,
                "triples": 0,
                "homeRuns": 1,
                "baseOnBalls": 3,
                "strikeOuts": 9,
                "hitByPitch": 0,
                "stolenBases": 1,
                "caughtStealing": 0,
                "avg": "0.256",
                "obp": "0.310",
                "slg": "0.385",
            }

        with patch.object(live_team_data_module, "_fetch_json", return_value=person_payload), patch.object(
            live_team_data_module, "_fetch_stats", side_effect=fake_fetch_stats
        ), patch.object(live_team_data_module, "_fetch_days_on_roster", return_value=15), patch.object(
            live_team_data_module, "_fetch_handedness_splits", return_value={}
        ), patch.object(
            live_team_data_module,
            "_fetch_optional_text",
            return_value=None,
        ), patch.object(
            live_team_data_module, "_fetch_savant_hitter_pitch_details", return_value={}
        ), patch.object(
            live_team_data_module, "_fetch_situation_splits", return_value={}
        ):
            player = live_team_data_module._fetch_roster_player(
                roster_entry,
                team_abbreviation="TOR",
                seasons=(2026, 2026),
                ssl_context=None,
                mlb_stats_api="https://statsapi.mlb.com/api/v1",
                baseball_savant="https://baseballsavant.mlb.com",
            )

        self.assertIsNotNone(player)
        assert player is not None
        self.assertEqual(player["name"], "Summary Failure Hitter")
        self.assertEqual(player["plate_appearances"], 42)
        self.assertEqual(player["savant_hitting_summary"], {})

    # ------------------------------------------------------------------
    # Issue 104 – HTTP failure tracking in fetch_team_players
    # ------------------------------------------------------------------

    def test_fetch_team_players_tracks_http_failures(self) -> None:
        """Players whose optional Savant fetches fail get an http_failures list attached."""
        roster_payload = {
            "roster": [
                {
                    "person": {"id": 99001, "fullName": "Failure Player"},
                    "position": {"abbreviation": "CF", "type": "Outfielder"},
                    "status": {"description": "Active", "code": "A"},
                }
            ]
        }
        base_player = {
            "name": "Failure Player",
            "player_id": 99001,
            "type": "hitter",
            "team": "TST",
            "plate_appearances": 400,
        }

        def fake_fetch_roster_player(
            entry, *, team_abbreviation, seasons, ssl_context, mlb_stats_api,
            baseball_savant, http_failures=None
        ):
            if http_failures is not None:
                # First call (initial pass): simulate a Savant HTTP failure
                http_failures.append(
                    {"url": "http://savant/x", "exc_type": "HTTPError", "stage": "savant_pitch_details"}
                )
                return dict(base_player)
            # Second call (retry): still failing — return None so original is kept
            return None

        with (
            patch.object(live_team_data_module, "_fetch_json", return_value=roster_payload),
            patch.object(
                live_team_data_module, "_fetch_roster_player", side_effect=fake_fetch_roster_player
            ),
            patch.object(live_team_data_module, "_apply_savant_arm_strength", return_value=None),
            patch.object(live_team_data_module, "_apply_savant_catcher_defense", return_value=None),
        ):
            players = fetch_team_players(
                143,
                team_abbreviation="TST",
                roster_season=2025,
                primary_stat_season=2025,
                fallback_stat_season=2024,
                ssl_context=None,
            )

        self.assertEqual(len(players), 1)
        failures = players[0].get("http_failures")
        self.assertIsInstance(failures, list)
        self.assertGreater(len(failures), 0)
        self.assertEqual(failures[0]["player_id"], 99001)
        self.assertEqual(failures[0]["player_name"], "Failure Player")
        self.assertEqual(failures[0]["stage"], "savant_pitch_details")

    def test_fetch_team_players_retries_and_clears_failures_on_success(self) -> None:
        """When the retry pass succeeds the player in the output list has no http_failures."""
        roster_payload = {
            "roster": [
                {
                    "person": {"id": 99002, "fullName": "Retry Player"},
                    "position": {"abbreviation": "SP", "type": "Pitcher"},
                    "status": {"description": "Active", "code": "A"},
                }
            ]
        }
        call_count = {"n": 0}

        def fake_fetch_roster_player(
            entry, *, team_abbreviation, seasons, ssl_context, mlb_stats_api,
            baseball_savant, http_failures=None
        ):
            call_count["n"] += 1
            player = {
                "name": "Retry Player",
                "player_id": 99002,
                "type": "pitcher",
                "team": "TST",
                "plate_appearances": 0,
            }
            if call_count["n"] == 1 and http_failures is not None:
                http_failures.append(
                    {"url": "http://savant/y", "exc_type": "TimeoutError", "stage": "savant_hitter_summary"}
                )
            return player

        with (
            patch.object(live_team_data_module, "_fetch_json", return_value=roster_payload),
            patch.object(
                live_team_data_module, "_fetch_roster_player", side_effect=fake_fetch_roster_player
            ),
            patch.object(live_team_data_module, "_apply_savant_arm_strength", return_value=None),
            patch.object(live_team_data_module, "_apply_savant_catcher_defense", return_value=None),
        ):
            players = fetch_team_players(
                143,
                team_abbreviation="TST",
                roster_season=2025,
                primary_stat_season=2025,
                fallback_stat_season=2024,
                ssl_context=None,
            )

        self.assertEqual(len(players), 1)
        self.assertNotIn("http_failures", players[0])
        self.assertEqual(call_count["n"], 2)

    def test_fetch_team_players_reports_persistent_http_failures_to_stderr(self) -> None:
        """Players with unrecoverable HTTP failures produce a stderr warning."""
        roster_payload = {
            "roster": [
                {
                    "person": {"id": 99003, "fullName": "Persistent Failure"},
                    "position": {"abbreviation": "LF", "type": "Outfielder"},
                    "status": {"description": "Active", "code": "A"},
                }
            ]
        }

        def fake_fetch_roster_player(
            entry, *, team_abbreviation, seasons, ssl_context, mlb_stats_api,
            baseball_savant, http_failures=None
        ):
            if http_failures is not None:
                # Initial pass: simulate a failure
                http_failures.append(
                    {"url": "http://savant/z", "exc_type": "HTTPError", "stage": "savant_pitch_details"}
                )
                return {
                    "name": "Persistent Failure",
                    "player_id": 99003,
                    "type": "hitter",
                    "team": "TST",
                    "plate_appearances": 300,
                }
            # Retry: return None so the original (with http_failures) is kept and warning fires
            return None

        captured = io.StringIO()
        with (
            patch.object(live_team_data_module, "_fetch_json", return_value=roster_payload),
            patch.object(
                live_team_data_module, "_fetch_roster_player", side_effect=fake_fetch_roster_player
            ),
            patch.object(live_team_data_module, "_apply_savant_arm_strength", return_value=None),
            patch.object(live_team_data_module, "_apply_savant_catcher_defense", return_value=None),
            patch("sys.stderr", captured),
        ):
            fetch_team_players(
                143,
                team_abbreviation="TST",
                roster_season=2025,
                primary_stat_season=2025,
                fallback_stat_season=2024,
                ssl_context=None,
            )

        warning = captured.getvalue()
        self.assertIn("Warning", warning)
        self.assertIn("Persistent Failure", warning)
        self.assertIn("savant_pitch_details", warning)

    def test_parse_savant_statcast_summary_extracts_contact_and_tool_fields(self) -> None:
        payload = """
        <script>
        var pageData = {
            statcast: [
                {"year": 2024, "iz_contact_percent": 80.1, "oz_contact_percent": 55.2},
                {"year": 2025, "iz_contact_percent": 84.1, "oz_contact_percent": 59.1, "exit_velocity_avg": "91.7", "barrel_batted_rate": 11.4, "sprint_speed": "27.7"}
            ],
            statcastArrayString: "..."
        };
        </script>
        """

        summary = parse_savant_statcast_summary(payload, season=2025)

        self.assertEqual(
            summary,
            {
                "zone_contact_pct": 84.1,
                "out_of_zone_contact_pct": 59.1,
                "avg_exit_velocity": 91.7,
                "barrel_rate": 11.4,
                "sprint_speed": 27.7,
            },
        )

    def test_parse_fangraphs_fielding_csv_extracts_drs_and_uzr(self) -> None:
        payload = """Name,Team,DRS,UZR\nAlejandro Kirk,TOR,9,7.1\nPitcher Example,TOR,,\n"""

        rows = parse_fangraphs_fielding_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["drs"], 9.0)
        self.assertEqual(rows[0]["uzr"], 7.1)

    def test_build_fangraphs_fielding_rows_matches_players_by_name_and_team(self) -> None:
        players = [
            {
                "player_id": 672386,
                "name": "Alejandro Kirk",
                "team": "TOR",
                "type": "hitter",
                "position": "C",
            }
        ]
        payload = """Name,Team,DRS,UZR\nAlejandro Kirk,TOR,8,6.4\n"""

        rows = build_fangraphs_fielding_rows(
            players,
            team_abbreviation="TOR",
            season=2025,
            csv_payload=payload,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_id"], 672386)
        self.assertEqual(rows[0]["DRS"], 8.0)
        self.assertEqual(rows[0]["UZR"], 6.4)

    def test_parse_savant_oaa_csv_extracts_position_when_present(self) -> None:
        payload = (
            '"name","display_team_name","position","outs_above_average"\n'
            '"Barger, Addison","Blue Jays","3B",3\n'
        )

        rows = parse_savant_oaa_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["position"], "3B")

    def test_build_savant_fielding_rows_merges_position_specific_savant_fallback(self) -> None:
        players = [
            {
                "player_id": 680718,
                "name": "Addison Barger",
                "team": "TOR",
                "type": "hitter",
                "position": "3B",
                "fielding_stats": {
                    "innings": "612.0",
                    "fielding": "0.967",
                },
            }
        ]
        frv_payload = (
            '"name","display_team_name","position","fielding_run_value","range_runs"\n'
            '"Barger, Addison","TOR","3B",5,2\n'
            '"Barger, Addison","TOR","RF",1,0\n'
        )
        oaa_payload = (
            '"name","display_team_name","position","outs_above_average"\n'
            '"Barger, Addison","TOR","3B",4\n'
            '"Barger, Addison","TOR","RF",1\n'
        )

        rows = build_savant_fielding_rows(
            players,
            team_abbreviation="TOR",
            season=2025,
            fielding_run_value_payload=frv_payload,
            oaa_payload=oaa_payload,
        )

        positions = {row["position"] for row in rows}
        self.assertIn("3B", positions)
        self.assertIn("RF", positions)

    def test_build_savant_fielding_rows_matches_fallback_by_player_id_across_team_labels(self) -> None:
        players = [
            {
                "player_id": 680718,
                "name": "Addison Barger",
                "team": "TOR",
                "type": "hitter",
                "position": "3B",
                "fielding_stats": {},
            }
        ]
        oaa_payload = (
            '"name","player_id","display_team_name","position","outs_above_average"\n'
            '"Barger, Addison",680718,"ARI","RF",1\n'
        )

        rows = build_savant_fielding_rows(
            players,
            team_abbreviation="TOR",
            season=2025,
            fielding_run_value_payload="",
            oaa_payload=oaa_payload,
        )

        positions = {row["position"] for row in rows}
        self.assertIn("RF", positions)

    def test_parse_savant_fielding_run_value_csv_extracts_components(self) -> None:
        payload = """Player,Team,Fielding Run Value,Range,Arm,Framing,Blocking,Throwing\nAlejandro Kirk,TOR,6,1,0,4,2,1\n"""

        rows = parse_savant_fielding_run_value_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["fielding_run_value"], 6.0)
        self.assertEqual(rows[0]["range_runs"], 1.0)
        self.assertEqual(rows[0]["framing_runs"], 4.0)
        self.assertEqual(rows[0]["blocking_runs"], 2.0)

    def test_parse_savant_fielding_run_value_csv_handles_current_savant_schema(self) -> None:
        payload = (
            '"name","id","total_runs","range_runs","arm_runs","framing_runs","blocking_runs","throwing_runs"\n'
            '"Kirk, Alejandro",672386,6,1,0,4,2,1\n'
        )

        rows = parse_savant_fielding_run_value_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["fielding_run_value"], 6.0)
        self.assertEqual(rows[0]["range_runs"], 1.0)
        self.assertEqual(rows[0]["framing_runs"], 4.0)
        self.assertEqual(rows[0]["blocking_runs"], 2.0)

    def test_parse_savant_oaa_csv_extracts_oaa_and_runs_prevented(self) -> None:
        payload = """Player,Team,Runs Prevented,OAA\nAlejandro Kirk,TOR,5,4\n"""

        rows = parse_savant_oaa_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["runs_prevented"], 5.0)
        self.assertEqual(rows[0]["oaa"], 4.0)

    def test_parse_savant_oaa_csv_handles_current_savant_schema(self) -> None:
        payload = (
            '"last_name, first_name","player_id","display_team_name","fielding_runs_prevented","outs_above_average"\n'
            '"Kirk, Alejandro","672386","Blue Jays",5,4\n'
        )

        rows = parse_savant_oaa_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["runs_prevented"], 5.0)
        self.assertEqual(rows[0]["oaa"], 4.0)

    def test_parse_savant_arm_strength_csv_handles_current_savant_schema(self) -> None:
        payload = (
            '"fielder_name","player_id","team_name","arm_overall","max_arm_strength"\n'
            '"Varsho, Daulton","662139","TOR","92.1","98.2"\n'
        )

        rows = parse_savant_arm_strength_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Daulton Varsho")
        self.assertEqual(rows[0]["player_id"], 662139)
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["arm_strength"], 92.1)

    def test_parse_savant_catcher_throwing_csv_handles_current_savant_schema(self) -> None:
        payload = (
            '"player_id","player_name","team_name","caught_stealing_above_average","pop_time","arm_strength"\n'
            '"672386","Kirk, Alejandro","TOR","0.20","1.9676","78.96"\n'
        )

        rows = parse_savant_catcher_throwing_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["player_id"], 672386)
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["catcher_throw_value"], 0.2)
        self.assertEqual(rows[0]["pop_time"], 1.9676)
        self.assertEqual(rows[0]["arm_strength"], 78.96)

    def test_parse_savant_catcher_framing_csv_handles_current_leaderboard_schema(self) -> None:
        payload = (
            '"player_id","player_name","team_name","pitches","rv_tot"\n'
            '"672386","Kirk, Alejandro","TOR","388","0.9"\n'
        )

        rows = parse_savant_catcher_framing_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["player_id"], 672386)
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["pitches"], 388.0)
        self.assertEqual(rows[0]["framing_runs"], 0.9)

    def test_parse_savant_catcher_framing_csv_parses_blocking_runs(self) -> None:
        payload = (
            '"player_id","player_name","team_name","pitches","rv_tot","blocking_runs"\n'
            '"672386","Kirk, Alejandro","TOR","388","0.9","1.2"\n'
        )

        rows = parse_savant_catcher_framing_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["player_id"], 672386)
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["pitches"], 388.0)
        self.assertEqual(rows[0]["framing_runs"], 0.9)
        self.assertAlmostEqual(rows[0]["blocking_runs"], 1.2)

    def test_apply_savant_catcher_defense_backfills_framing_metric_wise_across_seasons(self) -> None:
        players = [
            {
                "player_id": 672386,
                "name": "Alejandro Kirk",
                "team": "TOR",
                "type": "hitter",
                "position": "C",
                "fielding_stats": {},
            }
        ]
        catcher_current = (
            '"player_id","player_name","team_name","caught_stealing_above_average","pop_time","arm_strength"\n'
            '"672386","Kirk, Alejandro","TOR","0.20","1.9676","78.96"\n'
        )
        frv_current = (
            '"name","id","total_runs","range_runs","arm_runs","framing_runs","throwing_runs"\n'
            '"Kirk, Alejandro",672386,1,0,0,,0.2\n'
        )
        framing_previous = (
            '"player_id","player_name","team_name","pitches","rv_tot"\n'
            '"672386","Kirk, Alejandro","TOR","1200","1.5"\n'
        )

        with (
            patch.object(live_team_data_module, "_fetch_savant_catcher_throwing_csv", side_effect=[catcher_current, None]),
            patch.object(live_team_data_module, "_fetch_savant_fielding_run_value_csv", side_effect=[frv_current, None]),
            patch.object(live_team_data_module, "_fetch_savant_catcher_framing_csv", side_effect=[None, framing_previous]),
        ):
            live_team_data_module._apply_savant_catcher_defense(
                players,
                seasons=(2026, 2025),
                ssl_context=None,
                baseball_savant="https://baseballsavant.mlb.com",
            )

        fielding = players[0]["fielding_stats"]
        self.assertEqual(fielding["caughtStealingAboveAverage"], 0.2)
        self.assertEqual(fielding["avgPopTime2B"], 1.9676)
        self.assertEqual(fielding["armStrength"], 78.96)
        self.assertEqual(fielding["framingRuns"], 1.5)

    def test_apply_savant_catcher_defense_applies_blocking_runs_metric_wise(self) -> None:
        players = [
            {
                "player_id": 672386,
                "name": "Alejandro Kirk",
                "team": "TOR",
                "type": "hitter",
                "position": "C",
                "fielding_stats": {},
            }
        ]
        framing_current = (
            '"player_id","player_name","team_name","pitches","rv_tot","blocking_runs"\n'
            '"672386","Kirk, Alejandro","TOR","388","0.9","2.3"\n'
        )

        with (
            patch.object(live_team_data_module, "_fetch_savant_catcher_throwing_csv", return_value=None),
            patch.object(live_team_data_module, "_fetch_savant_fielding_run_value_csv", return_value=None),
            patch.object(live_team_data_module, "_fetch_savant_catcher_framing_csv", return_value=framing_current),
        ):
            live_team_data_module._apply_savant_catcher_defense(
                players,
                seasons=(2026,),
                ssl_context=None,
                baseball_savant="https://baseballsavant.mlb.com",
            )

        fielding = players[0]["fielding_stats"]
        self.assertAlmostEqual(fielding["framingRuns"], 0.9)
        self.assertAlmostEqual(fielding["blockingRuns"], 2.3)

    def test_build_fangraphs_fielding_rows_uses_savant_fallback_when_fangraphs_missing(self) -> None:
        players = [
            {
                "player_id": 672386,
                "name": "Alejandro Kirk",
                "team": "TOR",
                "type": "hitter",
                "position": "C",
            }
        ]
        savant_frv_payload = """Player,Team,Fielding Run Value,Range,Arm,Framing,Blocking,Throwing\nAlejandro Kirk,TOR,6,1,0,4,2,1\n"""
        savant_oaa_payload = """Player,Team,Runs Prevented,OAA\nAlejandro Kirk,TOR,5,4\n"""

        rows = build_fangraphs_fielding_rows(
            players,
            team_abbreviation="TOR",
            season=2025,
            csv_payload="",
            savant_fielding_run_value_payload=savant_frv_payload,
            savant_oaa_payload=savant_oaa_payload,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["player_id"], 672386)
        self.assertEqual(rows[0]["DRS"], 6.0)
        self.assertEqual(rows[0]["UZR"], 1.0)
        self.assertEqual(rows[0]["OAA"], 4.0)
        self.assertEqual(rows[0]["Framing Runs"], 4.0)
        self.assertEqual(rows[0]["Blocking Runs"], 2.0)
        self.assertEqual(rows[0]["Catcher Throw Value"], 1.0)


if __name__ == "__main__":
    unittest.main()