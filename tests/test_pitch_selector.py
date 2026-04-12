from __future__ import annotations

import unittest

from smb4_mlb_ratings.pitch_selector import PITCH_SLOT_LIMIT, select_pitch_mix


class PitchSelectorTests(unittest.TestCase):
    def test_select_pitch_mix_applies_smb4_mappings(self) -> None:
        recommended = select_pitch_mix({"si": 0.34, "sv": 0.22, "fs": 0.18, "ff": 0.15})

        self.assertEqual(recommended, ["2-Seam Fastball", "Slider", "Forkball", "4-Seam Fastball"])

    def test_select_pitch_mix_merges_multiple_mlb_pitches_into_same_smb4_pitch(self) -> None:
        recommended = select_pitch_mix({"sl": 0.18, "sv": 0.17, "ff": 0.40, "ch": 0.10})

        self.assertEqual(recommended, ["4-Seam Fastball", "Slider", "Changeup"])

    def test_select_pitch_mix_caps_output_at_slot_limit(self) -> None:
        recommended = select_pitch_mix({"ff": 0.24, "si": 0.21, "fc": 0.19, "sl": 0.16, "cu": 0.12, "ch": 0.08})

        self.assertEqual(len(recommended), PITCH_SLOT_LIMIT)
        self.assertEqual(recommended, ["4-Seam Fastball", "2-Seam Fastball", "Cut Fastball", "Slider"])


if __name__ == "__main__":
    unittest.main()