"""
Independent verification of the pipeline.

Deliberately re-derives every figure straight from the raw workbook using
different code paths from the cleaning notebook and pipeline/build.py, then
asserts they agree. It is the independent check that the clean table is right.
A number that only one implementation produces is a number nobody has checked.

Usage:  python pipeline/verify.py
"""
from __future__ import annotations

import json
import pathlib
import sys

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "Casestudy-Kiwi.com-BusinessAnalyst.xlsx"
CLEAN_DIR = ROOT / "data" / "clean"
OUT = CLEAN_DIR / "derived"

PASS, FAIL = [], []


def check(name: str, got, want, tol: float = 1e-9) -> None:
    if isinstance(want, float) or isinstance(got, float):
        ok = abs(float(got) - float(want)) <= tol
    else:
        ok = got == want
    (PASS if ok else FAIL).append((name, got, want))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:52s} got={got!r:>24}  expected={want!r}")


def main() -> int:
    # --- independent re-read of the source, dtype=object so nothing is coerced
    raw = pd.read_excel(RAW, sheet_name="fact_ticket", dtype=object)
    dim = pd.read_excel(RAW, sheet_name="dim_language", dtype=object).dropna(how="all")
    clean = pd.read_csv(CLEAN_DIR / "tickets_clean.csv",
                        parse_dates=["created_at", "resolved_at", "created_date", "resolved_date"])
    head = json.loads((OUT / "headline_kpis.json").read_text())

    created = pd.to_datetime(raw["creation_timestamp_utc"])
    resolved = pd.to_datetime(raw["resolution_timestamp_utc"])
    tat = (resolved - created).dt.total_seconds() / 60

    print("\n— row-level integrity —")
    check("clean row count == raw row count", len(clean), len(raw))
    check("no ticket_id lost", set(clean["ticket_id"]) == set(raw["ticket_id"]), True)
    check("ticket_id unique", clean["ticket_id"].is_unique, True)
    # raw is read with dtype=object, so coerce both sides before comparing
    a = clean.sort_values("ticket_id")["created_at"].reset_index(drop=True)
    b = pd.to_datetime(raw.sort_values("ticket_id")["creation_timestamp_utc"]).reset_index(drop=True)
    check("no created_at drift", int((a != b).sum()), 0)
    a2 = clean.sort_values("ticket_id")["resolved_at"].reset_index(drop=True)
    b2 = pd.to_datetime(raw.sort_values("ticket_id")["resolution_timestamp_utc"]).reset_index(drop=True)
    check("no resolved_at drift", int((a2 != b2).sum()), 0)

    print("\n— headline KPIs vs independent recomputation —")
    check("tickets_total", head["tickets_total"], len(raw))
    check("bookings_total", head["bookings_total"], int(raw["bid"].nunique()))
    check("days_covered", head["days_covered"], int(created.dt.date.nunique()))
    check("avg_created_per_day", head["avg_created_per_day"],
          round(len(raw) / created.dt.date.nunique(), 1), 0.05)
    win_end = created.dt.date.max()
    check("avg_resolved_per_day is NOT a copy of created", head["avg_resolved_per_day"],
          round(int((resolved.dt.date <= win_end).sum()) / created.dt.date.nunique(), 1), 0.05)
    check("resolutions_after_window", head["resolutions_after_window"],
          int((resolved.dt.date > win_end).sum()))
    check("median_tat_minutes", head["median_tat_minutes"], float(tat.median()), 1e-6)
    check("mean_tat_minutes", head["mean_tat_minutes"], round(float(tat.mean()), 2), 0.005)
    check("pct_resolved_same_day", head["pct_resolved_same_day"],
          round(100 * (created.dt.date == resolved.dt.date).mean(), 2), 0.005)
    check("carried_overnight", head["carried_overnight"],
          int((created.dt.date != resolved.dt.date).sum()))

    print("\n— repeat contacts —")
    vc = raw["bid"].value_counts()
    check("pct_bookings_with_repeat", head["pct_bookings_with_repeat"],
          round(100 * (vc > 1).mean(), 2), 0.005)
    check("pct_tickets_from_repeat_bookings", head["pct_tickets_from_repeat_bookings"],
          round(100 * vc[vc > 1].sum() / len(raw), 2), 0.005)

    print("\n— refund flags (the column a silent dtype bug had zeroed) —")
    acc_raw = raw["has_accepted_refund"]
    n_acc = int(acc_raw.map(lambda v: v is True or v == 1).sum())
    n_oop = int(raw["has_out_of_pocket_refund"].map(lambda v: v is True or v == 1).sum())
    check("accepted-refund True count survives transform",
          int((clean["has_accepted_refund"] == True).sum()), n_acc)  # noqa: E712
    check("out-of-pocket True count survives transform",
          int((clean["has_out_of_pocket_refund"] == True).sum()), n_oop)  # noqa: E712
    check("null refund flags preserved", int(clean["has_accepted_refund"].isna().sum()),
          int(acc_raw.isna().sum()))
    is_refund = raw["Ticket Type"].astype(str).str.endswith("- Refund requests")
    check("refund_tickets", head["refund_tickets"], int(is_refund.sum()))
    check("refund_accept_rate_pct_per_ticket", head["refund_accept_rate_pct_per_ticket"],
          round(100 * acc_raw[is_refund].map(lambda v: v is True or v == 1).sum() / int(is_refund.sum()), 2), 0.005)
    # The headline is the BOOKING-level rate, because the flag describes the booking.
    bk = (raw[is_refund].assign(_a=acc_raw[is_refund].map(lambda v: bool(v is True or v == 1)))
          .groupby("bid")["_a"].max())
    check("refund_accept_rate_pct_per_booking", head["refund_accept_rate_pct_per_booking"],
          round(100 * bk.mean(), 2), 0.005)
    check("refund_bookings", head["refund_bookings"], int(raw[is_refund]["bid"].nunique()))
    # The booking-level claim is only *provisional*: prove that it is untestable here.
    multi = raw["bid"].map(raw["bid"].value_counts()) > 1
    check("all positive refund flags sit on single-ticket bookings (claim untestable)",
          int(acc_raw[multi].map(lambda v: v is True or v == 1).sum()), 0)
    mixed = (raw.assign(_a=acc_raw).groupby("bid")["_a"]
             .apply(lambda t: t.isna().any() and t.notna().any()).sum())
    check("bookings mixing null and non-null flags (documented in the DQ note)", int(mixed), 10)

    print("\n— the synthetic-turnaround claim —")
    check("TAT is whole minutes in every row", bool((tat % 1 == 0).all()), True)
    check("TAT min", float(tat.min()), 15.0)
    check("TAT max", float(tat.max()), 45.0)
    check("sub-minute components identical in every row",
          int(((created.dt.second == resolved.dt.second)
               & (created.dt.microsecond == resolved.dt.microsecond)).sum()), len(raw))
    k = 31
    obs = tat.round().astype(int).value_counts().reindex(range(15, 46), fill_value=0).values
    chi2 = float(((obs - len(raw) / k) ** 2 / (len(raw) / k)).sum())
    # Two-sided: a chi2 near zero would mean the data was fabricated to LOOK uniform,
    # which is just as alarming as a rejection. chi2(30) 5%/95% points are 18.49/43.77.
    check("chi2 inside the two-sided acceptance band 18.49-43.77", 18.49 < chi2 < 43.77, True)
    check("no TAT outside 15-45 silently dropped from the test", int(obs.sum()), len(raw))
    check("wow_like_for_like_pct", head["wow_like_for_like_pct"],
          round(100 * (int((created.dt.date >= pd.Timestamp("2022-07-03").date()).sum())
                       / int((created.dt.date <= pd.Timestamp("2022-07-01").date()).sum()) - 1), 1), 0.05)
    print(f"        chi2 = {chi2:.2f} on {k-1} df; observed sd {tat.std():.3f} "
          f"vs theoretical {np.sqrt((k**2-1)/12):.3f}")

    print("\n— routing / language mismatch —")
    def q(t):
        t = str(t)
        if t.startswith("Helpdesk EN"): return "EN"
        if t.startswith("Helpdesk International"): return "International"
        if t == "Helpdesk - JA": return "JA"
        if t == "Helpdesk - KO": return "KO"
        return "Unclassified"
    queue = raw["Ticket Type"].map(q)
    print("\n— aggregate tables reconcile to the fact table —")
    daily = pd.read_csv(OUT / "kpi_daily.csv", parse_dates=["date"])
    check("kpi_daily created sums to total", int(daily["tickets_created"].sum()), len(raw))
    check("kpi_daily resolved = total minus spill", int(daily["tickets_resolved"].sum()),
          len(raw) - head["resolutions_after_window"])
    check("kpi_daily covers exactly the creation window (no phantom day)",
          len(daily), int(created.dt.date.nunique()))
    check("kpi_daily has no zero-intake day", int((daily["tickets_created"] == 0).sum()), 0)
    # the phantom row made Saturday appear twice and halved its weekday average
    check("Saturday weekday average is not halved by a phantom row",
          float(daily.groupby("day_of_week")["tickets_created"].mean()["Saturday"]),
          float(created.dt.date.value_counts()[pd.Timestamp("2022-07-02").date()]), 0.5)
    # --- P90, ratio and backlog, re-derived by a different route -----------
    # np.percentile(method="nearest") is a different library path from the
    # Series.quantile(interpolation="nearest") the pipeline uses, so agreement is
    # evidence rather than the same code run twice.
    check("headline p90_tat_minutes", head["p90_tat_minutes"],
          float(np.percentile(tat.astype(float), 90, method="nearest")))
    check("headline p90 >= median", head["p90_tat_minutes"] >= head["median_tat_minutes"], True)
    res_in = int((resolved.dt.date <= created.dt.date.max()).sum())
    check("headline resolved_to_created_ratio", head["resolved_to_created_ratio"],
          round(res_in / len(raw), 4), 5e-5)

    by_day = pd.DataFrame({"d": created.dt.date, "tat": tat.astype(float)})
    p90_mine = by_day.groupby("d")["tat"].apply(
        lambda v: float(np.percentile(v, 90, method="nearest")))
    check("kpi_daily p90 matches per day", 
          int((daily.set_index(daily["date"].dt.date)["p90_tat_minutes"] != p90_mine).sum()), 0)
    ratio_mine = (daily["tickets_resolved"] / daily["tickets_created"]).round(4)
    check("kpi_daily resolved_to_created_ratio per day",
          float((daily["resolved_to_created_ratio"] - ratio_mine).abs().max()), 0.0, 5e-5)

    # Backlog rebuilt from timestamps, NOT from a cumsum of the published counts, so the
    # "open at end of day == carried overnight" claim is audited rather than assumed.
    open_eod = []
    for day in daily["date"]:
        edge = day + pd.Timedelta(days=1)
        open_eod.append(int(((created < edge) & (resolved >= edge)).sum()))
    check("open_end_of_day re-derived from timestamps",
          int((daily["open_end_of_day"] != pd.Series(open_eod)).sum()), 0)
    check("open_end_of_day equals the midnight carry",
          int((daily["open_end_of_day"] != daily["carried_overnight"]).sum()), 0)
    # Same-weekday-previous-week, rebuilt by looking the date up in a raw value_counts
    # rather than by shifting the published series.
    raw_counts = created.dt.date.value_counts()
    prev_mine, ratio_mine = [], []
    for day in daily["date"]:
        ref = (day - pd.Timedelta(days=7)).date()
        n = raw_counts.get(ref)
        prev_mine.append(float("nan") if n is None else float(n))
        ratio_mine.append(float("nan") if n is None else round(
            float(daily.loc[daily["date"] == day, "tickets_created"].iloc[0]) / float(n), 4))
    prev_mine = pd.Series(prev_mine)
    check("tickets_created_prev_week re-derived from the raw counts",
          int((daily["tickets_created_prev_week"].fillna(-1) != prev_mine.fillna(-1)).sum()), 0)
    check("prev-week weekday alignment (all reference days are the same weekday)",
          int(sum((d - pd.Timedelta(days=7)).day_name() != d.day_name() for d in daily["date"])), 0)
    check("wow_ratio re-derived", int((daily["wow_ratio"].fillna(-1)
                                       != pd.Series(ratio_mine).fillna(-1)).sum()), 0)
    check("prev-week blank exactly for the first reference-free week",
          int(daily["tickets_created_prev_week"].isna().sum()),
          int((daily["date"] < daily["date"].min() + pd.Timedelta(days=7)).sum()))

    check("backlog at the window end equals the spill",
          int(daily["open_end_of_day"].iloc[-1]), head["resolutions_after_window"])

    for t, col in [("kpi_by_queue", "queue"),
                   ("kpi_by_request_type", "request_type"),
                   ("kpi_by_ticket_type", "ticket_type")]:

        tb = pd.read_csv(OUT / f"{t}.csv").set_index(col)
        check(f"{t}: tickets sum to total", int(tb["tickets"].sum()), len(raw))
        check(f"{t}: resolved sums to total minus spill", int(tb["tickets_resolved"].sum()),
              len(raw) - head["resolutions_after_window"])
        mine_res = (clean[clean["resolved_date"] <= clean["created_date"].max()]
                    .groupby(col).size().reindex(tb.index, fill_value=0))
        check(f"{t}: resolved matches per segment", int((tb["tickets_resolved"] != mine_res).sum()), 0)
        mine_p90 = clean.groupby(col)["turnaround_minutes_generated"].apply(
            lambda v: float(np.percentile(v.astype(float), 90, method="nearest"))).reindex(tb.index)
        check(f"{t}: p90 matches per segment", int((tb["p90_tat_minutes"] != mine_p90).sum()), 0)
        check(f"{t}: shares sum to 100%", round(float(tb["share_pct"].sum()), 1), 100.0, 0.06)
        # independent re-derivation of every published column
        g = clean.groupby(col)
        mine = pd.DataFrame({
            "tickets": g.size(),
            "bookings_touching_segment": g["booking_id"].nunique(),
            "median_tat_minutes": g["turnaround_minutes_generated"].median().round(2),
            "pct_repeat_within_segment": g.apply(
                lambda s: 100 * (s.groupby("booking_id")["ticket_id"].transform("size") > 1).mean(),
                include_groups=False).round(2),
        })
        for c_ in mine.columns:
            diff = int((tb[c_].reindex(mine.index) - mine[c_]).abs().gt(0.011).sum())
            check(f"{t}: {c_} re-derives exactly", diff, 0)
        # the repeat rate must be possible given tickets_per_booking
        bound = 1 / (1 - tb["pct_repeat_within_segment"] / 200)
        check(f"{t}: repeat rate consistent with tickets_per_booking",
              int((tb["tickets_per_booking"] < bound - 5e-3).sum()), 0)
    tatd = pd.read_csv(OUT / "kpi_tat_distribution.csv")
    check("kpi_tat_distribution sums to total", int(tatd["tickets"].sum()), len(raw))
    hd = pd.read_csv(OUT / "kpi_hour_dow.csv").set_index("created_weekday")
    check("kpi_hour_dow has 7 rows x 24 hours", hd.shape, (7, 24))
    cnt = clean.groupby(["created_weekday", "created_hour"]).size().unstack(fill_value=0)
    dseen = clean.groupby("created_weekday")["created_date"].nunique()
    mine_hd = (cnt.T / dseen).T.round(2)
    mine_hd.columns = [str(c_) for c_ in mine_hd.columns]
    check("kpi_hour_dow values re-derive exactly",
          int((hd[mine_hd.columns].reindex(mine_hd.index) - mine_hd).abs().gt(0.011).sum().sum()), 0)
    check("kpi_hour_dow Saturday denominator is 1, not 2",
          int(dseen["Saturday"]), 1)
    check("kpi_hour_dow row sums equal true weekday averages",
          int((hd.sum(axis=1).round(1)
               - (clean.groupby("created_weekday").size() / dseen).round(1)).abs().gt(0.15).sum()), 0)

    print(f"\n{'='*78}\n{len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("\nFAILURES:")
        for n, g, w in FAIL:
            print(f"  - {n}: got {g!r}, expected {w!r}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
