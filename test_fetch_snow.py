"""Offline regression tests; run: python -m unittest discover -s tests -v"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_snow as snow


class AggregationTests(unittest.TestCase):
    def setUp(self):
        self.end = datetime(2026, 11, 24, 10, tzinfo=timezone.utc)
        start = self.end - timedelta(hours=8 * 24)
        self.timestamps = [start + timedelta(hours=h) for h in range(8 * 24 + 1)]
        n = len(self.timestamps)
        self.payload = {
            'elevation': 1450.0,
            'hourly': {
                'time': [t.strftime('%Y-%m-%dT%H:%M') for t in self.timestamps],
                'snowfall': [1.0] * n,
                'snow_depth': [0.75] * n,
                'temperature_2m': [-8.0] * n,
                'wind_speed_10m': [25.0] * n,
                'wind_direction_10m': [360.0] * n,
                'wind_gusts_10m': [45.0] * n,
            },
        }

    def test_seven_consecutive_windows_and_conversions(self):
        record = snow.extract_zone(snow.ZONES[0], self.payload, self.end)
        self.assertEqual(record['snow_24h_cm'], 24)
        self.assertEqual(record['snow_7d_cm'], 168)
        self.assertEqual(record['snow_depth_cm'], 75)
        self.assertEqual(record['wind_direction_deg'], 0)
        self.assertEqual(record['grid_elevation_m'], 1450)
        self.assertEqual(len(record['snowfall_7d']), 7)
        self.assertEqual(record['snowfall_7d'][-1]['date'], '2026-11-24')
        self.assertEqual(record['sample_time_utc'], '2026-11-24T10:00:00Z')

    def test_missing_snow_is_null_not_zero(self):
        self.payload['hourly']['snowfall'][-1] = None
        record = snow.extract_zone(snow.ZONES[0], self.payload, self.end)
        self.assertIsNone(record['snow_24h_cm'])
        self.assertIsNone(record['snow_7d_cm'])
        self.assertIsNone(record['snowfall_7d'][-1]['snowfall_cm'])
        self.assertEqual(record['snowfall_7d'][0]['snowfall_cm'], 24)

    def test_zero_snow_is_real_zero(self):
        self.payload['hourly']['snowfall'] = [0] * len(self.timestamps)
        record = snow.extract_zone(snow.ZONES[0], self.payload, self.end)
        self.assertEqual(record['snow_24h_cm'], 0)
        self.assertEqual(record['snow_7d_cm'], 0)

    def test_bad_hourly_shape_rejected(self):
        self.payload['hourly']['wind_speed_10m'].pop()
        with self.assertRaisesRegex(ValueError, 'misaligned'):
            snow.extract_zone(snow.ZONES[0], self.payload, self.end)

    def test_missing_observation_hour_rejected(self):
        with self.assertRaisesRegex(ValueError, 'No model data'):
            snow.extract_zone(snow.ZONES[0], self.payload, self.end + timedelta(hours=1))


if __name__ == '__main__':
    unittest.main()
