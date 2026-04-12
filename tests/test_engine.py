from __future__ import annotations

import json
import unittest
from dataclasses import fields
from pathlib import Path

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
from smb4_mlb_ratings.models import PlayerInput


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

    def test_interpolate_rating_expands_elite_percentile_band(self) -> None:
        self.assertEqual(interpolate_rating(88.0), 85)
        self.assertEqual(interpolate_rating(93.0), 90)
        self.assertEqual(interpolate_rating(96.0), 94)
        self.assertEqual(interpolate_rating(99.5), 98)

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

    def _build_power_players(self, *, sample: float) -> list[dict[str, object]]:
        return [
            self._player("Poor Surface", 0.390, sample),
            self._player("Elite Surface", 0.650, sample),
            self._player("Balanced Peer", 0.500, 425, iso=0.220, hr_per_pa=0.045, barrel_rate=0.110, avg_exit_velocity=91.0),
            self._player("Low Peer", 0.360, 425, iso=0.120, hr_per_pa=0.025, barrel_rate=0.060, avg_exit_velocity=87.5),
        ]

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
    ) -> dict[str, object]:
        return {
            "name": name,
            "role": "pitcher",
            "team": "NYM",
            "primary_position": "P",
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
            "samples": {"weighted_bf": 650, "tracked_pitches": 2600, "tracked_fastballs": 1430},
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


if __name__ == "__main__":
    unittest.main()