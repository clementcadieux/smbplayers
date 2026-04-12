from __future__ import annotations

import unittest

from smb4_mlb_ratings.ingest.live_metrics import (
    aggregate_split_stats,
    game_log_days_on_roster,
    hitter_contact_platoon_delta,
    hitter_power_platoon_delta,
    pitcher_handedness_gap,
    pitcher_handedness_score,
)


class LiveMetricsTests(unittest.TestCase):
    def test_aggregate_hitting_splits_combines_rows(self) -> None:
        splits = [
            {"stat": {"hits": 18, "atBats": 60, "baseOnBalls": 8, "hitByPitch": 1, "sacFlies": 2, "totalBases": 31, "strikeOuts": 12, "plateAppearances": 71}},
            {"stat": {"hits": 12, "atBats": 40, "baseOnBalls": 3, "hitByPitch": 0, "sacFlies": 1, "totalBases": 19, "strikeOuts": 8, "plateAppearances": 44}},
        ]

        aggregated = aggregate_split_stats("hitting", splits)

        self.assertAlmostEqual(aggregated["avg"], 0.3)
        self.assertAlmostEqual(aggregated["slg"], 0.5)
        self.assertAlmostEqual(aggregated["iso"], 0.2)
        self.assertAlmostEqual(aggregated["strikeout_rate"], 20 / 115)

    def test_aggregate_pitching_splits_combines_rows(self) -> None:
        splits = [
            {"stat": {"hits": 14, "atBats": 55, "baseOnBalls": 5, "hitByPitch": 1, "sacFlies": 1, "totalBases": 24, "strikeOuts": 16, "battersFaced": 62}},
            {"stat": {"hits": 8, "atBats": 31, "baseOnBalls": 2, "hitByPitch": 0, "sacFlies": 1, "totalBases": 12, "strikeOuts": 9, "battersFaced": 35}},
        ]

        aggregated = aggregate_split_stats("pitching", splits)

        self.assertAlmostEqual(aggregated["avg"], 22 / 86)
        self.assertAlmostEqual(aggregated["slg"], 36 / 86)
        self.assertAlmostEqual(aggregated["ops"], aggregated["obp"] + aggregated["slg"])
        self.assertAlmostEqual(aggregated["strikeout_rate"], 25 / 97)

    def test_hitter_platoon_deltas_use_split_difference(self) -> None:
        splits = {
            "vl": {"avg": 0.281, "iso": 0.210, "strikeout_rate": 0.18},
            "vr": {"avg": 0.245, "iso": 0.165, "strikeout_rate": 0.24},
        }

        self.assertEqual(hitter_contact_platoon_delta(splits), 42.0)
        self.assertEqual(hitter_power_platoon_delta(splits), 45.0)

    def test_pitcher_handedness_metrics_are_relative_to_throwing_hand(self) -> None:
        splits = {
            "vr": {"ops": 0.61, "strikeout_rate": 0.29},
            "vl": {"ops": 0.74, "strikeout_rate": 0.22},
        }

        same_score = pitcher_handedness_score("R", splits, split_type="same")
        opposite_score = pitcher_handedness_score("R", splits, split_type="opposite")

        self.assertIsNotNone(same_score)
        self.assertIsNotNone(opposite_score)
        self.assertGreater(same_score or 0.0, opposite_score or 0.0)
        self.assertEqual(pitcher_handedness_gap("R", splits, split_type="same"), round((same_score or 0.0) - (opposite_score or 0.0), 3))
        self.assertEqual(pitcher_handedness_gap("R", splits, split_type="opposite"), round((opposite_score or 0.0) - (same_score or 0.0), 3))

    def test_game_log_days_on_roster_spans_first_to_last_date(self) -> None:
        splits = [
            {"date": "2025-04-02"},
            {"date": "2025-04-10"},
            {"date": "2025-04-06"},
        ]

        self.assertEqual(game_log_days_on_roster(splits), 9)
        self.assertIsNone(game_log_days_on_roster([{"date": "bad-date"}]))


if __name__ == "__main__":
    unittest.main()