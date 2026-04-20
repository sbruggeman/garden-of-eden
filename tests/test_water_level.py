import sys
import os
import unittest
import importlib.util

# Load water_level module directly to avoid triggering app/__init__.py (Flask)
_spec = importlib.util.spec_from_file_location(
    "water_level",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "app", "sensors", "water_level", "water_level.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
WaterLevelSampler = _mod.WaterLevelSampler


def make_sampler():
    published = []
    sampler = WaterLevelSampler(sensor_fn=lambda: None, on_publish=published.append)
    return sampler, published


class TestWaterLevelSampler(unittest.TestCase):

    def test_publishes_once_on_stable_readings(self):
        sampler, published = make_sampler()
        for _ in range(20):
            sampler.add_reading(10.0)
        self.assertEqual(len(published), 1)
        self.assertAlmostEqual(published[0], 10.0)

    def test_out_of_range_readings_discarded(self):
        sampler, published = make_sampler()
        for _ in range(20):
            sampler.add_reading(0.5)   # below VALID_MIN_CM (3.0) — sensor error
        for _ in range(20):
            sampler.add_reading(30.0)  # above VALID_MAX_CM (25.0) — out of range
        self.assertEqual(len(published), 0)

    def test_none_reading_discarded(self):
        sampler, published = make_sampler()
        for _ in range(20):
            sampler.add_reading(None)
        self.assertEqual(len(published), 0)

    def test_not_enough_readings_suppresses_publish(self):
        sampler, published = make_sampler()
        for _ in range(5):  # COUNT_FOR_VALUE is 6
            sampler.add_reading(10.0)
        self.assertEqual(len(published), 0)

    def test_realtime_publish_on_large_step_change(self):
        sampler, published = make_sampler()
        for _ in range(10):
            sampler.add_reading(10.0)
        initial_publishes = len(published)
        # step change of 5 cm exceeds REALTIME_CHANGE_THRESHOLD_CM (2.0)
        for _ in range(10):
            sampler.add_reading(15.0)
        self.assertGreater(len(published), initial_publishes)
        self.assertAlmostEqual(published[-1], 15.0)

    def test_noisy_readings_within_stable_threshold_no_extra_publish(self):
        sampler, published = make_sampler()
        for _ in range(10):
            sampler.add_reading(10.0)
        initial_publishes = len(published)
        # alternating 10.0 / 10.4 — delta is 0.4 cm, below both thresholds
        for i in range(20):
            sampler.add_reading(10.0 if i % 2 == 0 else 10.4)
        self.assertEqual(len(published), initial_publishes)

    def test_get_current_value_returns_stable_value(self):
        sampler, published = make_sampler()
        self.assertIsNone(sampler.get_current_value())
        for _ in range(10):
            sampler.add_reading(12.0)
        self.assertAlmostEqual(sampler.get_current_value(), 12.0)

    def test_stable_value_updates_after_threshold_crossed(self):
        sampler, published = make_sampler()
        for _ in range(10):
            sampler.add_reading(10.0)
        # change of 1.5 cm exceeds STABLE_VALUE_THRESHOLD_CM (1.0)
        for _ in range(10):
            sampler.add_reading(11.5)
        self.assertAlmostEqual(sampler.get_current_value(), 11.5)


if __name__ == "__main__":
    unittest.main()
