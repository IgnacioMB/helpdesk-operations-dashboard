"""Brand chrome: CSS + a code-drawn kiwi.com lockup.

NOTE: the wordmark below is drawn in SVG from scratch so the repo carries no
third-party asset. For the real submission, drop the official kiwi.com logo
into assets/ and point `logo_svg()` at it.
"""
from .theme import (CLOUD, CLOUD_DARK, INK, INK_MUTED, INK_SECONDARY,
                    KIWI_GREEN, KIWI_GREEN_DARK, KIWI_GREEN_WASH, STATUS)


def logo_svg(height: int = 34) -> str:
    return f"""
<svg viewBox="0 0 208 44" height="{height}" role="img" aria-label="kiwi.com"
     xmlns="http://www.w3.org/2000/svg">
  <rect x="0" y="0" width="44" height="44" rx="13" fill="{KIWI_GREEN}"/>
  <path d="M14 11 v22 M14 23 l9.5 -10.5 M14 23 l10.5 10.5" stroke="#fff"
        stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <circle cx="32.5" cy="14.5" r="2.9" fill="#fff"/>
  <text x="56" y="31" font-family="system-ui,-apple-system,'Segoe UI',sans-serif"
        font-size="26" font-weight="700" letter-spacing="-0.6" fill="{INK}">kiwi<tspan
        fill="{KIWI_GREEN}">.com</tspan></text>
</svg>"""


def css() -> str:
    return f"""
<style>
  .block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1400px; }}
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
