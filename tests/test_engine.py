from __future__ import annotations

import unittest

from smb4_mlb_ratings.engine import blend_component_percentiles, rate_players, surface_weight_factor


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