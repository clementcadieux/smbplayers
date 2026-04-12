from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()