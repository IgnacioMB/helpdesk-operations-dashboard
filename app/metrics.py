"""Metric definitions shared by the pipeline and the dashboard.

Anything computed in BOTH places lives here, so the two can never drift into
reporting different numbers for the same named metric.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def calendar_days(d_from, d_to) -> pd.DatetimeIndex:
    """Every calendar day in the window, including days with no tickets."""
    return pd.date_range(pd.Timestamp(d_from), pd.Timestamp(d_to), freq="D")


def weekday_occurrences(d_from, d_to) -> pd.Series:
    """How many times each weekday occurs in the window.

    The extract is 13 days (Sun 26 Jun - Fri 8 Jul 2022), so Saturday occurs ONCE
    and every other weekday twice. Dividing by observed days instead would inflate
    any weekday a filtered segment happens to miss.
    """
    cal = calendar_days(d_from, d_to)
    return pd.Series(cal.day_name()).value_counts()


def per_day(count: int, d_from, d_to) -> float:
    """Rate per CALENDAR day of the window, not per day that happened to have data."""
    return count / max(len(calendar_days(d_from, d_to)), 1)


def demand_trend(df: pd.DataFrame, d_from, d_to, date_col: str = "created_date"):
    """Change in intake, comparing weekday-matched windows wherever possible.

    Offsetting the comparison window by exactly 7 days guarantees the two halves
    contain the same weekdays, which matters here because Sunday is the weakest
    day (~1,167/day) and Saturday the second weakest (~1,328/day) - an unmatched
    split silently compares a Sunday against a Saturday.

    Returns (pct_change, label) or (None, reason).
    """
    start, end = pd.Timestamp(d_from), pd.Timestamp(d_to)
    span = (end - start).days + 1
    counts = df.groupby(date_col).size()
    counts.index = pd.to_datetime(counts.index)

    def total(a: pd.Timestamp, b: pd.Timestamp) -> int:
        return int(counts.reindex(pd.date_range(a, b), fill_value=0).sum())

    if span >= 8:
        n = min(7, span - 7)
        r_start, r_end = end - pd.Timedelta(days=n - 1), end
        p_start, p_end = r_start - pd.Timedelta(days=7), r_end - pd.Timedelta(days=7)
        label = f"Last {n} days vs the same {n} days a week earlier"
    elif span >= 2:
        n = span // 2
        r_start, r_end = end - pd.Timedelta(days=n - 1), end
        p_start, p_end = r_start - pd.Timedelta(days=n), r_start - pd.Timedelta(days=1)
        unit = "day" if n == 1 else "days"
        label = f"Last {n} {unit} vs prior {n} (weekdays not matched)"
    else:
        return None, "Needs at least 2 days selected"

    recent, prior = total(r_start, r_end), total(p_start, p_end)
    if prior == 0:
        return None, "No comparable earlier window"
    return 100 * (recent / prior - 1), label


def repeat_flag(df: pd.DataFrame) -> pd.Series:
    """Does this ticket's booking have more than one ticket IN THIS FRAME?

    Recomputed on whatever frame is passed, so a filtered view reports the repeat
    rate within that view rather than carrying a flag baked over the whole extract.
    """
    return df.groupby("booking_id")["ticket_id"].transform("size") > 1
