"""
Kiwi.com Helpdesk case study - derived aggregate tables for the dashboard.

Reads the clean ticket table produced by `data_cleaning.ipynb` and writes the
aggregates the dashboard reads. Everything written here is recomputable: the
only file that has to be maintained is data/clean/tickets_clean.csv.

Usage:  python pipeline/build.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.metrics import demand_trend, per_day, repeat_flag, weekday_occurrences  # noqa: E402

CLEAN = ROOT / "data" / "clean" / "tickets_clean.csv"
OUT = ROOT / "data" / "clean" / "derived"
OUT.mkdir(parents=True, exist_ok=True)

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WINDOW_DAYS = 13  # calendar days in the extract; recomputed in main() and asserted

BOOL_COLS = ["has_accepted_refund", "has_out_of_pocket_refund",
             "is_weekend", "resolved_same_day", "is_repeat_contact_booking"]


def load_clean() -> pd.DataFrame:
    """The clean table is the source of truth; this step never touches the raw workbook."""
    if not CLEAN.exists():
        raise SystemExit(f"{CLEAN} is missing - run data_cleaning.ipynb first.")
    df = pd.read_csv(CLEAN, parse_dates=["created_at", "resolved_at"])
    # The aggregations below group on plain dates, not midnight timestamps.
    df["created_date"] = df["created_at"].dt.date
    df["resolved_date"] = df["resolved_at"].dt.date
    for c in BOOL_COLS:
        df[c] = df[c].map({True: True, False: False, "True": True, "False": False,
                           1: True, 1.0: True, 0: False, 0.0: False}).astype("boolean")
    return df


def build_kpis(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}

    created = df.groupby("created_date").size().rename("tickets_created")
    resolved = df.groupby("resolved_date").size().rename("tickets_resolved")
    daily = pd.concat([created, resolved], axis=1).fillna(0).astype(int)
    daily.index = pd.to_datetime(daily.index)
    daily = daily.sort_index()
    # Resolutions spill past the creation window (tickets opened on the last day and
    # closed after midnight). Keeping that row would publish a day where intake
    # "fell to zero" and would make Saturday appear twice in any weekday rollup
    # built off this CSV, halving its average.
    last_created = pd.Timestamp(df["created_date"].max())
    spill = int(daily.loc[daily.index > last_created, "tickets_resolved"].sum())
    daily = daily.loc[daily.index <= last_created]
    daily["net_change"] = daily["tickets_created"] - daily["tickets_resolved"]
    daily["carried_overnight"] = (
        df[~df["resolved_same_day"]].groupby("created_date").size()
        .reindex(daily.index.date, fill_value=0).values
    )
    daily["day_of_week"] = daily.index.day_name()
    daily["median_tat_minutes"] = (
        df.groupby("created_date")["turnaround_minutes_generated"].median().reindex(daily.index.date).values
    )
    # interpolation="nearest" everywhere: turnaround is whole minutes, so the default
    # "linear" would publish values like 42.4 that cannot occur, and its position drifts
    # with n - a 300-ticket segment and a 6,000-ticket one would not be comparable.
    daily["p90_tat_minutes"] = (
        df.groupby("created_date")["turnaround_minutes_generated"]
        .quantile(0.9, interpolation="nearest").reindex(daily.index.date).values
    )
    daily["resolved_to_created_ratio"] = (
        daily["tickets_resolved"] / daily["tickets_created"]).round(4)
    # Tickets open at 23:59 on each day: created by then and not yet resolved, counted by
    # timestamp over the whole frame. Not a cumulative sum of the daily columns - that
    # would assume nothing was open before the first day, which is true of this extract
    # but not of a real one. main() asserts the two agree here, so the day a long-running
    # ticket appears, the assertion says so.
    _edges = daily.index + pd.Timedelta(days=1)
    _c, _r = df["created_at"], df["resolved_at"]
    daily["open_end_of_day"] = [
        int(((_c < e) & (_r.isna() | (_r >= e))).sum()) for e in _edges]
    # Same weekday a week earlier, carried ON the current day's row rather than looked up
    # across rows. A date filter keeps the comparison intact, which a self-join on the
    # filtered frame would not: the reference week is usually outside the selection.
    prev_week = daily["tickets_created"].copy()
    prev_week.index = prev_week.index + pd.Timedelta(days=7)
    daily["tickets_created_prev_week"] = prev_week.reindex(daily.index)
    daily["wow_ratio"] = (
        daily["tickets_created"] / daily["tickets_created_prev_week"]).round(4)
    out["kpi_daily"] = daily.reset_index(names="date")
    out["kpi_daily"].attrs["spill"] = spill

    out["kpi_by_queue"] = _segment(df, "queue")
    out["kpi_by_request_type"] = _segment(df, "request_type")
    out["kpi_by_ticket_type"] = _segment(df, "ticket_type")

    hm = df.groupby(["created_weekday", "created_hour"]).size().unstack(fill_value=0)
    days_seen = df.groupby("created_weekday")["created_date"].nunique()
    out["kpi_hour_dow"] = (hm.T / days_seen).T.round(2).reindex(DOW_ORDER).reset_index()

    rep = df[df["contact_seq"] > 1]["hours_since_prev_contact"]
    bins = [0, 1, 6, 24, 48, 72, np.inf]
    labels = ["<1h", "1-6h", "6-24h", "24-48h", "48-72h", "72h+"]
    out["kpi_recontact_gap"] = (
        pd.cut(rep, bins=bins, labels=labels, right=False)
        .value_counts().reindex(labels).rename("re_contacts")
        .rename_axis("gap_bucket").reset_index()
    )

    tat = df["turnaround_minutes_generated"].round().astype(int).value_counts().sort_index()
    out["kpi_tat_distribution"] = (
        tat.rename("tickets").rename_axis("turnaround_minutes_generated").reset_index()
    )
    return out


def _segment(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Per-segment metrics.

    Two naming rules are load-bearing here:

    * `bookings_touching_segment` is NOT additive - a booking with tickets in two
      segments is counted in both, so the column sums to more than the 17,450
      distinct bookings. The name says so rather than leaving a reader to add it up.
    * the repeat-contact rate is published BOTH ways. The `_extract` version asks
      "does this booking repeat anywhere in the 13 days", the `_within_segment`
      version asks "does it repeat inside this segment". They differ enormously
      (Refund: 19.9% vs 5.9%) and only the second one is consistent with the
      `tickets_per_booking` on the same row.
    """
    g = df.groupby(by)
    within = g.apply(
        lambda s: 100 * (s.groupby("booking_id")["ticket_id"].transform("size") > 1).mean(),
        include_groups=False,
    )
    # Resolved is scoped to the creation window so it reconciles with kpi_daily: it sums
    # to len(df) - spill, not len(df). `tickets` keeps meaning created.
    in_window = df["resolved_date"] <= df["created_date"].max()
    res = pd.DataFrame({
        "tickets": g.size(),
        "tickets_resolved": df[in_window].groupby(by).size().reindex(g.size().index, fill_value=0),
        "share_pct": (100 * g.size() / len(df)).round(2),
        "bookings_touching_segment": g["booking_id"].nunique(),
        "avg_tat_minutes": g["turnaround_minutes_generated"].mean().round(2),
        "median_tat_minutes": g["turnaround_minutes_generated"].median().round(2),
        "p90_tat_minutes": g["turnaround_minutes_generated"].quantile(0.9, interpolation="nearest"),
        "tickets_per_booking": (g.size() / g["booking_id"].nunique()).round(3),
        "pct_repeat_within_segment": within.round(2),
        "pct_on_bookings_repeating_anywhere": (100 * g["is_repeat_contact_booking"].mean()).round(2),
        "pct_resolved_same_day": (100 * g["resolved_same_day"].mean()).round(2),
    })
    res["tickets_per_window_day"] = (res["tickets"] / WINDOW_DAYS).round(2)
    return res.sort_values("tickets", ascending=False).reset_index()


# ------------------------------------------------------------ headline
def headline(df: pd.DataFrame) -> dict:
    n_days = df["created_date"].nunique()
    wow_pct, wow_label = demand_trend(df, df["created_date"].min(), df["created_date"].max())
    first_half = df[df["created_date"] <= pd.Timestamp("2022-07-01").date()]
    second_half = df[df["created_date"] >= pd.Timestamp("2022-07-03").date()]
    refund = df[df["request_type"] == "Refund"]
    return {
        "tickets_total": int(len(df)),
        "bookings_total": int(df["booking_id"].nunique()),
        "days_covered": int(n_days),
        "window_start": str(df["created_date"].min()),
        "window_end": str(df["created_date"].max()),
        "avg_created_per_day": round(len(df) / n_days, 1),
        # Resolutions that land INSIDE the creation window, over the same calendar
        # days - not a copy of the created figure. 10 tickets resolve on 9 Jul,
        # outside the window, and are reported separately as `resolutions_after_window`.
        "avg_resolved_per_day": round(
            int((df["resolved_date"] <= df["created_date"].max()).sum()) / n_days, 1),
        "resolutions_after_window": int((df["resolved_date"] > df["created_date"].max()).sum()),
        "median_tat_minutes": float(df["turnaround_minutes_generated"].median()),
        "p90_tat_minutes": float(
            df["turnaround_minutes_generated"].quantile(0.9, interpolation="nearest")),
        "resolved_to_created_ratio": round(
            int((df["resolved_date"] <= df["created_date"].max()).sum()) / len(df), 4),
        "mean_tat_minutes": round(float(df["turnaround_minutes_generated"].mean()), 2),
        # NOTE: both of these are derived from the synthetic resolution timestamp.
        # They are a deterministic function of creation time (every "overnight"
        # ticket was simply created after 23:17 UTC), not a measure of team output.
        "pct_resolved_same_day": round(100 * df["resolved_same_day"].mean(), 2),
        "carried_overnight": int((~df["resolved_same_day"]).sum()),
        "pct_created_after_2315_utc": round(
            100 * (df["created_at"].dt.hour == 23).mean(), 2),
        "pct_tickets_from_repeat_bookings": round(100 * df["is_repeat_contact_booking"].mean(), 2),
        "pct_bookings_with_repeat": round(
            100 * (df.groupby("booking_id").size() > 1).mean(), 2),
        "wow_like_for_like_pct": round(wow_pct, 1),
        "wow_method": wow_label,
        "wow_w1_per_day": round(len(first_half) / 6, 1),
        "wow_w2_per_day": round(len(second_half) / 6, 1),
        "peak_hour_utc": int(df["created_hour"].value_counts().idxmax()),
        "pct_volume_0719_utc": round(
            100 * df["created_hour"].between(7, 18).mean(), 1),
        "refund_tickets": int(len(refund)),
        "refund_bookings": int(refund["booking_id"].nunique()),
        # Per BOOKING, because the flag describes the booking, not the message.
        # The per-ticket figure is kept alongside so the two are never confused.
        "refund_accept_rate_pct_per_booking": round(
            100 * (refund.groupby("booking_id")["has_accepted_refund"].max() == True).mean(), 2),  # noqa: E712
        "refund_accept_rate_pct_per_ticket": round(
            100 * (refund["has_accepted_refund"].fillna(False) == True).sum() / len(refund), 2),  # noqa: E712
    }


def main() -> None:
    global WINDOW_DAYS
    clean = load_clean()

    assert clean["ticket_id"].is_unique, "ticket_id is not unique in the clean table"
    assert clean["queue"].notna().all(), "a ticket has no queue"

    created = pd.to_datetime(clean["created_date"])
    WINDOW_DAYS = (created.max() - created.min()).days + 1
    assert WINDOW_DAYS == created.dt.date.nunique(), "gap day in the window; per-day rates need care"

    kpis = build_kpis(clean)
    head = headline(clean)
    spill = kpis["kpi_daily"].attrs["spill"]
    d = kpis["kpi_daily"]
    assert (d["p90_tat_minutes"] >= d["median_tat_minutes"]).all(), "P90 below the median"
    assert (d["open_end_of_day"] >= 0).all(), "negative backlog"
    # These agree only because turnaround never exceeds 24h, so a ticket open at midnight
    # always closes the next day. If that stops being true this assertion is the warning.
    assert (d["open_end_of_day"] == d["carried_overnight"]).all(), \
        "backlog no longer equals the midnight carry - turnaround now exceeds 24h"
    assert d["open_end_of_day"].iloc[-1] == spill, "window-end backlog must equal the spill"
    # True for this extract because no ticket predates the window. If that ever changes,
    # the cumulative shortcut stops being equivalent and this is where you find out.
    assert (d["open_end_of_day"] == d["net_change"].cumsum()).all(), \
        "open tickets no longer equal the running net change - something predates the window"
    # The first week has no reference week inside the extract, so those rows must be blank
    # rather than silently zero - a 0 would render as a 100% collapse.
    first_ref = pd.Timestamp(clean["created_date"].min()) + pd.Timedelta(days=7)
    assert d.loc[d["date"] < first_ref, "tickets_created_prev_week"].isna().all(), \
        "prev-week column populated before a reference week exists"
    assert d.loc[d["date"] >= first_ref, "tickets_created_prev_week"].notna().all(), \
        "prev-week column missing where a reference week does exist"
    ref = d.dropna(subset=["tickets_created_prev_week"])
    assert ((ref["tickets_created"] / ref["tickets_created_prev_week"]).round(4)
            == ref["wow_ratio"]).all(), "wow_ratio disagrees with its own inputs"
    assert head["resolved_to_created_ratio"] == round(
        d["tickets_resolved"].sum() / d["tickets_created"].sum(), 4), "ratio disagrees with kpi_daily"
    assert kpis["kpi_daily"]["tickets_created"].sum() == len(clean)
    assert kpis["kpi_daily"]["tickets_resolved"].sum() == len(clean) - spill
    assert len(kpis["kpi_daily"]) == WINDOW_DAYS, "kpi_daily must cover exactly the creation window"
    for t in ["kpi_by_queue", "kpi_by_request_type", "kpi_by_ticket_type"]:
        assert kpis[t]["tickets"].sum() == len(clean), f"{t} loses tickets"
        assert abs(kpis[t]["share_pct"].sum() - 100) < 0.1, f"{t} shares do not sum to 100"
        # If a share R of a segment's tickets sit on bookings that repeat WITHIN the
        # segment, those tickets occupy at most R/2 of the bookings, so
        # tickets_per_booking >= 1/(1-R/2). Slack is for published rounding only.
        bound = 1 / (1 - kpis[t]["pct_repeat_within_segment"] / 200)
        assert (kpis[t]["tickets_per_booking"] >= bound - 5e-3).all(), \
            f"{t}: repeat rate impossible given tickets_per_booking"
        assert kpis[t]["tickets_resolved"].sum() == len(clean) - spill, \
            f"{t}: resolved counts do not reconcile with the creation window"
        assert (kpis[t]["p90_tat_minutes"] >= kpis[t]["median_tat_minutes"]).all(), f"{t}: P90 below median"
        assert kpis[t]["p90_tat_minutes"].between(15, 45).all(), f"{t}: P90 outside the observed range"

    for name, table in kpis.items():
        table.to_csv(OUT / f"{name}.csv", index=False)
    (OUT / "headline_kpis.json").write_text(json.dumps(head, indent=2))

    print(f"clean rows    : {len(clean):,}")
    print(f"tables written: {len(kpis)} + headline_kpis.json")
    print(f"written to    : {OUT}")
    for k, v in head.items():
        print(f"  {k:34s} {v}")


if __name__ == "__main__":
    main()
