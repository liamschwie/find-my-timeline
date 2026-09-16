import unittest

from find_my_timeline.battery import decode_battery


class TestDecodeBattery(unittest.TestCase):
    def test_full(self):
        self.assertEqual(decode_battery(0b00000000), "Full")

    def test_medium(self):
        self.assertEqual(decode_battery(0b01000000), "Medium")

    def test_low(self):
        self.assertEqual(decode_battery(0b10000000), "Low")

    def test_very_low(self):
        self.assertEqual(decode_battery(0b11000000), "Very Low")

    def test_ignores_lower_bits(self):
        # Lower 6 bits carry unrelated flags; only bits 6-7 encode battery.
        self.assertEqual(decode_battery(0b11111111), "Very Low")
        self.assertEqual(decode_battery(0b00111111), "Full")


if __name__ == "__main__":
    unittest.main()
