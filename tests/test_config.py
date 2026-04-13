from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from smb4_mlb_ratings.engine import interpolate_rating
from smb4_mlb_ratings.processing.core import refresh_runtime_tuning
from smb4_mlb_ratings.reference import load_processing_tuning_config, set_runtime_config_path


class RuntimeConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        set_runtime_config_path(None)
        refresh_runtime_tuning()

    def test_default_runtime_config_has_required_sections(self) -> None:
        config = load_processing_tuning_config()

        self.assertIn("season_weighting", config)
        self.assertIn("rating_curve", config)
        self.assertIn("confidence_weights", config)
        self.assertIn("personality_weights", config)
        self.assertIn("trait_limits", config)
        self.assertIn("trait_conflict_groups", config)
        self.assertIn("role_overall_weights", config)
        self.assertIn("secondary_positions", config)

        season_weighting = config["season_weighting"]
        self.assertGreater(season_weighting["full_season_pa_threshold"], 0)
        self.assertGreater(season_weighting["full_season_ip_threshold"], 0)
        self.assertEqual(set(season_weighting["season_recency_weights"].keys()), {"current", "previous", "two_years_ago"})

        percentile_curve = config["rating_curve"]["percentile_to_rating"]
        self.assertGreaterEqual(len(percentile_curve), 2)
        self.assertEqual(percentile_curve[0][0], 0.0)
        self.assertEqual(percentile_curve[-1][0], 100.0)

        personality = config["personality_weights"]
        self.assertGreaterEqual(personality["personal"], 0.0)
        self.assertGreaterEqual(personality["team"], 0.0)

    def test_custom_config_path_overrides_rating_curve(self) -> None:
        set_runtime_config_path(None)
        refresh_runtime_tuning()
        baseline_mid = interpolate_rating(50.0)

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "custom.yaml"
            config_path.write_text(
                json.dumps(
                    {
                        "rating_curve": {
                            "percentile_to_rating": [
                                [0.0, 1],
                                [100.0, 99],
                            ]
                        }
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            set_runtime_config_path(config_path)
            refresh_runtime_tuning()
            overridden_mid = interpolate_rating(50.0)

        self.assertNotEqual(baseline_mid, overridden_mid)
        self.assertEqual(overridden_mid, 50)


if __name__ == "__main__":
    unittest.main()
