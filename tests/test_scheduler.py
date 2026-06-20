"""Tests for the backup scheduler helpers."""

import pytest

from hostsolo.scheduler import (
    cron_to_oncalendar,
    render_service_unit,
    render_timer_unit,
)
from pathlib import Path


@pytest.mark.parametrize(
    "cron,expected",
    [
        # The default schedule: every 6 hours on the hour.
        ("0 */6 * * *", "*-*-* 00/6:00:00"),
        # Daily at 03:30.
        ("30 3 * * *", "*-*-* 03:30:00"),
        # Top of every hour.
        ("0 * * * *", "*-*-* *:00:00"),
        # Every 15 minutes.
        ("*/15 * * * *", "*-*-* *:00/15:00"),
        # Weekly on Sunday at midnight (cron 0 == Sunday).
        ("0 0 * * 0", "Sun *-*-* 00:00:00"),
        # cron 7 is also Sunday.
        ("0 0 * * 7", "Sun *-*-* 00:00:00"),
        # Specific weekday.
        ("0 2 * * 1", "Mon *-*-* 02:00:00"),
        # Comma list in the hour field.
        ("0 0,12 * * *", "*-*-* 00,12:00:00"),
    ],
)
def test_cron_to_oncalendar(cron, expected):
    assert cron_to_oncalendar(cron) == expected


@pytest.mark.parametrize(
    "cron",
    [
        "0 */6 * *",  # too few fields
        "0 0 * * * *",  # too many fields
        "0-5 * * * *",  # ranges unsupported
        "@daily",  # shortcuts unsupported
    ],
)
def test_cron_to_oncalendar_rejects_unsupported(cron):
    with pytest.raises(ValueError):
        cron_to_oncalendar(cron)


def test_render_service_unit_contains_backup_command():
    unit = render_service_unit("/opt/venv/bin/hostsolo", Path("/home/u/app"), "prod")
    assert "ExecStart=/opt/venv/bin/hostsolo backup all --env prod" in unit
    assert "WorkingDirectory=/home/u/app" in unit
    assert "Type=oneshot" in unit


def test_render_timer_unit_contains_oncalendar():
    unit = render_timer_unit("*-*-* 00/6:00:00", "prod")
    assert "OnCalendar=*-*-* 00/6:00:00" in unit
    assert "Persistent=true" in unit
    assert "WantedBy=timers.target" in unit