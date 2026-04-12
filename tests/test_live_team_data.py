from __future__ import annotations

import unittest

from smb4_mlb_ratings.ingest.live_team_data import (
    build_baseball_reference_hitter_rows,
    build_baseball_reference_pitcher_rows,
    build_mixed_source_manifest,
    build_roster_rows,
    build_savant_hitter_rows,
    build_savant_pitcher_rows,
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
            baseball_reference_hitters_file="bref_hitters.csv",
            baseball_reference_pitchers_file="bref_pitchers.csv",
        )

        self.assertEqual(manifest["roster_filter"], {"team": "TOR", "year": 2026})
        self.assertEqual(manifest["seasons"]["current"]["sources"]["baseball_savant"]["files"]["roster"], "roster.csv")
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
            "savant_hitting_summary": {"zone_contact_pct": 88.4, "out_of_zone_contact_pct": 61.2},
            "situational_hitting_metrics": {
                "first_pitch_hitting": 72.5,
                "risp_hitting": 76.0,
                "pressure_hitting": 67.0,
                "late_game_hitting": 64.5,
                "trailing_bases_empty_hitting": 68.0,
            },
            "hitting_handedness_splits": {
                "vl": {"avg": 0.300, "iso": 0.240, "strikeout_rate": 0.18},
                "vr": {"avg": 0.260, "iso": 0.180, "strikeout_rate": 0.24},
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
        bref_pitcher_rows = build_baseball_reference_pitcher_rows([pitcher], team_abbreviation="TOR")
        savant_pitcher_rows = build_savant_pitcher_rows([pitcher], team_abbreviation="TOR")

        self.assertEqual(len(roster_rows), 2)
        self.assertEqual(bref_hitter_rows[0]["Contact vs LHP Minus RHP"], 46.0)
        self.assertEqual(savant_hitter_rows[0]["Contact %"], 80.0)
        self.assertEqual(savant_hitter_rows[0]["z_contact_pct"], 88.4)
        self.assertEqual(savant_hitter_rows[0]["o_contact_pct"], 61.2)
        self.assertEqual(savant_hitter_rows[0]["first_pitch_hitting"], 72.5)
        self.assertEqual(savant_hitter_rows[0]["risp_hitting"], 76.0)
        self.assertEqual(savant_hitter_rows[0]["pressure_hitting"], 67.0)
        self.assertEqual(savant_hitter_rows[0]["late_game_hitting"], 64.5)
        self.assertEqual(savant_hitter_rows[0]["trailing_bases_empty_hitting"], 68.0)
        self.assertGreater(bref_pitcher_rows[0]["Same Handed Pitching"], bref_pitcher_rows[0]["Opposite Handed Pitching"])
        self.assertIn("Pitch Quality SL", savant_pitcher_rows[0])
        self.assertEqual(savant_pitcher_rows[0]["Strike %"], 65.4)
        self.assertEqual(savant_pitcher_rows[0]["first_pitch_pitching"], 78.0)
        self.assertEqual(savant_pitcher_rows[0]["runners_on_pitching"], 73.5)
        self.assertEqual(savant_pitcher_rows[0]["pressure_pitching"], 80.5)
        self.assertEqual(savant_pitcher_rows[0]["three_ball_accuracy"], 58.0)
        self.assertEqual(savant_pitcher_rows[0]["steal_suppression"], 59.2)

    def test_parse_savant_statcast_summary_extracts_contact_fields(self) -> None:
        payload = """
        <script>
        var pageData = {
            statcast: [{"year": 2024, "iz_contact_percent": 80.1, "oz_contact_percent": 55.2}, {"year": 2025, "iz_contact_percent": 84.1, "oz_contact_percent": 59.1}],
            statcastArrayString: "..."
        };
        </script>
        """

        summary = parse_savant_statcast_summary(payload, season=2025)

        self.assertEqual(summary, {"zone_contact_pct": 84.1, "out_of_zone_contact_pct": 59.1})


if __name__ == "__main__":
    unittest.main()