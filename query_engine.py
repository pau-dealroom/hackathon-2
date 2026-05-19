"""
Dealroom auto-query engine.

Usage:
    python query_engine.py "energy tech"
    python query_engine.py "quantum"
    python query_engine.py "life sciences"

Returns top companies for the theme as JSON.
"""

import os, sys, json, requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID     = os.environ["DEALROOM_CLIENT_ID"]
CLIENT_SECRET = os.environ["DEALROOM_CLIENT_SECRET"]
USER_AGENT    = os.environ["DEALROOM_USER_AGENT"]
API_BASE      = os.environ.get("DEALROOM_API_BASE", "https://api-next.beta.dealroom.co")
AUTH_URL      = "https://accounts.beta.dealroom.co/oauth/token"
AUDIENCE      = API_BASE

# ── Theme → search terms mapping ─────────────────────────────────────────────
# Maps a plain-English theme to lists of industry/sub-industry/sector search terms.
THEME_MAP = {
    "energy tech":    {"industry": ["energy"], "sub_industry": ["clean energy", "energy storage", "energy efficiency"], "sector": ["energy tech", "solar energy", "wind energy", "renewable energy"]},
    "clean energy":   {"industry": ["energy"], "sub_industry": ["clean energy", "energy efficiency"], "sector": ["solar energy", "wind energy", "renewable energy", "energy saving"]},
    "quantum":        {"industry": [],          "sub_industry": [],                                    "sector": ["quantum computing", "quantum", "quantum cryptography"]},
    "life sciences":  {"industry": ["health"],  "sub_industry": ["biotech", "pharmaceuticals"],        "sector": ["life sciences", "genomics", "drug discovery", "diagnostics"]},
    "fintech":        {"industry": ["fintech"], "sub_industry": [],                                    "sector": ["payments", "lending", "banking", "insurtech"]},
    "ai":             {"industry": [],          "sub_industry": ["artificial intelligence"],           "sector": ["machine learning", "generative ai", "computer vision", "nlp"]},
    "climate tech":   {"industry": ["energy"],  "sub_industry": ["clean energy"],                     "sector": ["carbon capture", "renewable energy", "energy efficiency", "waste to energy"]},
    "deeptech":       {"industry": [],          "sub_industry": [],                                    "sector": ["deep tech", "quantum computing", "robotics", "semiconductors"]},
}

def _normalize(theme: str) -> str:
    return theme.lower().strip()


class DealroomClient:
    def __init__(self):
        self._token = None
        self._refresh_token()

    def _refresh_token(self):
        r = requests.post(AUTH_URL, json={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "audience": AUDIENCE, "grant_type": "client_credentials"
        })
        r.raise_for_status()
        self._token = r.json()["access_token"]

    def _headers(self):
        return {
            "Authorization": f"Bearer {self._token}",
            "User-Agent": USER_AGENT,
            "X-Client-Id": CLIENT_ID,
        }

    def get(self, path: str, **kwargs):
        url = f"{API_BASE}/api{path}"
        r = requests.get(url, headers=self._headers(), **kwargs)
        if r.status_code == 401:
            self._refresh_token()
            r = requests.get(url, headers=self._headers(), **kwargs)
        r.raise_for_status()
        return r


def resolve_location_ids(client: DealroomClient, country_names: list[str]) -> list[int]:
    """Resolve country name strings to Dealroom location IDs."""
    ids = []
    for name in country_names:
        try:
            r = client.get("/filters/location/values", params={"q": name, "limit": 3})
            for item in r.json().get("data", []):
                if item.get("id") and item["id"] not in ids:
                    ids.append(item["id"])
                    break  # take best match per country
        except Exception:
            pass
    return ids


def resolve_tag_ids(client: DealroomClient, terms: dict) -> list[int]:
    """Resolve theme search terms to Dealroom tag IDs."""
    ids = []
    for tag_type, queries in terms.items():
        for q in queries:
            r = client.get("/filters/tag_id/values", params={"q": q, "type": tag_type, "limit": 5})
            for item in r.json().get("data", []):
                if item.get("id") and item["id"] not in ids:
                    ids.append(item["id"])
    return ids


def fetch_companies(client: DealroomClient, tag_ids: list[int], limit: int = 12) -> list[dict]:
    """Fetch top companies matching the given tag IDs."""
    if not tag_ids:
        return []

    tag_filter = "|".join(str(i) for i in tag_ids)
    filter_expr = f"tag_id[in_any]:{tag_filter}"

    r = client.get("/entities", params={
        "filter": filter_expr,
        "sort": "-total_funding",
        "limit": limit,
    })
    data = r.json().get("data", [])

    companies = []
    for c in data:
        funding = c.get("funding_summary", {}) or {}
        companies.append({
            "name":          c.get("name", ""),
            "tagline":       c.get("tagline", ""),
            "hq_country":    c.get("hq_country", ""),
            "hq_city":       c.get("hq_city", ""),
            "total_funding": funding.get("total_funding"),
            "employee_count": c.get("employee_count"),
            "launch_year":   c.get("launch_year"),
            "website":       c.get("website", ""),
            "dealroom_url":  c.get("dealroom_url", ""),
            "is_unicorn":    c.get("is_unicorn", False),
            "is_rising_star": c.get("is_rising_star", False),
            "tags":          [t["name"] for t in (c.get("tags") or []) if t.get("name")][:6],
        })
    return companies


def query_theme(theme: str, limit: int = 12) -> dict:
    """Main entry point: theme string → structured company data."""
    key = _normalize(theme)
    terms = THEME_MAP.get(key)

    client = DealroomClient()

    if terms:
        tag_ids = resolve_tag_ids(client, terms)
    else:
        # Fallback: search all tag types for the raw theme string
        tag_ids = resolve_tag_ids(client, {
            "industry":     [theme],
            "sub_industry": [theme],
            "sector":       [theme],
        })

    if not tag_ids:
        return {"theme": theme, "tag_ids": [], "companies": [], "error": "No matching taxonomy IDs found"}

    companies = fetch_companies(client, tag_ids, limit=limit)
    return {"theme": theme, "tag_ids": tag_ids, "companies": companies}


if __name__ == "__main__":
    theme = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "energy tech"
    result = query_theme(theme)
    print(json.dumps(result, indent=2))
