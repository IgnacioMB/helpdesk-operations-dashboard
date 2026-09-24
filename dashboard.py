"""
Kiwi.com Helpdesk - Daily Operations Dashboard
Business Analyst case study prototype.

Run:  .venv/bin/streamlit run dashboard.py

One rule governs every number on screen: it is either computed from the FILTERED
frame, or it is explicitly badged "full extract". Mixing the two inside a single
tile or sentence is what makes a dashboard quietly lie.
"""
from __future__ import annotations

import datetime as dt
import pathlib

import numpy as np
import pandas as pd
import streamlit as st

from app import charts
from app.branding import css, logo_svg, tile

from app.data import clean_mtime, load
from app.metrics import DOW_ORDER, calendar_days, demand_trend, repeat_flag, weekday_occurrences

# The tab icon is kiwi.com's own favicon, not the fruit emoji.
FAVICON = pathlib.Path(__file__).resolve().parent / "assets" / "kiwicom-favicon.png"
st.set_page_config(page_title="Kiwi.com Helpdesk — Daily Operations",
                   page_icon=str(FAVICON) if FAVICON.exists() else "🥝",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(css(), unsafe_allow_html=True)

df_all, issues, head = load(clean_mtime())

# =========================================================== sidebar filters
with st.sidebar:
    st.markdown(logo_svg(30), unsafe_allow_html=True)
    st.markdown('<div class="sb-title">Reporting period</div>', unsafe_allow_html=True)
    dmin, dmax = df_all["created_date"].min().date(), df_all["created_date"].max().date()
    date_range = st.date_input("Created between", value=(dmin, dmax), min_value=dmin,
                               max_value=dmax, key="f_dates", label_visibility="collapsed")
    d_from, d_to = date_range if isinstance(date_range, tuple) and len(date_range) == 2 else (dmin, dmax)

    st.markdown('<div class="sb-title">Language queue</div>', unsafe_allow_html=True)
    queues = sorted(df_all["queue"].unique())
    sel_q = st.multiselect("Queue", queues, default=queues, key="f_queue",
                           label_visibility="collapsed")

    st.markdown('<div class="sb-title">Request category</div>', unsafe_allow_html=True)
    cats = sorted(df_all["request_type"].unique())
    sel_c = st.multiselect("Category", cats, default=cats, key="f_category",
                           label_visibility="collapsed")


# Segment filters only, every date. The week-on-week comparison reads from this, so the
# reference week survives a date filter that excludes it.
df_span = df_all[df_all["queue"].isin(sel_q) & df_all["request_type"].isin(sel_c)]
df = df_span[(df_span["created_date"].dt.date >= d_from)
             & (df_span["created_date"].dt.date <= d_to)]

IS_FILTERED = ((d_from, d_to) != (dmin, dmax) or len(sel_q) != len(queues)
               or len(sel_c) != len(cats))

# =========================================================== header
scope = (f"{d_from:%d %b} → {d_to:%d %b %Y}" if IS_FILTERED
         else f"{head['window_start']} → {head['window_end']}")
sub = (f"{len(df):,} of {head['tickets_total']:,} tickets · filtered"
       if IS_FILTERED else f"{head['tickets_total']:,} tickets · {head['bookings_total']:,} bookings")
st.markdown(
    f"""<div class="kiwi-header">
      <div style="display:flex;align-items:center;gap:16px;">
        {logo_svg(38)}
        <div>
          <p class="title">Helpdesk — Daily Operations Dashboard</p>
          <div class="sub">Ticket volume, resolution and turnaround, by language queue and request type</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

if df.empty:
    st.warning("No tickets match the current filters. Widen the selection in the sidebar.")
    st.stop()

st.markdown(
    '<div class="dq-strip"><b>This dashboard is a work in progress.</b> We have identified '
    'data issues in the source data and are currently investigating them. Please do not draw '
    'conclusions from this dashboard until further notice. '
    '<b>Browse the <i>Data &amp; quality</i> tab</b> to see every issue we have found, how '
    'serious each one is, and which numbers it affects.</div>',
    unsafe_allow_html=True)

CAL_DAYS = len(calendar_days(d_from, d_to))
WEEKDAY_N = weekday_occurrences(d_from, d_to)

tab_dash, tab_analysis, tab_data, tab_dict = st.tabs([
    "01 · Operations Overview", "02 · Drill Down", "03 · Data & quality",
    "04 · Metric dictionary"])

# ============================================================== 01 Dashboard
with tab_dash:
    st.markdown('<div class="sec">Operations overview</div>'
                '<div class="sec-sub">The five numbers a team lead reads first, then the trends '
                'behind them, then where the work sits. Everything on this tab responds to the '
                'sidebar filters.</div>',
                unsafe_allow_html=True)

    # Resolutions are counted on their own date, inside the selected window, so this
    # is a real throughput figure rather than a copy of the intake figure.
    res_in_window = int(df["resolved_date"].dt.date.between(d_from, d_to).sum())
    spill = len(df) - res_in_window
    created_pd = len(df) / CAL_DAYS
    resolved_pd = res_in_window / CAL_DAYS
    same_day = 100 * df["resolved_same_day"].astype(bool).mean()
    overnight = int((~df["resolved_same_day"].astype(bool)).sum())
    med_tat = df["turnaround_minutes_generated"].median()
    # interpolation="nearest" matches the pipeline: turnaround is whole minutes, so a
    # linear-interpolated P90 would show a value that cannot occur.
    p90_tat = df["turnaround_minutes_generated"].quantile(0.9, interpolation="nearest")

    rep_tickets = repeat_flag(df)                       # recomputed WITHIN the selection
    rep_ticket_pct = 100 * rep_tickets.mean()
    wow, wow_caption = demand_trend(df, d_from, d_to)

    daily = (pd.concat([df.groupby("created_date").size().rename("tickets_created"),
                        df.groupby("resolved_date").size().rename("tickets_resolved")],
                       axis=1).fillna(0).astype(int).sort_index().reset_index(names="date"))
    last_created = df["created_date"].max()
    chart_spill = int(daily.loc[daily["date"] > last_created, "tickets_resolved"].sum())
    daily = daily[daily["date"] <= last_created].copy()
    # A day with no tickets in the current selection would otherwise drop out of the frame
    # entirely, and the trend lines would join the days either side as if they were
    # adjacent. Reindex across the calendar so an empty day is drawn as zero.
    daily = (daily.set_index("date")
             .reindex(pd.date_range(df["created_date"].min(), last_created, freq="D"),
                      fill_value=0)
             .rename_axis("date").reset_index())
    daily["carried_overnight"] = (
        df[~df["resolved_same_day"].astype(bool)].groupby("created_date").size()
        .reindex(daily["date"], fill_value=0).values)
    # Every ticket open at 23:59, whenever it was created - not just the ones opened inside
    # the selected range. Counted from the date-unfiltered frame by timestamp, so a date
    # filter cannot silently reset the opening balance to zero, and a ticket still open
    # from weeks earlier is still counted. A cumulative sum of the filtered days would
    # miss both.
    _edges = pd.to_datetime(daily["date"]) + pd.Timedelta(days=1)
    _c, _r = df_span["created_at"], df_span["resolved_at"]
    daily["open_end_of_day"] = [
        int(((_c < e) & (_r.isna() | (_r >= e))).sum()) for e in _edges]
    daily["median_tat_minutes"] = (
        df.groupby("created_date")["turnaround_minutes_generated"].median()
        .reindex(daily["date"]).values)
    daily["p90_tat_minutes"] = (
        df.groupby("created_date")["turnaround_minutes_generated"]
        .quantile(0.9, interpolation="nearest").reindex(daily["date"]).values)
    # Same weekday a week earlier, taken from the date-unfiltered frame and attached to
    # the current day's row, so it is still there when the filter excludes that week.
    span_counts = df_span.groupby("created_date").size()
    span_counts.index = span_counts.index + pd.Timedelta(days=7)
    daily["tickets_created_prev_week"] = span_counts.reindex(daily["date"]).values
    daily["wow_ratio"] = daily["tickets_created"] / daily["tickets_created_prev_week"]
    daily["net_change"] = daily["tickets_created"] - daily["tickets_resolved"]
    daily["resolved_to_created_ratio"] = daily["tickets_resolved"] / daily["tickets_created"]

    backlog_now = int(daily["open_end_of_day"].iloc[-1]) if len(daily) else 0

    # ---------------------------------------------------------------- tiles
    c = st.columns(5)
    c[0].markdown(tile("Created", f"{len(df):,}", kind="accent",
                       foot=f"{created_pd:,.0f} a day over {CAL_DAYS} calendar days"),
                  unsafe_allow_html=True)
    c[1].markdown(tile("Resolved", f"{res_in_window:,}",
                       foot=f"{resolved_pd:,.0f} a day"
                            + (f"; {spill} closed after the window" if spill else "")),
                  unsafe_allow_html=True)
    c[2].markdown(tile("Backlog", f"{backlog_now:,}",
                       foot="How big the pile is — every ticket still open at 23:59 on the "
                            "last day, whenever it arrived"),
                  unsafe_allow_html=True)
    c[3].markdown(tile("Median turnaround time", f"{med_tat:,.0f}", "min", kind="accent"),
                  unsafe_allow_html=True)
    c[4].markdown(tile("P90 turnaround time", f"{p90_tat:,.0f}", "min", kind="accent"),
                  unsafe_allow_html=True)

    # ------------------------------------------------------------ demand
    st.markdown('<div class="sec">Demand against the week before </div>'
                '<div class="sec-sub">Each day next to the same weekday a week earlier, with the '
                'ratio on the right axis. Comparing like weekdays is what makes the change '
                'readable — a Sunday against a Monday is not a trend. The first week of any '
                'selection has no reference week and is left blank rather than shown as zero.</div>',
                unsafe_allow_html=True)
    if daily["wow_ratio"].notna().any():
        st.plotly_chart(charts.demand_vs_prev_week(daily), config={"displayModeBar": False},
                        key="ov_wow")
    else:
        st.info("No day in this selection has a matching weekday in the previous week. "
                "Widen the date range to at least eight days to see the comparison.")

    # ------------------------------------------------- created vs resolved
    st.markdown('<div class="sec">Tickets created and resolved per day </div>'
                '<div class="sec-sub">The two lines sit on top of each other: intake is cleared '
                'the same day, so the team is not accumulating a backlog. Resolved counts tickets '
                '<i>created</i> in this window, by the day they closed.</div>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.created_vs_resolved(daily), config={"displayModeBar": False},
                    key="ov_created_resolved")
    gran_note = ("Daily only: the extract covers 13 days, so a weekly view would be two partial "
                 "weeks and a monthly one a single point.")
    if chart_spill:
        st.caption(f"Clipped to the creation window: a further **{chart_spill} tickets** opened on "
                   f"{last_created:%d %b} closed after midnight. {gran_note}")
    else:
        st.caption(gran_note)

    st.markdown('<div class="sec">Is work accumulating? </div>'
                '<div class="sec-sub">Two readings of the same question, and they answer it '
                'differently. <b>Net ticket change</b> (bars) is the absolute one: is the pile '
                'growing or shrinking today, counted in tickets — above the zero line the day '
                'took in more than it closed. <b>Resolved-to-created ratio</b> (line) is the '
                'scale-free one: what share of the day\'s intake was cleared, where 1.00× means '
                'the team kept pace exactly. Because it is a share, it means the same thing for '
                'a 200-ticket queue as for a 12,000-ticket one — it is the metric to read when '
                'comparing segments of different sizes.</div>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.net_change_and_ratio(daily), config={"displayModeBar": False},
                    key="ov_net_ratio")
    net_sel = len(df) - res_in_window
    st.caption(
        f"Over this selection: **{len(df):,} created**, **{res_in_window:,} resolved** — "
        + (f"net **{net_sel:+,} ticket{'' if abs(net_sel) == 1 else 's'}**, " if net_sel
           else "**no net change**, ")
        + f"ratio **{res_in_window / len(df):.2f}×**. "
        + (f"The shortfall is the **{net_sel:,} ticket{'' if net_sel == 1 else 's'} opened inside "
           "this range that closed after it** — a property of where the window ends, not of "
           "throughput. No single day is incomplete: each one takes in the previous night's "
           "carryover as it hands its own to the next morning."
           if net_sel > 0 else
           "Every ticket opened inside this range also closed inside it."))

    # --------------------------------------------------- backlog | TAT trend
    a, b = st.columns(2)
    with a:
        st.markdown('<div class="sec">Backlog trend </div>'
                    '<div class="sec-sub"><b>How big is the total pile of accumulated '
                    'workload?</b> Every ticket still open at 23:59, whatever day it arrived — '
                    'a level, not a flow. Here it never exceeds a few dozen and clears by the '
                    'next morning, so nothing is carrying over.</div>', unsafe_allow_html=True)
        st.plotly_chart(charts.backlog_trend(daily), config={"displayModeBar": False},
                        key="ov_backlog")

        st.markdown('<div class="sec">Backlog by age </div>'
                    '<div class="sec-sub">How old the open tickets are at the end of the '
                    'selected period. On real data this is the triage order — a pile of '
                    'week-old tickets is a different problem from the same pile an hour '
                    'old.</div>', unsafe_allow_html=True)
        # Age measured at the end of the last day in range, for the same population the
        # backlog tile counts.
        _edge = pd.to_datetime(daily["date"].iloc[-1]) + pd.Timedelta(days=1)
        _open = df_span[(df_span["created_at"] < _edge)
                        & (df_span["resolved_at"].isna() | (df_span["resolved_at"] >= _edge))]
        if len(_open):
            AGE_LABELS = ["<1h", "1–4h", "4–12h", "12–24h", "1–3d", "3–7d", "7d+"]
            _age_h = (_edge - _open["created_at"]).dt.total_seconds() / 3600
            _ages = (pd.cut(_age_h, [0, 1, 4, 12, 24, 72, 168, np.inf], labels=AGE_LABELS,
                            right=False).value_counts().reindex(AGE_LABELS, fill_value=0))
            st.plotly_chart(charts.hbar(AGE_LABELS, _ages.tolist(), title="Tickets open",
                                        height=260),
                            config={"displayModeBar": False}, key="ov_backlog_age")
            _oldest = _age_h.max()
            _n = len(_open)
            _subject = "The single open ticket is" if _n == 1 else f"All {_n:,} open tickets are"
            st.caption(
                f"{_subject} under "
                f"{'an hour' if _oldest < 1 else f'{_oldest:.0f} hours'} old, so the whole "
                "backlog sits in one bucket. That is a property of this extract, not of the "
                "helpdesk: the resolution timestamp is generated with a 45-minute ceiling, so "
                "nothing can age. On real data this chart is where you would look first."
                if _oldest < 1 else
                f"Oldest open ticket: **{_oldest:.0f} hours**. {_n:,} open in total.")
        else:
            st.info("Nothing is open at the end of this period, so there is no backlog to age.")
    with b:
        st.markdown('<div class="sec">Turnaround trend </div>'
                    '<div class="sec-sub">Median and P90 turnaround, in minutes.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(charts.tat_trend(daily), config={"displayModeBar": False},
                        key="ov_tat_trend")

    # ------------------------------------------- language | ticket type
    def _segment_view(frame, col):
        """Created, resolved and median turnaround per segment, within the selection."""
        g = frame.groupby(col)
        limit = frame["created_date"].max()
        out = pd.DataFrame({
            "tickets": g.size(),
            "tickets_resolved": frame[frame["resolved_date"] <= limit].groupby(col).size(),
            "median_tat_minutes": g["turnaround_minutes_generated"].median(),
        }).fillna(0).reset_index()
        return out.sort_values("tickets", ascending=False)

    seg_lang = _segment_view(df, "queue")
    seg_type = _segment_view(df, "request_type")

    a, b = st.columns(2)
    for col, seg, label, title in [(a, seg_lang, "queue", "By language queue"),
                                   (b, seg_type, "request_type", "By request type")]:
        with col:
            st.markdown(f'<div class="sec">{title}</div>'
                        '<div class="sec-sub">Counts inherit the population caveat; the '
                        'turnaround bars below them are generated.</div>',
                        unsafe_allow_html=True)
            st.plotly_chart(charts.segment_flow(seg, label), config={"displayModeBar": False},
                            key=f"ov_flow_{label}")
            st.plotly_chart(charts.tat_by_segment(seg, label, med_tat),
                            config={"displayModeBar": False}, key=f"ov_tat_{label}")

    with st.expander("Table view — daily figures"):
        st.dataframe(daily.assign(date=daily["date"].dt.strftime("%a %d %b"))
                     .rename(columns={"date": "Date", "tickets_created": "Created",
                                      "tickets_resolved": "Resolved",
                                      "open_end_of_day": "Open at 23:59",
                                      "carried_overnight": "Crossed midnight",
                                      "median_tat_minutes": "Median TAT",
                                      "p90_tat_minutes": "P90 TAT"}),
                     width="stretch", hide_index=True)

# ============================================================== 02 Analysis
with tab_analysis:
    st.markdown('<div class="sec">What is driving the numbers?</div>'
                '<div class="sec-sub">The overview tells you whether the day looks normal; this tab '
                'tells you what is driving it — the mix behind the totals, when the work actually '
                'arrives, and the distributions the headline figures average away. In practice: the '
                'timing charts are what you staff against, and repeat contact is the only '
                'avoidable-volume signal in this dataset.</div>',
                unsafe_allow_html=True)

    a, b = st.columns(2)
    with a:
        st.markdown('<div class="sec">Volume by ticket type </div>'
                    '<div class="sec-sub">The raw <code>Ticket Type</code> field, unsplit.</div>',
                    unsafe_allow_html=True)
        tt = df["ticket_type"].value_counts()
        st.plotly_chart(charts.hbar(tt.index.tolist(), tt.values.tolist(), title="Tickets"),
                        config={"displayModeBar": False})
    with b:
        other_share = 100 * (~df["queue"].isin(["EN", "International"])).mean()
        st.markdown('<div class="sec">Daily volume by language queue </div>'
                    f'<div class="sec-sub">JA, KO and unclassified are folded into “Other” — '
                    f'{other_share:.1f}% of the tickets in this selection.</div>',
                    unsafe_allow_html=True)
        st.plotly_chart(charts.daily_by_queue(df), config={"displayModeBar": False})

    st.markdown('<div class="sec">Daily volume by request type </div>'
                '<div class="sec-sub">The companion to the queue view above. Refund and '
                'non-refund track each other, so the mix is stable even as total volume '
                'falls across the window.</div>', unsafe_allow_html=True)
    st.plotly_chart(charts.daily_by_request_type(df), config={"displayModeBar": False},
                    key="dd_daily_request_type")

    with st.expander("Table view — full segment breakdown"):
        seg = (df.groupby(["queue", "request_type"])
               .agg(Tickets=("ticket_id", "size"),
                    **{"Bookings touching": ("booking_id", "nunique"),
                       "Median TAT (min)": ("turnaround_minutes_generated", "median")})
               .reset_index().sort_values("Tickets", ascending=False))
        within = (df.groupby(["queue", "request_type"])
                  .apply(lambda s: 100 * (s.groupby("booking_id")["ticket_id"].transform("size") > 1).mean(),
                         include_groups=False).rename("Repeat within segment %").round(1))
        seg = seg.merge(within.reset_index(), on=["queue", "request_type"])
        seg["Tickets/day"] = (seg["Tickets"] / CAL_DAYS).round(1)
        st.dataframe(seg, width="stretch", hide_index=True)
        st.caption("“Bookings touching” is **not additive** — a booking with tickets in two segments "
                   "is counted in both, so the column sums to more than the distinct booking total.")

# ====================================================== 02 Analysis (cont.)
with tab_analysis:
    st.markdown('<div class="sec">Drivers and diagnostics</div>'
                '<div class="sec-sub">When the work arrives, and how often the same booking '
                'comes back.</div>', unsafe_allow_html=True)

    st.markdown('<div class="sec">When does work actually arrive? </div>'
                '<div class="sec-sub">Average tickets per hour, by weekday and hour of day (UTC). '
                'Divided by how many times each weekday occurs in the selected window — Saturday '
                'occurs once in this 13-day extract, every other weekday twice.</div>',
                unsafe_allow_html=True)
    hm = df.groupby(["created_weekday", "created_hour"]).size().unstack(fill_value=0)
    hm = hm.reindex(columns=range(24), fill_value=0)
    present = [d for d in DOW_ORDER if d in hm.index]
    hm = hm.reindex(present)
    hm = hm.div(WEEKDAY_N.reindex(hm.index), axis=0).round(2).reset_index()
    st.plotly_chart(charts.arrival_heatmap(hm), config={"displayModeBar": False},
                    key="dd_heatmap")

    st.markdown('<div class="sec">Volume by weekday </div>'
                '<div class="sec-sub">The same normalisation as the heatmap: tickets per day '
                'for each weekday, divided by how often that weekday occurs in the selected '
                'window.</div>', unsafe_allow_html=True)
    per_dow_chart = (df.groupby("created_weekday").size()
                     .div(WEEKDAY_N.reindex(df["created_weekday"].unique()).dropna())
                     .reindex(DOW_ORDER).dropna())
    st.plotly_chart(charts.volume_by_weekday(per_dow_chart),
                    config={"displayModeBar": False}, key="dd_weekday")

    a, b = st.columns(2)
    with a:
        st.markdown('<div class="sec">Repeat contacts — how soon do people write again? </div>'
                    '<div class="sec-sub">Gap between consecutive tickets on the same booking, '
                    'resequenced within the current selection.</div>', unsafe_allow_html=True)
        # contact_seq / gap are frozen over the full extract in the CSV; recompute them
        # here or a filtered view measures the distance to a ticket that is not on screen.
        d = df.sort_values(["booking_id", "created_at", "ticket_id"], kind="mergesort")
        seq = d.groupby("booking_id").cumcount() + 1
        gap = d.groupby("booking_id")["created_at"].diff().dt.total_seconds() / 3600
        rep = gap[seq > 1].dropna()
        if len(rep):
            labels = ["<1h", "1–6h", "6–24h", "24–48h", "48–72h", "72h+"]
            vc = pd.cut(rep, [0, 1, 6, 24, 48, 72, np.inf], labels=labels,
                        right=False).value_counts().reindex(labels, fill_value=0)
            st.plotly_chart(charts.hbar(labels, vc.values.tolist(), title="Re-contacts", height=300),
                            config={"displayModeBar": False})
            st.caption(f"{len(rep):,} re-contacts in this selection · median gap **{rep.median():.1f} h** · "
                       f"**{100 * (rep < 1).mean():.0f}%** arrive within the hour.")
        else:
            st.info("No repeat contacts in the current selection.")
    with b:
        st.markdown('<div class="sec">Turnaround distribution </div>'
                    '<div class="sec-sub">How long tickets take, across the current '
                    'selection.</div>', unsafe_allow_html=True)
        dist = (df["turnaround_minutes_generated"].round().astype(int).value_counts().sort_index()
                .rename("tickets").rename_axis("turnaround_minutes_generated").reset_index())
        st.plotly_chart(charts.tat_distribution(dist), config={"displayModeBar": False})

    with st.expander("Ticket-level drill-down"):
        cols = ["ticket_id", "booking_id", "ticket_type", "queue", "request_type",
                "created_at", "resolved_at", "turnaround_minutes_generated",
                "tickets_on_booking"]
        st.dataframe(df[cols].head(1000), width="stretch", hide_index=True)
        st.download_button("Download the filtered ticket set (CSV)",
                           df[cols].to_csv(index=False).encode(),
                           file_name="kiwi_helpdesk_filtered.csv", mime="text/csv")

# ============================================================== DQ
with tab_data:
    clean_file = pathlib.Path(__file__).parent / "data" / "clean" / "tickets_clean.csv"
    refreshed = dt.datetime.fromtimestamp(clean_file.stat().st_mtime) if clean_file.exists() else None
    st.caption(
        f"Clean dataset `{clean_file.name}` last refreshed **{refreshed:%d %b %Y, %H:%M}** "
        f"· {len(df_all):,} tickets · produced by `data_cleaning.ipynb`"
        if refreshed else "Clean dataset not found.")

    st.markdown('<div class="sec">Data quality — what I checked before trusting anything above</div>'
                f'<div class="sec-sub">{len(issues)} issues found in '
                '<code>data_source_review.ipynb</code>, which is re-run whenever the source '
                'data is refreshed rather than living in a one-off note.</div>',
                unsafe_allow_html=True)

    counts = issues["priority"].value_counts()
    c = st.columns(3)
    for i, (pri, label) in enumerate([("Higher", "HIGHER — affecting core metrics"),
                                      ("Lower", "LOWER — affecting other fields"),
                                      ("Observation", "Observations")]):
        c[i].markdown(tile(label, f"{int(counts.get(pri, 0))}",
                           kind="warn" if pri == "Higher" else ""), unsafe_allow_html=True)

    sev_filter = st.multiselect("Show", ["Higher", "Lower", "Observation"],
                                default=["Higher", "Lower"], key="f_severity")
    view = issues[issues["priority"].isin(sev_filter)].copy()
    view = view.rename(columns={"n": "#", "priority": "Priority", "issue": "Issue",
                                "detail": "What it means / how it was handled"})
    st.dataframe(view, width="stretch", hide_index=True,
                 column_config={"What it means / how it was handled":
                                st.column_config.TextColumn(width="large")})
    st.download_button("Download the data-quality issue list (CSV)",
                       issues.to_csv(index=False).encode(),
                       file_name="kiwi_data_quality_issues.csv", mime="text/csv")

    rf_all = df_all[df_all["request_type"] == "Refund"]
    acc_book = 100 * (rf_all.groupby("booking_id")["has_accepted_refund"].max() == True).mean()  # noqa: E712

    gaps_all = df_all.loc[df_all["contact_seq"] > 1, "hours_since_prev_contact"].dropna()
    recontact_median = float(gaps_all.median()) if len(gaps_all) else float("nan")
    recontact_1h = 100 * float((gaps_all < 1).mean()) if len(gaps_all) else 0.0

    st.markdown('<div class="sec">Which numbers can be acted on</div>'
                '<div class="sec-sub">Every metric on this dashboard, judged against the issues '
                'above. <b>Reliable</b> means the number measures what its name says. '
                '<b>Not Reliable</b> means it is wrong, measures something narrower than its '
                'name, or cannot be verified from this data. Nothing currently qualifies as '
                'reliable, which is why the dashboard carries a warning rather than pills on '
                'individual charts. <b>Why</b> cites the numbered issues above rather than restating them. Values are for the full extract.</div>',
                unsafe_allow_html=True)

    kpi_rows = [
        ("Tickets created / day", "01 · Overview", f"{head['avg_created_per_day']:,.0f}", False,
         "<b>Issue 2.</b> Exact for the rows present, but automated and still-open "
         "tickets may never have reached the extract, so this is a floor on demand rather than "
         "demand."),
        ("Tickets resolved / day", "01 · Overview", f"{head['avg_resolved_per_day']:,.0f}", False,
         "<b>Issues 2 &amp; 6.</b> Same population limit, and it counts only tickets created "
         "inside the range, so the first day of a filtered range under-counts what closed."),
        ("Backlog / open tickets", "01 · Overview", f"{head['resolutions_after_window']:,}", False,
         "<b>Issue 2.</b> Nothing in the extract is unresolved, so this counts work crossing "
         "midnight, not outstanding workload."),
        ("Net ticket change", "01 · Overview", f"{head['resolutions_after_window']:+,}", False,
         "<b>Issue 2.</b> Created minus resolved, so both sides sit on the same population."),
        ("Resolved-to-created ratio", "01 · Overview",
         f"{head['resolved_to_created_ratio']:.3f}×", False,
         "<b>Issue 2.</b> Same inputs: the pace is only as real as the population."),
        ("Median turnaround", "01 · Overview", f"{head['median_tat_minutes']:.0f} min", False,
         "<b>Issue 1.</b> A median of generated numbers is another generated number."),
        ("P90 turnaround", "01 · Overview", f"{head['p90_tat_minutes']:.0f} min", False,
         "<b>Issue 1.</b> And with no real tail, there is nothing for a percentile to expose."),
        ("Same-day resolution %", "01 · Overview", f"{head['pct_resolved_same_day']:.1f}%", False,
         "<b>Issue 1.</b> Once the offset is generated, crossing midnight only means arriving "
         "shortly before it."),
        ("Backlog by age", "01 · Overview", "&lt; 1h", False,
         "<b>Issue 1.</b> Nothing can age past the generated 45-minute ceiling, so every open "
         "ticket lands in one bucket."),
        ("Week-on-week demand", "01 · Overview", f"{head['wow_like_for_like_pct']:+.0f}%", False,
         "<b>Issues 2, 3 &amp; 5.</b> Built on the created counts, across a window that "
         "allows exactly one like-for-like comparison — and issue 6 is the very question it "
         "would be used to answer."),
        ("Volume + share by language queue", "02 · Drill Down",
         f"{df_all['queue'].nunique()} queues", False,
         "<b>Issue 2.</b> The queue parses cleanly — that is why it is used instead of "
         "<code>language_dwid</code> (issue 4) — but a share only cancels a filtered population "
         "if the filter is unrelated to queue, and nothing shows that it is."),
        ("Volume + share by request type", "02 · Drill Down",
         f"{df_all['request_type'].nunique()} types", False,
         "<b>Issues 2 &amp; 9.</b> Same population limit, and the Japanese and Korean queues "
         "carry no refund split, so the breakdown is not comparable across every queue."),
        ("Arrival rate by hour × weekday", "02 · Drill Down",
         f"peak {head['peak_hour_utc']:02d}:00 UTC", False,
         "<b>Issues 2 &amp; 10.</b> The creation timestamps are sound, but this is the shape of "
         "the tickets present: automated work need not arrive at the same hours. Days are UTC "
         "days."),
        ("Time to re-contact", "02 · Drill Down", f"median {recontact_median:.0f} h", False,
         "<b>Issue 2.</b> It never touches the resolution field, but a missing ticket "
         "between two present ones stretches the gap that gets reported."),
        ("Repeat-contact rate", "01 · Overview",
         f"{head['pct_bookings_with_repeat']:.1f}% of bookings", False,
         "<b>Issue 2.</b> A floor: a booking whose follow-up never reached the extract "
         "looks like one that never came back."),
        ("Tickets per booking", "02 · Drill Down",
         f"{len(df_all) / df_all['booking_id'].nunique():.2f}", False,
         "<b>Issue 2.</b> Rows over distinct bookings, both limited to what the extract "
         "contains."),
        ("Refund acceptance per booking", "02 · Drill Down", f"{acc_book:.2f}%", False,
         "<b>Issue 8.</b> The flags appear on non-refund tickets, and every positive one sits on "
         "a single-ticket booking, so the booking-level reading cannot be tested here."),
    ]

    def pill(ok: bool) -> str:
        label, cls = ("Reliable", "ok") if ok else ("Not Reliable", "bad")
        return f'<span class="pill pill-{cls}">{label}</span>' 

    rows_html = "".join(
        f"<tr><td><b>{name}</b></td><td>{where}</td><td class='val'>{value}</td>"
        f"<td>{pill(ok)}</td><td class='why'>{why}</td></tr>"
        for name, where, value, ok, why in kpi_rows)
    st.markdown(
        "<table class='kpi-table'><thead><tr><th>Metric</th><th>Where</th>"
        "<th>Value (full extract)</th><th>Verdict</th><th>Why</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>", unsafe_allow_html=True)

    n_ok = sum(1 for r in kpi_rows if r[3])
    st.caption(
        f"**{n_ok} of {len(kpi_rows)} metrics are currently reliable.** Two issues do the "
        "damage. The resolution timestamp is generated, which takes out everything about "
        "speed. And the population is unverifiable — every row is `processing_type = Manual` "
        "and every row carries a resolution — which takes out the counts, and with them the "
        "shares and rates built on top. Confirm the extract is complete and most of this "
        "table can be re-judged; fix the timestamp and the rest follows.")

# ============================================================== Insights
with tab_analysis:
    st.info("**The findings below describe the full 13-day extract and do not respond to the sidebar "
            "filters.** These are the standing findings I would take to the Helpdesk team.")

    rep_all = repeat_flag(df_all)

    c = st.columns(4)
    c[0].markdown(tile("Demand decline", f"{head['wow_like_for_like_pct']:+,.0f}", "%", kind="accent",
                       foot=head["wow_method"]), unsafe_allow_html=True)
    c[1].markdown(tile("Bookings writing in twice+", f"{head['pct_bookings_with_repeat']:,.1f}", "%",
                       foot=f"{100 * rep_all.mean():.1f}% of all tickets"), unsafe_allow_html=True)
    ins_gaps = df_all.loc[df_all["contact_seq"] > 1, "hours_since_prev_contact"].dropna()
    ins_1h = 100 * float((ins_gaps < 1).mean()) if len(ins_gaps) else 0.0
    c[2].markdown(tile("Re-contacts within 1h", f"{ins_1h:,.0f}", "%",
                       foot="Likely the same unresolved issue"), unsafe_allow_html=True)
    c[3].markdown(tile("Refund acceptance", f"{acc_book:,.2f}", "%", kind="warn",
                       foot=f"{int((rf_all.groupby('booking_id')['has_accepted_refund'].max() == True).sum())}"  # noqa: E712
                            f" of {rf_all['booking_id'].nunique():,} refund bookings"), unsafe_allow_html=True)


# ============================================================== 04 Metric dictionary
with tab_dict:
    st.markdown('<div class="sec">Metric dictionary</div>'
                '<div class="sec-sub">The seven metrics the dashboard was designed around. '
                'Definition and why it matters come from the brief; the last column is what '
                'this build actually does with them.</div>',
                unsafe_allow_html=True)

    metric_dict = pd.DataFrame([
        ("Tickets Created",
         "Count of tickets where Created Date falls within the selected period.",
         "Measures incoming demand / workload.",
         "Row count of the clean table, filtered on created_date."),
        ("Tickets Resolved",
         "Count of tickets where Resolved Date falls within the selected period.",
         "Measures completed workload.",
         "Row count filtered on resolved_date, so it is a throughput figure rather than a "
         "copy of intake."),
        ("Median TAT",
         "Median time between ticket creation and resolution, for resolved tickets only.",
         "Typical resolution time. More robust than the average when there are outliers.",
         "Median of turnaround_minutes_generated."),
        ("P90 TAT",
         "90th percentile resolution time for resolved tickets.",
         "Exposes the long tail of slow tickets.",
         "quantile(0.9, interpolation='nearest') — turnaround is whole minutes, so a "
         "linear-interpolated percentile would show a value that cannot occur."),
        ("Backlog / Open Tickets",
         "Tickets created but not resolved as of the selected date.",
         "How big the total pile of accumulated workload is. A level, not a flow — and the "
         "only one of the three that says how much work is actually sitting there.",
         "Cumulative created minus resolved, read at the end of the last day in range."),
        ("Net Ticket Change",
         "Tickets Created − Tickets Resolved.",
         "Whether workload is currently accumulating or declining, in absolute numbers. "
         "Flips sign on the exact day the trend turns, which a level only shows as a change "
         "in slope.",
         "Difference of the two counts above, over the selected range."),
        ("Resolved-to-Created Ratio",
         "Tickets Resolved / Tickets Created for the selected period.",
         "Whether we are processing roughly as much as is coming in. Scale-free, so it means "
         "the same thing for segments of very different sizes — the one to compare across "
         "queues or request types.",
         "Ratio of the two counts above. 1.00 means the team cleared exactly what arrived."),
    ], columns=["Metric", "Definition", "Why it matters", "How it is computed here"])

    st.dataframe(metric_dict, width="stretch", hide_index=True, column_config={
        "Definition": st.column_config.TextColumn(width="medium"),
        "Why it matters": st.column_config.TextColumn(width="medium"),
        "How it is computed here": st.column_config.TextColumn(width="large"),
    })
    st.caption("“Except on the final day of a range” — resolutions are counted on their own "
               "date, so on the last day *created* is complete while *resolved* is not. "
               f"{head['resolutions_after_window']} tickets in the full extract close after the "
               "final creation day.")

    st.markdown('<div class="sec">Dimensions and filters</div>'
                '<div class="sec-sub">The three filters the design calls for, and what each one '
                'is built from.</div>', unsafe_allow_html=True)
    dim_dict = pd.DataFrame([
        ("Date", "Primary filter. Ticket creation date, UTC.", "created_date",
         f"{CAL_DAYS} days selected of 13 in the extract"),
        ("Language", "The queue a ticket was handled in, parsed out of Ticket Type.",
         "queue", ", ".join(sorted(df_all["queue"].unique()))),
        ("Ticket Type", "Refund vs non-refund, also parsed out of Ticket Type.",
         "request_type", ", ".join(sorted(df_all["request_type"].unique()))),
    ], columns=["Filter", "Definition", "Column", "Values"])
    st.dataframe(dim_dict, width="stretch", hide_index=True, column_config={
        "Definition": st.column_config.TextColumn(width="large"),
        "Values": st.column_config.TextColumn(width="medium")})
    st.caption("Language deliberately does **not** come from `language_dwid`. That field "
               "contradicts the queue on 17.5% of tickets and defaults to English — see "
               "issue 5 on the Data & quality tab. Days are UTC days.")
