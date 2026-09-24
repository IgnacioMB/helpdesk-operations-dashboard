"""Kiwi.com-flavoured chart theme.

Series colours are NOT picked by eye: the three categorical slots were run
through a port of the data-viz palette validator (OKLab Delta E + Vienot CVD
simulation + WCAG contrast) against the white chart surface and clear every
gate - worst normal-vision Delta E 19.7 (floor 15), worst CVD Delta E 10.7
(target 8), minimum contrast 3.10:1.
"""

# --- brand chrome (Orbit / Kiwi.com) ---------------------------------------
KIWI_GREEN = "#00A58E"
KIWI_GREEN_DARK = "#00756A"
KIWI_GREEN_WASH = "#E7F8F6"
INK = "#252A31"
INK_SECONDARY = "#5F6C75"
INK_MUTED = "#8C9AA5"
CLOUD = "#F5F7F9"
CLOUD_DARK = "#E8EDF1"
SURFACE = "#FFFFFF"
GRID = "#E8EDF1"

# --- validated categorical slots (fixed order, never cycled) ---------------
SERIES = ["#00A58E", "#0172CB", "#E8552A"]
SERIES_NAMES = ["Kiwi green", "Orbit blue", "Deep orange"]

# --- sequential ramp: one hue, light -> dark (heatmaps only) ---------------
SEQ_GREEN = [
    "#E7F8F6", "#C5EEE9", "#9BE2DA", "#6BD3C8",
    "#33BFB0", "#00A58E", "#008C7B", "#00756A", "#005C54",
]

# --- status: always shipped with an icon + text label, never colour alone --
STATUS = {
    "high": "#D03B3B",
    "medium": "#E8552A",
    "low": "#FAB219",
    "pass": "#0CA30C",
}
STATUS_LABEL = {"high": "HIGH", "medium": "MEDIUM", "low": "LOW", "pass": "PASS"}

FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif'


def layout(height=320, legend=True, margin=None):
    """Shared plotly layout: recessive grid, no chart junk, brand ink."""
    return dict(
        height=height,
        template="plotly_white",
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        font=dict(family=FONT, size=13, color=INK_SECONDARY),
        margin=margin or dict(l=8, r=8, t=28, b=8),
        xaxis=dict(showgrid=False, linecolor=CLOUD_DARK, tickfont=dict(color=INK_MUTED, size=12),
                   title_font=dict(color=INK_MUTED, size=12)),
        yaxis=dict(gridcolor=GRID, zerolinecolor=CLOUD_DARK, linecolor="rgba(0,0,0,0)",
                   tickfont=dict(color=INK_MUTED, size=12), title_font=dict(color=INK_MUTED, size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(color=INK_SECONDARY, size=12), title_text="") if legend else dict(),
        showlegend=legend,
        hoverlabel=dict(bgcolor=SURFACE, bordercolor=CLOUD_DARK,
                        font=dict(family=FONT, color=INK, size=12)),
        separators=".,",
    )
