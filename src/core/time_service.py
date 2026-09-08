from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


class TimeService:
    """
    Единый сервис времени.

    Технические временные метки храним в UTC.
    Бизнес-дата считается в Europe/Kyiv.
    """

    def __init__(self, timezone_name: str = "Europe/Kyiv") -> None:
        self.timezone_name = timezone_name
        self._tz = ZoneInfo(timezone_name)

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_kyiv(self) -> datetime:
        return self.now_utc().astimezone(self._tz)

    def utc_timestamp(self, dt: Optional[datetime] = None) -> str:
        """
        Возвращает UTC timestamp в ISO8601 с суффиксом Z.
        """
        if dt is None:
            dt = self.now_utc()

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def kyiv_date(self, dt: Optional[datetime] = None):
        """
        Возвращает date в Europe/Kyiv.
        Если dt naive, считаем его UTC.
        """
        if dt is None:
            return self.now_kyiv().date()

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(self._tz).date()

    def business_date(self, dt: Optional[datetime] = None) -> str:
        """
        Бизнес-дата в формате YYYY-MM-DD для Europe/Kyiv.
        """
        return self.kyiv_date(dt).isoformat()

    def is_today(self, dt: datetime) -> bool:
        """
        Проверяет, относится ли переданный момент к текущему бизнес-дню в Kyiv.
        """
        return self.business_date(dt) == self.business_date()