from __future__ import annotations

import unittest

from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
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
            "stolen_bases_allowed": 12,
            "caught_stealing": 7,
            "pickoffs": 3,
            "stolen_base_percentage": "63.2",
            "innings_pitched": "170.2",
            "number_of_pitches": 2600,
            "strikes": 1700,
            "strike_percentage": "65.4",
            "advanced_pitching": {"whiffPercentage": 0.294},
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
                "FF": {"percentage": 0.42, "averageSpeed": 96.4},
                "SL": {"percentage": 0.31, "averageSpeed": 86.1},
                "CH": {"percentage": 0.15, "averageSpeed": 87.4},
                "CU": {"percentage": 0.12, "averageSpeed": 80.0},
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
        self.assertIn("Pitch Quality SL", savant_pitcher_rows[0])
        self.assertEqual(savant_pitcher_rows[0]["Strike %"], 65.4)
        self.assertEqual(savant_pitcher_rows[0]["first_pitch_pitching"], 78.0)
        self.assertEqual(savant_pitcher_rows[0]["runners_on_pitching"], 73.5)
        self.assertEqual(savant_pitcher_rows[0]["pressure_pitching"], 80.5)
        self.assertEqual(savant_pitcher_rows[0]["three_ball_accuracy"], 58.0)
        self.assertEqual(savant_pitcher_rows[0]["steal_suppression"], 59.2)

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
        payload = """Player,Team,Fielding Run Value,Range,Arm,Framing,Throwing\nAlejandro Kirk,TOR,6,1,0,4,1\n"""

        rows = parse_savant_fielding_run_value_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["team"], "TOR")
        self.assertEqual(rows[0]["fielding_run_value"], 6.0)
        self.assertEqual(rows[0]["range_runs"], 1.0)
        self.assertEqual(rows[0]["framing_runs"], 4.0)

    def test_parse_savant_fielding_run_value_csv_handles_current_savant_schema(self) -> None:
        payload = (
            '"name","id","total_runs","range_runs","arm_runs","framing_runs","throwing_runs"\n'
            '"Kirk, Alejandro",672386,6,1,0,4,1\n'
        )

        rows = parse_savant_fielding_run_value_csv(payload)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Alejandro Kirk")
        self.assertEqual(rows[0]["fielding_run_value"], 6.0)
        self.assertEqual(rows[0]["range_runs"], 1.0)
        self.assertEqual(rows[0]["framing_runs"], 4.0)

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
        savant_frv_payload = """Player,Team,Fielding Run Value,Range,Arm,Framing,Throwing\nAlejandro Kirk,TOR,6,1,0,4,1\n"""
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
        self.assertEqual(rows[0]["Catcher Throw Value"], 1.0)


if __name__ == "__main__":
    unittest.main()