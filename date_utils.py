"""
Date Utilities for Stellaris
============================

Converts between Stellaris date strings and day counts.
Stellaris uses a 360-day year (12 months × 30 days).
Game start date is 2200.01.01 (day 0).
"""

from __future__ import annotations

import re

# Stellaris uses 360-day years
DAYS_PER_YEAR = 360
DAYS_PER_MONTH = 30
MONTHS_PER_YEAR = 12
GAME_START_YEAR = 2200


def parse_date(date_str: str) -> tuple[int, int, int] | None:
    """Parse a Stellaris date string into (year, month, day).

    Args:
        date_str: Date in format "YYYY.MM.DD" (e.g., "2450.07.15")

    Returns:
        Tuple of (year, month, day) or None if invalid
    """
    if not date_str:
        return None

    match = re.match(r"^(\d{4})\.(\d{2})\.(\d{2})$", date_str.strip())
    if not match:
        # Try alternate format YYYY.M.D
        match = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$", date_str.strip())
        if not match:
            return None

    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def date_to_days(date_str: str) -> int | None:
    """Convert a Stellaris date string to days since game start (2200.01.01).

    Args:
        date_str: Date in format "YYYY.MM.DD"

    Returns:
        Number of days since 2200.01.01, or None if invalid

    Examples:
        >>> date_to_days("2200.01.01")
        0
        >>> date_to_days("2200.02.01")
        30
        >>> date_to_days("2201.01.01")
        360
        >>> date_to_days("2450.07.15")
        90194
    """
    parsed = parse_date(date_str)
    if not parsed:
        return None

    year, month, day = parsed

    years_elapsed = year - GAME_START_YEAR
    months_elapsed = month - 1  # Month 1 = 0 months elapsed
    days_elapsed = day - 1  # Day 1 = 0 days elapsed

    total_days = (years_elapsed * DAYS_PER_YEAR) + (months_elapsed * DAYS_PER_MONTH) + days_elapsed
    return total_days


def days_to_date(days: int) -> str:
    """Convert days since game start to a Stellaris date string.

    Args:
        days: Number of days since 2200.01.01

    Returns:
        Date string in format "YYYY.MM.DD"

    Examples:
        >>> days_to_date(0)
        "2200.01.01"
        >>> days_to_date(30)
        "2200.02.01"
        >>> days_to_date(360)
        "2201.01.01"
    """
    if days < 0:
        days = 0

    years = days // DAYS_PER_YEAR
    remaining_days = days % DAYS_PER_YEAR

    months = remaining_days // DAYS_PER_MONTH
    day_of_month = remaining_days % DAYS_PER_MONTH

    year = GAME_START_YEAR + years
    month = months + 1  # Month 1-12
    day = day_of_month + 1  # Day 1-30

    return f"{year:04d}.{month:02d}.{day:02d}"


def days_between(date1: str, date2: str) -> int | None:
    """Calculate the number of days between two Stellaris dates.

    Args:
        date1: First date (earlier)
        date2: Second date (later)

    Returns:
        Number of days between dates (positive if date2 > date1), or None if invalid

    Examples:
        >>> days_between("2200.01.01", "2200.02.01")
        30
        >>> days_between("2450.01.01", "2450.07.15")
        194
    """
    d1 = date_to_days(date1)
    d2 = date_to_days(date2)

    if d1 is None or d2 is None:
        return None

    return d2 - d1


def format_duration(days: int) -> str:
    """Format a duration in days as a human-readable string.

    Args:
        days: Number of days

    Returns:
        Human-readable duration string

    Examples:
        >>> format_duration(45)
        "1 month, 15 days"
        >>> format_duration(450)
        "1 year, 3 months"
        >>> format_duration(30)
        "1 month"
    """
    if days < 0:
        return "0 days"

    years = days // DAYS_PER_YEAR
    remaining = days % DAYS_PER_YEAR
    months = remaining // DAYS_PER_MONTH
    remaining_days = remaining % DAYS_PER_MONTH

    parts = []
    if years > 0:
        parts.append(f"{years} year{'s' if years != 1 else ''}")
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if remaining_days > 0 and years == 0:  # Only show days if less than a year
        parts.append(f"{remaining_days} day{'s' if remaining_days != 1 else ''}")

    if not parts:
        return "0 days"

    return ", ".join(parts)


def get_game_year(date_str: str) -> int | None:
    """Extract just the year from a Stellaris date.

    Args:
        date_str: Date in format "YYYY.MM.DD"

    Returns:
        The year as an integer, or None if invalid
    """
    parsed = parse_date(date_str)
    return parsed[0] if parsed else None


def years_elapsed(date_str: str) -> int | None:
    """Get the number of full years elapsed since game start.

    Args:
        date_str: Current date in format "YYYY.MM.DD"

    Returns:
        Number of full years elapsed, or None if invalid
    """
    year = get_game_year(date_str)
    if year is None:
        return None
    return year - GAME_START_YEAR


def is_valid_date(date_str: str) -> bool:
    """Check if a string is a valid Stellaris date.

    Args:
        date_str: Date string to validate

    Returns:
        True if valid, False otherwise
    """
    parsed = parse_date(date_str)
    if not parsed:
        return False

    year, month, day = parsed
    return year >= GAME_START_YEAR and 1 <= month <= MONTHS_PER_YEAR and 1 <= day <= DAYS_PER_MONTH


def compare_dates(date1: str, date2: str) -> int | None:
    """Compare two Stellaris dates.

    Args:
        date1: First date
        date2: Second date

    Returns:
        -1 if date1 < date2, 0 if equal, 1 if date1 > date2
        None if either date is invalid
    """
    d1 = date_to_days(date1)
    d2 = date_to_days(date2)

    if d1 is None or d2 is None:
        return None

    if d1 < d2:
        return -1
    elif d1 > d2:
        return 1
    return 0


# Convenience for game phase detection
def get_game_phase(date_str: str, mid_game_start: int = 2300, end_game_start: int = 2400) -> str:
    """Determine the current game phase based on year.

    Args:
        date_str: Current date
        mid_game_start: Year when mid-game starts (default 2300)
        end_game_start: Year when end-game starts (default 2400)

    Returns:
        "early", "mid", or "late" game phase
    """
    year = get_game_year(date_str)
    if year is None:
        return "unknown"

    if year >= end_game_start:
        return "late"
    elif year >= mid_game_start:
        return "mid"
    return "early"
