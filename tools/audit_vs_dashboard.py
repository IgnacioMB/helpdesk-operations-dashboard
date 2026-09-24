"""Regression test: does the dashboard report what an independent recomputation says?

Drives the dashboard headlessly for a set of filter selections, scrapes the numbers it
actually renders, and compares them against `tools/audit_metrics.py`, which derives the
same figures from the raw workbook without touching any project code.

This is the check that catches a broken filter or a redefined metric. It compares the
five headline tiles, the accumulation caption and every row of the daily table.

Usage:
    python tools/audit_vs_dashboard.py            # all cases, exits non-zero on mismatch
    python tools/audit_vs_dashboard.py -v         # print every compared value
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "dashboard.py"

TILE_RE = re.compile(r'<span class="label">([^<]+?)(?:<span class="caution">[^<]*</span>)?</span>'
                     r'<div class="value">([\d,\.\-\+]+)')
CAPTION_RE = re.compile(r"\*\*([\d,]+) created\*\*, \*\*([\d,]+) resolved\*\*.*?"
                        r"ratio \*\*([\d\.]+)")

# (label, date range, queues, request types)
CASES = [
    ("full extract", None, None, None),
    ("last 3 days", (dt.date(2022, 7, 6), dt.date(2022, 7, 8)), None, None),
    ("first 3 days", (dt.date(2022, 6, 26), dt.date(2022, 6, 28)), None, None),
    ("single day", (dt.date(2022, 7, 3), dt.date(2022, 7, 3)), None, None),
    ("JA queue", None, ["JA"], None),
    ("EN + International", None, ["EN", "International"], None),
    ("Unclassified", None, ["Unclassified"], None),
    ("refund only", None, None, ["Refund"]),
    ("JA + date range", (dt.date(2022, 7, 4), dt.date(2022, 7, 8)), ["JA"], None),
]


def run_audit(date_range, queues, categories) -> dict:
    cmd = [sys.executable, str(ROOT / "tools" / "audit_metrics.py"), "--json"]
    if date_range:
        cmd += ["--from", str(date_range[0]), "--to", str(date_range[1])]
    if queues:
        cmd += ["--queue", *queues]
    if categories:
        cmd += ["--request-type", *categories]
    out = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        raise SystemExit(f"audit_metrics.py failed:\n{out.stderr[-1500:]}")
    return json.loads(out.stdout)


def run_dashboard(date_range, queues, categories) -> dict:
    # dashboard.py imports `app.*` relative to the project root, which is not on the path
    # when this script is invoked from tools/.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(DASHBOARD), default_timeout=300)
    at.run()
    if date_range:
        at.date_input(key="f_dates").set_value(date_range)
        at.run()
    if queues:
        at.multiselect(key="f_queue").set_value(queues)
        at.run()
    if categories:
        at.multiselect(key="f_category").set_value(categories)
        at.run()
    if at.exception:
        raise AssertionError(f"dashboard raised: {[str(e.value) for e in at.exception]}")

    tiles: dict[str, str] = {}
    caption: tuple | None = None
    for block in at.markdown:
        for label, value in TILE_RE.findall(block.value):
            tiles.setdefault(label.strip(), value.replace(",", ""))
    for cap in at.caption:
        hit = CAPTION_RE.search(cap.value)
        if hit:
            caption = (int(hit.group(1).replace(",", "")),
                       int(hit.group(2).replace(",", "")),
                       float(hit.group(3)))
    daily = None
    for frame in at.dataframe:
        cols = list(frame.value.columns)
        if "Created" in cols and "Resolved" in cols and "Date" in cols:
            daily = frame.value
    return {"tiles": tiles, "caption": caption, "daily": daily}


def compare(name: str, audit: dict, shown: dict, verbose: bool) -> list[str]:
    problems: list[str] = []

    def check(field, expected, got, tol=0.0):
        if expected is None or got is None:
            problems.append(f"{field}: missing (audit={expected}, dashboard={got})")
            return
        ok = abs(float(expected) - float(got)) <= tol
        if not ok:
            problems.append(f"{field}: dashboard={got} audit={expected}")
        elif verbose:
            print(f"      {field:<34} {got}")

    t = audit["tiles"]
    # Tile labels are part of the contract this test checks: if one is renamed, the
    # lookup fails loudly rather than silently skipping that tile.
    for label, key in [("Created", "created"), ("Resolved", "resolved"),
                       ("Backlog", "backlog"),
                       ("Median turnaround time", "median_tat_min"),
                       ("P90 turnaround time", "p90_tat_min")]:
        # tiles are rendered rounded to whole units
        check(f"tile {label}", round(float(t[key])), shown["tiles"].get(label), tol=0.5)

    if shown["caption"]:
        created, resolved, ratio = shown["caption"]
        check("caption created", t["created"], created)
        check("caption resolved", t["resolved"], resolved)
        check("caption ratio", round(audit["accumulation"]["resolved_to_created_ratio"], 2),
              ratio, tol=0.005)
    else:
        problems.append("caption: not found on the page")

    daily_shown = shown["daily"]
    if daily_shown is None:
        problems.append("daily table: not found on the page")
    else:
        audit_daily = {r["date"]: r for r in audit["daily"]}
        if len(daily_shown) != len(audit_daily):
            problems.append(f"daily table: {len(daily_shown)} rows, audit has {len(audit_daily)}")
        for _, row in daily_shown.iterrows():
            key = [k for k in audit_daily
                   if dt.datetime.strptime(k, "%Y-%m-%d").strftime("%a %d %b") == row["Date"]]
            if not key:
                problems.append(f"daily table: extra row {row['Date']}")
                continue
            ref = audit_daily[key[0]]
            check(f"{row['Date']} created", ref["created"], row["Created"])
            check(f"{row['Date']} resolved", ref["resolved"], row["Resolved"])
            if "Open at 23:59" in row:
                check(f"{row['Date']} open", ref["open_23_59"], row["Open at 23:59"])
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every compared value")
    args = ap.parse_args()

    failed = 0
    for name, date_range, queues, categories in CASES:
        audit = run_audit(date_range, queues, categories)
        if "error" in audit:
            print(f"SKIP  {name:<20} (no tickets in this selection)")
            continue
        if args.verbose:
            print(f"\n  {name}")
        shown = run_dashboard(date_range, queues, categories)
        problems = compare(name, audit, shown, args.verbose)
        if problems:
            failed += 1
            print(f"FAIL  {name:<20}")
            for p in problems:
                print(f"        {p}")
        else:
            t = audit["tiles"]
            print(f"OK    {name:<20} created={t['created']:>6,}  resolved={t['resolved']:>6,}  "
                  f"backlog={t['backlog']:>4,}  median={t['median_tat_min']:.0f}m  "
                  f"p90={t['p90_tat_min']:.0f}m")

    print("\n" + ("=" * 70))
    if failed:
        print(f"{failed} of {len(CASES)} selections DISAGREE with the independent audit")
        return 1
    print(f"all {len(CASES)} selections agree with the independent audit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
