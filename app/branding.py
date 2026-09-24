"""Brand chrome: CSS + the kiwi.com lockup.

The logo in assets/ is the official mark from images.kiwi.com, used unmodified.
"""
import functools
import pathlib
import re

from .theme import (CLOUD, CLOUD_DARK, INK, INK_MUTED, INK_SECONDARY,
                    KIWI_GREEN, KIWI_GREEN_DARK, KIWI_GREEN_WASH, STATUS)

LOGO = pathlib.Path(__file__).resolve().parent.parent / "assets" / "kiwicom-logo.svg"
# The source file ships width/height that do not match its own viewBox, so the site
# letterboxes it. Scale from the viewBox instead, or the mark comes out squashed.
_LOGO_ASPECT = 242.989 / 120


@functools.lru_cache(maxsize=8)
def logo_svg(height: int = 34) -> str:
    """The official mark, scaled to `height` with its true aspect ratio preserved."""
    markup = LOGO.read_text(encoding="utf-8")
    width = round(height * _LOGO_ASPECT)
    markup = re.sub(r'\s(width|height)="[^"]*"', "", markup, count=2)
    return markup.replace(
        "<svg ",
        f'<svg width="{width}" height="{height}" role="img" aria-label="kiwi.com" ',
        1)


def css() -> str:
    return f"""
<style>
  /* Streamlit Cloud overlays a toolbar (Share / edit / Deploy) on top of the page and
     reserves no space for it, so 1.4rem let the header card slide underneath it. Zero the
     header's own height and reserve the space here, which behaves the same locally and
     when deployed. */
  [data-testid="stHeader"] {{ background: transparent; height: 0; }}
  .block-container {{ padding-top: 4.2rem; padding-bottom: 3rem; max-width: 1400px; }}
  #MainMenu, footer {{ visibility: hidden; }}

  .kiwi-header {{
    display: flex; align-items: center; justify-content: space-between; gap: 20px;
    padding: 18px 24px; margin-bottom: 18px; flex-wrap: wrap;
    background: linear-gradient(105deg, {KIWI_GREEN_WASH} 0%, #FFFFFF 62%);
    border: 1px solid {CLOUD_DARK}; border-left: 5px solid {KIWI_GREEN};
    border-radius: 14px;
  }}
  .kiwi-header .title {{ font-size: 1.32rem; font-weight: 700; color: {INK};
                          line-height: 1.25; margin: 0; }}
  .kiwi-header .sub {{ font-size: .86rem; color: {INK_SECONDARY}; margin-top: 3px; }}
  .kiwi-header .meta {{ font-size: .78rem; color: {INK_MUTED}; text-align: right; line-height: 1.7; }}

  /* KPI tiles -------------------------------------------------------- */
  .tile {{
    background: #fff; border: 1px solid {CLOUD_DARK}; border-radius: 12px;
    padding: 14px 16px; height: 100%;
    box-shadow: 0 1px 2px rgba(37,42,49,.05);
  }}
  .tile .label {{ font-size: .73rem; font-weight: 600; letter-spacing: .04em;
                  text-transform: uppercase; color: {INK_MUTED}; display: block; }}
  .tile .value {{ font-size: 1.85rem; font-weight: 700; color: {INK};
                  line-height: 1.15; margin-top: 6px; font-variant-numeric: tabular-nums; }}
  .tile .value .unit {{ font-size: .92rem; font-weight: 600; color: {INK_SECONDARY};
                        margin-left: 3px; }}
  .tile .foot {{ font-size: .76rem; color: {INK_SECONDARY}; margin-top: 5px; line-height: 1.35; }}
  .tile.accent {{ border-left: 4px solid {KIWI_GREEN}; }}
  .tile.warn   {{ border-left: 4px solid {STATUS['low']}; background: #FFFCF3; }}

  .caution {{ display:inline-block; font-size:.66rem; font-weight:700; letter-spacing:.04em;
              padding:1px 6px; border-radius:5px; background:#FFF3D6; color:#8A6400;
              border:1px solid #F3DFAE; margin-left:6px; vertical-align:middle; }}

  /* severity chips (icon + word: never colour alone) ------------------ */
  .chip {{ display:inline-block; font-size:.7rem; font-weight:700; letter-spacing:.03em;
           padding:2px 8px; border-radius:20px; border:1px solid; }}
  .chip.high {{ color:{STATUS['high']}; border-color:{STATUS['high']}33; background:#FCEDED; }}
  .chip.medium {{ color:{STATUS['medium']}; border-color:{STATUS['medium']}33; background:#FDF0EB; }}
  .chip.low {{ color:#8A6400; border-color:#F3DFAE; background:#FFFCF3; }}
  .chip.pass {{ color:#0A7D0A; border-color:#BFE6BF; background:#F1FAF1; }}

  /* callouts --------------------------------------------------------- */
  .callout {{ border:1px solid {CLOUD_DARK}; border-left:4px solid {KIWI_GREEN};
              background:#fff; border-radius:10px; padding:14px 18px; margin:10px 0 16px; }}
  .callout.alert {{ border-left-color:{STATUS['high']}; background:#FEF7F7; }}
  .callout h4 {{ margin:0 0 6px; font-size:.95rem; color:{INK}; font-weight:700; }}
  .callout p  {{ margin:0; font-size:.87rem; color:{INK_SECONDARY}; line-height:1.55; }}
  .callout ul {{ margin:6px 0 0 18px; font-size:.87rem; color:{INK_SECONDARY}; line-height:1.6; }}

  .sec {{ font-size:1.02rem; font-weight:700; color:{INK}; margin:22px 0 2px; }}
  .sec-sub {{ font-size:.82rem; color:{INK_MUTED}; margin:0 0 10px; }}

  .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom:1px solid {CLOUD_DARK}; }}
  .stTabs [data-baseweb="tab"] {{
     height: 42px; padding: 0 16px; background: transparent;
     font-size: .88rem; font-weight: 600; color: {INK_SECONDARY}; }}
  .stTabs [aria-selected="true"] {{ color: {KIWI_GREEN_DARK} !important;
     border-bottom: 3px solid {KIWI_GREEN} !important; }}

  section[data-testid="stSidebar"] {{ background: {CLOUD}; border-right:1px solid {CLOUD_DARK}; }}
  section[data-testid="stSidebar"] .sb-title {{ font-size:.73rem; font-weight:700;
     letter-spacing:.05em; text-transform:uppercase; color:{INK_MUTED}; margin:14px 0 2px; }}
</style>"""


def tile(label: str, value: str, unit: str = "", foot: str = "",
         kind: str = "", caution: str = "") -> str:
    badge = f'<span class="caution">{caution}</span>' if caution else ""
    u = f'<span class="unit">{unit}</span>' if unit else ""
    return (f'<div class="tile {kind}"><span class="label">{label}{badge}</span>'
            f'<div class="value">{value}{u}</div>'
            f'<div class="foot">{foot}</div></div>')
