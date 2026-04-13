from __future__ import annotations

import json
import re
import unittest
from dataclasses import fields
from pathlib import Path

from smb4_mlb_ratings import engine as engine_module
from smb4_mlb_ratings.processing import core as processing_core_module
from smb4_mlb_ratings.engine import (
    blend_component_percentiles,
    interpolate_rating,
    rate_players,
    role_weighted_overall_numeric,
    resolved_projected_ip,
    resolved_projected_pa,
    surface_weight_factor,
    weighted_metric_value,
)
from smb4_mlb_ratings.models import PlayerInput, RatingOutput
from smb4_mlb_ratings.ingest.savant import HITTER_TRAIT_METRIC_COLUMNS, PITCHER_TRAIT_METRIC_COLUMNS


class SurfaceBlendTests(unittest.TestCase):
    def test_weighted_metric_value_keeps_tiny_current_hitter_sample_close_to_prior(self) -> None:
        weighted = weighted_metric_value(
            {"current": 0.350, "previous": 0.180, "two_years_ago": 0.170},
            {"current": 80, "previous": 600, "two_years_ago": 550},
            sample_key="weighted_pa",
        )

        self.assertIsNotNone(weighted)
        self.assertLess(abs((weighted or 0.0) - 0.1778), abs((weighted or 0.0) - 0.3500))
        self.assertLess(weighted or 0.0, 0.20)

    def test_weighted_metric_value_treats_half_current_hitter_season_like_full_previous(self) -> None:
        weighted = weighted_metric_value(
            {"current": 0.350, "previous": 0.180},
            {"current": 250, "previous": 500},
            sample_key="weighted_pa",
        )

        self.assertAlmostEqual(weighted or 0.0, 0.265)

    def test_weighted_metric_value_uses_pitcher_full_season_ip_baseline(self) -> None:
        weighted = weighted_metric_value(
            {"current": 0.250, "previous": 0.080},
            {"current": 100, "previous": 700},
            sample_key="weighted_bf",
        )

        self.assertIsNotNone(weighted)
        self.assertLess(abs((weighted or 0.0) - 0.080), abs((weighted or 0.0) - 0.250))
        self.assertLess(weighted or 0.0, 0.12)

    def test_weighted_metric_value_prefers_metadata_threshold_override_when_available(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Metadata Override",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "metadata": {"season_weighting": {"full_season_pa_threshold": 1000}},
            }
        )
        default_weighted = weighted_metric_value(
            {"current": 0.350, "previous": 0.180},
            {"current": 250, "previous": 500},
            sample_key="weighted_pa",
        )
        overridden_weighted = weighted_metric_value(
            {"current": 0.350, "previous": 0.180},
            {"current": 250, "previous": 500},
            sample_key="weighted_pa",
            player=player,
        )

        self.assertIsNotNone(default_weighted)
        self.assertIsNotNone(overridden_weighted)
        self.assertLess(overridden_weighted or 0.0, default_weighted or 0.0)

    def test_surface_weight_factor_caps_at_half(self) -> None:
        self.assertEqual(surface_weight_factor(0, 425), 0.0)
        self.assertAlmostEqual(surface_weight_factor(212.5, 425), 0.25)
        self.assertEqual(surface_weight_factor(425, 425), 0.5)
        self.assertEqual(surface_weight_factor(900, 425), 0.5)

    def test_surface_weight_factor_supports_configurable_cap(self) -> None:
        self.assertAlmostEqual(surface_weight_factor(425, 425, cap=0.72), 0.72)
        self.assertAlmostEqual(surface_weight_factor(212.5, 425, cap=0.60), 0.30)

    def test_blend_uses_only_underlying_when_surface_share_is_zero(self) -> None:
        combined = blend_component_percentiles(
            [
                (80.0, 0.6, False),
                (70.0, 0.4, False),
                (10.0, 1.0, True),
            ],
            sample=0,
            threshold=425,
        )

        self.assertAlmostEqual(combined, 76.0)

    def test_blend_caps_surface_share_at_half(self) -> None:
        combined = blend_component_percentiles(
            [
                (80.0, 0.6, False),
                (70.0, 0.4, False),
                (10.0, 1.0, True),
            ],
            sample=425,
            threshold=425,
        )

        self.assertAlmostEqual(combined, 43.0)

    def test_power_surface_stat_only_moves_rating_at_high_sample(self) -> None:
        zero_sample_outputs = rate_players(self._build_power_players(sample=0))
        zero_sample_percentiles = {output.name: output.percentiles["power"] for output in zero_sample_outputs}
        self.assertAlmostEqual(zero_sample_percentiles["Poor Surface"], zero_sample_percentiles["Elite Surface"])

        full_sample_outputs = rate_players(self._build_power_players(sample=425))
        full_sample_percentiles = {output.name: output.percentiles["power"] for output in full_sample_outputs}
        self.assertLess(full_sample_percentiles["Poor Surface"], full_sample_percentiles["Elite Surface"])

    def test_projected_pa_ignores_injury_shortened_season(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Healthy Volume Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": {"current": 120, "previous": 610, "two_years_ago": 550}},
                "metadata": {"ingest": {"injury_shortened": {"current": True}}},
            }
        )

        self.assertEqual(resolved_projected_pa(player), 580.0)

    def test_projected_ip_falls_back_to_career_average_when_all_seasons_shortened(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Shortened Pitcher",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "samples": {"weighted_bf": {"current": 85, "previous": 170, "two_years_ago": 255}},
                "metadata": {"ingest": {"injury_shortened": {"current": True, "previous": True, "two_years_ago": True}}},
            }
        )

        self.assertAlmostEqual(resolved_projected_ip(player), 40.0)

    def test_rate_players_surfaces_healthy_projected_pa(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Volume Test",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.200,
                        "hr_per_pa": 0.040,
                        "barrel_rate": 0.100,
                        "slugging": 0.450,
                        "avg_exit_velocity": 90.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.780,
                        "batting_average": 0.270,
                        "adjusted_obp": 0.340,
                        "two_strike_contact_rate": 0.620,
                    },
                    "samples": {"weighted_pa": {"current": 90, "previous": 600, "two_years_ago": 540}},
                    "metadata": {"ingest": {"injury_shortened": {"current": True}}},
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ]
        )

        volume_test = next(output for output in outputs if output.name == "Volume Test")
        self.assertEqual(volume_test.projected_pa, 570.0)

    def test_projected_pa_scales_partial_season_by_days_on_roster(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Late Call-Up Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": {"current": 120}},
                "days_on_roster": {"current": 30},
            }
        )

        self.assertEqual(resolved_projected_pa(player), 648.0)

    def test_projected_pa_is_capped_at_reference_maximum(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Extreme Volume Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": {"current": 200}},
                "days_on_roster": {"current": 30},
            }
        )

        self.assertEqual(resolved_projected_pa(player), 700.0)

    def test_projected_ip_falls_back_to_raw_totals_without_days_on_roster(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Raw Volume Pitcher",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "samples": {"weighted_bf": {"current": 255}},
            }
        )

        self.assertAlmostEqual(resolved_projected_ip(player), 60.0)

    def test_projected_ip_is_capped_at_reference_maximum(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Extreme Volume Pitcher",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "samples": {"defensive_innings": {"current": 100}},
                "days_on_roster": {"current": 30},
            }
        )

        self.assertEqual(resolved_projected_ip(player), 250.0)

    def test_projected_ip_is_none_for_non_pitcher_even_with_pitcher_samples(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Position Player With Bad Source Row",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_bf": {"current": 120}},
            }
        )

        self.assertIsNone(resolved_projected_ip(player))

    def test_rate_players_surfaces_recommended_pitches_for_pitchers(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Pitch Mix Test",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "pitch_mix": {"ff": 0.42, "sv": 0.21, "sl": 0.18, "fs": 0.12, "kn": 0.07},
                    "metrics": {
                        "avg_fastball_velocity": 96.0,
                        "peak_fastball_velocity": 98.0,
                        "fastball_usage": 0.42,
                        "swinging_strike_rate": 0.14,
                        "chase_rate": 0.31,
                        "movement_quality": 24.0,
                        "stuff_metric": 132.0,
                        "arsenal_diversity": 0.81,
                        "weak_contact_rate": 0.68,
                        "walk_rate": 0.07,
                        "strike_pct": 0.65,
                        "zone_pct": 0.49,
                        "first_pitch_strike_pct": 0.61,
                        "command_error_rate": 0.35,
                    },
                    "samples": {"weighted_bf": 680, "tracked_pitches": 2700, "tracked_fastballs": 1134},
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ]
        )

        pitch_mix_test = next(output for output in outputs if output.name == "Pitch Mix Test")
        self.assertEqual(pitch_mix_test.recommended_pitches, ["4-Seam Fastball", "Slider", "Forkball"])
        self.assertGreater(pitch_mix_test.ratings["junk"], 0)
        self.assertGreater(pitch_mix_test.ratings["accuracy"], 0)
        self.assertGreater(pitch_mix_test.percentiles["junk"], 0.0)
        self.assertGreater(pitch_mix_test.percentiles["accuracy"], 0.0)
        self.assertFalse(any("junk: missing metrics" in flag for flag in pitch_mix_test.review_flags))
        self.assertFalse(any("accuracy: missing metrics" in flag for flag in pitch_mix_test.review_flags))

    def test_secondary_positions_are_derived_from_positional_games(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Multi IF",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "2B",
                    "positional_games": {"2B": 980, "SS": 310, "3B": 120, "1B": 40},
                    "metrics": {
                        "iso": 0.175,
                        "hr_per_pa": 0.030,
                        "barrel_rate": 0.082,
                        "slugging": 0.435,
                        "avg_exit_velocity": 88.7,
                        "strikeout_rate": 0.198,
                        "contact_rate": 0.784,
                        "batting_average": 0.275,
                        "adjusted_obp": 0.342,
                        "two_strike_contact_rate": 0.637,
                        "sprint_speed": 28.4,
                        "baserunning_value": 4.1,
                        "sb_attempt_rate": 0.10,
                        "sb_success_rate": 0.80,
                        "triple_double_rate": 0.07,
                        "oaa": 6.0,
                        "drs": 5.0,
                        "uzr": 4.3,
                        "fielding_pct_proxy": 0.989,
                        "position_difficulty": 0.76,
                        "arm_strength": 83.0,
                        "arm_position_baseline": 0.48,
                    },
                    "samples": {"weighted_pa": 560, "baserunning_opportunities": 160, "defensive_innings": 1090},
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ]
        )

        multi_if = next(output for output in outputs if output.name == "Multi IF")
        self.assertEqual(multi_if.secondary_positions, ["SS", "3B", "1B"])
        self.assertEqual(multi_if.secondary_position, "SS")

    def test_full_outfield_coverage_boosts_utility_trait(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Utility OF",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "LF",
                    "positional_games": {"LF": 700, "CF": 220, "RF": 210},
                    "metrics": {
                        "iso": 0.180,
                        "hr_per_pa": 0.032,
                        "barrel_rate": 0.086,
                        "slugging": 0.444,
                        "avg_exit_velocity": 89.4,
                        "strikeout_rate": 0.204,
                        "contact_rate": 0.779,
                        "batting_average": 0.273,
                        "adjusted_obp": 0.339,
                        "two_strike_contact_rate": 0.631,
                        "sprint_speed": 28.7,
                        "baserunning_value": 4.4,
                        "sb_attempt_rate": 0.12,
                        "sb_success_rate": 0.81,
                        "triple_double_rate": 0.08,
                        "oaa": 7.0,
                        "drs": 8.0,
                        "uzr": 5.1,
                        "fielding_pct_proxy": 0.992,
                        "position_difficulty": 0.62,
                        "arm_strength": 86.0,
                        "outfield_arm_runs": 3.4,
                        "arm_position_baseline": 0.58,
                    },
                    "samples": {"weighted_pa": 575, "baserunning_opportunities": 165, "defensive_innings": 1120},
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ],
            trim_final_traits=False,
        )

        utility_of = next(output for output in outputs if output.name == "Utility OF")
        suggested_trait_names = {trait.name for trait in utility_of.suggested_traits}
        self.assertIn("Utility", suggested_trait_names)

    def test_missing_positional_games_leaves_secondary_positions_empty(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "No Positional History",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.171,
                        "hr_per_pa": 0.029,
                        "barrel_rate": 0.079,
                        "slugging": 0.426,
                        "avg_exit_velocity": 88.2,
                        "strikeout_rate": 0.208,
                        "contact_rate": 0.776,
                        "batting_average": 0.269,
                        "adjusted_obp": 0.336,
                        "two_strike_contact_rate": 0.625,
                        "sprint_speed": 28.1,
                        "baserunning_value": 3.9,
                        "sb_attempt_rate": 0.09,
                        "sb_success_rate": 0.78,
                        "triple_double_rate": 0.06,
                        "oaa": 4.0,
                        "drs": 2.0,
                        "uzr": 2.4,
                        "fielding_pct_proxy": 0.986,
                        "position_difficulty": 0.82,
                        "arm_strength": 82.0,
                        "outfield_arm_runs": 1.2,
                        "arm_position_baseline": 0.68,
                    },
                    "samples": {"weighted_pa": 540, "baserunning_opportunities": 150, "defensive_innings": 990},
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ]
        )

        no_history = next(output for output in outputs if output.name == "No Positional History")
        self.assertEqual(no_history.secondary_positions, [])
        self.assertIsNone(no_history.secondary_position)

    def test_rate_players_allocates_configured_trait_metrics(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Criteria Hitter",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.180,
                        "hr_per_pa": 0.032,
                        "barrel_rate": 0.085,
                        "slugging": 0.450,
                        "avg_exit_velocity": 89.0,
                        "strikeout_rate": 0.205,
                        "contact_rate": 0.780,
                        "batting_average": 0.274,
                        "adjusted_obp": 0.342,
                        "two_strike_contact_rate": 0.640,
                    },
                    "samples": {"weighted_pa": 560},
                    "trait_metrics": {
                        "first_pitch_hitting": {"current": 82},
                        "pressure_hitting": {"current": 79},
                        "out_of_zone_contact_pct": {"current": 74},
                        "fastball_hitting": {"current": 78},
                        "offspeed_hitting": {"current": 76},
                        "zone_hitting_high": {"current": 74},
                        "zone_hitting_inside": {"current": 72},
                    },
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ],
            trim_final_traits=False,
        )

        hitter = next(output for output in outputs if output.name == "Criteria Hitter")
        trait_names = {trait.name for trait in hitter.assigned_traits}
        self.assertIn("First Pitch Slayer", trait_names)
        self.assertIn("Clutch", trait_names)
        self.assertIn("Bad Ball Hitter", trait_names)
        self.assertIn("Fastball Hitter", trait_names)
        self.assertIn("Off-Speed Hitter", trait_names)
        self.assertIn("High Pitch", trait_names)
        self.assertIn("Inside Pitch", trait_names)

    def test_missing_trait_metrics_do_not_crash_trait_evaluation(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Sparse Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 94.2,
                        "peak_fastball_velocity": 96.4,
                        "fastball_usage": 0.52,
                        "swinging_strike_rate": 0.11,
                        "chase_rate": 0.28,
                        "movement_quality": 22.0,
                        "stuff_metric": 118.0,
                        "arsenal_diversity": 0.72,
                        "weak_contact_rate": 0.62,
                        "walk_rate": 0.08,
                        "strike_pct": 0.64,
                        "zone_pct": 0.47,
                        "first_pitch_strike_pct": 0.60,
                        "command_error_rate": 0.36,
                    },
                    "samples": {"weighted_bf": 640, "tracked_pitches": 2550, "tracked_fastballs": 1326},
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ]
        )

        pitcher = next(output for output in outputs if output.name == "Sparse Pitcher")
        self.assertIsInstance(pitcher.assigned_traits, list)

    def test_rate_players_allocates_dive_recovery_traits(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Dive Wizard Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.175,
                        "hr_per_pa": 0.030,
                        "barrel_rate": 0.080,
                        "slugging": 0.430,
                        "avg_exit_velocity": 88.7,
                        "strikeout_rate": 0.195,
                        "contact_rate": 0.790,
                        "batting_average": 0.278,
                        "adjusted_obp": 0.345,
                        "two_strike_contact_rate": 0.650,
                        "oaa": 7.0,
                        "drs": 5.0,
                        "uzr": 4.0,
                        "fielding_pct_proxy": 0.992,
                        "position_difficulty": 0.82,
                        "arm_strength": 87.0,
                        "outfield_arm_runs": 3.0,
                        "arm_position_baseline": 0.68,
                    },
                    "samples": {"weighted_pa": 550, "defensive_innings": 1120},
                    "trait_metrics": {
                        "dive_recovery": {"current": 74},
                    },
                },
                {
                    "name": "Butter Fingers Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "LF",
                    "metrics": {
                        "iso": 0.155,
                        "hr_per_pa": 0.022,
                        "barrel_rate": 0.060,
                        "slugging": 0.401,
                        "avg_exit_velocity": 87.4,
                        "strikeout_rate": 0.210,
                        "contact_rate": 0.760,
                        "batting_average": 0.266,
                        "adjusted_obp": 0.330,
                        "two_strike_contact_rate": 0.610,
                        "oaa": -2.0,
                        "drs": -3.0,
                        "uzr": -1.5,
                        "fielding_pct_proxy": 0.965,
                        "position_difficulty": 0.62,
                        "arm_strength": 79.0,
                        "outfield_arm_runs": -1.0,
                        "arm_position_baseline": 0.58,
                    },
                    "samples": {"weighted_pa": 505, "defensive_innings": 980},
                    "trait_metrics": {
                        "dive_recovery": {"current": 29},
                    },
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ],
            trim_final_traits=False,
        )

        dive_wizard = next(output for output in outputs if output.name == "Dive Wizard Candidate")
        butter_fingers = next(output for output in outputs if output.name == "Butter Fingers Candidate")

        self.assertIn("Dive Wizard", {trait.name for trait in dive_wizard.assigned_traits})
        self.assertIn("Butter Fingers", {trait.name for trait in butter_fingers.assigned_traits})

    def test_stimulated_triggers_from_role_specific_late_game_metric(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Late Game Hitter",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.185,
                        "hr_per_pa": 0.031,
                        "barrel_rate": 0.083,
                        "slugging": 0.444,
                        "avg_exit_velocity": 89.2,
                        "strikeout_rate": 0.201,
                        "contact_rate": 0.782,
                        "batting_average": 0.275,
                        "adjusted_obp": 0.343,
                        "two_strike_contact_rate": 0.636,
                    },
                    "samples": {"weighted_pa": 545},
                    "trait_metrics": {
                        "late_game_hitting": {"current": 71},
                    },
                },
                {
                    "name": "Late Game Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 95.1,
                        "peak_fastball_velocity": 97.3,
                        "fastball_usage": 0.49,
                        "swinging_strike_rate": 0.125,
                        "chase_rate": 0.295,
                        "movement_quality": 23.0,
                        "stuff_metric": 124.0,
                        "arsenal_diversity": 0.77,
                        "weak_contact_rate": 0.64,
                        "walk_rate": 0.074,
                        "strike_pct": 0.651,
                        "zone_pct": 0.487,
                        "first_pitch_strike_pct": 0.618,
                        "command_error_rate": 0.349,
                    },
                    "samples": {"weighted_bf": 670, "tracked_pitches": 2680, "tracked_fastballs": 1313},
                    "trait_metrics": {
                        "late_game_pitching": {"current": 73},
                    },
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ],
            trim_final_traits=False,
        )

        hitter = next(output for output in outputs if output.name == "Late Game Hitter")
        pitcher = next(output for output in outputs if output.name == "Late Game Pitcher")

        self.assertIn("Stimulated", {trait.name for trait in hitter.assigned_traits})
        self.assertIn("Stimulated", {trait.name for trait in pitcher.assigned_traits})

    def test_pitcher_platoon_traits_use_relative_gap_metrics(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Specialist Candidate",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 95.2,
                        "peak_fastball_velocity": 97.0,
                        "fastball_usage": 0.50,
                        "swinging_strike_rate": 0.12,
                        "chase_rate": 0.29,
                        "movement_quality": 23.0,
                        "stuff_metric": 123.0,
                        "arsenal_diversity": 0.76,
                        "weak_contact_rate": 0.64,
                        "walk_rate": 0.074,
                        "strike_pct": 0.651,
                        "zone_pct": 0.486,
                        "first_pitch_strike_pct": 0.617,
                        "command_error_rate": 0.349,
                    },
                    "samples": {"weighted_bf": 670, "tracked_pitches": 2680, "tracked_fastballs": 1313},
                    "trait_metrics": {
                        "same_handed_pitching": {"current": 76},
                        "opposite_handed_pitching": {"current": 72},
                        "same_handed_pitching_gap": {"current": 12},
                        "opposite_handed_pitching_gap": {"current": -12},
                    },
                },
                {
                    "name": "Reverse Splits Candidate",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 94.7,
                        "peak_fastball_velocity": 96.8,
                        "fastball_usage": 0.48,
                        "swinging_strike_rate": 0.118,
                        "chase_rate": 0.287,
                        "movement_quality": 22.5,
                        "stuff_metric": 120.0,
                        "arsenal_diversity": 0.74,
                        "weak_contact_rate": 0.63,
                        "walk_rate": 0.078,
                        "strike_pct": 0.646,
                        "zone_pct": 0.482,
                        "first_pitch_strike_pct": 0.612,
                        "command_error_rate": 0.354,
                    },
                    "samples": {"weighted_bf": 650, "tracked_pitches": 2600, "tracked_fastballs": 1248},
                    "trait_metrics": {
                        "same_handed_pitching": {"current": 71},
                        "opposite_handed_pitching": {"current": 77},
                        "same_handed_pitching_gap": {"current": -13},
                        "opposite_handed_pitching_gap": {"current": 13},
                    },
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ],
            trim_final_traits=False,
        )

        specialist = next(output for output in outputs if output.name == "Specialist Candidate")
        reverse_splits = next(output for output in outputs if output.name == "Reverse Splits Candidate")

        self.assertIn("Specialist", {trait.name for trait in specialist.assigned_traits})
        self.assertNotIn("Reverse Splits", {trait.name for trait in specialist.assigned_traits})
        self.assertIn("Reverse Splits", {trait.name for trait in reverse_splits.assigned_traits})
        self.assertNotIn("Specialist", {trait.name for trait in reverse_splits.assigned_traits})

    def test_elite_4f_heuristic_defers_to_explicit_pitch_quality_metric(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Explicit Metric Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 98.0,
                        "peak_fastball_velocity": 99.5,
                        "fastball_usage": 0.62,
                        "swinging_strike_rate": 0.13,
                        "chase_rate": 0.31,
                        "movement_quality": 24.0,
                        "stuff_metric": 130.0,
                        "arsenal_diversity": 0.78,
                        "weak_contact_rate": 0.66,
                        "walk_rate": 0.068,
                        "strike_pct": 0.67,
                        "zone_pct": 0.50,
                        "first_pitch_strike_pct": 0.63,
                        "command_error_rate": 0.33,
                    },
                    "samples": {"weighted_bf": 700, "tracked_pitches": 2800, "tracked_fastballs": 1736},
                    "trait_metrics": {
                        "pitch_quality_4f": {"current": 72},
                    },
                    "metadata": {"pitch_repertoire_codes": ["4F", "SL"]},
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ],
            trim_final_traits=False,
        )

        pitcher = next(output for output in outputs if output.name == "Explicit Metric Pitcher")
        self.assertNotIn("Elite 4F", {trait.name for trait in pitcher.assigned_traits})

    def test_additional_elite_pitch_traits_assign_from_trait_metrics(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Expanded Arsenal Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 95.4,
                        "peak_fastball_velocity": 97.6,
                        "fastball_usage": 0.55,
                        "swinging_strike_rate": 0.128,
                        "chase_rate": 0.301,
                        "movement_quality": 24.0,
                        "stuff_metric": 127.0,
                        "arsenal_diversity": 0.82,
                        "weak_contact_rate": 0.65,
                        "walk_rate": 0.071,
                        "strike_pct": 0.659,
                        "zone_pct": 0.493,
                        "first_pitch_strike_pct": 0.626,
                        "command_error_rate": 0.341,
                    },
                    "samples": {"weighted_bf": 690, "tracked_pitches": 2760, "tracked_fastballs": 1518},
                    "trait_metrics": {
                        "pitch_quality_2f": {"current": 83},
                        "pitch_quality_cf": {"current": 84},
                        "pitch_quality_fk": {"current": 85},
                        "pitch_quality_sb": {"current": 82},
                    },
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ],
            trim_final_traits=False,
        )

        pitcher = next(output for output in outputs if output.name == "Expanded Arsenal Pitcher")
        assigned = {trait.name for trait in pitcher.assigned_traits}

        self.assertIn("Elite 2F", assigned)
        self.assertIn("Elite CF", assigned)
        self.assertIn("Elite FK", assigned)
        self.assertIn("Elite SB", assigned)

    def test_final_assigned_traits_enforce_total_and_elite_pitch_caps(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Trait Cap Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 95.6,
                        "peak_fastball_velocity": 97.9,
                        "fastball_usage": 0.56,
                        "swinging_strike_rate": 0.129,
                        "chase_rate": 0.302,
                        "movement_quality": 24.3,
                        "stuff_metric": 128.0,
                        "arsenal_diversity": 0.83,
                        "weak_contact_rate": 0.65,
                        "walk_rate": 0.071,
                        "strike_pct": 0.661,
                        "zone_pct": 0.492,
                        "first_pitch_strike_pct": 0.628,
                        "command_error_rate": 0.339,
                    },
                    "samples": {"weighted_bf": 695, "tracked_pitches": 2780, "tracked_fastballs": 1556},
                    "trait_metrics": {
                        "pitch_quality_2f": {"current": 84},
                        "pitch_quality_cf": {"current": 85},
                        "pitch_quality_fk": {"current": 86},
                        "pitch_quality_sb": {"current": 83},
                        "pressure_pitching": {"current": 82},
                    },
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ]
        )

        pitcher = next(output for output in outputs if output.name == "Trait Cap Pitcher")
        elite_pitch_traits = {
            "Elite 4F",
            "Elite 2F",
            "Elite CF",
            "Elite CB",
            "Elite CH",
            "Elite FK",
            "Elite SL",
            "Elite SB",
        }
        assigned_names = [trait.name for trait in pitcher.assigned_traits]
        elite_count = sum(name in elite_pitch_traits for name in assigned_names)

        self.assertLessEqual(len(assigned_names), 2)
        self.assertLessEqual(elite_count, 1)
        self.assertEqual(
            elite_count,
            1,
            f"Expected one elite pitch trait to survive final trimming, got: {assigned_names}",
        )

    def test_breaking_elite_trait_prioritized_over_fastball_elite_trait(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Elite Mix Priority Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 95.6,
                        "peak_fastball_velocity": 97.9,
                        "fastball_usage": 0.56,
                        "swinging_strike_rate": 0.129,
                        "chase_rate": 0.302,
                        "movement_quality": 24.3,
                        "stuff_metric": 128.0,
                        "arsenal_diversity": 0.83,
                        "weak_contact_rate": 0.65,
                        "walk_rate": 0.071,
                        "strike_pct": 0.661,
                        "zone_pct": 0.492,
                        "first_pitch_strike_pct": 0.628,
                        "command_error_rate": 0.339,
                    },
                    "samples": {"weighted_bf": 695, "tracked_pitches": 2780, "tracked_fastballs": 1556},
                    "trait_metrics": {
                        "pitch_quality_4f": {"current": 86},
                        "pitch_quality_sl": {"current": 86},
                        "pressure_pitching": {"current": 82},
                    },
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ]
        )

        pitcher = next(output for output in outputs if output.name == "Elite Mix Priority Pitcher")
        assigned = {trait.name for trait in pitcher.assigned_traits}

        self.assertIn("Elite SL", assigned)
        self.assertNotIn("Elite 4F", assigned)

    def test_rating_outputs_are_deterministic_across_repeated_runs(self) -> None:
        players = [
            {
                "name": "Deterministic Pitcher",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "metrics": {
                    "avg_fastball_velocity": 95.4,
                    "peak_fastball_velocity": 97.4,
                    "fastball_usage": 0.53,
                    "swinging_strike_rate": 0.126,
                    "chase_rate": 0.299,
                    "movement_quality": 23.8,
                    "stuff_metric": 126.0,
                    "arsenal_diversity": 0.81,
                    "weak_contact_rate": 0.64,
                    "walk_rate": 0.074,
                    "strike_pct": 0.656,
                    "zone_pct": 0.488,
                    "first_pitch_strike_pct": 0.622,
                    "command_error_rate": 0.344,
                },
                "samples": {"weighted_bf": 680, "tracked_pitches": 2720, "tracked_fastballs": 1480},
                "trait_metrics": {
                    "pitch_quality_fk": {"current": 84},
                    "pressure_pitching": {"current": 79},
                },
            },
            self._pitcher_peer("Determinism Peer 1", 95.0, 0.13, 0.30, 0.075),
            self._pitcher_peer("Determinism Peer 2", 93.5, 0.11, 0.28, 0.085),
        ]

        first = [output.to_dict() for output in rate_players(players)]
        second = [output.to_dict() for output in rate_players(players)]

        self.assertEqual(first, second)

    def test_assigned_traits_never_exceed_canonical_limit(self) -> None:
        players = [
            {
                "name": "Trait Limit Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "metrics": {
                    "iso": 0.190,
                    "hr_per_pa": 0.036,
                    "barrel_rate": 0.095,
                    "slugging": 0.470,
                    "avg_exit_velocity": 90.0,
                    "strikeout_rate": 0.195,
                    "contact_rate": 0.790,
                    "batting_average": 0.281,
                    "adjusted_obp": 0.349,
                    "sprint_speed": 29.5,
                    "baserunning_value": 6.0,
                    "sb_attempt_rate": 0.10,
                    "sb_success_rate": 0.84,
                    "triple_double_rate": 0.071,
                },
                "samples": {"weighted_pa": 600, "baserunning_opportunities": 170},
                "trait_metrics": {
                    "fastball_hitting": {"current": 78},
                    "offspeed_hitting": {"current": 74},
                    "zone_hitting_inside": {"current": 72},
                    "zone_hitting_outside": {"current": 70},
                },
            },
            {
                "name": "Trait Limit Pitcher",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "metrics": {
                    "avg_fastball_velocity": 95.8,
                    "peak_fastball_velocity": 98.1,
                    "fastball_usage": 0.55,
                    "swinging_strike_rate": 0.131,
                    "chase_rate": 0.305,
                    "movement_quality": 24.2,
                    "stuff_metric": 129.0,
                    "arsenal_diversity": 0.84,
                    "weak_contact_rate": 0.65,
                    "walk_rate": 0.070,
                    "strike_pct": 0.662,
                    "zone_pct": 0.495,
                    "first_pitch_strike_pct": 0.629,
                    "command_error_rate": 0.338,
                },
                "samples": {"weighted_bf": 700, "tracked_pitches": 2800, "tracked_fastballs": 1560},
                "trait_metrics": {
                    "pitch_quality_2f": {"current": 84},
                    "pitch_quality_cf": {"current": 85},
                    "pitch_quality_fk": {"current": 86},
                    "pressure_pitching": {"current": 81},
                },
            },
            self._pitcher_peer("Trait Cap Peer 1", 95.0, 0.13, 0.30, 0.075),
            self._pitcher_peer("Trait Cap Peer 2", 93.5, 0.11, 0.28, 0.085),
        ]

        outputs = rate_players(players)
        canonical_limit = int(engine_module.TRAIT_LIMIT_CONFIG.get("max_traits_per_player", engine_module.DEFAULT_FINAL_TRAIT_LIMIT))

        self.assertTrue(all(len(output.assigned_traits) <= canonical_limit for output in outputs))

    def test_elite_pitch_traits_prefer_mlb_wide_percentiles_from_metadata(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "MLB Percentile Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "metrics": {
                        "avg_fastball_velocity": 94.8,
                        "peak_fastball_velocity": 96.0,
                        "fastball_usage": 0.49,
                        "swinging_strike_rate": 0.121,
                        "chase_rate": 0.289,
                        "movement_quality": 22.8,
                        "stuff_metric": 121.0,
                        "arsenal_diversity": 0.78,
                        "weak_contact_rate": 0.64,
                        "walk_rate": 0.076,
                        "strike_pct": 0.648,
                        "zone_pct": 0.485,
                        "first_pitch_strike_pct": 0.614,
                        "command_error_rate": 0.35,
                    },
                    "samples": {"weighted_bf": 660, "tracked_pitches": 2620, "tracked_fastballs": 1280},
                    "trait_metrics": {
                        "pitch_quality_ch": {"current": 40},
                    },
                    "metadata": {
                        "mlb_trait_metric_percentiles": {"pitch_quality_ch": 92.0},
                        "mlb_trait_metric_percentile_peer_counts": {"pitch_quality_ch": 120},
                    },
                },
                self._pitcher_peer("Pitcher Peer 1", 95.0, 0.13, 0.30, 0.075),
                self._pitcher_peer("Pitcher Peer 2", 93.5, 0.11, 0.28, 0.085),
            ],
            trim_final_traits=False,
        )

        pitcher = next(output for output in outputs if output.name == "MLB Percentile Pitcher")
        assigned = {trait.name for trait in pitcher.assigned_traits}
        self.assertIn("Elite CH", assigned)

    def test_pop_time_boosts_catcher_arm_rating(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Quick Exchange",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "C",
                    "metrics": {
                        "iso": 0.150,
                        "hr_per_pa": 0.020,
                        "barrel_rate": 0.060,
                        "slugging": 0.395,
                        "avg_exit_velocity": 87.6,
                        "strikeout_rate": 0.175,
                        "contact_rate": 0.815,
                        "batting_average": 0.276,
                        "adjusted_obp": 0.338,
                        "two_strike_contact_rate": 0.665,
                        "oaa": 1.0,
                        "drs": 4.0,
                        "uzr": 2.0,
                        "fielding_pct_proxy": 0.995,
                        "position_difficulty": 0.98,
                        "arm_strength": 84.0,
                        "catcher_throw_value": 5.0,
                        "pop_time": 1.89,
                        "framing_runs": 8.0,
                        "arm_position_baseline": 0.95,
                    },
                    "samples": {"weighted_pa": 420, "defensive_innings": 930},
                },
                {
                    "name": "Average Exchange",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "C",
                    "metrics": {
                        "iso": 0.150,
                        "hr_per_pa": 0.020,
                        "barrel_rate": 0.060,
                        "slugging": 0.395,
                        "avg_exit_velocity": 87.6,
                        "strikeout_rate": 0.175,
                        "contact_rate": 0.815,
                        "batting_average": 0.276,
                        "adjusted_obp": 0.338,
                        "two_strike_contact_rate": 0.665,
                        "oaa": 1.0,
                        "drs": 4.0,
                        "uzr": 2.0,
                        "fielding_pct_proxy": 0.995,
                        "position_difficulty": 0.98,
                        "arm_strength": 84.0,
                        "catcher_throw_value": 5.0,
                        "framing_runs": 8.0,
                        "arm_position_baseline": 0.95,
                    },
                    "samples": {"weighted_pa": 420, "defensive_innings": 930},
                },
                {
                    "name": "Slow Exchange Peer",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "C",
                    "metrics": {
                        "iso": 0.132,
                        "hr_per_pa": 0.016,
                        "barrel_rate": 0.050,
                        "slugging": 0.372,
                        "avg_exit_velocity": 86.8,
                        "strikeout_rate": 0.188,
                        "contact_rate": 0.798,
                        "batting_average": 0.261,
                        "adjusted_obp": 0.324,
                        "two_strike_contact_rate": 0.642,
                        "oaa": -1.0,
                        "drs": 0.0,
                        "uzr": -1.0,
                        "fielding_pct_proxy": 0.989,
                        "position_difficulty": 0.98,
                        "arm_strength": 78.0,
                        "catcher_throw_value": -1.0,
                        "pop_time": 2.08,
                        "framing_runs": -4.0,
                        "arm_position_baseline": 0.95,
                    },
                    "samples": {"weighted_pa": 390, "defensive_innings": 870},
                },
            ]
        )

        quick_exchange = next(output for output in outputs if output.name == "Quick Exchange")
        average_exchange = next(output for output in outputs if output.name == "Average Exchange")

        self.assertGreater(quick_exchange.ratings["arm"], average_exchange.ratings["arm"])
        self.assertGreater(quick_exchange.percentiles["arm"], average_exchange.percentiles["arm"])

    def test_trait_criteria_reference_known_player_input_roots(self) -> None:
        reference_path = Path(__file__).resolve().parents[1] / "smb4_player_reference.json"
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        criteria_payload = payload.get("trait_criteria", {})
        traits = criteria_payload.get("traits", {}) if isinstance(criteria_payload, dict) else {}
        player_input_fields = {item.name for item in fields(PlayerInput)} | {"metadata", "metrics", "samples"}

        for trait_name, config in traits.items():
            self.assertIsInstance(config, dict, trait_name)
            self.assertIn("criteria", config, trait_name)
            for rule in config.get("criteria", []):
                self.assertIsInstance(rule, dict, trait_name)
                root = str(rule.get("stat", "")).split(".", 1)[0]
                self.assertIn(root, player_input_fields, f"{trait_name}: unknown stat root {root}")

    def test_trait_catalog_assignment_paths_are_audited(self) -> None:
        reference_path = Path(__file__).resolve().parents[1] / "smb4_player_reference.json"
        payload = json.loads(reference_path.read_text(encoding="utf-8"))

        catalog_traits = {
            str(trait.get("name"))
            for group in payload.get("traits", {}).values()
            if isinstance(group, list)
            for trait in group
            if isinstance(trait, dict) and isinstance(trait.get("name"), str)
        }
        criteria_traits = {
            str(name)
            for name in payload.get("trait_criteria", {}).get("traits", {}).keys()
            if isinstance(name, str)
        }

        engine_source = Path(engine_module.__file__).read_text(encoding="utf-8")
        processing_source = Path(processing_core_module.__file__).read_text(encoding="utf-8")
        heuristic_traits = set(re.findall(r'name="([^"]+)"', engine_source + "\n" + processing_source))

        # Two-way assignment happens in a loop and does not appear as name="..." literals.
        heuristic_traits.update({"Two Way (C)", "Two Way (IF)", "Two Way (OF)"})

        covered_traits = criteria_traits | heuristic_traits
        uncovered_traits = catalog_traits - covered_traits

        self.assertEqual(
            uncovered_traits,
            set(),
            f"Unexpected uncovered catalog traits: {sorted(uncovered_traits)}",
        )

    def test_trait_criteria_trait_metrics_are_supported_or_explicitly_annotated(self) -> None:
        reference_path = Path(__file__).resolve().parents[1] / "smb4_player_reference.json"
        payload = json.loads(reference_path.read_text(encoding="utf-8"))
        criteria_payload = payload.get("trait_criteria", {})
        traits = criteria_payload.get("traits", {}) if isinstance(criteria_payload, dict) else {}

        supported_trait_metrics = set(HITTER_TRAIT_METRIC_COLUMNS) | set(PITCHER_TRAIT_METRIC_COLUMNS)
        unsupported: list[str] = []
        for trait_name, config in traits.items():
            if not isinstance(config, dict):
                continue
            feasibility = str(config.get("feasibility", "")).strip().lower()
            uses_proxy = bool(config.get("proxy", False))
            for rule in config.get("criteria", []):
                if not isinstance(rule, dict):
                    continue
                stat = str(rule.get("stat", ""))
                if not stat.startswith("trait_metrics."):
                    continue
                metric_key = stat.split(".", 1)[1]
                if metric_key in supported_trait_metrics:
                    continue
                if feasibility == "none" or uses_proxy:
                    continue
                unsupported.append(f"{trait_name}:{metric_key}")

        self.assertEqual(unsupported, [], f"Trait criteria uses unsupported trait_metrics without feasibility/proxy annotation: {unsupported}")

    def test_base_rounder_assigns_from_speed_and_baserunning_signals(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Base Rounder Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.165,
                        "hr_per_pa": 0.026,
                        "barrel_rate": 0.070,
                        "slugging": 0.420,
                        "avg_exit_velocity": 88.2,
                        "strikeout_rate": 0.182,
                        "contact_rate": 0.804,
                        "batting_average": 0.281,
                        "adjusted_obp": 0.349,
                        "sprint_speed": 29.9,
                        "baserunning_value": 7.1,
                        "stolen_bases": 29,
                        "caught_stealing": 4,
                        "plate_appearances": 565,
                    },
                    "samples": {"weighted_pa": 565},
                },
                {
                    "name": "Speed Peer",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.160,
                        "hr_per_pa": 0.024,
                        "barrel_rate": 0.067,
                        "slugging": 0.410,
                        "avg_exit_velocity": 87.8,
                        "strikeout_rate": 0.195,
                        "contact_rate": 0.790,
                        "batting_average": 0.272,
                        "adjusted_obp": 0.337,
                        "sprint_speed": 28.2,
                        "baserunning_value": 3.5,
                        "stolen_bases": 18,
                        "caught_stealing": 6,
                        "plate_appearances": 545,
                    },
                    "samples": {"weighted_pa": 545},
                },
                {
                    "name": "Base Jogger Peer",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "1B",
                    "metrics": {
                        "iso": 0.175,
                        "hr_per_pa": 0.030,
                        "barrel_rate": 0.080,
                        "slugging": 0.432,
                        "avg_exit_velocity": 89.0,
                        "strikeout_rate": 0.215,
                        "contact_rate": 0.752,
                        "batting_average": 0.260,
                        "adjusted_obp": 0.324,
                        "sprint_speed": 25.4,
                        "baserunning_value": -2.9,
                        "stolen_bases": 2,
                        "caught_stealing": 3,
                        "plate_appearances": 530,
                    },
                    "samples": {"weighted_pa": 530},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(output for output in outputs if output.name == "Base Rounder Candidate")
        trait_names = {trait.name for trait in candidate.assigned_traits}
        self.assertIn("Base Rounder", trait_names)

    def test_easy_target_assigns_from_low_mind_games_metric(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Easy Target Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "LF",
                    "metrics": {
                        "iso": 0.150,
                        "hr_per_pa": 0.021,
                        "barrel_rate": 0.058,
                        "slugging": 0.393,
                        "avg_exit_velocity": 87.2,
                        "strikeout_rate": 0.224,
                        "contact_rate": 0.748,
                        "batting_average": 0.254,
                        "adjusted_obp": 0.319,
                    },
                    "samples": {"weighted_pa": 520},
                    "trait_metrics": {
                        "mind_games": {"current": 24},
                    },
                },
                self._player("Peer 1", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
                self._player("Peer 2", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
            ],
            trim_final_traits=False,
        )

        candidate = next(output for output in outputs if output.name == "Easy Target Candidate")
        trait_names = {trait.name for trait in candidate.assigned_traits}
        self.assertIn("Easy Target", trait_names)
        self.assertNotIn("Mind Gamer", trait_names)

    def test_tough_out_assigns_when_strikeout_avoidance_outpaces_other_contact_signals(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Tough Out Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "2B",
                    "metrics": {
                        "iso": 0.150,
                        "hr_per_pa": 0.020,
                        "barrel_rate": 0.055,
                        "slugging": 0.395,
                        "avg_exit_velocity": 86.8,
                        "strikeout_rate": 0.090,
                        "contact_rate": 0.758,
                        "batting_average": 0.247,
                        "adjusted_obp": 0.314,
                    },
                    "samples": {"weighted_pa": 540},
                },
                {
                    "name": "Elite Contact Peer",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.175,
                        "hr_per_pa": 0.028,
                        "barrel_rate": 0.078,
                        "slugging": 0.435,
                        "avg_exit_velocity": 89.0,
                        "strikeout_rate": 0.120,
                        "contact_rate": 0.855,
                        "batting_average": 0.311,
                        "adjusted_obp": 0.381,
                    },
                    "samples": {"weighted_pa": 560},
                },
                {
                    "name": "High Whiff Peer",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "RF",
                    "metrics": {
                        "iso": 0.180,
                        "hr_per_pa": 0.031,
                        "barrel_rate": 0.082,
                        "slugging": 0.445,
                        "avg_exit_velocity": 89.2,
                        "strikeout_rate": 0.298,
                        "contact_rate": 0.688,
                        "batting_average": 0.228,
                        "adjusted_obp": 0.302,
                    },
                    "samples": {"weighted_pa": 535},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(output for output in outputs if output.name == "Tough Out Candidate")
        trait_names = {trait.name for trait in candidate.assigned_traits}
        self.assertIn("Tough Out", trait_names)
        self.assertNotIn("Whiffer", trait_names)

    def test_tough_out_does_not_assign_for_elite_contact_profile(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Elite Contact Candidate",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.170,
                        "hr_per_pa": 0.026,
                        "barrel_rate": 0.072,
                        "slugging": 0.430,
                        "avg_exit_velocity": 88.7,
                        "strikeout_rate": 0.108,
                        "contact_rate": 0.872,
                        "batting_average": 0.319,
                        "adjusted_obp": 0.392,
                    },
                    "samples": {"weighted_pa": 560},
                },
                {
                    "name": "Peer One",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "LF",
                    "metrics": {
                        "iso": 0.162,
                        "hr_per_pa": 0.023,
                        "barrel_rate": 0.066,
                        "slugging": 0.414,
                        "avg_exit_velocity": 87.9,
                        "strikeout_rate": 0.176,
                        "contact_rate": 0.786,
                        "batting_average": 0.271,
                        "adjusted_obp": 0.338,
                    },
                    "samples": {"weighted_pa": 545},
                },
                {
                    "name": "Peer Two",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "1B",
                    "metrics": {
                        "iso": 0.179,
                        "hr_per_pa": 0.031,
                        "barrel_rate": 0.081,
                        "slugging": 0.446,
                        "avg_exit_velocity": 89.3,
                        "strikeout_rate": 0.220,
                        "contact_rate": 0.744,
                        "batting_average": 0.252,
                        "adjusted_obp": 0.322,
                    },
                    "samples": {"weighted_pa": 540},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(output for output in outputs if output.name == "Elite Contact Candidate")
        trait_names = {trait.name for trait in candidate.assigned_traits}
        self.assertNotIn("Tough Out", trait_names)

    def test_interpolate_rating_expands_elite_percentile_band(self) -> None:
        self.assertEqual(interpolate_rating(88.0), 85)
        self.assertEqual(interpolate_rating(93.0), 90)
        self.assertEqual(interpolate_rating(96.0), 94)
        self.assertEqual(interpolate_rating(99.5), 98)

    def test_elite_contact_hitter_reaches_extreme_rating_values(self) -> None:
        outputs = rate_players(self._build_contact_players())
        elite = next(output for output in outputs if output.name == "Elite Contact")

        self.assertGreaterEqual(elite.ratings["contact"], 95)
        self.assertGreaterEqual(elite.percentiles["contact"], 96.0)

    def test_elite_power_hitter_reaches_extreme_rating_values(self) -> None:
        outputs = rate_players(self._build_elite_power_players())
        elite = next(output for output in outputs if output.name == "Elite Power")

        self.assertGreaterEqual(elite.ratings["power"], 95)
        self.assertGreaterEqual(elite.percentiles["power"], 96.0)

    def test_average_hitter_profile_stays_in_middle_band_after_surface_cap_tuning(self) -> None:
        outputs = rate_players(self._build_average_hitter_band())
        average = next(output for output in outputs if output.name == "Average Hitter")

        self.assertGreaterEqual(average.ratings["contact"], 45)
        self.assertLessEqual(average.ratings["contact"], 75)
        self.assertGreaterEqual(average.ratings["power"], 38)
        self.assertLessEqual(average.ratings["power"], 75)

    def test_elite_pitcher_profile_reaches_elite_overall_rating(self) -> None:
        peers = [
            {
                "name": f"Pitcher Peer {index}",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "metrics": {
                    "avg_fastball_velocity": 92.2 + (index * 0.04),
                    "peak_fastball_velocity": 94.1 + (index * 0.04),
                    "fastball_usage": 0.49,
                    "swinging_strike_rate": 0.103 + (index * 0.001),
                    "chase_rate": 0.269 + (index * 0.001),
                    "movement_quality": 20.0 + (index * 0.1),
                    "stuff_metric": 110.0 + index,
                    "arsenal_diversity": 0.68,
                    "weak_contact_rate": 0.58,
                    "walk_rate": 0.088 - (index * 0.0004),
                    "strike_pct": 0.618,
                    "zone_pct": 0.458,
                    "first_pitch_strike_pct": 0.578,
                    "command_error_rate": 0.382,
                },
                "samples": {"weighted_bf": 760, "tracked_pitches": 2800, "tracked_fastballs": 1380},
            }
            for index in range(1, 26)
        ]

        elite = {
            "name": "Elite Pitcher",
            "role": "pitcher",
            "team": "NYM",
            "primary_position": "P",
            "metrics": {
                "avg_fastball_velocity": 97.8,
                "peak_fastball_velocity": 99.7,
                "fastball_usage": 0.52,
                "swinging_strike_rate": 0.171,
                "chase_rate": 0.354,
                "movement_quality": 29.5,
                "stuff_metric": 152.0,
                "arsenal_diversity": 0.88,
                "weak_contact_rate": 0.73,
                "walk_rate": 0.041,
                "strike_pct": 0.704,
                "zone_pct": 0.542,
                "first_pitch_strike_pct": 0.689,
                "command_error_rate": 0.201,
            },
            "samples": {"weighted_bf": 860, "tracked_pitches": 3200, "tracked_fastballs": 1650},
        }

        outputs = rate_players([elite, *peers])
        elite_output = next(output for output in outputs if output.name == "Elite Pitcher")
        self.assertGreaterEqual(elite_output.overall_numeric or 0, 95)

    def test_average_pitcher_profile_stays_in_middle_band(self) -> None:
        peers = [
            {
                "name": f"Peer Band {index}",
                "role": "pitcher",
                "team": "NYM",
                "primary_position": "P",
                "metrics": {
                    "avg_fastball_velocity": 91.8 + (index * 0.05),
                    "peak_fastball_velocity": 93.7 + (index * 0.05),
                    "fastball_usage": 0.50,
                    "swinging_strike_rate": 0.100 + (index * 0.001),
                    "chase_rate": 0.266 + (index * 0.001),
                    "movement_quality": 19.5 + (index * 0.08),
                    "stuff_metric": 108.0 + index,
                    "arsenal_diversity": 0.67,
                    "weak_contact_rate": 0.57,
                    "walk_rate": 0.090 - (index * 0.0005),
                    "strike_pct": 0.614,
                    "zone_pct": 0.454,
                    "first_pitch_strike_pct": 0.576,
                    "command_error_rate": 0.386,
                },
                "samples": {"weighted_bf": 760, "tracked_pitches": 2800, "tracked_fastballs": 1380},
            }
            for index in range(1, 26)
        ]

        average = {
            "name": "Average Pitcher",
            "role": "pitcher",
            "team": "NYM",
            "primary_position": "P",
            "metrics": {
                "avg_fastball_velocity": 92.5,
                "peak_fastball_velocity": 94.4,
                "fastball_usage": 0.50,
                "swinging_strike_rate": 0.109,
                "chase_rate": 0.274,
                "movement_quality": 21.1,
                "stuff_metric": 116.0,
                "arsenal_diversity": 0.70,
                "weak_contact_rate": 0.60,
                "walk_rate": 0.081,
                "strike_pct": 0.628,
                "zone_pct": 0.468,
                "first_pitch_strike_pct": 0.591,
                "command_error_rate": 0.366,
            },
            "samples": {"weighted_bf": 790, "tracked_pitches": 2900, "tracked_fastballs": 1450},
        }

        outputs = rate_players([average, *peers])
        average_output = next(output for output in outputs if output.name == "Average Pitcher")
        self.assertGreaterEqual(average_output.overall_numeric or 0, 70)
        self.assertLessEqual(average_output.overall_numeric or 0, 84)

    def test_heavy_platoon_dependency_reduces_contact_and_power_percentiles(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Heavy Platoon",
                    weighted_pa=520,
                    contact_gap=24.0,
                    power_gap=30.0,
                    contact_vs_lhp=72.0,
                    contact_vs_rhp=24.0,
                    power_vs_lhp=78.0,
                    power_vs_rhp=26.0,
                ),
                self._platoon_hitter(
                    "Balanced Peer",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Strong Peer",
                    weighted_pa=540,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=66.0,
                    contact_vs_rhp=64.0,
                    power_vs_lhp=68.0,
                    power_vs_rhp=67.0,
                    batting_average=0.301,
                    adjusted_obp=0.372,
                    slugging=0.510,
                    iso=0.218,
                    hr_per_pa=0.040,
                    barrel_rate=0.108,
                    avg_exit_velocity=90.8,
                ),
                self._platoon_hitter(
                    "Weak Peer",
                    weighted_pa=510,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=32.0,
                    contact_vs_rhp=31.0,
                    power_vs_lhp=34.0,
                    power_vs_rhp=33.0,
                    batting_average=0.246,
                    adjusted_obp=0.314,
                    slugging=0.401,
                    iso=0.144,
                    hr_per_pa=0.022,
                    barrel_rate=0.061,
                    avg_exit_velocity=87.2,
                ),
            ],
            trim_final_traits=False,
        )

        heavy = next(output for output in outputs if output.name == "Heavy Platoon")
        balanced = next(output for output in outputs if output.name == "Balanced Peer")

        self.assertLess(heavy.percentiles["contact"], balanced.percentiles["contact"])
        self.assertLess(heavy.percentiles["power"], balanced.percentiles["power"])

    def test_heavy_platoon_profile_still_assigns_platoon_traits(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Trait Platoon",
                    weighted_pa=540,
                    contact_gap=24.0,
                    power_gap=30.0,
                    contact_vs_lhp=72.0,
                    contact_vs_rhp=24.0,
                    power_vs_lhp=78.0,
                    power_vs_rhp=26.0,
                ),
                self._platoon_hitter(
                    "Peer A",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Peer B",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                    batting_average=0.250,
                    adjusted_obp=0.320,
                    slugging=0.410,
                    iso=0.150,
                    hr_per_pa=0.024,
                    barrel_rate=0.064,
                ),
            ],
            trim_final_traits=False,
        )

        hitter = next(output for output in outputs if output.name == "Trait Platoon")
        assigned_traits = {trait.name for trait in hitter.assigned_traits}

        self.assertIn("CON vs LHP", assigned_traits)
        self.assertIn("POW vs LHP", assigned_traits)

    def test_balanced_platoon_profile_has_no_trait_or_penalty(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Below Threshold Split",
                    weighted_pa=540,
                    contact_gap=19.0,
                    power_gap=19.0,
                    contact_vs_lhp=72.0,
                    contact_vs_rhp=24.0,
                    power_vs_lhp=78.0,
                    power_vs_rhp=26.0,
                ),
                self._platoon_hitter(
                    "No Split Baseline",
                    weighted_pa=540,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Peer C",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                    batting_average=0.252,
                    adjusted_obp=0.324,
                    slugging=0.412,
                    iso=0.148,
                    hr_per_pa=0.023,
                    barrel_rate=0.062,
                ),
            ],
            trim_final_traits=False,
        )

        below = next(output for output in outputs if output.name == "Below Threshold Split")
        baseline = next(output for output in outputs if output.name == "No Split Baseline")
        below_traits = {trait.name for trait in below.assigned_traits}

        self.assertEqual(below.percentiles["contact"], baseline.percentiles["contact"])
        self.assertEqual(below.percentiles["power"], baseline.percentiles["power"])
        self.assertNotIn("CON vs LHP", below_traits)
        self.assertNotIn("CON vs RHP", below_traits)
        self.assertNotIn("POW vs LHP", below_traits)
        self.assertNotIn("POW vs RHP", below_traits)

    def test_platoon_threshold_borderline_behavior(self) -> None:
        below_outputs = rate_players(
            [
                self._platoon_hitter(
                    "Contact Below",
                    weighted_pa=540,
                    contact_gap=19.0,
                    power_gap=0.0,
                    contact_vs_lhp=72.0,
                    contact_vs_rhp=24.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter("Peer 1", weighted_pa=520, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=50.0, contact_vs_rhp=50.0, power_vs_lhp=50.0, power_vs_rhp=50.0),
                self._platoon_hitter("Peer 2", weighted_pa=515, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=34.0, contact_vs_rhp=35.0, power_vs_lhp=36.0, power_vs_rhp=37.0),
            ],
            trim_final_traits=False,
        )
        above_outputs = rate_players(
            [
                self._platoon_hitter(
                    "Contact Above",
                    weighted_pa=540,
                    contact_gap=21.0,
                    power_gap=0.0,
                    contact_vs_lhp=72.0,
                    contact_vs_rhp=24.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter("Peer A", weighted_pa=520, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=50.0, contact_vs_rhp=50.0, power_vs_lhp=50.0, power_vs_rhp=50.0),
                self._platoon_hitter("Peer B", weighted_pa=515, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=34.0, contact_vs_rhp=35.0, power_vs_lhp=36.0, power_vs_rhp=37.0),
            ],
            trim_final_traits=False,
        )
        power_outputs = rate_players(
            [
                self._platoon_hitter(
                    "Power Above",
                    weighted_pa=540,
                    contact_gap=0.0,
                    power_gap=21.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=78.0,
                    power_vs_rhp=26.0,
                ),
                self._platoon_hitter("Peer X", weighted_pa=520, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=50.0, contact_vs_rhp=50.0, power_vs_lhp=50.0, power_vs_rhp=50.0),
                self._platoon_hitter("Peer Y", weighted_pa=515, contact_gap=0.0, power_gap=0.0, contact_vs_lhp=34.0, contact_vs_rhp=35.0, power_vs_lhp=36.0, power_vs_rhp=37.0),
            ],
            trim_final_traits=False,
        )

        contact_below_player = PlayerInput.from_dict(
            {
                "name": "Contact Below Sample",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 540},
                "trait_metrics": {
                    "contact_vs_lhp": 72.0,
                    "contact_vs_rhp": 24.0,
                    "contact_vs_lhp_minus_rhp": 19.0,
                    "power_vs_lhp": 50.0,
                    "power_vs_rhp": 50.0,
                    "power_vs_lhp_minus_rhp": 0.0,
                },
            }
        )
        contact_above_player = PlayerInput.from_dict(
            {
                "name": "Contact Above Sample",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 540},
                "trait_metrics": {
                    "contact_vs_lhp": 72.0,
                    "contact_vs_rhp": 24.0,
                    "contact_vs_lhp_minus_rhp": 21.0,
                    "power_vs_lhp": 50.0,
                    "power_vs_rhp": 50.0,
                    "power_vs_lhp_minus_rhp": 0.0,
                },
            }
        )

        below_traits = {
            trait.name for trait in next(output for output in below_outputs if output.name == "Contact Below").assigned_traits
        }
        above_traits = {
            trait.name for trait in next(output for output in above_outputs if output.name == "Contact Above").assigned_traits
        }
        power_traits = {
            trait.name for trait in next(output for output in power_outputs if output.name == "Power Above").assigned_traits
        }

        contact_split_percentiles = {
            "contact_vs_lhp": 83.33,
            "contact_vs_rhp": 16.67,
        }
        self.assertEqual(
            processing_core_module.platoon_penalty_percentile(
                "contact",
                contact_below_player,
                540,
                split_percentiles=contact_split_percentiles,
                trait_names={"CON vs LHP"},
            ),
            0.0,
        )
        self.assertGreater(
            processing_core_module.platoon_penalty_percentile(
                "contact",
                contact_above_player,
                540,
                split_percentiles=contact_split_percentiles,
                trait_names={"CON vs LHP"},
            ),
            0.0,
        )
        self.assertNotIn("CON vs LHP", below_traits)
        self.assertIn("CON vs LHP", above_traits)
        self.assertIn("POW vs LHP", power_traits)

    def test_platoon_gap_without_weak_side_profile_has_no_trait_or_penalty(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Strong Both Sides",
                    weighted_pa=540,
                    contact_gap=24.0,
                    power_gap=30.0,
                    contact_vs_lhp=76.0,
                    contact_vs_rhp=66.0,
                    power_vs_lhp=82.0,
                    power_vs_rhp=70.0,
                ),
                self._platoon_hitter(
                    "Average Peer",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Weak Peer",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=32.0,
                    contact_vs_rhp=33.0,
                    power_vs_lhp=34.0,
                    power_vs_rhp=35.0,
                ),
            ],
            trim_final_traits=False,
        )

        strong_both = next(output for output in outputs if output.name == "Strong Both Sides")
        assigned_traits = {trait.name for trait in strong_both.assigned_traits}

        self.assertNotIn("CON vs LHP", assigned_traits)
        self.assertNotIn("CON vs RHP", assigned_traits)
        self.assertNotIn("POW vs LHP", assigned_traits)
        self.assertNotIn("POW vs RHP", assigned_traits)

    def test_platoon_penalty_requires_minimum_weighted_pa(self) -> None:
        low_sample_player = PlayerInput.from_dict(
            {
                "name": "Low Sample Split",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 180},
                "trait_metrics": {
                    "contact_vs_lhp_minus_rhp": 24.0,
                    "power_vs_lhp_minus_rhp": 30.0,
                },
            }
        )
        full_sample_player = PlayerInput.from_dict(
            {
                "name": "Full Sample Split",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 520},
                "trait_metrics": {
                    "contact_vs_lhp_minus_rhp": 24.0,
                    "power_vs_lhp_minus_rhp": 30.0,
                },
            }
        )

        split_percentiles = {
            "contact_vs_lhp": 80.0,
            "contact_vs_rhp": 20.0,
            "power_vs_lhp": 80.0,
            "power_vs_rhp": 20.0,
        }
        self.assertEqual(
            processing_core_module.platoon_penalty_percentile(
                "contact",
                low_sample_player,
                180,
                split_percentiles=split_percentiles,
                trait_names={"CON vs LHP"},
            ),
            0.0,
        )
        self.assertEqual(
            processing_core_module.platoon_penalty_percentile(
                "power",
                low_sample_player,
                180,
                split_percentiles=split_percentiles,
                trait_names={"POW vs LHP"},
            ),
            0.0,
        )
        self.assertGreater(
            processing_core_module.platoon_penalty_percentile(
                "contact",
                full_sample_player,
                520,
                split_percentiles=split_percentiles,
                trait_names={"CON vs LHP"},
            ),
            0.0,
        )
        self.assertGreater(
            processing_core_module.platoon_penalty_percentile(
                "power",
                full_sample_player,
                520,
                split_percentiles=split_percentiles,
                trait_names={"POW vs LHP"},
            ),
            0.0,
        )

    def test_platoon_penalty_increases_with_split_pa_imbalance(self) -> None:
        balanced_split_player = PlayerInput.from_dict(
            {
                "name": "Balanced Split Volume",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 520},
                "trait_metrics": {
                    "contact_vs_lhp_minus_rhp": 24.0,
                    "power_vs_lhp_minus_rhp": 30.0,
                    "pa_vs_lhp": 260.0,
                    "pa_vs_rhp": 260.0,
                },
            }
        )
        imbalanced_split_player = PlayerInput.from_dict(
            {
                "name": "Imbalanced Split Volume",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": 520},
                "trait_metrics": {
                    "contact_vs_lhp_minus_rhp": 24.0,
                    "power_vs_lhp_minus_rhp": 30.0,
                    "pa_vs_lhp": 460.0,
                    "pa_vs_rhp": 60.0,
                },
            }
        )

        split_percentiles = {
            "contact_vs_lhp": 80.0,
            "contact_vs_rhp": 20.0,
            "power_vs_lhp": 80.0,
            "power_vs_rhp": 20.0,
        }
        balanced_contact_penalty = processing_core_module.platoon_penalty_percentile(
            "contact",
            balanced_split_player,
            520,
            split_percentiles=split_percentiles,
            trait_names={"CON vs LHP"},
        )
        imbalanced_contact_penalty = processing_core_module.platoon_penalty_percentile(
            "contact",
            imbalanced_split_player,
            520,
            split_percentiles=split_percentiles,
            trait_names={"CON vs LHP"},
        )
        balanced_power_penalty = processing_core_module.platoon_penalty_percentile(
            "power",
            balanced_split_player,
            520,
            split_percentiles=split_percentiles,
            trait_names={"POW vs LHP"},
        )
        imbalanced_power_penalty = processing_core_module.platoon_penalty_percentile(
            "power",
            imbalanced_split_player,
            520,
            split_percentiles=split_percentiles,
            trait_names={"POW vs LHP"},
        )

        self.assertGreater(imbalanced_contact_penalty, balanced_contact_penalty)
        self.assertGreater(imbalanced_power_penalty, balanced_power_penalty)

    def test_platoon_penalty_only_applies_when_platoon_trait_assigned(self) -> None:
        player = PlayerInput.from_dict(
            self._platoon_hitter(
                "Penalty Gate",
                weighted_pa=540,
                contact_gap=24.0,
                power_gap=30.0,
            )
        )

        split_percentiles = {
            "contact_vs_lhp": 80.0,
            "contact_vs_rhp": 20.0,
            "power_vs_lhp": 80.0,
            "power_vs_rhp": 20.0,
        }
        penalty_contact = processing_core_module.platoon_penalty_percentile(
            "contact",
            player,
            540,
            split_percentiles=split_percentiles,
            trait_names={"CON vs LHP"},
        )
        penalty_power = processing_core_module.platoon_penalty_percentile(
            "power",
            player,
            540,
            split_percentiles=split_percentiles,
            trait_names={"POW vs LHP"},
        )

        no_platoon_output = RatingOutput.from_dict(
            {
                "name": "Penalty Gate",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "ratings": {"contact": 50, "power": 50},
                "percentiles": {"contact": 50.0, "power": 50.0},
                "overall_numeric": 50,
                "overall_grade": "C",
                "confidence": "medium",
                "review_flags": [],
                "suggested_traits": [],
                "assigned_traits": [
                    {
                        "name": "Stealer",
                        "chemistry_type": "Crafty",
                        "polarity": "positive",
                        "confidence": "high",
                        "reason": "Test trait",
                    }
                ],
                "recommended_personalities": [],
                "metadata": {},
            }
        )

        contact_assigned = processing_core_module.assigned_platoon_trait_names(no_platoon_output, "contact")
        power_assigned = processing_core_module.assigned_platoon_trait_names(no_platoon_output, "power")
        effective_contact_penalty = penalty_contact if contact_assigned else 0.0
        effective_power_penalty = penalty_power if power_assigned else 0.0

        self.assertGreater(penalty_contact, 0.0)
        self.assertGreater(penalty_power, 0.0)
        self.assertEqual(effective_contact_penalty, 0.0)
        self.assertEqual(effective_power_penalty, 0.0)

    def test_extreme_rhp_usage_forces_rhp_platoon_traits_and_penalty(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Sheltered RHP",
                    weighted_pa=540,
                    contact_gap=4.0,
                    power_gap=5.0,
                    contact_vs_lhp=18.0,
                    contact_vs_rhp=62.0,
                    power_vs_lhp=22.0,
                    power_vs_rhp=70.0,
                    pa_vs_lhp=24.0,
                    pa_vs_rhp=516.0,
                    batting_average=0.286,
                    adjusted_obp=0.353,
                    slugging=0.474,
                    iso=0.188,
                    hr_per_pa=0.032,
                    barrel_rate=0.086,
                    avg_exit_velocity=89.8,
                ),
                self._platoon_hitter(
                    "Balanced Baseline",
                    weighted_pa=540,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                    pa_vs_lhp=270.0,
                    pa_vs_rhp=270.0,
                    batting_average=0.286,
                    adjusted_obp=0.353,
                    slugging=0.474,
                    iso=0.188,
                    hr_per_pa=0.032,
                    barrel_rate=0.086,
                    avg_exit_velocity=89.8,
                ),
                self._platoon_hitter(
                    "Peer A",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Peer B",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                ),
            ]
        )

        sheltered = next(output for output in outputs if output.name == "Sheltered RHP")
        baseline = next(output for output in outputs if output.name == "Balanced Baseline")
        assigned_traits = {trait.name for trait in sheltered.assigned_traits}

        self.assertIn("CON vs RHP", assigned_traits)
        self.assertIn("POW vs RHP", assigned_traits)
        self.assertNotIn("CON vs LHP", assigned_traits)
        self.assertNotIn("POW vs LHP", assigned_traits)
        self.assertLess(sheltered.percentiles["contact"], baseline.percentiles["contact"])
        self.assertLess(sheltered.percentiles["power"], baseline.percentiles["power"])

    def test_extreme_lhp_usage_forces_usage_side_even_when_gap_points_other_way(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Sheltered LHP",
                    weighted_pa=530,
                    contact_gap=-8.0,
                    power_gap=-10.0,
                    contact_vs_lhp=42.0,
                    contact_vs_rhp=68.0,
                    power_vs_lhp=40.0,
                    power_vs_rhp=72.0,
                    pa_vs_lhp=500.0,
                    pa_vs_rhp=30.0,
                ),
                self._platoon_hitter(
                    "Peer A",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Peer B",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                ),
            ]
        )

        sheltered = next(output for output in outputs if output.name == "Sheltered LHP")
        assigned_traits = {trait.name for trait in sheltered.assigned_traits}

        self.assertIn("CON vs LHP", assigned_traits)
        self.assertIn("POW vs LHP", assigned_traits)
        self.assertNotIn("CON vs RHP", assigned_traits)
        self.assertNotIn("POW vs RHP", assigned_traits)

    def test_extreme_usage_override_respects_split_pa_floor(self) -> None:
        outputs = rate_players(
            [
                self._platoon_hitter(
                    "Tiny Split Sample",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=18.0,
                    contact_vs_rhp=62.0,
                    power_vs_lhp=22.0,
                    power_vs_rhp=70.0,
                    pa_vs_lhp=18.0,
                    pa_vs_rhp=2.0,
                ),
                self._platoon_hitter(
                    "Balanced Baseline",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                    pa_vs_lhp=260.0,
                    pa_vs_rhp=260.0,
                ),
                self._platoon_hitter(
                    "Peer",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                ),
            ]
        )

        tiny_sample = next(output for output in outputs if output.name == "Tiny Split Sample")
        baseline = next(output for output in outputs if output.name == "Balanced Baseline")
        assigned_traits = {trait.name for trait in tiny_sample.assigned_traits}

        self.assertNotIn("CON vs RHP", assigned_traits)
        self.assertNotIn("POW vs RHP", assigned_traits)
        self.assertEqual(tiny_sample.percentiles["contact"], baseline.percentiles["contact"])
        self.assertEqual(tiny_sample.percentiles["power"], baseline.percentiles["power"])

    def test_extreme_usage_override_uses_total_multiseason_pa_for_sample_gate(self) -> None:
        outputs = rate_players(
            [
                {
                    "name": "Sheltered Multi Season",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": {"current": 0.209, "previous": 0.245},
                        "hr_per_pa": {"current": 0.052632, "previous": 0.056034},
                        "barrel_rate": {"current": 0.143, "previous": 0.125},
                        "slugging": {"current": 0.417, "previous": 0.497},
                        "avg_exit_velocity": {"current": 93.3, "previous": 91.4},
                        "strikeout_rate": {"current": 0.368421, "previous": 0.228448},
                        "contact_rate": {"current": 0.631579, "previous": 0.771552},
                        "batting_average": {"current": 0.208, "previous": 0.252},
                        "adjusted_obp": {"current": 0.316, "previous": 0.291},
                        "sprint_speed": {"current": 26.3, "previous": 27.1},
                        "baserunning_value": {"current": 0.0, "previous": -0.5},
                        "sb_attempt_rate": {"current": 0.0, "previous": 0.023529},
                        "triple_double_rate": {"current": 0.017544, "previous": 0.049569},
                    },
                    "samples": {
                        "weighted_pa": {"current": 57.0, "previous": 464.0},
                        "baserunning_opportunities": {"current": 14.0, "previous": 85.0},
                        "defensive_innings": {"current": 9.0, "previous": 188.0},
                    },
                    "trait_metrics": {
                        "contact_vs_lhp": {"current": 99.0, "previous": 19.905},
                        "contact_vs_rhp": {"current": 0.0, "previous": 50.862},
                        "contact_vs_lhp_minus_rhp": {"current": 343.237, "previous": -39.986},
                        "power_vs_lhp": {"current": 45.783, "previous": 51.867},
                        "power_vs_rhp": {"current": 61.299, "previous": 78.839},
                        "power_vs_lhp_minus_rhp": {"current": -217.391, "previous": -71.358},
                        "pa_vs_lhp": {"current": 3.0, "previous": 63.0},
                        "pa_vs_rhp": {"current": 54.0, "previous": 401.0},
                        "pa_split_imbalance": {"current": 0.8947, "previous": 0.7284},
                        "fastball_hitting": {"current": 99.0, "previous": 99.0},
                        "first_pitch_hitting": {"current": 99.0, "previous": 82.976},
                        "pressure_hitting": {"current": 0.0, "previous": 0.743},
                    },
                },
                self._platoon_hitter(
                    "Balanced Baseline",
                    weighted_pa=540,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                    pa_vs_lhp=270.0,
                    pa_vs_rhp=270.0,
                    batting_average=0.286,
                    adjusted_obp=0.353,
                    slugging=0.474,
                    iso=0.188,
                    hr_per_pa=0.032,
                    barrel_rate=0.086,
                    avg_exit_velocity=89.8,
                ),
                self._platoon_hitter(
                    "Peer A",
                    weighted_pa=520,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=50.0,
                    contact_vs_rhp=50.0,
                    power_vs_lhp=50.0,
                    power_vs_rhp=50.0,
                ),
                self._platoon_hitter(
                    "Peer B",
                    weighted_pa=515,
                    contact_gap=0.0,
                    power_gap=0.0,
                    contact_vs_lhp=34.0,
                    contact_vs_rhp=35.0,
                    power_vs_lhp=36.0,
                    power_vs_rhp=37.0,
                ),
            ]
        )

        sheltered = next(output for output in outputs if output.name == "Sheltered Multi Season")
        assigned_traits = {trait.name for trait in sheltered.assigned_traits}

        self.assertIn("CON vs RHP", assigned_traits)
        self.assertIn("POW vs RHP", assigned_traits)
        self.assertNotIn("CON vs LHP", assigned_traits)

    def test_extreme_usage_threshold_uses_dominant_side_share(self) -> None:
        player = PlayerInput.from_dict(
            {
                "name": "Dominant Share Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "samples": {"weighted_pa": {"current": 57.0, "previous": 464.0}},
                "trait_metrics": {
                    "pa_vs_lhp": {"current": 3.0, "previous": 63.0},
                    "pa_vs_rhp": {"current": 54.0, "previous": 401.0},
                },
            }
        )

        self.assertEqual(processing_core_module.effective_sample_volume(player.samples.get("weighted_pa")), 521.0)
        self.assertEqual(processing_core_module.hitter_extreme_usage_side(player), "rhp")

    def test_pitcher_components_use_role_specific_peer_groups(self) -> None:
        players = [
            self._pitcher_peer(
                "Starter Candidate",
                94.0,
                0.125,
                0.285,
                0.082,
                role_hint="starter",
                weighted_bf=820,
            ),
            self._pitcher_peer(
                "Reliever Candidate",
                94.0,
                0.125,
                0.285,
                0.082,
                role_hint="reliever",
                weighted_bf=300,
            ),
            self._pitcher_peer("SP Peer 1", 91.0, 0.105, 0.255, 0.095, role_hint="starter", weighted_bf=790),
            self._pitcher_peer("SP Peer 2", 91.2, 0.106, 0.256, 0.094, role_hint="starter", weighted_bf=800),
            self._pitcher_peer("SP Peer 3", 91.4, 0.107, 0.257, 0.093, role_hint="starter", weighted_bf=810),
            self._pitcher_peer("SP Peer 4", 91.6, 0.108, 0.258, 0.092, role_hint="starter", weighted_bf=805),
            self._pitcher_peer("RP Peer 1", 97.2, 0.152, 0.322, 0.068, role_hint="reliever", weighted_bf=310),
            self._pitcher_peer("RP Peer 2", 97.0, 0.150, 0.320, 0.069, role_hint="reliever", weighted_bf=320),
            self._pitcher_peer("RP Peer 3", 96.8, 0.148, 0.318, 0.070, role_hint="reliever", weighted_bf=330),
            self._pitcher_peer("RP Peer 4", 96.6, 0.146, 0.316, 0.071, role_hint="reliever", weighted_bf=340),
        ]

        outputs = rate_players(players)
        starter = next(output for output in outputs if output.name == "Starter Candidate")
        reliever = next(output for output in outputs if output.name == "Reliever Candidate")

        self.assertGreater(starter.percentiles["velocity"], reliever.percentiles["velocity"])
        self.assertGreater(starter.percentiles["junk"], reliever.percentiles["junk"])
        self.assertGreater(starter.percentiles["accuracy"], reliever.percentiles["accuracy"])

    def test_pitcher_role_peer_group_falls_back_to_combined_pool_for_unknown_two_way_role(self) -> None:
        players = [
            self._pitcher_peer("Starter Peer", 95.0, 0.130, 0.295, 0.078, role_hint="starter", weighted_bf=820),
            self._pitcher_peer("Reliever Peer", 93.0, 0.120, 0.280, 0.086, role_hint="reliever", weighted_bf=300),
            self._pitcher_peer(
                "Unknown Role Two-Way",
                94.0,
                0.125,
                0.287,
                0.082,
                role="two_way",
                team="LAA",
                primary_position="DH",
                tracked_fastballs=220,
                tracked_pitches=850,
                weighted_bf=None,
            ),
        ]

        outputs = rate_players(players)
        unknown = next(output for output in outputs if output.name == "Unknown Role Two-Way")

        self.assertGreater(unknown.percentiles["velocity"], 30.0)
        self.assertLess(unknown.percentiles["velocity"], 70.0)

    def test_two_way_role_weighting_prioritizes_pitching_components(self) -> None:
        ratings = {
            "power": 58,
            "contact": 60,
            "speed": 56,
            "fielding": 55,
            "arm": 52,
            "velocity": 96,
            "junk": 95,
            "accuracy": 92,
        }
        weighted = role_weighted_overall_numeric("two_way", ratings)
        equal_weighted = int(round(sum(ratings.values()) / len(ratings)))
        self.assertIsNotNone(weighted)
        self.assertGreater(weighted or 0, equal_weighted)

    def test_pitcher_elite_component_mix_gets_elite_overall_boost(self) -> None:
        ratings = {
            "velocity": 87,
            "junk": 84,
            "accuracy": 95,
        }
        weighted = role_weighted_overall_numeric("pitcher", ratings)
        self.assertGreaterEqual(weighted or 0, 95)

    def test_duplicate_names_keep_identity_specific_traits(self) -> None:
        base_metrics = {
            "iso": 0.175,
            "hr_per_pa": 0.030,
            "barrel_rate": 0.082,
            "slugging": 0.432,
            "avg_exit_velocity": 88.9,
            "strikeout_rate": 0.208,
            "contact_rate": 0.772,
            "batting_average": 0.268,
            "adjusted_obp": 0.338,
        }
        outputs = rate_players(
            [
                {
                    "name": "Chris Duplicate",
                    "player_id": "1001",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": base_metrics,
                    "samples": {"weighted_pa": 540},
                    "metadata": {"manual_traits": ["Bad Ball Hitter"]},
                },
                {
                    "name": "Chris Duplicate",
                    "player_id": "2002",
                    "role": "hitter",
                    "team": "LAD",
                    "primary_position": "RF",
                    "metrics": {**base_metrics, "sprint_speed": 30.1},
                    "samples": {"weighted_pa": 535},
                    "metadata": {"manual_traits": ["Stealer"]},
                },
                {
                    "name": "Peer Hitter",
                    "player_id": "3003",
                    "role": "hitter",
                    "team": "ATL",
                    "primary_position": "LF",
                    "metrics": {**base_metrics, "iso": 0.190},
                    "samples": {"weighted_pa": 520},
                },
            ]
        )

        nym_output = next(output for output in outputs if output.team == "NYM")
        lad_output = next(output for output in outputs if output.team == "LAD")

        self.assertEqual(nym_output.player_id, "1001")
        self.assertEqual(lad_output.player_id, "2002")
        self.assertIn("Bad Ball Hitter", {trait.name for trait in nym_output.assigned_traits})
        self.assertIn("Stealer", {trait.name for trait in lad_output.assigned_traits})

    def _build_power_players(self, *, sample: float) -> list[dict[str, object]]:
        return [
            self._player("Poor Surface", 0.390, sample),
            self._player("Elite Surface", 0.650, sample),
            self._player("Balanced Peer", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
            self._player("Low Peer", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
        ]

    def _build_contact_players(self) -> list[dict[str, object]]:
        players = [
            self._contact_hitter(
                "Elite Contact",
                0.080,
                0.905,
                0.334,
                0.417,
                0.512,
                620,
            )
        ]
        players.extend(
            self._contact_hitter(
                f"Contact Peer {index}",
                0.148 + (index * 0.005),
                0.842 - (index * 0.009),
                0.302 - (index * 0.006),
                0.374 - (index * 0.006),
                0.485 - (index * 0.011),
                560,
            )
            for index in range(1, 11)
        )
        players.extend(
            self._contact_hitter(
                f"Whiff Peer {index}",
                0.210 + (index * 0.007),
                0.765 - (index * 0.010),
                0.264 - (index * 0.005),
                0.332 - (index * 0.004),
                0.424 - (index * 0.008),
                535,
            )
            for index in range(1, 11)
        )
        return players

    def _build_elite_power_players(self) -> list[dict[str, object]]:
        players = [
            self._power_hitter(
                "Elite Power",
                0.315,
                0.071,
                0.183,
                0.626,
                95.4,
                610,
            )
        ]
        players.extend(
            self._power_hitter(
                f"Power Peer {index}",
                0.230 - (index * 0.006),
                0.050 - (index * 0.001),
                0.128 - (index * 0.004),
                0.535 - (index * 0.010),
                92.4 - (index * 0.25),
                560,
            )
            for index in range(1, 11)
        )
        players.extend(
            self._power_hitter(
                f"Light Bat {index}",
                0.142 - (index * 0.003),
                0.024 - (index * 0.0007),
                0.067 - (index * 0.002),
                0.408 - (index * 0.007),
                88.4 - (index * 0.20),
                520,
            )
            for index in range(1, 11)
        )
        return players

    def _build_average_hitter_band(self) -> list[dict[str, object]]:
        players = [
            {
                "name": "Average Hitter",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "metrics": {
                    "iso": 0.176,
                    "hr_per_pa": 0.031,
                    "barrel_rate": 0.082,
                    "slugging": 0.439,
                    "avg_exit_velocity": 89.1,
                    "strikeout_rate": 0.196,
                    "contact_rate": 0.784,
                    "batting_average": 0.272,
                    "adjusted_obp": 0.341,
                },
                "samples": {"weighted_pa": 560},
            }
        ]
        players.extend(
            {
                "name": f"Band Peer {index}",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "CF",
                "metrics": {
                    "iso": 0.150 + (index * 0.004),
                    "hr_per_pa": 0.024 + (index * 0.001),
                    "barrel_rate": 0.068 + (index * 0.003),
                    "slugging": 0.410 + (index * 0.010),
                    "avg_exit_velocity": 87.8 + (index * 0.22),
                    "strikeout_rate": 0.228 - (index * 0.004),
                    "contact_rate": 0.742 + (index * 0.008),
                    "batting_average": 0.248 + (index * 0.004),
                    "adjusted_obp": 0.316 + (index * 0.004),
                },
                "samples": {"weighted_pa": 540},
            }
            for index in range(1, 16)
        )
        return players

    def _player(
        self,
        name: str,
        slugging: float,
        sample: float,
        *,
        iso: float = 0.300,
        hr_per_pa: float = 0.070,
        barrel_rate: float = 0.170,
        avg_exit_velocity: float = 95.0,
    ) -> dict[str, object]:
        return {
            "name": name,
            "role": "hitter",
            "team": "NYM",
            "primary_position": "CF",
            "metrics": {
                "iso": iso,
                "hr_per_pa": hr_per_pa,
                "barrel_rate": barrel_rate,
                "slugging": slugging,
                "avg_exit_velocity": avg_exit_velocity,
            },
            "samples": {
                "weighted_pa": sample,
            },
        }

    def _pitcher_peer(
        self,
        name: str,
        avg_fastball_velocity: float,
        swinging_strike_rate: float,
        chase_rate: float,
        walk_rate: float,
        *,
        role: str = "pitcher",
        role_hint: str | None = None,
        team: str = "NYM",
        primary_position: str = "P",
        tracked_fastballs: float = 1430,
        tracked_pitches: float = 2600,
        weighted_bf: float | None = 650,
    ) -> dict[str, object]:
        metadata = {"pitching_role": role_hint} if role_hint else {}
        samples: dict[str, float] = {
            "tracked_pitches": tracked_pitches,
            "tracked_fastballs": tracked_fastballs,
        }
        if weighted_bf is not None:
            samples["weighted_bf"] = weighted_bf

        return {
            "name": name,
            "role": role,
            "team": team,
            "primary_position": primary_position,
            "pitch_mix": {"ff": 0.55, "sl": 0.25, "ch": 0.20},
            "metrics": {
                "avg_fastball_velocity": avg_fastball_velocity,
                "peak_fastball_velocity": avg_fastball_velocity + 2.0,
                "fastball_usage": 0.55,
                "swinging_strike_rate": swinging_strike_rate,
                "chase_rate": chase_rate,
                "movement_quality": 22.0,
                "stuff_metric": 120.0,
                "arsenal_diversity": 0.75,
                "weak_contact_rate": 0.64,
                "walk_rate": walk_rate,
                "strike_pct": 0.64,
                "zone_pct": 0.48,
                "first_pitch_strike_pct": 0.60,
                "command_error_rate": 0.36,
            },
            "samples": samples,
            "metadata": metadata,
        }

    def _contact_hitter(
        self,
        name: str,
        strikeout_rate: float,
        contact_rate: float,
        batting_average: float,
        adjusted_obp: float,
        slugging: float,
        sample: float,
    ) -> dict[str, object]:
        return {
            "name": name,
            "role": "hitter",
            "team": "NYM",
            "primary_position": "CF",
            "metrics": {
                "iso": max(0.120, slugging - batting_average),
                "hr_per_pa": 0.020 + max(0.0, slugging - 0.400) * 0.09,
                "barrel_rate": 0.060 + max(0.0, slugging - 0.400) * 0.18,
                "slugging": slugging,
                "avg_exit_velocity": 88.0 + max(0.0, slugging - 0.400) * 20.0,
                "strikeout_rate": strikeout_rate,
                "contact_rate": contact_rate,
                "batting_average": batting_average,
                "adjusted_obp": adjusted_obp,
            },
            "samples": {"weighted_pa": sample},
        }

    def _power_hitter(
        self,
        name: str,
        iso: float,
        hr_per_pa: float,
        barrel_rate: float,
        slugging: float,
        avg_exit_velocity: float,
        sample: float,
    ) -> dict[str, object]:
        return {
            "name": name,
            "role": "hitter",
            "team": "NYM",
            "primary_position": "RF",
            "metrics": {
                "iso": iso,
                "hr_per_pa": hr_per_pa,
                "barrel_rate": barrel_rate,
                "slugging": slugging,
                "avg_exit_velocity": avg_exit_velocity,
                "strikeout_rate": 0.214,
                "contact_rate": 0.758,
                "batting_average": max(0.220, slugging - iso),
                "adjusted_obp": max(0.300, slugging - iso + 0.070),
            },
            "samples": {"weighted_pa": sample},
        }

    def _platoon_hitter(
        self,
        name: str,
        *,
        weighted_pa: float,
        contact_gap: float,
        power_gap: float,
        contact_vs_lhp: float | None = None,
        contact_vs_rhp: float | None = None,
        power_vs_lhp: float | None = None,
        power_vs_rhp: float | None = None,
        pa_vs_lhp: float | None = None,
        pa_vs_rhp: float | None = None,
        batting_average: float = 0.272,
        adjusted_obp: float = 0.341,
        slugging: float = 0.445,
        iso: float = 0.182,
        hr_per_pa: float = 0.030,
        barrel_rate: float = 0.082,
        avg_exit_velocity: float = 89.1,
    ) -> dict[str, object]:
        return {
            "name": name,
            "role": "hitter",
            "team": "NYM",
            "primary_position": "CF",
            "metrics": {
                "iso": iso,
                "hr_per_pa": hr_per_pa,
                "barrel_rate": barrel_rate,
                "slugging": slugging,
                "avg_exit_velocity": avg_exit_velocity,
                "strikeout_rate": 0.196,
                "contact_rate": 0.786,
                "batting_average": batting_average,
                "adjusted_obp": adjusted_obp,
            },
            "samples": {"weighted_pa": weighted_pa},
            "trait_metrics": {
                "contact_vs_lhp": contact_vs_lhp,
                "contact_vs_rhp": contact_vs_rhp,
                "contact_vs_lhp_minus_rhp": contact_gap,
                "power_vs_lhp": power_vs_lhp,
                "power_vs_rhp": power_vs_rhp,
                "power_vs_lhp_minus_rhp": power_gap,
                "pa_vs_lhp": pa_vs_lhp,
                "pa_vs_rhp": pa_vs_rhp,
            },
        }


class MissingFieldConsumptionTests(unittest.TestCase):
    """Issue 41: verify oaa/drs/uzr are active in rating composites."""

    def _build_fielder(self, name: str, oaa: float, drs: float, uzr: float) -> dict:
        """Build a hitter with controlled defensive metrics and identical offensive stats."""
        return {
            "name": name,
            "role": "hitter",
            "team": "NYM",
            "primary_position": "CF",
            "metrics": {
                "iso": 0.180,
                "hr_per_pa": 0.032,
                "barrel_rate": 0.085,
                "slugging": 0.445,
                "avg_exit_velocity": 89.0,
                "strikeout_rate": 0.200,
                "contact_rate": 0.780,
                "batting_average": 0.272,
                "adjusted_obp": 0.340,
                "oaa": oaa,
                "drs": drs,
                "uzr": uzr,
                "fielding_pct_proxy": 0.990,
                "position_difficulty": 0.82,
                "arm_strength": 87.0,
                "outfield_arm_runs": 1.0,
                "arm_position_baseline": 0.68,
            },
            "samples": {"weighted_pa": 550, "defensive_innings": 1050},
        }

    def test_high_oaa_player_has_higher_fielding_percentile(self) -> None:
        players = [
            self._build_fielder("Elite Fielder", oaa=18.0, drs=15.0, uzr=12.0),
            self._build_fielder("Average Fielder", oaa=0.0, drs=0.0, uzr=0.0),
            self._build_fielder("Poor Fielder", oaa=-15.0, drs=-12.0, uzr=-10.0),
        ]
        outputs = rate_players(players)
        by_name = {output.name: output for output in outputs}

        elite_pct = by_name["Elite Fielder"].percentiles["fielding"]
        average_pct = by_name["Average Fielder"].percentiles["fielding"]
        poor_pct = by_name["Poor Fielder"].percentiles["fielding"]

        self.assertGreater(elite_pct, average_pct)
        self.assertGreater(average_pct, poor_pct)

    def test_two_strike_contact_rate_is_ignored_for_contact_rating(self) -> None:
        base_metrics = {
            "iso": 0.160,
            "hr_per_pa": 0.028,
            "barrel_rate": 0.075,
            "slugging": 0.420,
            "avg_exit_velocity": 88.5,
            "strikeout_rate": 0.215,
            "contact_rate": 0.765,
            "batting_average": 0.262,
            "adjusted_obp": 0.330,
        }
        players = [
            {
                "name": "High Two Strike",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "2B",
                "metrics": {**base_metrics, "two_strike_contact_rate": 0.820},
                "samples": {"weighted_pa": 500},
            },
            {
                "name": "Low Two Strike",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "2B",
                "metrics": {**base_metrics, "two_strike_contact_rate": 0.520},
                "samples": {"weighted_pa": 500},
            },
            {
                "name": "Peer A",
                "role": "hitter",
                "team": "NYM",
                "primary_position": "2B",
                "metrics": {**base_metrics, "two_strike_contact_rate": 0.650},
                "samples": {"weighted_pa": 500},
            },
        ]
        outputs = rate_players(players)
        by_name = {output.name: output for output in outputs}

        self.assertEqual(
            by_name["High Two Strike"].percentiles["contact"],
            by_name["Low Two Strike"].percentiles["contact"],
        )


    # ------------------------------------------------------------------
    # Issue 105 – derive missing trait metrics from raw stats
    # ------------------------------------------------------------------

    def test_mind_gamer_assigns_from_high_walk_rate_without_explicit_trait_metric(self) -> None:
        """A high bb_pct in metrics should derive mind_games ≥ 65 and trigger Mind Gamer."""
        # bb_pct = 0.155 → (15.5 - 4.0) / (20.0 - 4.0) * 100 ≈ 71.9 → ≥ 65 → Mind Gamer
        outputs = rate_players(
            [
                {
                    "name": "High Walk Hitter",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "1B",
                    "metrics": {
                        "bb_pct": 0.155,
                        "iso": 0.180,
                        "hr_per_pa": 0.033,
                        "barrel_rate": 0.085,
                        "slugging": 0.450,
                        "avg_exit_velocity": 89.5,
                        "strikeout_rate": 0.185,
                        "contact_rate": 0.775,
                        "batting_average": 0.268,
                        "adjusted_obp": 0.370,
                    },
                    "samples": {"weighted_pa": 530},
                    # No explicit trait_metrics.mind_games — must be derived
                },
                {
                    "name": "Peer 1",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.220,
                        "hr_per_pa": 0.045,
                        "barrel_rate": 0.110,
                        "slugging": 0.500,
                        "avg_exit_velocity": 91.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.760,
                        "batting_average": 0.270,
                        "adjusted_obp": 0.340,
                    },
                    "samples": {"weighted_pa": 425},
                },
                {
                    "name": "Peer 2",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "RF",
                    "metrics": {
                        "iso": 0.120,
                        "hr_per_pa": 0.025,
                        "barrel_rate": 0.060,
                        "slugging": 0.360,
                        "avg_exit_velocity": 87.5,
                        "strikeout_rate": 0.230,
                        "contact_rate": 0.720,
                        "batting_average": 0.245,
                        "adjusted_obp": 0.305,
                    },
                    "samples": {"weighted_pa": 425},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(o for o in outputs if o.name == "High Walk Hitter")
        trait_names = {t.name for t in candidate.assigned_traits}
        self.assertIn("Mind Gamer", trait_names)

    def test_mind_gamer_assigns_from_walk_rate_fallback_when_bb_pct_absent(self) -> None:
        """Mind Gamer should still derive when ingest provides walk_rate but not bb_pct."""
        outputs = rate_players(
            [
                {
                    "name": "Walk Rate Hitter",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "1B",
                    "metrics": {
                        "walk_rate": 0.155,
                        "iso": 0.180,
                        "hr_per_pa": 0.033,
                        "barrel_rate": 0.085,
                        "slugging": 0.450,
                        "avg_exit_velocity": 89.5,
                        "strikeout_rate": 0.185,
                        "contact_rate": 0.775,
                        "batting_average": 0.268,
                        "adjusted_obp": 0.370,
                    },
                    "samples": {"weighted_pa": 530},
                },
                {
                    "name": "Peer 1",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.220,
                        "hr_per_pa": 0.045,
                        "barrel_rate": 0.110,
                        "slugging": 0.500,
                        "avg_exit_velocity": 91.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.760,
                        "batting_average": 0.270,
                        "adjusted_obp": 0.340,
                    },
                    "samples": {"weighted_pa": 425},
                },
                {
                    "name": "Peer 2",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "RF",
                    "metrics": {
                        "iso": 0.120,
                        "hr_per_pa": 0.025,
                        "barrel_rate": 0.060,
                        "slugging": 0.360,
                        "avg_exit_velocity": 87.5,
                        "strikeout_rate": 0.230,
                        "contact_rate": 0.720,
                        "batting_average": 0.245,
                        "adjusted_obp": 0.305,
                    },
                    "samples": {"weighted_pa": 425},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(o for o in outputs if o.name == "Walk Rate Hitter")
        trait_names = {t.name for t in candidate.assigned_traits}
        self.assertIn("Mind Gamer", trait_names)

    def test_workhorse_assigns_from_projected_ip_without_explicit_trait_metric(self) -> None:
        """A pitcher with projected_ip = 200 derives workhorse = 80.0 and should get the Workhorse trait."""
        # workhorse = 200 / 250 * 100 = 80.0 → ≥ 80 → Workhorse
        outputs = rate_players(
            [
                {
                    "name": "Workhorse Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "projected_ip": 200.0,
                    "metrics": {
                        "era": 3.50,
                        "whip": 1.18,
                        "strikeout_rate": 0.230,
                        "walk_rate": 0.075,
                        "hr_per_9": 0.95,
                        "fip": 3.65,
                    },
                    "samples": {"weighted_bf": {"current": 650}},
                    # No explicit trait_metrics.workhorse — must be derived
                },
                {
                    "name": "Peer Pitcher",
                    "role": "pitcher",
                    "team": "NYM",
                    "primary_position": "P",
                    "projected_ip": 165.0,
                    "metrics": {
                        "era": 4.20,
                        "whip": 1.30,
                        "strikeout_rate": 0.205,
                        "walk_rate": 0.090,
                        "hr_per_9": 1.10,
                        "fip": 4.10,
                    },
                    "samples": {"weighted_bf": {"current": 580}},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(o for o in outputs if o.name == "Workhorse Pitcher")
        trait_names = {t.name for t in candidate.assigned_traits}
        self.assertIn("Workhorse", trait_names)

    def test_durable_assigns_from_multi_season_pa_volumes_without_explicit_trait_metric(self) -> None:
        """A hitter with all seasons above 500 PA derives durability = 100 and should get Durable."""
        # durability = 3/3 * 100 = 100 → ≥ 65 → Durable
        outputs = rate_players(
            [
                {
                    "name": "Iron Man Hitter",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "2B",
                    "metrics": {
                        "iso": 0.165,
                        "hr_per_pa": 0.027,
                        "barrel_rate": 0.070,
                        "slugging": 0.415,
                        "avg_exit_velocity": 88.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.768,
                        "batting_average": 0.265,
                        "adjusted_obp": 0.338,
                    },
                    "samples": {
                        "weighted_pa": {"current": 555, "previous": 540, "two_years_ago": 510}
                    },
                    # No explicit trait_metrics.durability — must be derived
                },
                {
                    "name": "Peer 1",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.220,
                        "hr_per_pa": 0.045,
                        "barrel_rate": 0.110,
                        "slugging": 0.500,
                        "avg_exit_velocity": 91.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.760,
                        "batting_average": 0.270,
                        "adjusted_obp": 0.340,
                    },
                    "samples": {"weighted_pa": 425},
                },
                {
                    "name": "Peer 2",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "RF",
                    "metrics": {
                        "iso": 0.120,
                        "hr_per_pa": 0.025,
                        "barrel_rate": 0.060,
                        "slugging": 0.360,
                        "avg_exit_velocity": 87.5,
                        "strikeout_rate": 0.230,
                        "contact_rate": 0.720,
                        "batting_average": 0.245,
                        "adjusted_obp": 0.305,
                    },
                    "samples": {"weighted_pa": 425},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(o for o in outputs if o.name == "Iron Man Hitter")
        trait_names = {t.name for t in candidate.assigned_traits}
        self.assertIn("Durable", trait_names)

    def test_dive_wizard_derives_from_range_metrics_without_explicit_dive_recovery(self) -> None:
        """Dive Wizard should trigger when oaa/drs/uzr imply a dive_recovery ≥ 65 with no explicit value."""
        # avg(12, 10, 9) = 10.33 → (10.33 - (-5)) / (20 - (-5)) * 100 = 15.33/25 * 100 ≈ 61.3
        # Let's use higher values: avg(15, 14, 13) = 14 → (14 + 5) / 25 * 100 = 76 → ≥ 65
        outputs = rate_players(
            [
                {
                    "name": "Range Wizard",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "CF",
                    "metrics": {
                        "iso": 0.175,
                        "hr_per_pa": 0.030,
                        "barrel_rate": 0.080,
                        "slugging": 0.430,
                        "avg_exit_velocity": 88.7,
                        "strikeout_rate": 0.195,
                        "contact_rate": 0.790,
                        "batting_average": 0.278,
                        "adjusted_obp": 0.345,
                        "oaa": 15.0,
                        "drs": 14.0,
                        "uzr": 13.0,
                    },
                    "samples": {"weighted_pa": 540, "defensive_innings": 1100},
                    # No explicit trait_metrics.dive_recovery — must be derived
                },
                {
                    "name": "Peer 1",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "LF",
                    "metrics": {
                        "iso": 0.220,
                        "hr_per_pa": 0.045,
                        "barrel_rate": 0.110,
                        "slugging": 0.500,
                        "avg_exit_velocity": 91.0,
                        "strikeout_rate": 0.200,
                        "contact_rate": 0.760,
                        "batting_average": 0.270,
                        "adjusted_obp": 0.340,
                    },
                    "samples": {"weighted_pa": 425},
                },
                {
                    "name": "Peer 2",
                    "role": "hitter",
                    "team": "NYM",
                    "primary_position": "RF",
                    "metrics": {
                        "iso": 0.120,
                        "hr_per_pa": 0.025,
                        "barrel_rate": 0.060,
                        "slugging": 0.360,
                        "avg_exit_velocity": 87.5,
                        "strikeout_rate": 0.230,
                        "contact_rate": 0.720,
                        "batting_average": 0.245,
                        "adjusted_obp": 0.305,
                    },
                    "samples": {"weighted_pa": 425},
                },
            ],
            trim_final_traits=False,
        )

        candidate = next(o for o in outputs if o.name == "Range Wizard")
        trait_names = {t.name for t in candidate.assigned_traits}
        self.assertIn("Dive Wizard", trait_names)


if __name__ == "__main__":
    unittest.main()