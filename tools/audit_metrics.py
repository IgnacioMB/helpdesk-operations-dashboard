"""Independent audit of every metric the dashboard reports.

Reads the RAW workbook and re-derives each figure from scratch, for a given date range
and filter selection, so the output can be compared against the dashboard at a glance.

Deliberately standalone: it imports nothing from `app/` or `pipeline/`, does not read
`tickets_clean.csv`, and re-implements every definition (queue parsing, turnaround,
backlog, percentiles) rather than calling the project's own helpers. A number that only
one implementation produces is a number nobody has checked — so if this script and the
dashboard agree, the agreement means something.

Usage:
    python tools/audit_metrics.py                                  # full extract
    python tools/audit_metrics.py --from 2022-07-01 --to 2022-07-05
    python tools/audit_metrics.py --queue EN --request-type Refund
    python tools/audit_metrics.py --from 2022-07-06 --to 2022-07-08 --json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

import numpy as np
import pandas as pd

RAW = pathlib.Path(__file__).resolve().parent.parent / "data" / "raw" / \
    "Casestudy-Kiwi.com-BusinessAnalyst.xlsx"

QUEUE_RE = re.compile(r"Helpdesk (?:- )?(EN|International|JA|KO)")
CATEGORY_RE = re.compile(r"- (Refund|Non-refund) requests")
AGE_BUCKETS = [(0, 1, "<1h"), (1, 4, "1-4h"), (4, 12, "4-12h"), (12, 24, "12-24h"),
               (24, 72, "1-3d"), (72, 168, "3-7d"), (168, np.inf, "7d+")]


# ----------------------------------------------------------------- load
def load_raw() -> pd.DataFrame:
    """Rebuild the analysis frame from the workbook, independently of the cleaning step."""
    if not RAW.exists():
        sys.exit(f"{RAW} not found.")
    t = pd.read_excel(RAW, sheet_name="fact_ticket")
    df = pd.DataFrame({
        "ticket_id": t["ticket_id"],
        "booking_id": t["bid"],
        "ticket_type": t["Ticket Type"],
        "created_at": pd.to_datetime(t["creation_timestamp_utc"]),
        "resolved_at": pd.to_datetime(t["resolution_timestamp_utc"]),
    })
    df["queue"] = df["ticket_type"].str.extract(QUEUE_RE)[0].fillna("Unclassified")
    df["request_type"] = df["ticket_type"].str.extract(CATEGORY_RE)[0].fillna("Not specified")
    df["created_date"] = df["created_at"].dt.normalize()
    df["resolved_date"] = df["resolved_at"].dt.normalize()
    df["tat_minutes"] = (df["resolved_at"] - df["created_at"]).dt.total_seconds() / 60
    return df


def p90(series: pd.Series) -> float:
    """Nearest-rank 90th percentile, via numpy rather than Series.quantile."""
    values = series.dropna().astype(float)
    return float("nan") if values.empty else float(np.percentile(values, 90, method="nearest"))


def open_at(frame: pd.DataFrame, edge: pd.Timestamp) -> pd.DataFrame:
    """Tickets created before `edge` and not resolved by it - whenever they arrived."""
    return frame[(frame["created_at"] < edge)
                 & (frame["resolved_at"].isna() | (frame["resolved_at"] >= edge))]


# ----------------------------------------------------------------- audit
def audit(df: pd.DataFrame, d_from, d_to, queues, categories) -> dict:
    # Segment filters apply to everything; the date filter does NOT apply to `span`,
    # which is what the backlog and the week-on-week comparison read from.
    span = df[df["queue"].isin(queues) & df["request_type"].isin(categories)]
    sel = span[(span["created_date"].dt.date >= d_from) & (span["created_date"].dt.date <= d_to)]
    if sel.empty:
        return {"error": "no tickets match this selection"}

    last_day = sel["created_date"].max()
    days = pd.date_range(sel["created_date"].min(), last_day, freq="D")

    # --- daily table -----------------------------------------------------
    rows = []
    for day in days:
        edge = day + pd.Timedelta(days=1)
        same_day = sel[sel["created_date"] == day]
        # Resolved, cohort definition: created in range, resolved on this day.
        cohort_resolved = int((sel["resolved_date"] == day).sum())
        # Resolved, throughput definition: anything resolved on this day, whenever created.
        throughput_resolved = int((span["resolved_date"] == day).sum())
        prev = span[span["created_date"] == day - pd.Timedelta(days=7)]
        rows.append({
            "date": day.date(),
            "weekday": day.day_name()[:3],
            "created": len(same_day),
            "resolved": cohort_resolved,
            "resolved_throughput": throughput_resolved,
            "net_change": len(same_day) - cohort_resolved,
            "ratio": round(cohort_resolved / len(same_day), 4) if len(same_day) else float("nan"),
            "open_23_59": len(open_at(span, edge)),
            "median_tat": float(same_day["tat_minutes"].median()),
            "p90_tat": p90(same_day["tat_minutes"]),
            "created_prev_week": len(prev) if len(prev) else None,
            "wow_ratio": round(len(same_day) / len(prev), 3) if len(prev) else None,
        })
    daily = pd.DataFrame(rows)

    # --- headline --------------------------------------------------------
    resolved_in_range = int(sel["resolved_date"].dt.date.between(d_from, d_to).sum())
    final_edge = last_day + pd.Timedelta(days=1)
    still_open = open_at(span, final_edge)

    ages = []
    if len(still_open):
        age_h = (final_edge - still_open["created_at"]).dt.total_seconds() / 3600
        for lo, hi, label in AGE_BUCKETS:
            ages.append({"bucket": label, "tickets": int(((age_h >= lo) & (age_h < hi)).sum())})

    # --- segments --------------------------------------------------------
    def segment(by: str) -> pd.DataFrame:
        out = []
        for name, grp in sel.groupby(by):
            out.append({
                by: name,
                "created": len(grp),
                "resolved": int((grp["resolved_date"] <= last_day).sum()),
                "median_tat": float(grp["tat_minutes"].median()),
                "p90_tat": p90(grp["tat_minutes"]),
            })
        return pd.DataFrame(out).sort_values("created", ascending=False)

    per_booking = sel.groupby("booking_id").size()

    return {
        "selection": {
            "from": str(d_from), "to": str(d_to),
            "queues": sorted(queues), "request_types": sorted(categories),
            "calendar_days": len(days),
        },
        "tiles": {
            "created": len(sel),
            "resolved": resolved_in_range,
            "backlog": len(still_open),
            "median_tat_min": float(sel["tat_minutes"].median()),
            "p90_tat_min": p90(sel["tat_minutes"]),
        },
        "accumulation": {
            "net_change": len(sel) - resolved_in_range,
            "resolved_to_created_ratio": round(resolved_in_range / len(sel), 4),
        },
        "repeat_contact": {
            "bookings": int(per_booking.size),
            "bookings_with_repeat": int((per_booking > 1).sum()),
            "pct_bookings_with_repeat": round(100 * (per_booking > 1).mean(), 2),
            "pct_tickets_on_repeat_bookings": round(
                100 * int(per_booking[per_booking > 1].sum()) / len(sel), 2),
        },
        "peak_hour_utc": int(sel["created_at"].dt.hour.value_counts().idxmax()),
        "daily": daily,
        "backlog_by_age": pd.DataFrame(ages),
        "by_queue": segment("queue"),
        "by_request_type": segment("request_type"),
    }


# ----------------------------------------------------------------- output
def show(a: dict) -> None:
    if "error" in a:
        print(a["error"])
        return
    s, t = a["selection"], a["tiles"]
    print("=" * 78)
    print(f"  {s['from']} to {s['to']}   ({s['calendar_days']} calendar days)")
    print(f"  queues: {', '.join(s['queues'])}")
    print(f"  types : {', '.join(s['request_types'])}")
    print("=" * 78)

    print("\nTILES  (compare with the five on Operations Overview)")
    print(f"  Created      {t['created']:>10,}")
    print(f"  Resolved     {t['resolved']:>10,}")
    print(f"  Backlog      {t['backlog']:>10,}")
    print(f"  Median TAT   {t['median_tat_min']:>10,.0f} min")
    print(f"  P90 TAT      {t['p90_tat_min']:>10,.0f} min")

    acc = a["accumulation"]
    print("\nIS WORK ACCUMULATING?")
    print(f"  Net change   {acc['net_change']:>+10,} tickets")
    print(f"  Resolved/created {acc['resolved_to_created_ratio']:>6.4f}x")

    print("\nREPEAT CONTACT")
    r = a["repeat_contact"]
    print(f"  Bookings {r['bookings']:,} · repeating {r['bookings_with_repeat']:,} "
          f"({r['pct_bookings_with_repeat']}%) · {r['pct_tickets_on_repeat_bookings']}% of tickets")
    print(f"  Peak arrival hour: {a['peak_hour_utc']:02d}:00 UTC")

    print("\nDAILY  (compare with the trend charts and the daily table)")
    d = a["daily"].copy()
    d["median_tat"] = d["median_tat"].round(1)
    d["p90_tat"] = d["p90_tat"].round(1)
    print(d.to_string(index=False))
    print("  'resolved' is the cohort definition the dashboard shows (created in range).")
    print("  'resolved_throughput' counts everything resolved that day, whenever created.")

    if len(a["backlog_by_age"]):
        print("\nBACKLOG BY AGE  (at the end of the last day)")
        print(a["backlog_by_age"].to_string(index=False))

    for title, key in [("BY LANGUAGE QUEUE", "by_queue"), ("BY REQUEST TYPE", "by_request_type")]:
        print(f"\n{title}")
        seg = a[key].copy()
        seg["median_tat"] = seg["median_tat"].round(1)
        seg["p90_tat"] = seg["p90_tat"].round(1)
        print(seg.to_string(index=False))


def to_json(a: dict) -> str:
    out = {k: (v.to_dict("records") if isinstance(v, pd.DataFrame) else v)
           for k, v in a.items()}
    return json.dumps(out, indent=2, default=str)


def main() -> None:
    df = load_raw()
    lo, hi = df["created_date"].min().date(), df["created_date"].max().date()

    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--from", dest="d_from", default=str(lo), help=f"start date (default {lo})")
    p.add_argument("--to", dest="d_to", default=str(hi), help=f"end date (default {hi})")
    p.add_argument("--queue", nargs="*", default=None,
                   help="EN International JA KO Unclassified (default: all)")
    p.add_argument("--request-type", nargs="*", default=None,
                   help="Refund 'Non-refund' 'Not specified' (default: all)")
    p.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = p.parse_args()

    result = audit(
        df,
        pd.Timestamp(args.d_from).date(),
        pd.Timestamp(args.d_to).date(),
        args.queue or sorted(df["queue"].unique()),
        args.request_type or sorted(df["request_type"].unique()),
    )
    print(to_json(result) if args.json else "", end="")
    if not args.json:
        show(result)


if __name__ == "__main__":
    main()
