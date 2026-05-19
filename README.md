# Dealroom Bespoke Outreach Pages

Generates a personalised Dealroom company-discovery page for any VC or research fund.  
Give it a firm name **or** a link to a news article about their focus — it auto-researches their thesis, finds their logo, queries Dealroom for matching early-stage companies, and produces a dark-themed HTML page ready to share.

---

## How it works

```
Investor name  ─┐
                ├─▶  Claude (thesis + logo + tags)  ─▶  Dealroom API  ─▶  HTML page
News article URL┘
```

1. **Claude** reads the investor name or article URL and extracts their thesis, brand colour, logo domain, and the Dealroom taxonomy terms to search for.  
2. The script resolves those terms to **Dealroom tag IDs** via `/api/filters/tag_id/values`.  
3. It fetches **rising-star companies** in the investor's funding range via `/api/entities`.  
4. Renders a bespoke dark HTML page with the investor's logo, accent colour, and company table.

---

## Setup (5 minutes)

### 1. Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create `.env`

Copy and fill in your keys:

```bash
cp .env.example .env
```

`.env` needs four values:

```
DEALROOM_API_BASE="https://api-next.beta.dealroom.co"
DEALROOM_CLIENT_ID="your-client-id"
DEALROOM_CLIENT_SECRET="your-client-secret"
DEALROOM_USER_AGENT="your-project/0.1 (your@email.com)"

ANTHROPIC_API_KEY="sk-ant-..."
```

**Dealroom key** — go to `https://app-next.beta.dealroom.co/settings/api`, click **+ Create key**, choose **Programmatic (M2M)**, copy both `client_id` and `client_secret`.

**Anthropic key** — get one at `https://console.anthropic.com/`.

### 3. Keep secrets out of git

```bash
echo ".env" >> .gitignore
```

---

## Usage

```bash
# From an investor name
python generate.py --investor "Accel"

# From a news article about a thesis shift
python generate.py --url "https://techcrunch.com/2024/03/accel-climate-fund"

# Custom output file and company limit
python generate.py --investor "Sequoia Capital" --out sequoia.html --limit 20

# Short flags
python generate.py -i "Balderton Capital" -o balderton.html
```

Open the output HTML file in any browser — no server needed.

---

## Files

| File | Purpose |
|------|---------|
| `generate.py` | Main CLI — ties everything together |
| `research.py` | Claude-powered VC thesis extraction |
| `query_engine.py` | Dealroom API client + tag resolution |
| `requirements.txt` | Python dependencies |
| `.env` | Your secrets (not committed) |
| `.env.example` | Template to copy |

---

## Examples already generated

| File | Investor | Theme |
|------|----------|-------|
| `index_ventures.html` | Index Ventures | AI, Fintech, Dev Tools |
| `lightrock.html` | Lightrock | Energy Tech |

---

## Tips

- **Logo**: fetched automatically via Clearbit (`logo.clearbit.com/{domain}`). Falls back to styled initials if unavailable.
- **Rising Star filter**: Dealroom's quality flag for high-trajectory early-stage companies — the best signal when `growth_stage` is sparsely populated in the API.
- **Funding range**: Claude sets this from the investor's typical check size. Override it in `research.py → PROFILE_SCHEMA` if needed.
- **Adding a new theme to `query_engine.py`**: add an entry to `THEME_MAP` with `industry`, `sub_industry`, and `sector` lists to skip the Claude step entirely.
