"""
Date Integrity & Timezone Handling for EdgeScout.
Specifications:
- Parses football-data.co.uk UK local kickoff times (Europe/London).
- Converts to UTC (stored in DB and API responses).
- Formats to Africa/Lagos (WAT, UTC+1) for user display: "Tue 3 Nov, 19:45 WAT" + "in 3h 20m".
- Strict filtering: Excludes any fixture whose kickoff is before now + 10 minutes.
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")
WAT_TZ = ZoneInfo("Africa/Lagos") # UTC+1 all year


def get_now_utc() -> datetime:
    """Returns current UTC time."""
    return datetime.now(timezone.utc)


def parse_kickoff_to_utc(date_str: str, time_str: Optional[str] = None) -> Optional[datetime]:
    """
    Parses football-data.co.uk Date and Time strings.
    Interprets as Europe/London local time, converts to UTC.
    Accepts:
    - Date: '03/11/2026', '3/11/2026', '2026-11-03'
    - Time: '19:45', '15:00', or None (defaults to 15:00 UK)
    """
    if not date_str or not isinstance(date_str, str):
        return None

    clean_date = date_str.strip()
    clean_time = (time_str or "15:00").strip()

    # Normalize time if only 1 digit hour like '9:45'
    if ":" in clean_time:
        parts = clean_time.split(":")
        clean_time = f"{int(parts[0]):02d}:{parts[1]}"
    else:
        clean_time = "15:00"

    formats = [
        ("%d/%m/%Y %H:%M", f"{clean_date} {clean_time}"),
        ("%d/%m/%y %H:%M", f"{clean_date} {clean_time}"),
        ("%Y-%m-%d %H:%M", f"{clean_date} {clean_time}"),
        ("%Y-%m-%dT%H:%M:%SZ", clean_date),
        ("%Y-%m-%dT%H:%M:%S%z", clean_date),
    ]

    for fmt, val in formats:
        try:
            parsed = datetime.strptime(val, fmt)
            # If format had timezone offset
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc)
            # Otherwise interpret as Europe/London
            uk_dt = parsed.replace(tzinfo=UK_TZ)
            return uk_dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue

    return None


def format_wat(dt_utc: datetime) -> str:
    """
    Formats UTC datetime to Africa/Lagos (WAT):
    e.g. 'Tue 3 Nov, 19:45 WAT'
    """
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    wat_dt = dt_utc.astimezone(WAT_TZ)
    # Day without leading zero
    day = wat_dt.day
    return f"{wat_dt.strftime('%a')} {day} {wat_dt.strftime('%b, %H:%M WAT')}"


def format_countdown(dt_utc: datetime, now_utc: Optional[datetime] = None) -> str:
    """
    Returns human countdown string relative to now:
    e.g. 'in 3h 20m', 'in 45m', 'in 2d 5h', or 'Live / Past'
    """
    now = now_utc or get_now_utc()
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    delta = dt_utc - now
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        return "Started"

    minutes = total_seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        rem_hours = hours % 24
        return f"in {days}d {rem_hours}h"
    if hours > 0:
        rem_minutes = minutes % 60
        return f"in {hours}h {rem_minutes}m"
    return f"in {max(1, minutes)}m"


def is_upcoming_fixture(
    dt_utc: datetime, 
    min_buffer_minutes: int = 10, 
    max_days: float = 7.0,
    now_utc: Optional[datetime] = None
) -> Tuple[bool, bool]:
    """
    Evaluates if fixture meets date integrity rules:
    - Exclude if kickoff < now + 10 minutes.
    - is_today: kickoff within next 24 hours.
    - is_this_week: kickoff within next 7 days.
    Returns: (is_today, is_this_week)
    """
    now = now_utc or get_now_utc()
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    diff = dt_utc - now

    # Exclude past or matches kicking off in < 10 mins
    if diff < timedelta(minutes=min_buffer_minutes):
        return False, False

    # Within 7 days
    if diff > timedelta(days=max_days):
        return False, False

    is_today = diff <= timedelta(hours=24)
    return is_today, True

