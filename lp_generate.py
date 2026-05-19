"""
LP recommendations page builder.
5+5 LP cards for a VC fund, with logo prominently centered.
"""

from dotenv import load_dotenv
load_dotenv()

from lp_research import research_lp


def _fmt_invested(v) -> str:
    if not v: return "—"
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    if n >= 1e9: return f"${n/1e9:.1f}B invested"
    if n >= 1e6: return f"${n/1e6:.0f}M invested"
    return "—"


def _letters(name: str) -> str:
    w = name.split()
    return (w[0][0] + (w[1][0] if len(w) > 1 else (w[0][1] if len(w[0]) > 1 else "X"))).upper()


def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


AVATAR_BG = ["#eef2ff","#f0fdf4","#fff7ed","#fdf2f8","#eff6ff","#f0fdfa","#fefce8","#fdf4ff","#fff1f2","#f0f9ff"]
AVATAR_FG = ["#4f46e5","#16a34a","#ea580c","#db2777","#2563eb","#0d9488","#ca8a04","#9333ea","#e11d48","#0284c7"]


def _lp_logo(lp: dict, idx: int) -> str:
    img  = lp.get("image", "")
    dom  = lp.get("website_domain", "")
    src  = (f"https://{img}" if img and not img.startswith("http") else img) if img else \
           (f"https://logo.clearbit.com/{dom}" if dom else "")
    bg   = AVATAR_BG[idx % len(AVATAR_BG)]
    fg   = AVATAR_FG[idx % len(AVATAR_FG)]
    ini  = _letters(lp["name"])
    img_tag = (
        f'<img src="{src}" class="lp-img" '
        f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
        f'<span class="lp-ini" style="display:none;color:{fg};">{ini}</span>'
    ) if src else f'<span class="lp-ini" style="color:{fg};">{ini}</span>'
    return f'<div class="lp-logo" style="background:{bg};">{img_tag}</div>'


def _lp_card(lp: dict, idx: int, accent: str) -> str:
    loc  = ", ".join(filter(None, [lp.get("hq_city"), lp.get("hq_country")]))
    aum  = _fmt_invested(lp.get("total_invested"))
    types = lp.get("types") or lp.get("type") or []
    if isinstance(types, list):
        # Pick the most descriptive type label, prefer family_office/private_equity over generic investment_fund
        priority = ["family_office", "private_equity", "investment_fund"]
        chosen = next((t for t in priority if t in types), types[0] if types else "lp")
        tp = chosen.replace("_", " ").title()
    else:
        tp = str(types).replace("_", " ").title() or "LP"
    why        = lp.get("rationale", "")
    dr_url     = lp.get("dealroom_url") or f"https://app.dealroom.co/search?q={lp['name']}"
    acc_light  = _hex_rgba(accent, 0.07)
    acc_border = _hex_rgba(accent, 0.22)
    return f"""<a class="lp-card" href="{dr_url}" target="_blank" rel="noopener">
        <div class="lp-card-top">
          {_lp_logo(lp, idx)}
          <div class="lp-body">
            <div class="lp-name">{lp["name"]}</div>
            <div class="lp-type-row">
              <span class="lp-type-badge" style="background:{acc_light};border-color:{acc_border};color:{accent};">{tp}</span>
              <span class="lp-loc">
                <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
                {loc or "—"}
              </span>
              <span class="lp-aum">
                <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
                {aum}
              </span>
            </div>
          </div>
        </div>
        {f'<div class="lp-why">{why}</div>' if why else ''}
      </a>"""


def build_lp_page(profile: dict, out_path: str, meeting_url: str = "") -> None:
    accent     = profile["accent_color"]
    acc_light  = _hex_rgba(accent, 0.08)
    acc_border = _hex_rgba(accent, 0.25)
    vc_name    = profile["vc_name"]
    tagline    = profile["tagline"]
    intro      = profile["intro"]
    logo_url   = profile.get("logo_url", "")
    domain     = profile.get("domain", "")
    lps        = profile.get("lps", [])

    # VC hero logo
    src = logo_url or (f"https://logo.clearbit.com/{domain}" if domain else "")
    ini = _letters(vc_name)
    if src:
        logo_html = (
            f'<img src="{src}" alt="{vc_name}" class="hero-logo-img" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
            f'<div class="hero-logo-ini" style="color:{accent};display:none;">{ini}</div>'
        )
    else:
        logo_html = f'<div class="hero-logo-ini" style="color:{accent};">{ini}</div>'

    left  = lps[:5]
    right = lps[5:10]
    left_cards  = "\n".join(_lp_card(lp, i, accent)       for i, lp in enumerate(left))
    right_cards = "\n".join(_lp_card(lp, i + 5, accent)   for i, lp in enumerate(right))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{vc_name} · LP Recommendations · Dealroom</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #f5f6fa; --white: #fff; --border: #e5e7eb;
      --text: #111827; --muted: #6b7280; --muted2: #9ca3af;
      --accent: {accent};
    }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

    /* NAV */
    .nav {{ background: var(--white); border-bottom: 1px solid var(--border); height: 52px;
            display: flex; align-items: center; justify-content: space-between;
            padding: 0 32px; position: sticky; top: 0; z-index: 100; }}
    .nav-logo {{ display: flex; align-items: center; gap: 8px; text-decoration: none; }}
    .nav-logo-mark {{ height: 28px; display: flex; align-items: center; }}
    .nav-logo-mark img {{ height: 28px; width: auto; display: block; }}
    .nav-logo-text {{ font-size: 14px; font-weight: 700; color: #1a1f36; }}
    .nav-badge {{ background: {acc_light}; border: 1px solid {acc_border};
                  color: {accent}; font-size: 11px; font-weight: 600;
                  padding: 4px 12px; border-radius: 20px; }}

    /* PAGE */
    .page {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 72px; }}

    /* HERO — big centered logo */
    .hero {{ background: var(--white); border: 1px solid var(--border); border-radius: 16px;
             padding: 48px 32px 32px; text-align: center; margin-bottom: 24px;
             box-shadow: 0 1px 6px rgba(0,0,0,.05); }}
    .hero-logo-wrap {{ width: 96px; height: 96px; border-radius: 22px; background: var(--white);
                       border: 1px solid var(--border); box-shadow: 0 6px 24px rgba(0,0,0,.10);
                       display: flex; align-items: center; justify-content: center;
                       margin: 0 auto 20px; overflow: hidden; }}
    .hero-logo-img {{ width: 72px; height: 72px; object-fit: contain; }}
    .hero-logo-ini {{ font-size: 32px; font-weight: 800; width: 100%; height: 100%;
                      display: flex; align-items: center; justify-content: center; }}
    .hero-name {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
    .hero-tagline {{ font-size: 13px; color: var(--muted); line-height: 1.6; max-width: 520px;
                     margin: 0 auto 14px; }}
    .hero-intro {{ font-size: 13px; color: var(--muted); line-height: 1.7; max-width: 560px;
                   margin: 0 auto; padding: 14px 20px; background: {acc_light};
                   border: 1px solid {acc_border}; border-radius: 10px; }}
    .hero-book {{ margin: 20px auto 0; text-align: center; }}
    .hero-book button {{ background: #3662e3; color: #fff; border: none; border-radius: 10px;
                         padding: 11px 24px; font-size: 13px; font-weight: 600;
                         font-family: inherit; cursor: pointer; white-space: nowrap;
                         transition: opacity .15s; letter-spacing: .1px; }}
    .hero-book button:hover {{ opacity: .85; }}

    /* SECTION HEADER */
    .section-head {{ display: flex; align-items: baseline; justify-content: space-between;
                     margin-bottom: 12px; }}
    .section-title {{ font-size: 15px; font-weight: 600; }}
    .section-sub {{ font-size: 11px; color: var(--muted2); }}

    /* 5+5 GRID */
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
    .col {{ display: flex; flex-direction: column; gap: 8px; }}

    /* LP CARD */
    .lp-card {{ background: var(--white); border: 1px solid var(--border); border-radius: 12px;
                padding: 14px 16px; transition: box-shadow .15s, border-color .15s, transform .15s;
                text-decoration: none; color: inherit; cursor: pointer; display: block; }}
    .lp-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.08); border-color: {acc_border}; transform: translateY(-1px); }}
    .lp-card-top {{ display: flex; align-items: flex-start; gap: 12px; }}
    .lp-logo {{ width: 40px; height: 40px; border-radius: 9px; flex-shrink: 0;
                display: flex; align-items: center; justify-content: center;
                overflow: hidden; border: 1px solid var(--border); }}
    .lp-img {{ width: 28px; height: 28px; object-fit: contain; }}
    .lp-ini {{ font-size: 11px; font-weight: 700; width: 100%; height: 100%;
               display: flex; align-items: center; justify-content: center; }}
    .lp-body {{ flex: 1; min-width: 0; }}
    .lp-name {{ font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 5px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .lp-type-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }}
    .lp-type-badge {{ border: 1px solid; border-radius: 5px; padding: 2px 8px;
                      font-size: 10px; font-weight: 600; white-space: nowrap; }}
    .lp-loc, .lp-aum {{ display: flex; align-items: center; gap: 3px;
                         font-size: 11px; color: var(--muted); white-space: nowrap; }}
    .lp-loc svg, .lp-aum svg {{ color: var(--muted2); flex-shrink: 0; }}
    .lp-why {{ font-size: 11px; color: var(--muted); line-height: 1.55; margin-top: 8px;
               padding-top: 8px; border-top: 1px solid var(--border); }}

    @media (max-width: 640px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

<nav class="nav">
  <a class="nav-logo" href="#">
    <div class="nav-logo-mark">
      <svg width="120" height="30" viewBox="0 0 120 30" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="120" height="30" rx="5" fill="#1a1f36"/>
        <!-- bar-chart D icon -->
        <rect x="8" y="18" width="3" height="5" fill="white"/>
        <rect x="13" y="13" width="3" height="10" fill="white"/>
        <rect x="18" y="9" width="3" height="14" fill="white"/>
        <path d="M8 7h6a7 7 0 010 14H8V7z" fill="none" stroke="white" stroke-width="2"/>
        <!-- wordmark -->
        <text x="30" y="20" font-family="system-ui,-apple-system,sans-serif" font-size="11" font-weight="700" fill="white">dealroom.co</text>
      </svg>
    </div>
  </a>
  <span class="nav-badge">LP Recommendations</span>
</nav>

<div class="page">

  <!-- Hero -->
  <div class="hero">
    <div class="hero-logo-wrap">{logo_html}</div>
    <div class="hero-name">{vc_name}</div>
    <div style="margin-top:18px;"><a href="{meeting_url or 'https://app.dealroom.co/'}" target="_blank" rel="noopener" style="display:inline-block;background:#3662e3;color:#fff;text-decoration:none;font-size:13px;font-weight:600;padding:11px 24px;border-radius:10px;font-family:inherit;">Book a meeting to activate access</a></div>
  </div>

  <!-- 5 + 5 LP cards -->
  <div class="section-head">
    <span class="section-title">Recommended Limited Partners</span>
    <span class="section-sub">Selected by Dealroom · Matched to {vc_name}'s profile</span>
  </div>

  <div class="grid">
    <div class="col">{left_cards}</div>
    <div class="col">{right_cards}</div>
  </div>

</div>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ {out_path} — {len(lps)} LPs")
