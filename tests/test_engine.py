from __future__ import annotations

import json
import unittest
from dataclasses import fields
from pathlib import Path

from smb4_mlb_ratings.engine import (
    blend_component_percentiles,
    rate_players,
    resolved_projected_ip,
    resolved_projected_pa,
    surface_weight_factor,
)
from smb4_mlb_ratings.models import PlayerInput


class SurfaceBlendTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()