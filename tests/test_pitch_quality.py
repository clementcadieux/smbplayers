from __future__ import annotations

import unittest

from smb4_mlb_ratings.ingest.pitch_quality import (
    ELITE_PITCH_SPECS,
    derive_pitch_quality_metrics,
    parse_savant_pitch_details,
)


class PitchQualityTests(unittest.TestCase):
    def test_parse_savant_pitch_details_extracts_pitch_rows(self) -> None:
        payload = """
        <script>
        window.serverVals.pitchDetails = [
            {"api_pitch_type": "FF", "xba": 0.201, "xwoba": 0.299, "xslg": 0.401, "hard_hit_percent": 33.0, "brl_percent": 5.0, "swings": 100, "misses": 21, "release_speed": 95.4, "pitches": 180, "total_pitches": 600},
            {"api_pitch_type": "FS", "xba": 0.171, "xwoba": 0.250, "xslg": 0.290, "hard_hit_percent": 24.0, "brl_percent": 3.0, "swings": 80, "misses": 30, "release_speed": 85.0, "pitches": 120, "total_pitches": 600}
        ];
        </script>
        """

        details = parse_savant_pitch_details(payload)

        self.assertEqual(sorted(details), ["FF", "FS"])
        self.assertEqual(details["FF"]["pitches"], 180.0)
        self.assertEqual(details["FS"]["xwoba"], 0.25)

    def test_pitch_quality_derivation_boosts_prominent_secondary_pitch(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.36, "count": 360, "totalPitches": 1000, "averageSpeed": 95.0, "type": {"code": "FF"}},
            "SL": {"percentage": 0.34, "count": 340, "totalPitches": 1000, "averageSpeed": 84.0, "type": {"code": "SL"}},
            "CH": {"percentage": 0.12, "count": 120, "totalPitches": 1000, "averageSpeed": 86.5, "type": {"code": "CH"}},
        }
        savant_pitch_details = {
            "FF": {"xwoba": 0.305, "xba": 0.235, "xslg": 0.420, "hard_hit_percent": 37.0, "brl_percent": 7.0, "swings": 220.0, "misses": 45.0, "release_speed": 95.0},
            "SL": {"xwoba": 0.215, "xba": 0.170, "xslg": 0.280, "hard_hit_percent": 24.0, "brl_percent": 3.0, "swings": 190.0, "misses": 78.0, "release_speed": 84.0},
            "CH": {"xwoba": 0.290, "xba": 0.220, "xslg": 0.410, "hard_hit_percent": 34.0, "brl_percent": 6.0, "swings": 80.0, "misses": 20.0, "release_speed": 86.5},
        }

        metrics = derive_pitch_quality_metrics(arsenal, savant_pitch_details)

        self.assertIsNotNone(metrics["pitch_quality_4f"])
        self.assertIsNotNone(metrics["pitch_quality_sl"])
        self.assertGreater(metrics["pitch_quality_sl"], 65.0)
        self.assertGreater(metrics["pitch_quality_sl"], metrics["pitch_quality_ch"] or 0.0)

    def test_pitch_quality_derivation_supports_all_smb_pitch_families(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.22, "count": 220, "totalPitches": 1000, "averageSpeed": 95.5, "type": {"code": "FF"}},
            "SI": {"percentage": 0.16, "count": 160, "totalPitches": 1000, "averageSpeed": 94.0, "type": {"code": "SI"}},
            "FC": {"percentage": 0.11, "count": 110, "totalPitches": 1000, "averageSpeed": 90.5, "type": {"code": "FC"}},
            "CU": {"percentage": 0.10, "count": 100, "totalPitches": 1000, "averageSpeed": 80.0, "type": {"code": "CU"}},
            "CH": {"percentage": 0.12, "count": 120, "totalPitches": 1000, "averageSpeed": 85.8, "type": {"code": "CH"}},
            "FS": {"percentage": 0.10, "count": 100, "totalPitches": 1000, "averageSpeed": 84.7, "type": {"code": "FS"}},
            "SV": {"percentage": 0.11, "count": 110, "totalPitches": 1000, "averageSpeed": 83.4, "type": {"code": "SV"}},
            "SC": {"percentage": 0.08, "count": 80, "totalPitches": 1000, "averageSpeed": 81.6, "type": {"code": "SC"}},
        }
        savant_pitch_details = {
            "FF": {"xwoba": 0.245, "xba": 0.190, "xslg": 0.320, "hard_hit_percent": 28.0, "brl_percent": 4.0, "swings": 140.0, "misses": 38.0, "release_speed": 95.5, "pitches": 220.0},
            "SI": {"xwoba": 0.255, "xba": 0.205, "xslg": 0.340, "hard_hit_percent": 30.0, "brl_percent": 4.5, "swings": 95.0, "misses": 22.0, "release_speed": 94.0, "pitches": 160.0},
            "FC": {"xwoba": 0.235, "xba": 0.185, "xslg": 0.305, "hard_hit_percent": 26.0, "brl_percent": 3.5, "swings": 88.0, "misses": 27.0, "release_speed": 90.5, "pitches": 110.0},
            "CU": {"xwoba": 0.210, "xba": 0.165, "xslg": 0.270, "hard_hit_percent": 23.0, "brl_percent": 2.5, "swings": 82.0, "misses": 34.0, "release_speed": 80.0, "pitches": 100.0},
            "CH": {"xwoba": 0.225, "xba": 0.175, "xslg": 0.290, "hard_hit_percent": 25.0, "brl_percent": 3.0, "swings": 96.0, "misses": 36.0, "release_speed": 85.8, "pitches": 120.0},
            "FS": {"xwoba": 0.205, "xba": 0.160, "xslg": 0.255, "hard_hit_percent": 22.0, "brl_percent": 2.0, "swings": 78.0, "misses": 31.0, "release_speed": 84.7, "pitches": 100.0},
            "SV": {"xwoba": 0.215, "xba": 0.168, "xslg": 0.275, "hard_hit_percent": 24.0, "brl_percent": 2.8, "swings": 89.0, "misses": 35.0, "release_speed": 83.4, "pitches": 110.0},
            "SC": {"xwoba": 0.220, "xba": 0.172, "xslg": 0.285, "hard_hit_percent": 24.5, "brl_percent": 2.7, "swings": 62.0, "misses": 22.0, "release_speed": 81.6, "pitches": 80.0},
        }

        metrics = derive_pitch_quality_metrics(arsenal, savant_pitch_details)

        for spec in ELITE_PITCH_SPECS.values():
            self.assertIsNotNone(metrics[str(spec["metric_key"])])

    def test_pitch_quality_derivation_prioritizes_quality_over_usage(self) -> None:
        arsenal = {
            "FF": {"percentage": 0.45, "count": 450, "totalPitches": 1000, "averageSpeed": 95.0, "type": {"code": "FF"}},
            "SL": {"percentage": 0.30, "count": 300, "totalPitches": 1000, "averageSpeed": 84.5, "type": {"code": "SL"}},
            "CH": {"percentage": 0.22, "count": 220, "totalPitches": 1000, "averageSpeed": 86.0, "type": {"code": "CH"}},
        }
        savant_pitch_details = {
            "SL": {"xwoba": 0.195, "xba": 0.145, "xslg": 0.240, "hard_hit_percent": 20.0, "brl_percent": 2.0, "swings": 210.0, "misses": 92.0, "release_speed": 84.5},
            "CH": {"xwoba": 0.330, "xba": 0.255, "xslg": 0.500, "hard_hit_percent": 42.0, "brl_percent": 9.0, "swings": 160.0, "misses": 32.0, "release_speed": 86.0},
        }

        metrics = derive_pitch_quality_metrics(arsenal, savant_pitch_details)

        self.assertGreater(metrics["pitch_quality_sl"], metrics["pitch_quality_ch"] or 0.0)

    def test_pitch_quality_derivation_handles_missing_arsenal_data(self) -> None:
        metrics = derive_pitch_quality_metrics({})

        self.assertEqual(
            metrics,
            {
                "pitch_quality_4f": None,
                "pitch_quality_2f": None,
                "pitch_quality_cf": None,
                "pitch_quality_cb": None,
                "pitch_quality_ch": None,
                "pitch_quality_fk": None,
                "pitch_quality_sl": None,
                "pitch_quality_sb": None,
            },
        )


if __name__ == "__main__":
    unittest.main()