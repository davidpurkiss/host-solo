"""Helpers for installing scheduled backups as systemd user units.

The backup schedule is configured in ``hostsolo.yaml`` as a standard 5-field
cron expression. systemd timers use ``OnCalendar`` expressions instead, so we
translate the cron expression and render a oneshot service + timer pair that
run ``hostsolo backup all`` on the configured cadence.
"""

from pathlib import Path

# cron day-of-week (0 or 7 == Sunday) -> systemd day abbreviation
_DOW_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def _convert_field(field: str, pad: int) -> str:
    """Convert a single numeric cron field to its OnCalendar equivalent.

    Supports ``*``, integers, ``*/n`` step values, and comma-separated lists.
    Anything else raises ValueError so the caller can surface a clear message.
    """
    if field == "*":
        return "*"

    if "," in field:
        return ",".join(_convert_field(part, pad) for part in field.split(","))

    if field.startswith("*/"):
        step = field[2:]
        if not step.isdigit():
            raise ValueError(f"Unsupported cron step value: '{field}'")
        # systemd expresses repetition as "start/interval"; start at zero.
        return f"{0:0{pad}d}/{int(step)}"

    if field.isdigit():
        return f"{int(field):0{pad}d}"

    raise ValueError(f"Unsupported cron field: '{field}'")


def _convert_dow(field: str) -> str:
    """Convert the cron day-of-week field to a systemd weekday prefix.

    Returns an empty string for ``*`` (every day), which systemd represents by
    omitting the weekday component entirely.
    """
    if field == "*":
        return ""

    parts = field.split(",")
    names = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"Unsupported cron day-of-week field: '{field}'")
        # cron allows both 0 and 7 for Sunday.
        names.append(_DOW_NAMES[int(part) % 7])
    return ",".join(names)


def cron_to_oncalendar(cron: str) -> str:
    """Translate a 5-field cron expression into a systemd OnCalendar value.

    Example: ``0 */6 * * *`` -> ``*-*-* 00/6:00:00``

    Raises:
        ValueError: if the expression is not 5 fields or uses syntax we don't
            translate (ranges, ``@`` shortcuts, etc.).
    """
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(
            f"Expected a 5-field cron expression, got {len(fields)} field(s): '{cron}'"
        )

    minute, hour, dom, month, dow = fields

    cal_minute = _convert_field(minute, pad=2)
    cal_hour = _convert_field(hour, pad=2)
    cal_dom = _convert_field(dom, pad=2)
    cal_month = _convert_field(month, pad=2)
    cal_dow = _convert_dow(dow)

    date_time = f"*-{cal_month}-{cal_dom} {cal_hour}:{cal_minute}:00"
    if cal_dow:
        return f"{cal_dow} {date_time}"
    return date_time


def render_service_unit(
    hostsolo_bin: str, working_dir: Path, env_name: str
) -> str:
    """Render the oneshot systemd service that performs the backup."""
    return f"""[Unit]
Description=Host Solo backup ({env_name})
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={working_dir}
ExecStart={hostsolo_bin} backup all --env {env_name}
"""


def render_timer_unit(oncalendar: str, env_name: str) -> str:
    """Render the systemd timer that triggers the backup service."""
    return f"""[Unit]
Description=Host Solo backup timer ({env_name})

[Timer]
OnCalendar={oncalendar}
Persistent=true

[Install]
WantedBy=timers.target
"""