"""
Bespoke VC one-pager generator.
Shows 10 companies (5+5) not in the investor's portfolio, matched to their thesis.

Usage:
    python generate.py --investor "Eurazeo"
    python generate.py --url "https://www.lightrock.com/news/..." --out lightrock.html
"""

import argparse, sys
from dotenv import load_dotenv
load_dotenv()

from research import research_investor
from query_engine import DealroomClient, resolve_tag_ids, resolve_location_ids


# ── Fetch ──────────────────────────────────────────────────────────────────────

# Maps investor's preferred round → (target company fmin, fmax, sort)
# Logic: show companies one stage behind (ready to raise the investor's round)
PIPELINE_STAGE = {
    "PRE-SEED":         (0,           500_000,     "-total_funding"),
    "SEED":             (0,           2_000_000,   "-total_funding"),
    "ANGEL":            (0,           2_000_000,   "-total_funding"),
    "EARLY VC":         (500_000,     8_000_000,   "-total_funding"),
    "SERIES A":         (1_000_000,   12_000_000,  "-total_funding"),
    "SERIES B":         (5_000_000,   60_000_000,  "-total_funding"),
    "SERIES C":         (20_000_000,  200_000_000, "-total_funding"),
    "SERIES D":         (60_000_000,  400_000_000, "-total_funding"),
    "LATE VC":          (50_000_000,  500_000_000, "-total_funding"),
    "GROWTH EQUITY VC": (50_000_000,  400_000_000, "-total_funding"),
    "BUYOUT":           (100_000_000, 2_000_000_000, "-total_funding"),
}


def fetch_companies(profile: dict, limit: int = 10) -> list:
    client     = DealroomClient()
    tag_ids    = resolve_tag_ids(client, profile["dealroom_terms"])
    portfolio  = profile.get("portfolio_ids", set())

    if not tag_ids:
        all_terms = [t for lst in profile["dealroom_terms"].values() for t in lst]
        tag_ids   = resolve_tag_ids(client, {"sector": all_terms[:6]})
    if not tag_ids:
        return []

    tag_str         = "|".join(str(i) for i in tag_ids)
    focus_countries = profile.get("focus_countries", [])
    preferred_round = (profile.get("preferred_round") or "").upper()

    # Stage-down rule: target companies one stage behind the investor's round
    if preferred_round in PIPELINE_STAGE:
        fmin, fmax, sort_field = PIPELINE_STAGE[preferred_round]
    else:
        fmin       = profile.get("funding_min", 1_000_000)
        fmax       = profile.get("funding_max", 50_000_000)
        sort_field = "-total_funding"

    # Rule 2: strict geo — only resolve and filter if investor has a clear focus
    loc_ids = resolve_location_ids(client, focus_countries) if focus_countries else []

    # Build filter parts
    parts = [f"tag_id[in_any]:{tag_str}"]
    if fmin > 0:
        parts.append(f"total_funding[gte]:{fmin}")
    parts.append(f"total_funding[lte]:{fmax}")
    if loc_ids:
        parts.append(f"location[in_any]:{'|'.join(str(i) for i in loc_ids)}")

    filter_expr = f"and({','.join(parts)})" if len(parts) > 1 else parts[0]

    r = client.get("/entities", params={
        "filter": filter_expr,
        "sort":   sort_field,
        "limit":  limit + len(portfolio) + 40,
    })
    results = r.json().get("data", [])

    # Rule 2 fallback: if geo filter is too restrictive, widen to all focus countries
    # but do NOT drop geo entirely — keep at least the top country
    if loc_ids and len(results) < limit + 5 and len(loc_ids) > 1:
        parts_wide = [p for p in parts if not p.startswith("location")]
        parts_wide.append(f"location[in_any]:{loc_ids[0]}")  # top country only
        r = client.get("/entities", params={
            "filter": f"and({','.join(parts_wide)})",
            "sort":   sort_field,
            "limit":  limit + len(portfolio) + 40,
        })
        results = r.json().get("data", [])

    # Rule 3: investor not US-based → skip heavily-funded US companies (>$100M)
    investor_in_us = "United States" in focus_countries[:2]

    companies = []
    for c in results:
        if c["id"] in portfolio:
            continue
        try:
            total_funding = float((c.get("funding_summary") or {}).get("total_funding") or 0)
        except (TypeError, ValueError):
            total_funding = 0
        if (not investor_in_us
                and (c.get("hq_country") or "") == "United States"
                and total_funding > 100_000_000):
            continue
        funding  = (c.get("funding_summary") or {})
        val_data = (c.get("latest_valuation") or {})
        founders = c.get("founders") or []
        ceo      = founders[0]["name"] if founders else "—"
        sector_tags = [t["name"] for t in (c.get("tags") or [])
                       if t.get("type") in ("sector", "industry", "sub_industry")][:2]
        companies.append({
            "id":            c["id"],
            "name":          c.get("name", ""),
            "tagline":       (c.get("tagline") or "")[:70],
            "hq_country":    c.get("hq_country", ""),
            "hq_city":       c.get("hq_city", ""),
            "total_funding": funding.get("total_funding"),
            "valuation":     val_data.get("value"),
            "launch_year":   c.get("launch_year"),
            "website_domain": c.get("website_domain", ""),
            "image":         c.get("image", ""),
            "sector_tags":   sector_tags,
            "ceo":           ceo,
            "dealroom_url":  c.get("dealroom_url") or f"https://app.dealroom.co/search?q={c.get('name', '')}",
        })
        if len(companies) >= limit:
            break

    return companies


# ── HTML helpers ───────────────────────────────────────────────────────────────

def _fmt(v) -> str:
    if not v: return "—"
    n = float(v)
    if n >= 1e9: return f"${n/1e9:.1f}B"
    if n >= 1e6: return f"${n/1e6:.0f}M"
    return f"${n/1e3:.0f}K"

def _letters(name: str) -> str:
    w = name.split()
    return (w[0][0] + (w[1][0] if len(w) > 1 else (w[0][1] if len(w[0]) > 1 else "X"))).upper()

def _hex_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

AVATAR_BG = ["#eef2ff","#f0fdf4","#fff7ed","#fdf2f8","#eff6ff","#f0fdfa","#fefce8","#fdf4ff","#fff1f2","#f0f9ff"]
AVATAR_FG = ["#4f46e5","#16a34a","#ea580c","#db2777","#2563eb","#0d9488","#ca8a04","#9333ea","#e11d48","#0284c7"]

def _co_logo(co: dict, idx: int, size: int = 40) -> str:
    domain = co.get("website_domain", "")
    dr_img = co.get("image", "")
    src = (f"https://{dr_img}" if dr_img and not dr_img.startswith("http") else dr_img) if dr_img else \
          (f"https://logo.clearbit.com/{domain}" if domain else "")
    bg  = AVATAR_BG[idx % len(AVATAR_BG)]
    fg  = AVATAR_FG[idx % len(AVATAR_FG)]
    ini = _letters(co["name"])
    img_tag = (
        f'<img src="{src}" class="co-img" '
        f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
        f'<span class="co-ini" style="display:none;color:{fg};">{ini}</span>'
    ) if src else f'<span class="co-ini" style="color:{fg};">{ini}</span>'
    return f'<div class="co-logo" style="background:{bg};width:{size}px;height:{size}px;">{img_tag}</div>'


def _co_card(co: dict, idx: int) -> str:
    funding = _fmt(co["total_funding"])
    sector  = " · ".join(co["sector_tags"]) if co["sector_tags"] else (co.get("tagline") or "")[:40]
    loc     = ", ".join(filter(None, [co.get("hq_city"), co.get("hq_country")]))
    url     = co.get("dealroom_url", "")
    return f"""<a class="co-card" href="{url}" target="_blank" rel="noopener">
        {_co_logo(co, idx)}
        <div class="co-body">
          <div class="co-name">{co["name"]}</div>
          <div class="co-sector">{sector}</div>
          <div class="co-meta">
            <span class="meta-item">
              <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/></svg>
              {funding}
            </span>
            <span class="meta-item">
              <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              {co["ceo"]}
            </span>
            <span class="meta-item">
              <svg width="11" height="11" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z"/><circle cx="12" cy="10" r="3"/></svg>
              {loc or "—"}
            </span>
          </div>
        </div>
      </a>"""


# ── Page builder ───────────────────────────────────────────────────────────────

def _meeting_btn(url: str, accent: str) -> str:
    href = url or "https://app.dealroom.co/"
    return (
        f'<div style="margin-top:18px;">'
        f'<a href="{href}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background:#3662e3;color:#fff;text-decoration:none;'
        f'font-size:13px;font-weight:600;padding:11px 24px;border-radius:10px;font-family:inherit;">'
        f'Book a meeting to activate access</a></div>'
    )


def build_page(profile: dict, companies: list, out_path: str, meeting_url: str = "") -> None:
    accent     = profile["accent_color"]
    acc_light  = _hex_rgba(accent, 0.07)
    acc_border = _hex_rgba(accent, 0.25)
    name       = profile["client_name"]
    tagline    = profile["tagline"]
    tags       = profile["display_tags"]
    insights   = profile["insight_lines"]
    logo_url   = profile.get("logo_url", "")
    domain     = profile.get("website_domain", "")
    n_excluded = len(profile.get("portfolio_ids", set()))

    # Logo HTML
    src = logo_url or (f"https://logo.clearbit.com/{domain}" if domain else "")
    ini = _letters(name)
    if src:
        logo_html = (
            f'<img src="{src}" alt="{name}" class="hero-logo-img" '
            f'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'flex\';">'
            f'<div class="hero-logo-ini" style="color:{accent};display:none;">{ini}</div>'
        )
    else:
        logo_html = f'<div class="hero-logo-ini" style="color:{accent};">{ini}</div>'

    # Tags
    tag_chips = " ".join(
        f'<span class="tag" style="background:{acc_light};border-color:{acc_border};color:{accent};">{t}</span>'
        if i < 3 else
        f'<span class="tag tag-grey">{t}</span>'
        for i, t in enumerate(tags)
    )

    # Insight bullets
    insight_html = "".join(
        f'<li><span style="color:{accent};">▸</span> {line}</li>'
        for line in insights
    )

    # 5 + 5
    left  = companies[:5]
    right = companies[5:10]
    left_cards  = "\n".join(_co_card(co, i)       for i, co in enumerate(left))
    right_cards = "\n".join(_co_card(co, i + 5)   for i, co in enumerate(right))

    stage_label = (profile.get("preferred_round") or "").replace("_", " ").title() or \
                  " · ".join(s.title() for s in (profile.get("investor_stages") or []))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>{name} · Dealroom</title>
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
    .nav-logo-mark {{ display: flex; align-items: center; }}
    .nav-logo-text {{ font-size: 14px; font-weight: 700; color: #1a1f36; }}
    .nav-right {{ display: flex; align-items: center; gap: 12px; }}
    .nav-badge {{ background: {acc_light}; border: 1px solid {acc_border};
                  color: {accent}; font-size: 11px; font-weight: 600;
                  padding: 4px 12px; border-radius: 20px; }}
    .nav-excl {{ font-size: 11px; color: var(--muted2); }}

    /* PAGE */
    .page {{ max-width: 960px; margin: 0 auto; padding: 32px 24px 72px; }}

    /* HERO */
    .hero {{ background: var(--white); border: 1px solid var(--border); border-radius: 16px;
             padding: 36px 32px 28px; text-align: center; margin-bottom: 20px;
             box-shadow: 0 1px 6px rgba(0,0,0,.05); }}
    .hero-logo-wrap {{ width: 125px; height: 125px; border-radius: 28px; background: var(--white);
                       border: 1px solid var(--border); box-shadow: 0 4px 16px rgba(0,0,0,.08);
                       display: flex; align-items: center; justify-content: center;
                       margin: 0 auto 18px; overflow: hidden; }}
    .hero-logo-img {{ width: 94px; height: 94px; object-fit: contain; }}
    .hero-logo-ini {{ font-size: 40px; font-weight: 800; width: 100%; height: 100%;
                      display: flex; align-items: center; justify-content: center; }}
    .hero-name {{ font-size: 20px; font-weight: 700; margin-bottom: 3px; }}
    .hero-stage {{ font-size: 12px; color: var(--muted); margin-bottom: 8px; }}
    .hero-tagline {{ font-size: 13px; color: var(--muted); line-height: 1.6; max-width: 500px;
                     margin: 0 auto 16px; }}
    .tags {{ display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }}
    .tag {{ border: 1px solid; border-radius: 6px; padding: 3px 10px; font-size: 11px; font-weight: 500; }}
    .tag-grey {{ background: #f3f4f6; border-color: var(--border); color: var(--muted); }}

    /* SECTION HEADER */
    .section-head {{ display: flex; align-items: baseline; justify-content: space-between;
                     margin-bottom: 12px; }}
    .section-title {{ font-size: 15px; font-weight: 600; }}
    .section-sub {{ font-size: 11px; color: var(--muted2); }}

    /* 5+5 GRID */
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px; }}
    .col {{ display: flex; flex-direction: column; gap: 8px; }}

    /* COMPANY CARD */
    .co-card {{ background: var(--white); border: 1px solid var(--border); border-radius: 12px;
                padding: 14px 16px; display: flex; align-items: flex-start; gap: 12px;
                transition: box-shadow .15s, border-color .15s, transform .15s;
                text-decoration: none; color: inherit; cursor: pointer; }}
    .co-card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.08); border-color: {acc_border}; transform: translateY(-1px); }}
    .co-logo {{ border-radius: 9px; flex-shrink: 0; display: flex; align-items: center;
                justify-content: center; overflow: hidden; border: 1px solid var(--border); }}
    .co-img {{ width: 28px; height: 28px; object-fit: contain; }}
    .co-ini {{ font-size: 11px; font-weight: 700; display: flex; align-items: center;
               justify-content: center; width: 100%; height: 100%; }}
    .co-body {{ flex: 1; min-width: 0; }}
    .co-name {{ font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px;
                white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .co-sector {{ font-size: 11px; color: var(--muted2); margin-bottom: 6px;
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .co-meta {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .meta-item {{ display: flex; align-items: center; gap: 3px; font-size: 11px; color: var(--muted);
                  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }}
    .meta-item svg {{ flex-shrink: 0; color: var(--muted2); }}

    /* INSIGHT */
    .insight {{ background: var(--white); border: 1px solid var(--border);
                border-left: 3px solid {accent}; border-radius: 12px;
                padding: 18px 20px; }}
    .insight-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase;
                      letter-spacing: .8px; color: {accent}; margin-bottom: 10px; }}
    .insight ul {{ list-style: none; display: flex; flex-direction: column; gap: 8px; }}
    .insight li {{ font-size: 12px; color: var(--muted); line-height: 1.55; display: flex; gap: 6px; }}

    @media (max-width: 640px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>

<nav class="nav">
  <a class="nav-logo" href="#">
    <div class="nav-logo-mark">
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="32" height="32" rx="6" fill="#0f1a2e"/>
        <rect x="8" y="20" width="3.5" height="6" rx="1" fill="white"/>
        <rect x="14" y="14" width="3.5" height="12" rx="1" fill="white"/>
        <rect x="20" y="9" width="3.5" height="17" rx="1" fill="white"/>
      </svg>
    </div>
    <span class="nav-logo-text">dealroom.co</span>
  </a>
  <div class="nav-right">
    <span class="nav-excl">{n_excluded} portfolio companies excluded</span>
    <span class="nav-badge">★ Curated for {name}</span>
  </div>
</nav>

<div class="page">

  <!-- Hero -->
  <div class="hero">
    <div class="hero-logo-wrap">{logo_html}</div>
    <div class="hero-name">{name}</div>
    <div class="hero-stage">{stage_label}</div>
    <div class="hero-tagline">{tagline}</div>
    <div class="tags">{tag_chips}</div>
    {_meeting_btn(meeting_url, accent)}
  </div>

  <!-- 5 + 5 -->
  <div class="section-head">
    <span class="section-title">Recommended companies</span>
    <span class="section-sub">Not in your portfolio · Matched to your thesis</span>
  </div>

  <div class="grid">
    <div class="col">{left_cards}</div>
    <div class="col">{right_cards}</div>
  </div>

  <!-- Why this view -->
  <div class="insight">
    <div class="insight-label">Why these companies</div>
    <ul>{insight_html}</ul>
  </div>

</div>
</body>
</html>"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✓ {out_path} — {len(companies)} companies, {n_excluded} portfolio excluded")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--investor", "-i")
    group.add_argument("--url",      "-u")
    parser.add_argument("--out",   "-o")
    parser.add_argument("--limit", "-l", type=int, default=10)
    args = parser.parse_args()

    source = args.investor or args.url
    print(f"[1/3] Researching: {source!r}")
    profile = research_investor(source)
    name    = profile["client_name"]
    print(f"      → {name} | portfolio: {len(profile['portfolio_ids'])} companies excluded")

    out = args.out or f"{name.lower().replace(' ','_')}.html"
    print(f"[2/3] Querying Dealroom…")
    companies = fetch_companies(profile, limit=args.limit)
    print(f"      → {len(companies)} recommendations")

    print(f"[3/3] Building page → {out}")
    build_page(profile, companies, out)

if __name__ == "__main__":
    main()
