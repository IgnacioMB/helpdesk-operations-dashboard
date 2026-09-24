"""Chart builders. One form per analytical job; colour assigned last."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from .theme import (CLOUD_DARK, GRID, INK, INK_MUTED, INK_SECONDARY, KIWI_GREEN,
                    KIWI_GREEN_DARK, SEQ_GREEN, SERIES, SURFACE, layout)

# Colour follows the entity, never its rank: a filter that drops a series
# must not repaint the survivors.
QUEUE_COLOR = {"EN": SERIES[0], "International": SERIES[1], "Other": SERIES[2]}
CATEGORY_COLOR = {"Non-refund": SERIES[0], "Refund": SERIES[1], "Not specified": SERIES[2]}
FLOW_COLOR = {"Created": SERIES[0], "Resolved": SERIES[1]}
TAT_COLOR = {"Median": SERIES[0], "P90": SERIES[1]}


def _bar_ends(fig):
    """4px rounded data-ends, 2px surface gap between adjacent fills."""
    fig.update_traces(marker_cornerradius=4, selector=dict(type="bar"))
    fig.update_layout(bargap=0.28, bargroupgap=0.12)
    return fig


# ------------------------------------------------------------------ L0
def created_vs_resolved(daily: pd.DataFrame) -> go.Figure:
    # The two series very nearly coincide - that IS the finding - so Resolved is
    # drawn dashed on top of a solid Created, otherwise the upper line simply
    # hides the lower one and the chart reads as a single series.
    spec = [("Created", "tickets_created", "solid", 2.5),
            ("Resolved", "tickets_resolved", "dot", 2)]
    fig = go.Figure()
    for i, (name, col, dash, wide) in enumerate(spec):
        fig.add_trace(go.Scatter(
            x=daily["date"], y=daily[col], name=name, mode="lines+markers",
            line=dict(color=FLOW_COLOR[name], width=wide, dash=dash),
            marker=dict(size=8 if i == 0 else 6, color=FLOW_COLOR[name],
                        line=dict(width=2, color=SURFACE)),
            hovertemplate=f"<b>{name}</b>: %{{y:,}} tickets<br>%{{x|%a %d %b}}<extra></extra>",
        ))
        # direct label on the last point, nudged apart so the two never collide
        fig.add_annotation(x=daily["date"].iloc[-1], y=daily[col].iloc[-1], text=f" {name}",
                           showarrow=False, xanchor="left", yshift=11 if i == 0 else -11,
                           font=dict(color=FLOW_COLOR[name], size=12, family="system-ui"))
    lay = layout(height=330, margin=dict(l=8, r=78, t=28, b=8))
    lay["hovermode"] = "x unified"
    fig.update_layout(**lay)
    fig.update_yaxes(title="Tickets per day", rangemode="tozero")
    return fig


def net_change_and_ratio(daily: pd.DataFrame) -> go.Figure:
    """Net ticket change (bars) and the resolved-to-created ratio (line) together.

    Both answer "is work accumulating?" from the same two series, so they share a chart.
    Sign is carried by position against the zero line; colour only reinforces it.

    No day is singled out as incomplete. Each day's resolved count receives the previous
    night's carryover just as it loses its own to the next morning, so the last bar is as
    complete as any other. The window-level shortfall - tickets opened inside the range
    that close after it - belongs to the totals, not to one bar.
    """
    d = daily.reset_index(drop=True)
    colours = [SERIES[2] if v > 0 else KIWI_GREEN for v in d["net_change"]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["date"], y=d["net_change"], name="Net change (created − resolved)",
        marker=dict(color=colours),
        hovertemplate="<b>Net change</b>: %{y:+,} tickets<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=d["date"], y=d["resolved_to_created_ratio"], name="Resolved / created",
        yaxis="y2", mode="lines+markers",
        line=dict(color=SERIES[1], width=2.5),
        marker=dict(size=7, color=SERIES[1], line=dict(width=2, color=SURFACE)),
        hovertemplate="<b>%{y:.3f}×</b> resolved per created<extra></extra>"))

    lay = layout(height=300, margin=dict(l=8, r=64, t=28, b=8))
    lay["hovermode"] = "x unified"
    lay["yaxis2"] = dict(overlaying="y", side="right", showgrid=False, zeroline=False,
                         tickformat=".2f", ticksuffix="×",
                         tickfont=dict(color=SERIES[1], size=12),
                         title=dict(text="resolved / created",
                                    font=dict(color=SERIES[1], size=12)))
    fig.update_layout(**lay)
    fig.update_yaxes(title="Net change (tickets)", zeroline=True, zerolinecolor=INK_MUTED,
                     zerolinewidth=2)
    fig.add_hline(y=1, yref="y2", line=dict(color=INK_MUTED, width=2, dash="dot"))
    return _bar_ends(fig)


def demand_vs_prev_week(daily: pd.DataFrame) -> go.Figure:
    """Each day against the same weekday a week earlier, with the ratio on a second axis.

    The reference bar is deliberately recessive grey: it is context for the green bar,
    not a peer series. The ratio line carries the reading - above 1.0x demand grew.
    """
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["tickets_created"], name="This day",
        marker_color=KIWI_GREEN,
        hovertemplate="<b>This day</b>: %{y:,} tickets<extra></extra>"))
    fig.add_trace(go.Bar(
        x=daily["date"], y=daily["tickets_created_prev_week"],
        name="Same weekday, week before", marker_color=INK_MUTED,
        hovertemplate="<b>Week before</b>: %{y:,} tickets<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=daily["date"], y=daily["wow_ratio"], name="Change", yaxis="y2",
        mode="lines+markers", connectgaps=False,
        line=dict(color=SERIES[2], width=2.5),
        marker=dict(size=7, color=SERIES[2], line=dict(width=2, color=SURFACE)),
        hovertemplate="<b>%{y:.2f}×</b> vs the week before<extra></extra>"))

    lay = layout(height=340, margin=dict(l=8, r=64, t=28, b=8))
    lay["barmode"] = "group"
    lay["hovermode"] = "x unified"
    lay["yaxis2"] = dict(overlaying="y", side="right", rangemode="tozero",
                         showgrid=False, zeroline=False, ticksuffix="×",
                         tickfont=dict(color=SERIES[2], size=12),
                         title=dict(text="vs week before", font=dict(color=SERIES[2], size=12)))
    fig.update_layout(**lay)
    fig.update_yaxes(title="Tickets created", rangemode="tozero")
    # 1.0x = flat week on week; the line crossing it is the whole point of the chart
    fig.add_hline(y=1, yref="y2", line=dict(color=INK_MUTED, width=2, dash="dot"))
    return _bar_ends(fig)


def overnight_carry(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=daily["date"], y=daily["carried_overnight"],
        marker_color=KIWI_GREEN, name="Carried overnight",
        hovertemplate="<b>%{y:,}</b> tickets crossed midnight<br>%{x|%a %d %b}<extra></extra>",
    ))
    fig.update_layout(**layout(height=210, legend=False))
    fig.update_yaxes(title="Tickets crossing midnight", rangemode="tozero")
    return _bar_ends(fig)


# ------------------------------------------------------------------ L1
def daily_by_queue(df: pd.DataFrame) -> go.Figure:
    """Stacked daily volume, folded to three slots (the 4th+ would break CVD gates)."""
    d = df.copy()
    d["grp"] = np.where(d["queue"].isin(["EN", "International"]),
                        d["queue"], "Other")
    piv = (d.groupby(["created_date", "grp"]).size().unstack(fill_value=0)
             .reindex(columns=["EN", "International", "Other"], fill_value=0))
    fig = go.Figure()
    for col in piv.columns:
        fig.add_trace(go.Bar(
            x=piv.index, y=piv[col], name=col, marker_color=QUEUE_COLOR[col],
            marker_line=dict(width=2, color=SURFACE),  # 2px surface gap between segments
            hovertemplate=f"<b>{col}</b>: %{{y:,}}<extra></extra>",
        ))
    lay = layout(height=330)
    lay["barmode"] = "stack"
    lay["hovermode"] = "x unified"
    fig.update_layout(**lay)
    fig.update_yaxes(title="Tickets created", rangemode="tozero")
    return _bar_ends(fig)


def hbar(labels, values, value_fmt="{:,.0f}", title="", height=None,
         color=KIWI_GREEN, suffix="") -> go.Figure:
    """Single-series horizontal bar with direct value labels (no legend needed)."""
    h = height or max(200, 34 * len(labels) + 60)
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h", marker_color=color,
        text=[value_fmt.format(v) + suffix for v in values],
        textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY, size=12),
        hovertemplate="<b>%{y}</b><br>%{x:,.2f}" + suffix + "<extra></extra>",
    ))
    fig.update_layout(**layout(height=h, legend=False,
                               margin=dict(l=8, r=64, t=28, b=8)))
    fig.update_xaxes(title=title, showgrid=True, gridcolor=GRID, rangemode="tozero")
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _bar_ends(fig)


def daily_by_request_type(df: pd.DataFrame) -> go.Figure:
    """Stacked daily volume by request type - the companion to daily_by_queue."""
    order = [c for c in ["Non-refund", "Refund", "Not specified"]
             if c in set(df["request_type"])]
    piv = (df.groupby(["created_date", "request_type"]).size().unstack(fill_value=0)
             .reindex(columns=order, fill_value=0))
    fig = go.Figure()
    for col in piv.columns:
        fig.add_trace(go.Bar(
            x=piv.index, y=piv[col], name=col, marker_color=CATEGORY_COLOR[col],
            marker_line=dict(width=2, color=SURFACE),
            hovertemplate=f"<b>{col}</b>: %{{y:,}}<extra></extra>",
        ))
    lay = layout(height=330)
    lay["barmode"] = "stack"
    lay["hovermode"] = "x unified"
    fig.update_layout(**lay)
    fig.update_yaxes(title="Tickets created", rangemode="tozero")
    return _bar_ends(fig)


def tat_by_segment(seg: pd.DataFrame, label_col: str, overall: float) -> go.Figure:
    """Median TAT per segment against the global median - the point is that it is flat."""
    fig = go.Figure(go.Bar(
        x=seg["median_tat_minutes"], y=seg[label_col], orientation="h",
        marker_color=KIWI_GREEN,
        text=[f"{v:.1f} min" for v in seg["median_tat_minutes"]],
        textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY, size=12),
        hovertemplate="<b>%{y}</b><br>median %{x:.1f} min<extra></extra>",
    ))
    fig.add_vline(x=overall, line=dict(color=INK_MUTED, width=2, dash="dot"))
    fig.add_annotation(x=overall, y=1.11, yref="paper", text=f"All tickets {overall:.0f} min",
                       showarrow=False, xanchor="center", yanchor="bottom",
                       font=dict(color=INK_MUTED, size=11))
    h = max(240, 34 * len(seg) + 96)
    fig.update_layout(**layout(height=h, legend=False, margin=dict(l=8, r=86, t=48, b=8)))
    # headroom so the outside value labels never sit on the reference line
    fig.update_xaxes(title="Median turnaround (minutes)", showgrid=True, gridcolor=GRID,
                     range=[0, float(seg["median_tat_minutes"].max()) * 1.38])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _bar_ends(fig)


def tat_trend(daily: pd.DataFrame) -> go.Figure:
    """Median and P90 turnaround per day. Same treatment as created_vs_resolved:
    the two lines run close together, so P90 is dotted over a solid median."""
    spec = [("Median", "median_tat_minutes", "solid", 2.5),
            ("P90", "p90_tat_minutes", "dot", 2)]
    fig = go.Figure()
    for i, (name, col, dash, wide) in enumerate(spec):
        fig.add_trace(go.Scatter(
            x=daily["date"], y=daily[col], name=name, mode="lines+markers",
            line=dict(color=TAT_COLOR[name], width=wide, dash=dash),
            marker=dict(size=8 if i == 0 else 6, color=TAT_COLOR[name],
                        line=dict(width=2, color=SURFACE)),
            hovertemplate=f"<b>{name}</b>: %{{y:.0f}} min<br>%{{x|%a %d %b}}<extra></extra>",
        ))
        fig.add_annotation(x=daily["date"].iloc[-1], y=daily[col].iloc[-1], text=f" {name}",
                           showarrow=False, xanchor="left", yshift=11 if i == 0 else -11,
                           font=dict(color=TAT_COLOR[name], size=12, family="system-ui"))
    lay = layout(height=330, margin=dict(l=8, r=78, t=28, b=8))
    lay["hovermode"] = "x unified"
    fig.update_layout(**lay)
    fig.update_yaxes(title="Turnaround (minutes)", rangemode="tozero")
    return fig


def backlog_trend(daily: pd.DataFrame) -> go.Figure:
    """Tickets still open at 23:59. Same form as overnight_carry - on this extract the
    two are identical, because nothing takes longer than 45 minutes to close."""
    fig = go.Figure(go.Bar(
        x=daily["date"], y=daily["open_end_of_day"],
        marker_color=KIWI_GREEN, name="Open at end of day",
        hovertemplate="<b>%{y:,}</b> tickets open at 23:59<br>%{x|%a %d %b}<extra></extra>",
    ))
    fig.update_layout(**layout(height=330, legend=False))
    fig.update_yaxes(title="Tickets open at end of day", rangemode="tozero")
    return _bar_ends(fig)


def segment_flow(seg: pd.DataFrame, label_col: str) -> go.Figure:
    """Created vs resolved per segment. Tickets only - turnaround is minutes and belongs
    on its own axis, so it sits in the companion tat_by_segment chart instead."""
    fig = go.Figure()
    for name, col in [("Created", "tickets"), ("Resolved", "tickets_resolved")]:
        fig.add_trace(go.Bar(
            x=seg[col], y=seg[label_col], orientation="h", name=name,
            marker_color=FLOW_COLOR[name],
            text=[f"{v:,.0f}" for v in seg[col]],
            textposition="outside", cliponaxis=False,
            textfont=dict(color=INK_SECONDARY, size=11),
            hovertemplate=f"<b>%{{y}}</b><br>{name}: %{{x:,}} tickets<extra></extra>",
        ))
    h = max(240, 46 * len(seg) + 96)
    lay = layout(height=h, legend=True, margin=dict(l=8, r=86, t=48, b=8))
    lay["barmode"] = "group"
    fig.update_layout(**lay)
    fig.update_xaxes(title="Tickets", showgrid=True, gridcolor=GRID,
                     range=[0, float(seg[["tickets", "tickets_resolved"]].max().max()) * 1.22])
    fig.update_yaxes(autorange="reversed", showgrid=False)
    return _bar_ends(fig)


# ------------------------------------------------------------------ L2
def volume_by_weekday(per_dow: pd.Series) -> go.Figure:
    """Average tickets per weekday. Pre-divided by how often each weekday occurs, so a
    13-day window (one Saturday, two of everything else) does not read as a Saturday dip."""
    fig = go.Figure(go.Bar(
        x=per_dow.index, y=per_dow.values, marker_color=KIWI_GREEN,
        text=[f"{v:,.0f}" for v in per_dow.values],
        textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_SECONDARY, size=12),
        hovertemplate="<b>%{x}</b>: %{y:,.0f} tickets/day<extra></extra>",
    ))
    fig.update_layout(**layout(height=300, legend=False))
    fig.update_yaxes(title="Tickets per day", rangemode="tozero")
    return _bar_ends(fig)


def arrival_heatmap(hm: pd.DataFrame) -> go.Figure:
    """Sequential encoding: one hue, light -> dark."""
    z = hm.drop(columns=["created_weekday"]).values
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"{int(c):02d}" for c in hm.columns[1:]], y=hm["created_weekday"],
        colorscale=[[i / (len(SEQ_GREEN) - 1), c] for i, c in enumerate(SEQ_GREEN)],
        xgap=2, ygap=2,  # 2px surface gap between cells
        hovertemplate="<b>%{y} %{x}:00 UTC</b><br>%{z:.0f} tickets/hour<extra></extra>",
        colorbar=dict(title=dict(text="Tickets<br>per hour", font=dict(size=11, color=INK_MUTED)),
                      thickness=12, len=0.82, outlinewidth=0,
                      tickfont=dict(size=11, color=INK_MUTED)),
    ))
    fig.update_layout(**layout(height=330, legend=False,
                               margin=dict(l=8, r=8, t=28, b=8)))
    fig.update_xaxes(title="Hour of day (UTC)", showgrid=False)
    fig.update_yaxes(showgrid=False, autorange="reversed")
    return fig


def tat_distribution(dist: pd.DataFrame) -> go.Figure:
    """The smoking gun: observed TAT against the flat line a synthetic draw implies."""
    # The support of Uniform{15..45} is 31 values, ALWAYS - not the number of
    # values this subset happens to contain. Dividing by len(dist) put the line
    # 2.2x too high on small filtered subsets, flattening the very anomaly the
    # chart exists to show.
    dist = (dist.set_index("turnaround_minutes_generated")["tickets"]
            .reindex(range(15, 46), fill_value=0).rename_axis("turnaround_minutes_generated").reset_index())
    expected = dist["tickets"].sum() / 31
    fig = go.Figure(go.Bar(
        x=dist["turnaround_minutes_generated"], y=dist["tickets"], marker_color=KIWI_GREEN,
        name="Observed tickets",
        hovertemplate="<b>%{x} min</b>: %{y:,} tickets<extra></extra>",
    ))
    fig.add_hline(y=expected, line=dict(color=SERIES[2], width=2, dash="dash"))
    fig.add_annotation(x=dist["turnaround_minutes_generated"].max(), y=expected, text=" Uniform expectation",
                       showarrow=False, xanchor="right", yanchor="bottom",
                       font=dict(color=SERIES[2], size=12))
    fig.update_layout(**layout(height=300, legend=False, margin=dict(l=8, r=8, t=34, b=8)))
    fig.update_xaxes(title="Turnaround time (minutes)", showgrid=False, dtick=5)
    fig.update_yaxes(title="Tickets", rangemode="tozero")
    return _bar_ends(fig)
