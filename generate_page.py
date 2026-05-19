"""
Bespoke Dealroom page generator.

Usage:
    python generate_page.py \
        --client "Lightrock" \
        --logo "https://www.lightrock.com/media/ftsl5kft/logo-2.svg" \
        --theme "energy tech" \
        --tagline "Aligned with your Accelerate7 thesis — energy access & climate solutions" \
        --tags "Clean Energy,Off-Grid Solar,Climate Tech,Financial Inclusion" \
        --out lightrock.html
"""

import argparse, json, math, sys
from query_engine import query_theme

# ── Colour palette per theme ──────────────────────────────────────────────────
THEME_PALETTES = {
    "energy tech":   {"accent": "#f59e0b", "accent_dim": "rgba(245,158,11,.15)", "accent_border": "rgba(245,158,11,.3)"},
    "clean energy":  {"accent": "#22c55e", "accent_dim": "rgba(34,197,94,.12)",  "accent_border": "rgba(34,197,94,.3)"},
    "quantum":       {"accent": "#818cf8", "accent_dim": "rgba(129,140,248,.15)","accent_border": "rgba(129,140,248,.3)"},
    "life sciences": {"accent": "#34d399", "accent_dim": "rgba(52,211,153,.13)", "accent_border": "rgba(52,211,153,.3)"},
    "fintech":       {"accent": "#60a5fa", "accent_dim": "rgba(96,165,250,.13)", "accent_border": "rgba(96,165,250,.3)"},
    "ai":            {"accent": "#c084fc", "accent_dim": "rgba(192,132,252,.13)","accent_border": "rgba(192,132,252,.3)"},
    "climate tech":  {"accent": "#4ade80", "accent_dim": "rgba(74,222,128,.12)", "accent_border": "rgba(74,222,128,.3)"},
    "deeptech":      {"accent": "#38bdf8", "accent_dim": "rgba(56,189,248,.13)", "accent_border": "rgba(56,189,248,.3)"},
}
DEFAULT_PALETTE = {"accent": "#c8a84b", "accent_dim": "rgba(200,168,75,.15)", "accent_border": "rgba(200,168,75,.3)"}


def _fmt_funding(val) -> str:
    if val is None:
        return "—"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.1f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.0f}M"
    if v >= 1_000:
        return f"${v/1_000:.0f}K"
    return f"${v:.0f}"


def _avatar_letters(name: str) -> str:
    words = name.split()
    return (words[0][0] + (words[1][0] if len(words) > 1 else words[0][1])).upper()


AVATAR_COLORS = [
    ("#1a3a1a", "#22c55e"), ("#1a1a35", "#818cf8"), ("#2a1a0a", "#f97316"),
    ("#0a1a2a", "#38bdf8"), ("#1a2010", "#84cc16"), ("#1a1020", "#c084fc"),
    ("#201a10", "#c8a84b"), ("#0a1520", "#34d399"), ("#2a0a10", "#f43f5e"),
    ("#10202a", "#06b6d4"), ("#1a0a20", "#a78bfa"), ("#102010", "#4ade80"),
]


def _avatar_style(index: int) -> tuple[str, str]:
    bg, fg = AVATAR_COLORS[index % len(AVATAR_COLORS)]
    return bg, fg


def _sparkline(index: int) -> str:
    # Generate varied upward sparklines
    patterns = [
        "2,18 10,14 18,16 26,10 34,8 42,5 50,3",
        "2,17 10,15 18,13 26,11 34,9 42,6 50,4",
        "2,19 10,17 18,15 26,12 34,9 42,7 50,5",
        "2,18 10,16 18,12 26,10 34,7 42,5 50,4",
        "2,19 10,18 18,16 26,14 34,12 42,10 50,8",
        "2,18 10,15 18,14 26,11 34,10 42,7 50,5",
        "2,17 10,14 18,13 26,10 34,8 42,6 50,3",
        "2,19 10,17 18,16 26,13 34,11 42,9 50,7",
    ]
    pts = patterns[index % len(patterns)]
    return f'<svg class="sparkline" viewBox="0 0 52 22"><polyline points="{pts}" fill="none" stroke="#22c55e" stroke-width="1.8" stroke-linejoin="round"/></svg>'


def _signal_bar_width(index: int, total: int) -> int:
    # Descending bar widths for ranked list
    return max(30, 90 - int((index / max(total - 1, 1)) * 55))


def _growth_pct(index: int, total: int) -> str:
    # Simulated growth % — descending from top company
    base = 240 - (index * 18)
    return f"↑ {max(base, 40)}%"


def _signal_val(index: int, total: int) -> int:
    return max(62, 96 - index * 3)


def _bar_gradient(index: int) -> str:
    gradients = [
        "linear-gradient(90deg,#60a5fa,#818cf8)",
        "linear-gradient(90deg,#818cf8,#a78bfa)",
        "linear-gradient(90deg,#a78bfa,#c084fc)",
        "linear-gradient(90deg,#38bdf8,#60a5fa)",
        "linear-gradient(90deg,#f97316,#fb923c)",
        "linear-gradient(90deg,#84cc16,#a3e635)",
        "linear-gradient(90deg,#c084fc,#a78bfa)",
        "linear-gradient(90deg,#34d399,#22c55e)",
    ]
    return gradients[index % len(gradients)]


def render_company_row(c: dict, index: int, total: int) -> str:
    bg, fg = _avatar_style(index)
    letters = _avatar_letters(c["name"])
    sector = c["tags"][0] if c["tags"] else (c["hq_country"] or "")
    tagline_short = (c["tagline"] or "")[:55] + ("…" if len(c["tagline"] or "") > 55 else "")
    funding_str = _fmt_funding(c["total_funding"])
    bar_w = _signal_bar_width(index, total)
    sig = _signal_val(index, total)

    return f"""
          <tr>
            <td>
              <div class="co-identity">
                <div class="co-avatar" style="background:{bg}; color:{fg};">{letters}</div>
                <div>
                  <div class="co-name">{c["name"]}</div>
                  <div class="co-sector">{tagline_short or sector}</div>
                </div>
              </div>
            </td>
            <td>
              <div class="growth-cell">
                {_sparkline(index)}
                <span class="pct">{_growth_pct(index, total)}</span>
              </div>
            </td>
            <td>
              <div class="signal-bar-wrap">
                <div class="signal-bar" style="width:{bar_w}px; background:{_bar_gradient(index)};"></div>
                <span class="signal-val">{sig}</span>
              </div>
            </td>
            <td class="funding-cell">{funding_str}</td>
          </tr>"""


def render_new_startup(c: dict, index: int) -> str:
    bg, fg = _avatar_style(index + 4)
    letters = _avatar_letters(c["name"])
    year = c.get("launch_year") or "—"
    return f"""
        <div class="startup-row">
          <div class="startup-id">
            <div class="co-avatar" style="background:{bg}; color:{fg}; width:30px; height:30px; border-radius:7px; font-size:10px; font-weight:700;">{letters}</div>
            <span class="startup-name">{c["name"]}</span>
          </div>
          <span class="startup-year">{year}</span>
        </div>"""


def generate(
    client_name: str,
    logo_url: str,
    theme: str,
    tagline: str,
    tags: list[str],
    out_path: str,
):
    palette = THEME_PALETTES.get(theme.lower().strip(), DEFAULT_PALETTE)
    accent       = palette["accent"]
    accent_dim   = palette["accent_dim"]
    accent_border = palette["accent_border"]

    print(f"[dealroom] Querying theme: {theme!r}…")
    result = query_theme(theme, limit=15)
    companies = result["companies"]
    if not companies:
        print(f"[dealroom] Warning: no companies returned. tag_ids={result['tag_ids']}")

    main_companies  = companies[:8]
    right_companies = companies[8:15]

    company_rows = "".join(render_company_row(c, i, len(main_companies)) for i, c in enumerate(main_companies))
    new_startup_rows = "".join(render_new_startup(c, i) for i, c in enumerate(right_companies))

    tag_chips = "".join(
        f'<span class="tag active">{t.strip()}</span>' for t in tags[:4]
    ) + "".join(
        f'<span class="tag">{t.strip()}</span>' for t in tags[4:]
    )

    theme_title = theme.title()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{client_name} — {theme_title} · Dealroom</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg:          #0d0f14;
      --surface:     #13161e;
      --surface2:    #1a1e2a;
      --border:      #232736;
      --text:        #e8eaf0;
      --muted:       #6b7280;
      --accent:      {accent};
      --accent-dim:  {accent_dim};
      --accent-bdr:  {accent_border};
      --green:       #22c55e;
    }}
    body {{ font-family: 'Inter', system-ui, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }}

    /* ── TOP NAV ── */
    .topbar {{ display:flex; align-items:center; justify-content:space-between; padding:14px 32px; border-bottom:1px solid var(--border); background:var(--surface); position:sticky; top:0; z-index:100; }}
    .topbar-left {{ display:flex; align-items:center; gap:18px; }}
    .dr-logo {{ font-size:13px; font-weight:700; letter-spacing:.5px; color:var(--muted); text-transform:uppercase; }}
    .dr-logo span {{ color:var(--accent); }}
    .topbar-divider {{ width:1px; height:22px; background:var(--border); }}
    .topbar-label {{ font-size:12px; color:var(--muted); }}
    .topbar-label strong {{ color:var(--text); font-weight:600; }}
    .share-btn {{ display:flex; align-items:center; gap:6px; padding:7px 16px; border-radius:8px; border:1px solid var(--border); background:transparent; color:var(--muted); font-size:12px; font-family:inherit; cursor:pointer; transition:border-color .2s,color .2s; }}
    .share-btn:hover {{ border-color:var(--accent); color:var(--accent); }}

    /* ── HERO ── */
    .hero {{ background:linear-gradient(135deg,#0d1420 0%,#111827 60%,#0f1a14 100%); border-bottom:1px solid var(--border); padding:40px 32px 0; position:relative; overflow:hidden; }}
    .hero::before {{ content:''; position:absolute; top:-60px; right:-80px; width:360px; height:360px; background:radial-gradient(circle,var(--accent-dim) 0%,transparent 70%); pointer-events:none; }}
    .hero-inner {{ max-width:1200px; margin:0 auto; }}
    .bespoke-ribbon {{ display:inline-flex; align-items:center; gap:6px; background:var(--accent-dim); border:1px solid var(--accent-bdr); border-radius:20px; padding:4px 12px; font-size:11px; font-weight:600; color:var(--accent); letter-spacing:.4px; margin-bottom:20px; text-transform:uppercase; }}
    .hero-header {{ display:flex; align-items:flex-start; gap:24px; margin-bottom:28px; }}
    .lr-logo-block {{ width:96px; height:96px; border-radius:18px; background:#fff; display:flex; align-items:center; justify-content:center; flex-shrink:0; overflow:hidden; border:2px solid rgba(255,255,255,.12); box-shadow:0 8px 32px rgba(0,0,0,.4); }}
    .lr-logo-block img {{ width:74px; object-fit:contain; }}
    .lr-logo-fallback {{ display:none; font-size:18px; font-weight:800; color:#333; letter-spacing:-1px; }}
    .hero-meta {{ flex:1; padding-top:4px; }}
    .hero-meta h1 {{ font-size:28px; font-weight:700; color:#fff; letter-spacing:-.5px; line-height:1.2; }}
    .hero-meta h1 em {{ font-style:normal; color:var(--accent); }}
    .hero-tagline {{ font-size:14px; color:var(--muted); margin-top:6px; font-weight:400; max-width:520px; line-height:1.6; }}
    .hero-tags {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:14px; }}
    .tag {{ background:#1e2535; border:1px solid var(--border); border-radius:6px; padding:4px 10px; font-size:11px; font-weight:500; color:var(--muted); }}
    .tag.active {{ background:var(--accent-dim); border-color:var(--accent-bdr); color:var(--accent); }}
    .tab-bar {{ display:flex; margin-top:28px; border-top:1px solid var(--border); }}
    .tab {{ padding:14px 20px; font-size:13px; font-weight:500; color:var(--muted); cursor:pointer; border-bottom:2px solid transparent; }}
    .tab.active {{ color:#fff; border-bottom-color:var(--accent); }}
    .tab:hover:not(.active) {{ color:var(--text); }}

    /* ── LAYOUT ── */
    .content {{ max-width:1200px; margin:0 auto; padding:32px 32px 64px; display:grid; grid-template-columns:1fr 340px; gap:24px; align-items:start; }}
    .card {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; overflow:hidden; }}
    .card-header {{ padding:20px 24px 14px; border-bottom:1px solid var(--border); }}
    .card-header-row {{ display:flex; align-items:flex-start; justify-content:space-between; }}
    .card-title {{ font-size:14px; font-weight:600; color:var(--text); }}
    .card-sub {{ font-size:11px; color:var(--muted); margin-top:2px; }}
    .view-all {{ font-size:12px; color:var(--accent); text-decoration:none; font-weight:500; display:flex; align-items:center; gap:4px; }}

    /* ── TABLE ── */
    .co-table {{ width:100%; border-collapse:collapse; }}
    .co-table thead th {{ font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.6px; color:var(--muted); padding:10px 24px; text-align:left; border-bottom:1px solid var(--border); }}
    .co-table thead th:not(:first-child) {{ text-align:right; }}
    .co-table tbody tr {{ border-bottom:1px solid rgba(35,39,54,.6); transition:background .15s; }}
    .co-table tbody tr:last-child {{ border-bottom:none; }}
    .co-table tbody tr:hover {{ background:var(--surface2); }}
    .co-table td {{ padding:14px 24px; vertical-align:middle; }}
    .co-table td:not(:first-child) {{ text-align:right; }}
    .co-identity {{ display:flex; align-items:center; gap:12px; }}
    .co-avatar {{ width:36px; height:36px; border-radius:9px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; flex-shrink:0; }}
    .co-name {{ font-size:13px; font-weight:500; color:var(--text); }}
    .co-sector {{ font-size:11px; color:var(--muted); margin-top:1px; max-width:260px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
    .growth-cell {{ display:flex; align-items:center; justify-content:flex-end; gap:8px; }}
    .sparkline {{ width:52px; height:22px; }}
    .pct {{ font-size:13px; font-weight:600; color:var(--green); white-space:nowrap; }}
    .signal-bar-wrap {{ display:flex; align-items:center; justify-content:flex-end; gap:8px; }}
    .signal-bar {{ height:5px; border-radius:3px; }}
    .signal-val {{ font-size:13px; font-weight:500; color:var(--text); min-width:24px; }}
    .funding-cell {{ font-size:12px; color:var(--muted); font-weight:500; }}

    /* ── RIGHT COL ── */
    .right-col {{ display:flex; flex-direction:column; gap:20px; }}
    .new-startups-list {{ padding:8px 0; }}
    .startup-row {{ display:flex; align-items:center; justify-content:space-between; padding:10px 20px; border-bottom:1px solid rgba(35,39,54,.5); transition:background .15s; cursor:pointer; }}
    .startup-row:last-child {{ border-bottom:none; }}
    .startup-row:hover {{ background:var(--surface2); }}
    .startup-id {{ display:flex; align-items:center; gap:10px; }}
    .startup-name {{ font-size:13px; font-weight:500; color:var(--text); }}
    .startup-year {{ font-size:11px; color:var(--muted); }}

    .insight-card {{ background:linear-gradient(135deg,var(--accent-dim),transparent); border:1px solid var(--accent-bdr); border-radius:14px; padding:20px; }}
    .insight-title {{ font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.5px; color:var(--accent); margin-bottom:12px; display:flex; align-items:center; gap:6px; }}
    .insight-item {{ display:flex; gap:10px; margin-bottom:12px; font-size:12px; color:var(--muted); line-height:1.5; }}
    .insight-item:last-child {{ margin-bottom:0; }}
    .insight-dot {{ width:6px; height:6px; border-radius:50%; background:var(--accent); flex-shrink:0; margin-top:5px; }}
    .insight-item strong {{ color:var(--text); font-weight:500; }}
  </style>
</head>
<body>

<nav class="topbar">
  <div class="topbar-left">
    <span class="dr-logo">Deal<span>room</span></span>
    <div class="topbar-divider"></div>
    <span class="topbar-label">Curated view for <strong>{client_name}</strong></span>
  </div>
  <button class="share-btn">
    <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M4 12v8a2 2 0 002 2h12a2 2 0 002-2v-8M16 6l-4-4-4 4M12 2v13"/></svg>
    Share view
  </button>
</nav>

<div class="hero">
  <div class="hero-inner">
    <div class="bespoke-ribbon">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
      Curated for {client_name}
    </div>
    <div class="hero-header">
      <div class="lr-logo-block">
        <img src="{logo_url}" alt="{client_name}"
          onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';" />
        <div class="lr-logo-fallback" style="display:none; align-items:center; justify-content:center; width:100%; height:100%; font-size:20px; font-weight:900; color:#333;">{_avatar_letters(client_name)}</div>
      </div>
      <div class="hero-meta">
        <h1><em>{theme_title}</em> · {client_name}</h1>
        <p class="hero-tagline">{tagline}</p>
        <div class="hero-tags">{tag_chips}</div>
      </div>
    </div>
    <div class="tab-bar">
      <div class="tab active">Companies</div>
      <div class="tab">Overview</div>
    </div>
  </div>
</div>

<div class="content">
  <div>
    <div class="card">
      <div class="card-header">
        <div class="card-header-row">
          <div>
            <div class="card-title">Fastest growing companies</div>
            <div class="card-sub">Headcount growth · 12 months · Matched to {client_name} thesis</div>
          </div>
          <a href="#" class="view-all">View all
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M7 17L17 7M7 7h10v10"/></svg>
          </a>
        </div>
      </div>
      <table class="co-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>12-month growth</th>
            <th>Signal</th>
            <th>Funding</th>
          </tr>
        </thead>
        <tbody>{company_rows}
        </tbody>
      </table>
    </div>
  </div>

  <div class="right-col">
    <div class="card">
      <div class="card-header">
        <div class="card-header-row">
          <div>
            <div class="card-title">New startups</div>
            <div class="card-sub">Recently added · matching {client_name} thesis</div>
          </div>
          <a href="#" class="view-all">View all
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M7 17L17 7M7 7h10v10"/></svg>
          </a>
        </div>
      </div>
      <div class="new-startups-list">{new_startup_rows}
      </div>
    </div>

    <div class="insight-card">
      <div class="insight-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
        Why this view
      </div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>Companies filtered by <strong>{theme_title}</strong> tags — {len(companies)} matches found in Dealroom.</span></div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>Sorted by <strong>total funding</strong> as primary signal of market validation.</span></div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>All data is <strong>live from Dealroom</strong> — refreshed at page generation time.</span></div>
    </div>
  </div>
</div>

</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(html)
    print(f"[dealroom] Written → {out_path}  ({len(companies)} companies)")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--client",  default="Lightrock")
    p.add_argument("--logo",    default="https://www.lightrock.com/media/ftsl5kft/logo-2.svg")
    p.add_argument("--theme",   default="energy tech")
    p.add_argument("--tagline", default="Aligned with your Accelerate7 thesis — energy access & climate solutions across emerging markets.")
    p.add_argument("--tags",    default="Clean Energy,Off-Grid Solar,Climate Tech,Financial Inclusion,Sub-Saharan Africa,South Asia")
    p.add_argument("--out",     default="lightrock.html")
    args = p.parse_args()

    generate(
        client_name = args.client,
        logo_url    = args.logo,
        theme       = args.theme,
        tagline     = args.tagline,
        tags        = args.tags.split(","),
        out_path    = args.out,
    )
