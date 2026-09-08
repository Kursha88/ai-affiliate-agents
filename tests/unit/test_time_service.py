import unittest
from datetime import datetime, timezone

from src.core.time_service import TimeService


class TestTimeService(unittest.TestCase):
    def setUp(self) -> None:
        self.time_service = TimeService("Europe/Kyiv")

    def test_timezone_name(self) -> None:
        self.assertEqual(self.time_service.timezone_name, "Europe/Kyiv")

    def test_business_date_summer_late_utc_is_next_day_in_kyiv(self) -> None:
        # 2026-09-07 21:30 UTC -> 2026-09-08 00:30 Europe/Kyiv
        dt = datetime(2026, 9, 7, 21, 30, tzinfo=timezone.utc)
        self.assertEqual(self.time_service.business_date(dt), "2026-09-08")

    def test_business_date_winter_late_utc_is_next_day_in_kyiv(self) -> None:
        # 2026-01-01 22:30 UTC -> 2026-01-02 00:30 Europe/Kyiv
        dt = datetime(2026, 1, 1, 22, 30, tzinfo=timezone.utc)
        self.assertEqual(self.time_service.business_date(dt), "2026-01-02")

    def test_utc_timestamp_contains_z(self) -> None:
        ts = self.time_service.utc_timestamp()
        self.assertTrue(ts.endswith("Z"))


if __name__ == "__main__":
    unittest.main()