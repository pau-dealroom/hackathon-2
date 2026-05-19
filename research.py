"""
VC research — Dealroom-first pipeline.

1. Find investor on Dealroom (real ID, logo, stages, deal sizes)
2. Pull their real portfolio via transactions (for exclusion + thesis signal)
3. Derive preferred stage from round-type distribution
4. Ask GPT to map portfolio company names → Dealroom taxonomy terms
5. Return a complete profile ready for fetch + page generation
"""

import json, re, requests
from collections import Counter
from openai import OpenAI
from query_engine import DealroomClient

STAGE_FUNDING = {
    "seed":         (500_000,    15_000_000),
    "early":        (2_000_000,  30_000_000),
    "early_growth": (10_000_000, 150_000_000),
    "late_growth":  (50_000_000, 500_000_000),
    "mature":       (100_000_000, 5_000_000_000),
}
ROUND_FUNDING = {
    "PRE-SEED":        (200_000,     3_000_000),
    "SEED":            (500_000,    15_000_000),
    "EARLY VC":        (2_000_000,  30_000_000),
    "SERIES A":        (5_000_000,  50_000_000),
    "SERIES B":        (20_000_000, 150_000_000),
    "SERIES C":        (50_000_000, 300_000_000),
    "SERIES D":        (100_000_000, 500_000_000),
    "LATE VC":         (100_000_000, 600_000_000),
    "GROWTH EQUITY VC":(50_000_000, 400_000_000),
    "BUYOUT":          (100_000_000, 2_000_000_000),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fetch_url(url: str, max_chars: int = 5000) -> str:
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", r.text)
        return re.sub(r"\s+", " ", text).strip()[:max_chars]
    except Exception as e:
        return f"[fetch failed: {e}]"


def _lookup_dealroom(name: str):
    """Find investor on Dealroom by exact name, then partial match."""
    c = DealroomClient()
    r = c.get("/investors", params={"filter": f"name[eq]:{name}", "limit": 1})
    data = r.json().get("data", [])
    if data:
        return data[0]
    # Partial match — only accept if name overlaps significantly
    r = c.get("/investors", params={"q": name, "limit": 10})
    nl = name.lower()
    for inv in r.json().get("data", []):
        inv_nl = inv["name"].lower()
        if nl in inv_nl or inv_nl in nl:
            return inv
    return None


def _get_portfolio(investor_id: int):
    """
    Returns (portfolio_ids: set, portfolio_sample: list, preferred_round: str, funding_range: tuple)
    portfolio_sample = list of {name, round_type, hq_country} for GPT thesis analysis
    """
    c = DealroomClient()
    r = c.get("/transactions", params={
        "filter": f"investor_id[eq]:{investor_id}",
        "sort": "-year",
        "limit": 100,
    })
    txns = r.json().get("data", [])

    portfolio_ids = {t["entity_id"] for t in txns}
    portfolio_sample = [
        {
            "name":        t["company"]["name"],
            "round_type":  t.get("round_type", ""),
            "hq_country":  t["company"].get("hq_country", ""),
        }
        for t in txns
    ]

    # Round distribution → preferred round + funding range
    counts = Counter(t.get("round_type") for t in txns if t.get("round_type"))
    preferred_round = counts.most_common(1)[0][0] if counts else None
    fmin, fmax = ROUND_FUNDING.get(preferred_round, (5_000_000, 250_000_000))

    # Top portfolio countries (geo focus signal)
    # Only keep countries that represent ≥15% of portfolio OR the clear top 2,
    # capped at 2 to avoid borderline countries polluting the filter.
    country_counts = Counter(
        t["company"].get("hq_country") for t in txns
        if t.get("company") and t["company"].get("hq_country")
    )
    total_txns = len(txns) or 1
    focus_countries = []
    for country, cnt in country_counts.most_common(2):
        if country and (cnt / total_txns >= 0.12 or len(focus_countries) == 0):
            focus_countries.append(country)

    return portfolio_ids, portfolio_sample, preferred_round, (fmin, fmax), focus_countries


def _gpt_enrich(name: str, dr_profile, article: str, portfolio_sample: list) -> dict:
    """GPT extracts: taxonomy terms, tagline, accent color, insight lines."""
    dr_block = ""
    if dr_profile:
        stages = ", ".join(s["name"] for s in (dr_profile.get("investor_stages") or []))
        dr_block = f"""
Dealroom profile:
- Name: {dr_profile['name']}
- Tagline: {dr_profile.get('tagline', '')}
- HQ: {dr_profile.get('hq_city', '')} {dr_profile.get('hq_country', '')}
- Stages: {stages}
"""

    portfolio_block = ""
    if portfolio_sample:
        lines = "\n".join(
            f"- {p['name']} ({p['round_type']}, {p['hq_country']})"
            for p in portfolio_sample[:25]
        )
        portfolio_block = f"\nRecent portfolio companies (use these to infer thesis sectors):\n{lines}"

    article_block = f"\nArticle/page content:\n{article}" if article else ""

    prompt = f"""You are building a bespoke Dealroom discovery page for a VC/investor.

Investor: {name}
{dr_block}{portfolio_block}{article_block}

Return ONLY valid JSON matching this schema exactly:
{{
  "tagline": "One sentence investment thesis, max 120 chars",
  "display_tags": ["Tag1","Tag2","Tag3","Tag4","Tag5","Tag6"],
  "dealroom_terms": {{
    "industry":     ["e.g. health, energy, fintech, software"],
    "sub_industry": ["e.g. artificial intelligence, clean energy, biotech, medtech"],
    "sector":       ["e.g. machine learning, solar energy, digital health, saas, cybersecurity"]
  }},
  "accent_color": "#hex brand color",
  "insight_lines": [
    "Stage insight: their typical entry point and check size",
    "Signal: what quality filter was applied to these recommendations",
    "Fit: 2-3 named portfolio companies that illustrate the thesis DNA"
  ]
}}

Rules:
- Infer sectors primarily from the portfolio company names — those are ground truth
- dealroom_terms: be specific. Use real Dealroom taxonomy language.
- accent_color: use known brand colors where possible:
  Index=#e42313, Lightrock=#22a06b, Accel=#0f52ba, Sequoia=#e33d26,
  Eurazeo=#0b2b3f, a16z=#1652f0, Balderton=#1a1a2e, GV=#4285f4, 20VC=#000000
- display_tags: 5-6 tags covering sectors + geography + stage
- insight_lines: reference REAL portfolio companies by name"""

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content)


# ── Main entry ────────────────────────────────────────────────────────────────

def research_investor(name_or_url: str) -> dict:
    """
    Build full investor profile.
    Returns dict with: client_name, logo_url, accent_color, tagline,
    display_tags, dealroom_terms, funding_min, funding_max, insight_lines,
    investor_id, portfolio_ids, preferred_round, investor_stages
    """
    is_url  = name_or_url.startswith("http")
    article = ""
    name    = name_or_url

    if is_url:
        article = _fetch_url(name_or_url)
        # Try to pull investor name from article first 200 chars or URL domain
        snippet = article[:300]
        m = re.search(r"\b([A-Z][A-Za-z&\s]{2,30}?)\s+(is |are |has |launches|announces|fund|venture|capital|invest)", snippet)
        if m:
            name = m.group(1).strip()
        else:
            parts = name_or_url.split("/")
            domain_parts = [p for p in parts if "." in p]
            if domain_parts:
                name = domain_parts[0].split(".")[0].replace("-", " ").title()

    # 1. Look up on Dealroom
    dr = _lookup_dealroom(name)
    if dr:
        name = dr["name"]

    # 2. Portfolio analysis
    portfolio_ids   = set()
    portfolio_sample = []
    preferred_round = None
    fmin, fmax      = 5_000_000, 250_000_000

    focus_countries = []
    if dr:
        portfolio_ids, portfolio_sample, preferred_round, (fmin, fmax), focus_countries = _get_portfolio(dr["id"])

    # Also consider investor_stages from profile
    if dr and dr.get("investor_stages"):
        stages = [s["code"] for s in dr["investor_stages"]]
        stage_mins = [STAGE_FUNDING[s][0] for s in stages if s in STAGE_FUNDING]
        stage_maxs = [STAGE_FUNDING[s][1] for s in stages if s in STAGE_FUNDING]
        if stage_mins:
            fmin = min(fmin, min(stage_mins))
            fmax = max(fmax, max(stage_maxs))

    # 3. GPT fills presentation + taxonomy
    enriched = _gpt_enrich(name, dr, article, portfolio_sample)

    # 4. Logo
    logo_url = ""
    if dr and dr.get("image"):
        img = dr["image"]
        logo_url = f"https://{img}" if not img.startswith("http") else img

    domain = (dr.get("website_domain") or "") if dr else ""

    return {
        "client_name":    name,
        "website_domain": domain,
        "logo_url":       logo_url,
        "accent_color":   enriched["accent_color"],
        "tagline":        enriched["tagline"],
        "display_tags":   enriched["display_tags"],
        "dealroom_terms": enriched["dealroom_terms"],
        "funding_min":    fmin,
        "funding_max":    fmax,
        "insight_lines":  enriched["insight_lines"],
        "investor_id":    dr["id"] if dr else None,
        "portfolio_ids":  portfolio_ids,
        "preferred_round": preferred_round or "",
        "investor_stages": [s["name"] for s in (dr.get("investor_stages") or [])] if dr else [],
        "focus_countries": focus_countries,
    }
