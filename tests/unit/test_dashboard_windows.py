"""Unit: dashboard time-window math (feature 014 — research R4).

Pure logic: every window is anchored to the configured city timezone
(``resolved_city_timezone()``, RNF06) and every custom range is inclusive
on both ends. No database, no routes — the shapes later consumed by the
metric queries (contracts/dashboard.md §1–§5 / T007).
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from passanorte_back.core.config import Settings
from passanorte_back.modules.dashboard.services.metrics import (
    resolve_period_window,
    resolve_ranking_window,
    validate_limit,
)

CITY_TZ = ZoneInfo("America/Sao_Paulo")
UTC_TZ = UTC

# 2026-11-06 is a Friday; the week begins Monday 2026-11-02.
FROZEN_NOW = datetime(2026, 11, 6, 20, 30, tzinfo=UTC_TZ)


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CITY_TIMEZONE", "America/Sao_Paulo")
    return Settings.model_construct(
        database_url="sqlite:///:memory:",
        jwt_secret="unused",
        sensitive_data_key="unused",
    )


def _freeze_now(monkeypatch: pytest.MonkeyPatch) -> None:
    import passanorte_back.modules.dashboard.services.metrics as metrics

    monkeypatch.setattr(metrics, "_utc_now", lambda: FROZEN_NOW)


def test_today_window_covers_the_whole_city_tz_day(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-009: 'hoje' = [city-tz 00:00, agora] — inclusive at both ends."""
    _freeze_now(monkeypatch)
    start, end = resolve_period_window(_settings(monkeypatch), period="today")
    city_now = FROZEN_NOW.astimezone(CITY_TZ)
    day_start = city_now.replace(hour=0, minute=0, second=0, microsecond=0)
    assert start is not None and end is not None
    assert end == city_now
    assert start == day_start
    # Inclusive at both ends: the city-tz anchor itself is inside the window.
    assert day_start <= end.astimezone(CITY_TZ) and start <= end


def test_week_window_is_monday_to_sunday_of_the_city_tz_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: anchored to the Monday of the current city-tz week."""
    _freeze_now(monkeypatch)
    start, end = resolve_period_window(_settings(monkeypatch), period="week")
    city_now = FROZEN_NOW.astimezone(CITY_TZ)
    monday = city_now - timedelta(days=city_now.weekday())
    assert start is not None and end is not None
    assert start == monday.replace(hour=0, minute=0, second=0, microsecond=0)
    assert end == city_now


def test_month_window_is_the_whole_current_calendar_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-009: month = 1st day 00:00 → now (open month)."""
    _freeze_now(monkeypatch)
    start, end = resolve_period_window(_settings(monkeypatch), period="month")
    city_now = FROZEN_NOW.astimezone(CITY_TZ)
    month_start = city_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    assert start is not None and end is not None
    assert start == month_start
    assert end == city_now


def test_custom_period_is_inclusive_on_both_ends(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-009/edge case: custom range [startDate 00:00, endDate 23:59:59.999]."""
    _freeze_now(monkeypatch)
    start, end = resolve_period_window(
        _settings(monkeypatch),
        period="custom",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 3),
    )
    assert start is not None and end is not None
    assert start == datetime(2026, 10, 1, 0, 0, tzinfo=CITY_TZ)
    assert end == datetime(2026, 10, 3, 23, 59, 59, 999999, tzinfo=CITY_TZ)
    # Inclusive: a record exactly at endDate's last microsecond is inside.
    assert start <= end


def test_period_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(HTTPException) as error:
        resolve_period_window(_settings(monkeypatch), period=None)
    assert error.value.status_code == 422


def test_unknown_period_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(HTTPException) as error:
        resolve_period_window(_settings(monkeypatch), period="year")
    assert error.value.status_code == 422


def test_custom_without_dates_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """contracts/dashboard.md: period=custom requires both dates."""
    with pytest.raises(HTTPException) as error:
        resolve_period_window(_settings(monkeypatch), period="custom")
    assert error.value.status_code == 422


def test_custom_with_missing_start_date_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(HTTPException) as error:
        resolve_period_window(_settings(monkeypatch), period="custom", end_date=date(2026, 10, 3))
    assert error.value.status_code == 422


def test_inverted_custom_range_is_422(monkeypatch: pytest.MonkeyPatch) -> None:
    """Edge case: endDate before startDate is rejected with 422."""
    _freeze_now(monkeypatch)
    with pytest.raises(HTTPException) as error:
        resolve_period_window(
            _settings(monkeypatch),
            period="custom",
            start_date=date(2026, 10, 3),
            end_date=date(2026, 10, 1),
        )
    assert error.value.status_code == 422


def test_ranking_day_window_covers_reference_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-012 (Q3): one window per query — day = the reference date."""
    _freeze_now(monkeypatch)
    start, end = resolve_ranking_window(granularity="day", reference_date=date(2026, 11, 4))
    assert start == datetime(2026, 11, 4, 0, 0, tzinfo=CITY_TZ)
    assert end == datetime(2026, 11, 4, 23, 59, 59, 999999, tzinfo=CITY_TZ)


def test_ranking_month_window_covers_the_whole_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _freeze_now(monkeypatch)
    start, end = resolve_ranking_window(granularity="month", reference_date=date(2026, 11, 6))
    assert start == datetime(2026, 11, 1, 0, 0, tzinfo=CITY_TZ)
    # November — 30 days.
    assert end == datetime(2026, 11, 30, 23, 59, 59, 999999, tzinfo=CITY_TZ)


def test_ranking_year_window_covers_the_whole_year(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze_now(monkeypatch)
    start, end = resolve_ranking_window(granularity="year", reference_date=date(2026, 11, 6))
    assert start == datetime(2026, 1, 1, 0, 0, tzinfo=CITY_TZ)
    assert end == datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=CITY_TZ)


def test_ranking_without_reference_date_uses_frozen_today(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-012: referenceDate defaults to the current date (city tz)."""
    _freeze_now(monkeypatch)
    start, _end = resolve_ranking_window(granularity="day", reference_date=None)
    today = FROZEN_NOW.astimezone(CITY_TZ).date()
    assert start == datetime.combine(today, datetime.min.time(), tzinfo=CITY_TZ)


def test_limit_clamps_to_documented_default_and_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-013: default 5, range 1–100, out of range → 422."""
    assert validate_limit(None) == 5
    assert validate_limit(1) == 1
    assert validate_limit(100) == 100
    for bad in (0, -1, 101, 1000):
        with pytest.raises(HTTPException) as error:
            validate_limit(bad)
        assert error.value.status_code == 422
