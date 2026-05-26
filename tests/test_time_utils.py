from datetime import datetime, timedelta
from zoneinfo import ZoneInfoNotFoundError

from atv_player import time_utils


def test_beijing_timezone_falls_back_to_fixed_utc8_when_zoneinfo_data_is_missing(
    monkeypatch,
) -> None:
    def missing_zoneinfo(key: str):
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr(time_utils, "ZoneInfo", missing_zoneinfo)

    tzinfo = time_utils.beijing_timezone()

    assert tzinfo.utcoffset(datetime(2026, 5, 27)) == timedelta(hours=8)
    assert tzinfo.tzname(datetime(2026, 5, 27)) == "Asia/Shanghai"
