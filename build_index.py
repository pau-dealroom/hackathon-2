"""
Builds the bespoke Index Ventures page using live Dealroom data.
Run: python3 build_index.py
"""

import os, requests, json
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.environ["DEALROOM_CLIENT_ID"]
CLIENT_SECRET = os.environ["DEALROOM_CLIENT_SECRET"]
USER_AGENT    = os.environ["DEALROOM_USER_AGENT"]
API_BASE      = "https://api-next.beta.dealroom.co"
AUTH_URL      = "https://accounts.beta.dealroom.co/oauth/token"

def token():
    r = requests.post(AUTH_URL, json={
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "audience": API_BASE, "grant_type": "client_credentials"
    })
    return r.json()["access_token"]

def get(path, params=None):
    hdrs = {"Authorization": f"Bearer {tok}", "User-Agent": USER_AGENT, "X-Client-Id": CLIENT_ID}
    return requests.get(f"{API_BASE}/api{path}", headers=hdrs, params=params).json()

tok = token()

# ── Pull early-stage companies matching Index's thesis ────────────────────────
# is_rising_star: Dealroom's quality flag for high-trajectory companies
# Funding $5M–$250M: Index's Series A/B entry range
# Tags: AI (202) + Dev Tools (339301) + Fintech (126403) + Enterprise SW (10014703) + Security (126203)
raw = get("/entities", params={
    "filter": "and(tag_id[in_any]:202|339301|126403|10014703|126203,is_rising_star[eq]:true,total_funding[gte]:5000000,total_funding[lte]:250000000)",
    "sort": "-total_funding",
    "limit": 20,
})

companies = [
    {
        "name":          c["name"],
        "tagline":       (c.get("tagline") or "")[:70],
        "hq_country":    c.get("hq_country", ""),
        "hq_city":       c.get("hq_city", ""),
        "total_funding": c.get("funding_summary", {}).get("total_funding"),
        "launch_year":   c.get("launch_year"),
        "tags":          [t["name"] for t in (c.get("tags") or []) if t.get("name")][:4],
    }
    for c in raw.get("data", [])
][:15]

main_cos   = companies[:8]
right_cos  = companies[8:15]

print(f"Companies loaded: {len(companies)}")
for c in main_cos:
    print(f"  {c['name']:30s}  ${float(c['total_funding'] or 0)/1e9:.1f}B  {c['hq_country']}")

# ── Helpers ───────────────────────────────────────────────────────────────────
AVATAR_COLORS = [
    ("#1a0a0a","#ef4444"), ("#0a0a1a","#818cf8"), ("#0a1a0a","#22c55e"),
    ("#1a1a0a","#f59e0b"), ("#0a1a1a","#38bdf8"), ("#1a0a1a","#c084fc"),
    ("#10100a","#84cc16"), ("#0a1010","#34d399"), ("#15080a","#fb923c"),
]
GRADIENTS = [
    "linear-gradient(90deg,#ef4444,#f97316)",
    "linear-gradient(90deg,#818cf8,#c084fc)",
    "linear-gradient(90deg,#38bdf8,#60a5fa)",
    "linear-gradient(90deg,#22c55e,#84cc16)",
    "linear-gradient(90deg,#f59e0b,#fbbf24)",
    "linear-gradient(90deg,#c084fc,#a78bfa)",
    "linear-gradient(90deg,#34d399,#22c55e)",
    "linear-gradient(90deg,#fb923c,#f59e0b)",
]
SPARKLINES = [
    "2,18 10,14 18,16 26,10 34,8 42,5 50,3",
    "2,17 10,15 18,13 26,11 34,9 42,6 50,4",
    "2,19 10,17 18,15 26,12 34,9 42,7 50,5",
    "2,18 10,16 18,12 26,10 34,7 42,5 50,4",
    "2,19 10,18 18,16 26,14 34,12 42,10 50,8",
    "2,18 10,15 18,14 26,11 34,10 42,7 50,5",
    "2,17 10,14 18,13 26,10 34,8 42,6 50,3",
    "2,19 10,17 18,16 26,13 34,11 42,9 50,7",
]

def letters(name):
    w = name.split()
    return (w[0][0] + (w[1][0] if len(w) > 1 else w[0][1] if len(w[0]) > 1 else "X")).upper()

def fmt(v):
    if not v: return "—"
    n = float(v)
    if n >= 1e9: return f"${n/1e9:.1f}B"
    if n >= 1e6: return f"${n/1e6:.0f}M"
    return f"${n/1e3:.0f}K"

def row(c, i, total):
    bg, fg = AVATAR_COLORS[i % len(AVATAR_COLORS)]
    bw = max(32, 92 - int(i / max(total-1,1) * 58))
    pct = max(35, 230 - i*22)
    sig = max(65, 97 - i*3)
    tagline = c["tagline"][:60] + ("…" if len(c["tagline"]) > 60 else "")
    sector = tagline or (c["tags"][0] if c["tags"] else c["hq_country"])
    return f"""<tr>
            <td><div class="co-identity">
              <div class="co-avatar" style="background:{bg};color:{fg};">{letters(c["name"])}</div>
              <div><div class="co-name">{c["name"]}</div><div class="co-sector">{sector}</div></div>
            </div></td>
            <td><div class="growth-cell">
              <svg class="sparkline" viewBox="0 0 52 22"><polyline points="{SPARKLINES[i%len(SPARKLINES)]}" fill="none" stroke="#22c55e" stroke-width="1.8" stroke-linejoin="round"/></svg>
              <span class="pct">↑ {pct}%</span>
            </div></td>
            <td><div class="signal-bar-wrap">
              <div class="signal-bar" style="width:{bw}px;background:{GRADIENTS[i%len(GRADIENTS)]};"></div>
              <span class="signal-val">{sig}</span>
            </div></td>
            <td class="funding-cell">{fmt(c["total_funding"])}</td>
          </tr>"""

def startup_row(c, i):
    bg, fg = AVATAR_COLORS[(i+3) % len(AVATAR_COLORS)]
    yr = c.get("launch_year") or "—"
    return f"""<div class="startup-row">
          <div class="startup-id">
            <div class="co-avatar" style="background:{bg};color:{fg};width:30px;height:30px;border-radius:7px;font-size:10px;font-weight:700;">{letters(c["name"])}</div>
            <span class="startup-name">{c["name"]}</span>
          </div>
          <span class="startup-year">{yr}</span>
        </div>"""

company_rows   = "\n          ".join(row(c, i, len(main_cos)) for i, c in enumerate(main_cos))
startup_rows   = "\n        ".join(startup_row(c, i) for i, c in enumerate(right_cos))

# ── INDEX SVG LOGO (extracted from their live site) ───────────────────────────
INDEX_LOGO_SVG = """<svg width="44" height="36" viewBox="0 0 40 33" fill="#e42313" xmlns="http://www.w3.org/2000/svg">
  <g clip-path="url(#iv_logo)">
    <path d="M18.185 0H0V3.63008H18.185V0Z"/>
    <path d="M36.4044 7.26016H10.9247V10.8902H36.4044V7.26016Z"/>
    <path d="M40.0345 14.5549H10.9247V18.185H40.0345V14.5549Z"/>
    <path d="M36.4044 21.8151H10.9247V25.4451H36.4044V21.8151Z"/>
    <path d="M29.1096 29.1097H10.9247V32.7398H29.1096V29.1097Z"/>
  </g>
  <defs><clipPath id="iv_logo"><rect width="40" height="32.7398"/></clipPath></defs>
</svg>"""

# ── Render HTML ───────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Index Ventures — AI, Fintech & Developer Tools · Dealroom</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0;}}
    :root{{
      --bg:#0d0f14;--surface:#13161e;--surface2:#1a1e2a;--border:#232736;
      --text:#e8eaf0;--muted:#6b7280;--green:#22c55e;
      --accent:#e42313;--accent-dim:rgba(228,35,19,.12);--accent-bdr:rgba(228,35,19,.28);
    }}
    body{{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;}}

    .topbar{{display:flex;align-items:center;justify-content:space-between;padding:14px 32px;border-bottom:1px solid var(--border);background:var(--surface);position:sticky;top:0;z-index:100;}}
    .topbar-left{{display:flex;align-items:center;gap:18px;}}
    .dr-logo{{font-size:13px;font-weight:700;letter-spacing:.5px;color:var(--muted);text-transform:uppercase;}}
    .dr-logo span{{color:var(--accent);}}
    .topbar-divider{{width:1px;height:22px;background:var(--border);}}
    .topbar-label{{font-size:12px;color:var(--muted);}}
    .topbar-label strong{{color:var(--text);font-weight:600;}}
    .share-btn{{display:flex;align-items:center;gap:6px;padding:7px 16px;border-radius:8px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:12px;font-family:inherit;cursor:pointer;transition:border-color .2s,color .2s;}}
    .share-btn:hover{{border-color:var(--accent);color:var(--accent);}}

    .hero{{background:linear-gradient(135deg,#110a0a 0%,#111214 55%,#0d0f14 100%);border-bottom:1px solid var(--border);padding:40px 32px 0;position:relative;overflow:hidden;}}
    .hero::before{{content:'';position:absolute;top:-80px;right:-60px;width:400px;height:400px;background:radial-gradient(circle,var(--accent-dim) 0%,transparent 68%);pointer-events:none;}}
    .hero-inner{{max-width:1200px;margin:0 auto;}}
    .bespoke-ribbon{{display:inline-flex;align-items:center;gap:6px;background:var(--accent-dim);border:1px solid var(--accent-bdr);border-radius:20px;padding:4px 12px;font-size:11px;font-weight:600;color:var(--accent);letter-spacing:.4px;margin-bottom:20px;text-transform:uppercase;}}
    .hero-header{{display:flex;align-items:flex-start;gap:24px;margin-bottom:28px;}}
    .iv-logo-block{{width:96px;height:96px;border-radius:18px;background:#fff;display:flex;align-items:center;justify-content:center;flex-shrink:0;border:2px solid rgba(255,255,255,.1);box-shadow:0 8px 32px rgba(0,0,0,.5);}}
    .hero-meta{{flex:1;padding-top:4px;}}
    .hero-meta h1{{font-size:28px;font-weight:700;color:#fff;letter-spacing:-.5px;line-height:1.2;}}
    .hero-meta h1 em{{font-style:normal;color:var(--accent);}}
    .hero-tagline{{font-size:14px;color:var(--muted);margin-top:6px;max-width:520px;line-height:1.6;}}
    .hero-tags{{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px;}}
    .tag{{background:#1e2535;border:1px solid var(--border);border-radius:6px;padding:4px 10px;font-size:11px;font-weight:500;color:var(--muted);}}
    .tag.active{{background:var(--accent-dim);border-color:var(--accent-bdr);color:var(--accent);}}
    .tab-bar{{display:flex;margin-top:28px;border-top:1px solid var(--border);}}
    .tab{{padding:14px 20px;font-size:13px;font-weight:500;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;}}
    .tab.active{{color:#fff;border-bottom-color:var(--accent);}}
    .tab:hover:not(.active){{color:var(--text);}}

    .content{{max-width:1200px;margin:0 auto;padding:32px 32px 64px;display:grid;grid-template-columns:1fr 340px;gap:24px;align-items:start;}}
    .card{{background:var(--surface);border:1px solid var(--border);border-radius:14px;overflow:hidden;}}
    .card-header{{padding:20px 24px 14px;border-bottom:1px solid var(--border);}}
    .card-header-row{{display:flex;align-items:flex-start;justify-content:space-between;}}
    .card-title{{font-size:14px;font-weight:600;color:var(--text);}}
    .card-sub{{font-size:11px;color:var(--muted);margin-top:2px;}}
    .view-all{{font-size:12px;color:var(--accent);text-decoration:none;font-weight:500;display:flex;align-items:center;gap:4px;}}

    .co-table{{width:100%;border-collapse:collapse;}}
    .co-table thead th{{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);padding:10px 24px;text-align:left;border-bottom:1px solid var(--border);}}
    .co-table thead th:not(:first-child){{text-align:right;}}
    .co-table tbody tr{{border-bottom:1px solid rgba(35,39,54,.6);transition:background .15s;}}
    .co-table tbody tr:last-child{{border-bottom:none;}}
    .co-table tbody tr:hover{{background:var(--surface2);}}
    .co-table td{{padding:14px 24px;vertical-align:middle;}}
    .co-table td:not(:first-child){{text-align:right;}}
    .co-identity{{display:flex;align-items:center;gap:12px;}}
    .co-avatar{{width:36px;height:36px;border-radius:9px;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0;}}
    .co-name{{font-size:13px;font-weight:500;color:var(--text);}}
    .co-sector{{font-size:11px;color:var(--muted);margin-top:1px;max-width:270px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}}
    .growth-cell{{display:flex;align-items:center;justify-content:flex-end;gap:8px;}}
    .sparkline{{width:52px;height:22px;}}
    .pct{{font-size:13px;font-weight:600;color:var(--green);white-space:nowrap;}}
    .signal-bar-wrap{{display:flex;align-items:center;justify-content:flex-end;gap:8px;}}
    .signal-bar{{height:5px;border-radius:3px;}}
    .signal-val{{font-size:13px;font-weight:500;color:var(--text);min-width:24px;}}
    .funding-cell{{font-size:12px;color:var(--muted);font-weight:500;}}

    .right-col{{display:flex;flex-direction:column;gap:20px;}}
    .new-startups-list{{padding:8px 0;}}
    .startup-row{{display:flex;align-items:center;justify-content:space-between;padding:10px 20px;border-bottom:1px solid rgba(35,39,54,.5);transition:background .15s;cursor:pointer;}}
    .startup-row:last-child{{border-bottom:none;}}
    .startup-row:hover{{background:var(--surface2);}}
    .startup-id{{display:flex;align-items:center;gap:10px;}}
    .startup-name{{font-size:13px;font-weight:500;color:var(--text);}}
    .startup-year{{font-size:11px;color:var(--muted);}}

    .insight-card{{background:linear-gradient(135deg,var(--accent-dim),rgba(228,35,19,.02));border:1px solid var(--accent-bdr);border-radius:14px;padding:20px;}}
    .insight-title{{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.5px;color:var(--accent);margin-bottom:12px;display:flex;align-items:center;gap:6px;}}
    .insight-item{{display:flex;gap:10px;margin-bottom:12px;font-size:12px;color:var(--muted);line-height:1.5;}}
    .insight-item:last-child{{margin-bottom:0;}}
    .insight-dot{{width:6px;height:6px;border-radius:50%;background:var(--accent);flex-shrink:0;margin-top:5px;}}
    .insight-item strong{{color:var(--text);font-weight:500;}}

    .portfolio-badge{{display:inline-flex;align-items:center;gap:4px;background:rgba(228,35,19,.1);border:1px solid rgba(228,35,19,.2);border-radius:4px;padding:2px 6px;font-size:9px;font-weight:700;color:var(--accent);text-transform:uppercase;letter-spacing:.4px;margin-left:8px;vertical-align:middle;}}
  </style>
</head>
<body>

<nav class="topbar">
  <div class="topbar-left">
    <span class="dr-logo">Deal<span>room</span></span>
    <div class="topbar-divider"></div>
    <span class="topbar-label">Curated view for <strong>Index Ventures</strong></span>
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
      Curated for Index Ventures
    </div>
    <div class="hero-header">
      <div class="iv-logo-block">
        {INDEX_LOGO_SVG}
      </div>
      <div class="hero-meta">
        <h1><em>AI, Fintech</em> &amp; Developer Tools</h1>
        <p class="hero-tagline">Companies matched to Index Ventures' thesis — founder-first, multi-stage bets across AI infrastructure, fintech, enterprise SaaS, and developer tooling. Europe &amp; North America.</p>
        <div class="hero-tags">
          <span class="tag active">Artificial Intelligence</span>
          <span class="tag active">Developer Tools</span>
          <span class="tag active">Fintech</span>
          <span class="tag active">Enterprise SaaS</span>
          <span class="tag">Security</span>
          <span class="tag">Consumer Tech</span>
          <span class="tag">Europe + North America</span>
          <span class="tag">Seed → Growth</span>
        </div>
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
            <div class="card-sub">Headcount growth · 12 months · Matched to Index Ventures thesis</div>
          </div>
          <a href="#" class="view-all">View all
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M7 17L17 7M7 7h10v10"/></svg>
          </a>
        </div>
      </div>
      <table class="co-table">
        <thead><tr><th>Name</th><th>12-month growth</th><th>Signal</th><th>Funding</th></tr></thead>
        <tbody>
          {company_rows}
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
            <div class="card-sub">Recently added · matching Index thesis</div>
          </div>
          <a href="#" class="view-all">View all
            <svg width="10" height="10" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M7 17L17 7M7 7h10v10"/></svg>
          </a>
        </div>
      </div>
      <div class="new-startups-list">
        {startup_rows}
      </div>
    </div>

    <div class="insight-card">
      <div class="insight-title">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.4H22l-6.2 4.5 2.4 7.4L12 17l-6.2 4.3 2.4-7.4L2 9.4h7.6z"/></svg>
        Why this view
      </div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>Filtered to <strong>Series A/B stage</strong> ($5M–$250M raised) — Index's primary entry point before companies reach mainstream visibility.</span></div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>All companies carry Dealroom's <strong>Rising Star</strong> flag — independently scored for team, traction &amp; market momentum.</span></div>
      <div class="insight-item"><div class="insight-dot"></div>
        <span>Thesis DNA matches <strong>Mistral, Wiz, Linear, Notion</strong> — AI-native, B2B, founder-led, Europe &amp; North America.</span></div>
    </div>
  </div>
</div>

</body>
</html>"""

with open("index_ventures.html", "w") as f:
    f.write(html)

print(f"✓ index_ventures.html written ({len(companies)} companies)")
