"""
LP recommendations — activity-based matching.

Signal: find institutional investors (family offices, investment funds, PE)
that have been actively backing companies in the same sectors, stage, and
geography as the target VC's portfolio. Those entities have demonstrated
conviction in the same thesis and are natural LP candidates.

Pipeline:
1. Look up the VC on Dealroom → get profile + portfolio company IDs
2. Pull the VC's recent portfolio transactions → extract sector tags + stage + countries
3. Query recent transactions in those sectors/stages/geographies
4. Collect investor IDs from those transactions, rank by frequency
5. Look up top investors, keep only LP types (family_office, investment_fund, PE — not VC)
6. GPT writes a rationale for each selected LP
"""

import json
from collections import Counter
from openai import OpenAI
from query_engine import DealroomClient, resolve_tag_ids

LP_CODES = {"family_office", "investment_fund", "private_equity"}
EXCLUDE  = {"venture_capital", "accelerator", "angel_fund"}


# ── Step 1: Look up VC ────────────────────────────────────────────────────────

def _lookup_vc(name: str):
    c = DealroomClient()
    r = c.get("/investors", params={"filter": f"name[eq]:{name}", "limit": 1})
    data = r.json().get("data", [])
    if data:
        return data[0]
    r = c.get("/investors", params={"q": name, "limit": 10})
    nl = name.lower()
    for inv in r.json().get("data", []):
        if nl in inv["name"].lower() or inv["name"].lower() in nl:
            return inv
    return None


# ── Step 2: Build thesis signal from portfolio ────────────────────────────────

def _build_thesis_signal(investor_id: int) -> dict:
    """
    Pull portfolio transactions → extract:
    - Most common round types (stage signal)
    - Top tag IDs by type (technology, industry) from portfolio companies
    - Top HQ countries (geography signal)
    """
    c = DealroomClient()
    r = c.get("/transactions", params={
        "filter": f"investor_id[eq]:{investor_id}",
        "sort":   "-year",
        "limit":  100,
    })
    txns = r.json().get("data", [])

    round_counts   = Counter()
    country_counts = Counter()
    entity_ids     = []

    for t in txns:
        if t.get("round_type"):
            round_counts[t["round_type"]] += 1
        co = t.get("company") or {}
        if co.get("hq_country"):
            country_counts[co["hq_country"]] += 1
        if t.get("entity_id"):
            entity_ids.append(t["entity_id"])

    top_rounds    = [r for r, _ in round_counts.most_common(3)]
    top_countries = [c for c, _ in country_counts.most_common(3)]

    # Get tags from portfolio companies, grouped by type
    tags_by_type = {"technology": [], "industry": [], "sub_industry": [], "sector": []}
    for eid in entity_ids[:15]:
        try:
            er = c.get(f"/entities/{eid}")
            entity = er.json().get("data") or {}
            for tag in (entity.get("tags") or []):
                tp = tag.get("type", "")
                if tp in tags_by_type and tag["id"] not in tags_by_type[tp]:
                    tags_by_type[tp].append(tag["id"])
        except Exception:
            pass

    return {
        "top_rounds":    top_rounds,
        "top_countries": top_countries,
        "tags_by_type":  tags_by_type,
        "investor_id":   investor_id,
    }


# ── Step 3: Find active LPs in the same space ─────────────────────────────────

def _find_active_lps(signal: dict) -> list:
    """
    Query transactions matching the VC's stage + sector signal.
    Collect non-VC investors from those transactions.
    Return ranked list of LP-type investor profiles.
    """
    c = DealroomClient()

    round_types  = signal["top_rounds"][:2]
    tags_by_type = signal.get("tags_by_type", {})

    # Flatten all tag IDs across types (tag_id[in_any] works without type qualifier)
    all_tag_ids = []
    for tp in ("technology", "industry", "sub_industry", "sector"):
        for tid in tags_by_type.get(tp, [])[:5]:
            if tid not in all_tag_ids:
                all_tag_ids.append(tid)
    all_tag_ids = all_tag_ids[:10]

    if not round_types and not all_tag_ids:
        return []

    # Build filter — valid transaction filter keys: round_type, tag_id, location
    filters = []
    if round_types:
        filters.append(f"round_type[in_any]:{'|'.join(round_types)}")
    if all_tag_ids:
        filters.append(f"tag_id[in_any]:{'|'.join(str(i) for i in all_tag_ids)}")

    filter_expr = f"and({','.join(filters)})" if len(filters) > 1 else filters[0]

    r = c.get("/transactions", params={
        "filter": filter_expr,
        "sort":   "-year",
        "limit":  200,
    })
    txns = r.json().get("data", [])

    # Count investors across those transactions (excluding the VC itself)
    vc_id = signal["investor_id"]
    inv_counts = Counter()
    for t in txns:
        for inv in (t.get("investors") or []):
            if inv["id"] != vc_id:
                inv_counts[inv["id"]] += 1

    # Look up top investors, keep LP types only
    lps = []
    seen = set()
    for inv_id, count in inv_counts.most_common(80):
        if inv_id in seen:
            continue
        seen.add(inv_id)
        try:
            ir = c.get(f"/investors/{inv_id}")
            inv = ir.json().get("data") or ir.json()
            if not isinstance(inv, dict) or not inv.get("name"):
                continue
            types = {t["code"] for t in (inv.get("investor_types") or [])}
            # Keep LP types; exclude pure VCs and pure angels
            if (types & LP_CODES) and not (types & EXCLUDE):
                lps.append({
                    "id":             inv["id"],
                    "name":           inv["name"],
                    "types":          sorted(types),
                    "hq_city":        inv.get("hq_city", ""),
                    "hq_country":     inv.get("hq_country", ""),
                    "tagline":        (inv.get("tagline") or "")[:120],
                    "total_invested": (inv.get("investments") or {}).get("total_invested"),
                    "deal_count":     count,
                    "image":          inv.get("image", ""),
                    "website_domain": inv.get("website_domain", ""),
                    "stages":         [s["name"] for s in (inv.get("investor_stages") or [])],
                    "dealroom_url":   inv.get("dealroom_url") or f"https://app.dealroom.co/search?q={inv.get('name', '')}",
                })
                if len(lps) >= 40:
                    break
        except Exception:
            pass

    # If we found very few from transactions, pad with broad top-investors fallback
    if len(lps) < 15:
        r2 = c.get("/investors", params={"sort": "-total_invested", "limit": 400})
        for inv in r2.json().get("data", []):
            if inv["id"] in seen:
                continue
            seen.add(inv["id"])
            types = {t["code"] for t in (inv.get("investor_types") or [])}
            if (types & LP_CODES) and not (types & EXCLUDE):
                lps.append({
                    "id":             inv["id"],
                    "name":           inv["name"],
                    "types":          sorted(types),
                    "hq_city":        inv.get("hq_city", ""),
                    "hq_country":     inv.get("hq_country", ""),
                    "tagline":        (inv.get("tagline") or "")[:120],
                    "total_invested": (inv.get("investments") or {}).get("total_invested"),
                    "deal_count":     0,
                    "image":          inv.get("image", ""),
                    "website_domain": inv.get("website_domain", ""),
                    "stages":         [s["name"] for s in (inv.get("investor_stages") or [])],
                    "dealroom_url":   inv.get("dealroom_url") or f"https://app.dealroom.co/search?q={inv.get('name', '')}",
                })
            if len(lps) >= 40:
                break

    return lps


# ── Step 4: GPT selects + writes rationales ───────────────────────────────────

def _gpt_select(vc_profile: dict, signal: dict, lp_pool: list) -> list:
    """GPT picks 10 most relevant LPs and writes a rationale for each."""
    vc_block = f"""
VC name: {vc_profile['name']}
Tagline: {vc_profile.get('tagline', '')}
Preferred stages: {', '.join(signal['top_rounds'])}
Top geographies: {', '.join(signal['top_countries'])}
HQ: {vc_profile.get('hq_city', '')} {vc_profile.get('hq_country', '')}
"""

    lp_lines = "\n".join(
        f"[{lp['id']}] {lp['name']} | {', '.join(lp['types'])} | "
        f"{lp.get('hq_country', '')} | deals in thesis area: {lp['deal_count']} | {lp.get('tagline', '')}"
        for lp in lp_pool
    )

    prompt = f"""You are a venture capital expert recommending LPs (Limited Partners) for a VC fund.

VC Profile:
{vc_block}

LP pool — institutional investors that have been active in this fund's thesis area:
{lp_lines}

Select the 10 best LP candidates. Prioritise:
1. LPs with more deals in the thesis area (deal_count is the key signal)
2. Geographic alignment with the fund
3. LP type fit (family offices and fund-of-funds suit smaller/emerging managers;
   sovereign wealth funds and pension funds suit established managers)

Return ONLY valid JSON:
{{
  "selected": [
    {{"id": <integer LP id>, "rationale": "1 sentence: what in their investment activity makes them a fit"}},
    ...10 items
  ]
}}"""

    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content).get("selected", [])


def _gpt_vc_presentation(vc_name: str, vc_dr: dict) -> dict:
    dr_block = ""
    if vc_dr:
        stages = ", ".join(s["name"] for s in (vc_dr.get("investor_stages") or []))
        dr_block = f"Stages: {stages}\nHQ: {vc_dr.get('hq_city','')} {vc_dr.get('hq_country','')}\nTagline: {vc_dr.get('tagline','')}"
    prompt = f"""Building a bespoke LP-matching page for a VC fund.
VC: {vc_name}
{dr_block}
Return ONLY valid JSON:
{{
  "tagline": "One-sentence fund thesis, max 100 chars",
  "intro": "2-sentence intro for LPs: what makes this fund a great LP opportunity",
  "accent_color": "#hex (known: 20VC=#000000, Sequoia=#e33d26, a16z=#1652f0, Accel=#0f52ba, Index=#e42313, Lightrock=#22a06b)"
}}"""
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o", temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content)


# ── Main entry ────────────────────────────────────────────────────────────────

def research_lp(vc_name: str) -> dict:
    # 1. Look up VC
    vc_dr = _lookup_vc(vc_name)
    if vc_dr:
        vc_name = vc_dr["name"]

    # 2. VC presentation
    enriched = _gpt_vc_presentation(vc_name, vc_dr)

    # 3. Logo
    logo_url = ""
    if vc_dr and vc_dr.get("image"):
        img = vc_dr["image"]
        logo_url = f"https://{img}" if not img.startswith("http") else img
    domain = (vc_dr.get("website_domain") or "") if vc_dr else ""

    # 4. Thesis signal from portfolio
    vc_id = vc_dr["id"] if vc_dr else None
    if vc_id:
        signal = _build_thesis_signal(vc_id)
    else:
        signal = {"top_rounds": [], "top_countries": [], "tags_by_type": {}, "investor_id": None}

    # 5. Find active LPs in same space
    lp_pool = _find_active_lps(signal)

    # 6. GPT selects best 10
    vc_profile_for_gpt = {
        "name":       vc_name,
        "tagline":    (vc_dr.get("tagline") or "") if vc_dr else "",
        "hq_city":    (vc_dr.get("hq_city") or "") if vc_dr else "",
        "hq_country": (vc_dr.get("hq_country") or "") if vc_dr else "",
    }
    selected = _gpt_select(vc_profile_for_gpt, signal, lp_pool)

    # 7. Merge rationales
    id_to_lp = {lp["id"]: lp for lp in lp_pool}
    lps = []
    for sel in selected:
        lp = id_to_lp.get(sel["id"])
        if not lp:
            continue
        lp_copy = dict(lp)
        lp_copy["rationale"] = sel.get("rationale", "")
        lps.append(lp_copy)

    return {
        "vc_name":      vc_name,
        "logo_url":     logo_url,
        "domain":       domain,
        "accent_color": enriched["accent_color"],
        "tagline":      enriched["tagline"],
        "intro":        enriched["intro"],
        "lps":          lps[:10],
        "signal":       signal,
    }
