"""
Dealroom bespoke outreach page generator — web app.

Run:
    python3 app.py
    open http://localhost:5001
"""

import os, uuid, threading, time
from pathlib import Path
from flask import Flask, Response, request, redirect, send_file, abort
from dotenv import load_dotenv

load_dotenv()

from research import research_investor
from generate import fetch_companies, build_page
from lp_research import research_lp
from lp_generate import build_lp_page

app = Flask(__name__)
OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)


# ── Job tracking ──────────────────────────────────────────────────────────────

class Job:
    def __init__(self, input_val: str, meeting_url: str = ""):
        self.input_val = input_val
        self.meeting_url = meeting_url
        self.messages: list[str] = []   # SSE payload strings
        self.done = False
        self.slug: str | None = None
        self.error: str | None = None

JOBS: dict[str, Job] = {}
LP_JOBS: dict[str, Job] = {}


def _slug(name: str) -> str:
    import re
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s[:40].strip("_")


def run_pipeline(job_id: str, input_val: str):
    job = JOBS[job_id]
    try:
        job.messages.append(f"step|Researching <b>{input_val}</b> via Claude…")
        profile = research_investor(input_val)
        name    = profile["client_name"]
        tags    = ", ".join(profile.get("display_tags", [])[:4])
        job.messages.append(f"step|Thesis extracted for <b>{name}</b> — {tags}")

        job.messages.append("step|Querying Dealroom for rising-star companies…")
        companies = fetch_companies(profile, limit=15)
        job.messages.append(f"step|Found <b>{len(companies)} companies</b> matching thesis")

        slug     = _slug(name)
        out_path = str(OUTPUT / f"{slug}.html")
        job.messages.append("step|Building bespoke page…")
        build_page(profile, companies, out_path, meeting_url=job.meeting_url)

        job.slug = slug
        job.messages.append(f"done|{slug}")
    except Exception as e:
        job.error = str(e)
        job.messages.append(f"error|{e}")
    finally:
        job.done = True


def run_lp_pipeline(job_id: str, vc_name: str):
    job = LP_JOBS[job_id]
    try:
        job.messages.append(f"step|Researching <b>{vc_name}</b> on Dealroom…")
        profile = research_lp(vc_name)
        name    = profile["vc_name"]
        job.messages.append(f"step|Found profile for <b>{name}</b> · fetching LP pool…")

        job.messages.append("step|Asking GPT to select the 10 most relevant LPs…")
        n_lps   = len(profile.get("lps", []))
        job.messages.append(f"step|Selected <b>{n_lps} LPs</b> — building page…")

        slug     = "lp_" + _slug(name)
        out_path = str(OUTPUT / f"{slug}.html")
        build_lp_page(profile, out_path, meeting_url=job.meeting_url)

        job.slug = slug
        job.messages.append(f"done|{slug}")
    except Exception as e:
        job.error = str(e)
        job.messages.append(f"error|{e}")
    finally:
        job.done = True


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    # Collect any already-generated pages for the gallery
    pages = sorted(OUTPUT.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    cards = "".join(_gallery_card(p) for p in pages)
    gallery_section = f"""
      <div class="gallery-title">Recently generated</div>
      <div class="gallery">{cards}</div>
    """ if cards else ""

    return LANDING_HTML.replace("{{GALLERY}}", gallery_section)


@app.route("/generate", methods=["POST"])
def generate():
    input_val   = (request.form.get("q") or "").strip()
    meeting_url = (request.form.get("meeting_url") or "").strip()
    if not input_val:
        return redirect("/")
    job_id = uuid.uuid4().hex[:10]
    JOBS[job_id] = Job(input_val, meeting_url=meeting_url)
    threading.Thread(target=run_pipeline, args=(job_id, input_val), daemon=True).start()
    return redirect(f"/loading/{job_id}")


@app.route("/loading/<job_id>")
def loading(job_id):
    if job_id not in JOBS:
        abort(404)
    job = JOBS[job_id]
    return LOADING_HTML.replace("{{JOB_ID}}", job_id).replace("{{INPUT}}", job.input_val)


@app.route("/stream/<job_id>")
def stream(job_id):
    if job_id not in JOBS:
        abort(404)

    def event_stream():
        sent = 0
        job  = JOBS[job_id]
        while True:
            while sent < len(job.messages):
                yield f"data: {job.messages[sent]}\n\n"
                sent += 1
            if job.done:
                break
            time.sleep(0.4)

    return Response(event_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/view/<slug>")
@app.route("/lp/view/<slug>")
def view(slug):
    p = OUTPUT / f"{slug}.html"
    if not p.exists():
        abort(404)
    return send_file(str(p))


# ── LP routes ─────────────────────────────────────────────────────────────────

@app.route("/lp")
def lp_index():
    pages = sorted(OUTPUT.glob("lp_*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    cards = "".join(_gallery_card(p) for p in pages)
    gallery_section = f"""
      <div class="gallery-title">Recently generated</div>
      <div class="gallery">{cards}</div>
    """ if cards else ""
    return LP_LANDING_HTML.replace("{{GALLERY}}", gallery_section)


@app.route("/lp/generate", methods=["POST"])
def lp_generate():
    vc_name     = (request.form.get("q") or "").strip()
    meeting_url = (request.form.get("meeting_url") or "").strip()
    if not vc_name:
        return redirect("/")
    job_id = uuid.uuid4().hex[:10]
    LP_JOBS[job_id] = Job(vc_name, meeting_url=meeting_url)
    threading.Thread(target=run_lp_pipeline, args=(job_id, vc_name), daemon=True).start()
    return redirect(f"/lp/loading/{job_id}")


@app.route("/lp/loading/<job_id>")
def lp_loading(job_id):
    if job_id not in LP_JOBS:
        abort(404)
    job = LP_JOBS[job_id]
    return LP_LOADING_HTML.replace("{{JOB_ID}}", job_id).replace("{{INPUT}}", job.input_val)


@app.route("/lp/stream/<job_id>")
def lp_stream(job_id):
    if job_id not in LP_JOBS:
        abort(404)

    def event_stream():
        sent = 0
        job  = LP_JOBS[job_id]
        while True:
            while sent < len(job.messages):
                yield f"data: {job.messages[sent]}\n\n"
                sent += 1
            if job.done:
                break
            time.sleep(0.4)

    return Response(event_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Gallery helper ────────────────────────────────────────────────────────────

def _gallery_card(p: Path) -> str:
    slug  = p.stem
    label = slug.replace("_", " ").title()
    # Extract accent color from the HTML
    accent = "#6366f1"
    try:
        txt = p.read_text(encoding="utf-8")
        import re
        m = re.search(r"--accent:(#[0-9a-fA-F]{6})", txt)
        if m:
            accent = m.group(1)
    except Exception:
        pass
    return f"""<a class="gcard" href="/view/{slug}" style="--c:{accent}">
      <div class="gcard-dot" style="background:{accent};"></div>
      <span>{label}</span>
      <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M7 17L17 7M7 7h10v10"/></svg>
    </a>"""


# ── HTML templates ────────────────────────────────────────────────────────────

LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Dealroom · Bespoke VC Outreach</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    :root{
      --bg:#f6f8fa;--white:#ffffff;--border:#e3e8ef;--border2:#d1d9e0;
      --text:#0f1117;--muted:#64748b;--muted2:#94a3b8;
      --blue:#3662e3;--blue-dim:rgba(54,98,227,.08);--blue-bdr:rgba(54,98,227,.2);
      --blue-hover:#2952d3;
    }
    body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;}

    /* NAV */
    nav{display:flex;align-items:center;justify-content:space-between;padding:0 32px;height:56px;border-bottom:1px solid var(--border);background:var(--white);}
    .nav-left{display:flex;align-items:center;gap:10px;}
    .dr-mark{width:28px;height:28px;background:#3662e3;border-radius:7px;display:flex;align-items:center;justify-content:center;flex-shrink:0;}
    .dr-mark svg{display:block;}
    .dr-wordmark{font-size:15px;font-weight:700;color:var(--text);letter-spacing:-.3px;}
    .dr-wordmark span{color:var(--muted2);}
    .nav-badge{font-size:11px;font-weight:600;color:var(--blue);background:var(--blue-dim);border:1px solid var(--blue-bdr);padding:3px 10px;border-radius:20px;letter-spacing:.1px;}

    /* HERO */
    main{flex:1;display:flex;flex-direction:column;align-items:center;padding:72px 24px 80px;}
    .eyebrow{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;color:var(--blue);margin-bottom:20px;letter-spacing:.2px;}
    .eyebrow-dot{width:6px;height:6px;border-radius:50%;background:var(--blue);}
    h1{font-size:clamp(32px,5vw,54px);font-weight:800;text-align:center;line-height:1.1;letter-spacing:-1.8px;color:var(--text);max-width:640px;margin-bottom:14px;}
    h1 em{font-style:normal;color:var(--blue);}
    .sub{font-size:15px;color:var(--muted);text-align:center;max-width:440px;line-height:1.65;margin-bottom:40px;font-weight:400;}

    /* MODE TABS */
    .mode-tabs{display:inline-flex;background:var(--white);border:1px solid var(--border);border-radius:10px;padding:3px;gap:2px;margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,.06);}
    .tab{display:flex;align-items:center;gap:6px;padding:8px 18px;border-radius:7px;font-size:13px;font-weight:600;color:var(--muted);cursor:pointer;transition:all .15s;border:none;background:transparent;font-family:inherit;}
    .tab svg{flex-shrink:0;opacity:.7;}
    .tab.active{background:var(--blue);color:#fff;box-shadow:0 1px 4px rgba(54,98,227,.35);}
    .tab.active svg{opacity:1;}
    .tab:hover:not(.active){background:var(--bg);color:var(--text);}

    /* PANELS */
    .panel{display:none;flex-direction:column;align-items:center;width:100%;max-width:580px;}
    .panel.active{display:flex;}
    .panel-desc{font-size:13px;color:var(--muted);text-align:center;margin-bottom:14px;line-height:1.6;}

    /* INPUT */
    .input-wrap{width:100%;background:var(--white);border:1.5px solid var(--border);border-radius:12px;padding:5px 5px 5px 18px;display:flex;align-items:center;gap:8px;box-shadow:0 2px 12px rgba(0,0,0,.06);transition:border-color .15s,box-shadow .15s;}
    .input-wrap:focus-within{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-dim),0 2px 12px rgba(0,0,0,.06);}
    .input-wrap input{flex:1;background:transparent;border:none;outline:none;font-size:14px;font-family:inherit;color:var(--text);padding:9px 0;font-weight:500;}
    .input-wrap input::placeholder{color:var(--muted2);font-weight:400;}
    .input-wrap button{background:var(--blue);border:none;border-radius:8px;padding:10px 20px;font-size:13px;font-weight:700;color:#fff;cursor:pointer;font-family:inherit;white-space:nowrap;display:flex;align-items:center;gap:6px;transition:background .15s;letter-spacing:.1px;}
    .input-wrap button:hover{background:var(--blue-hover);}
    .input-wrap button svg{flex-shrink:0;}

    /* PILLS */
    .examples{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;justify-content:center;}
    .ex-pill{background:var(--white);border:1px solid var(--border);border-radius:20px;padding:5px 13px;font-size:12px;font-weight:500;color:var(--muted);cursor:pointer;transition:all .12s;}
    .ex-pill:hover{border-color:var(--blue-bdr);color:var(--blue);background:var(--blue-dim);}

    /* DIVIDER */
    .divider{display:flex;align-items:center;gap:12px;width:100%;max-width:580px;margin:48px 0 20px;}
    .divider-line{flex:1;height:1px;background:var(--border);}
    .divider-label{font-size:11px;font-weight:600;color:var(--muted2);letter-spacing:.5px;text-transform:uppercase;white-space:nowrap;}

    /* GALLERY */
    .gallery{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:580px;}
    .gcard{display:flex;align-items:center;gap:9px;background:var(--white);border:1px solid var(--border);border-radius:8px;padding:9px 14px;text-decoration:none;color:var(--text);font-size:12px;font-weight:600;transition:all .12s;border-left:3px solid var(--c,#3662e3);}
    .gcard:hover{border-color:var(--c,#3662e3);box-shadow:0 2px 8px rgba(0,0,0,.08);transform:translateY(-1px);}
    .gcard-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;}
    .gcard svg{color:var(--muted2);margin-left:2px;}
  </style>
</head>
<body>
<nav>
  <div class="nav-left">
    <div class="dr-mark" style="background:transparent;width:auto;height:auto;border-radius:0;">
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="32" height="32" rx="6" fill="#0f1a2e"/>
        <rect x="8" y="20" width="3.5" height="6" rx="1" fill="white"/>
        <rect x="14" y="14" width="3.5" height="12" rx="1" fill="white"/>
        <rect x="20" y="9" width="3.5" height="17" rx="1" fill="white"/>
      </svg>
    </div>
    <span class="dr-wordmark">dealroom<span>.co</span></span>
  </div>
  <span class="nav-badge">Bespoke Pages</span>
</nav>

<main>
  <p class="sub">Recommend companies to a VC based on their thesis, or find the right Limited Partners for a fund.</p>

  <div class="mode-tabs">
    <button class="tab active" id="tab-co" onclick="switchTab('co')">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 7V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v2"/></svg>
      Company recommendations
    </button>
    <button class="tab" id="tab-lp" onclick="switchTab('lp')">
      <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg>
      LP recommendations
    </button>
  </div>

  <div class="panel active" id="panel-co">
    <p class="panel-desc">Enter a VC name, their website, or a news article about their latest fund.</p>
    <form action="/generate" method="POST" style="width:100%;display:flex;flex-direction:column;gap:8px;">
      <div class="input-wrap">
        <input name="q" id="q-co" type="text" placeholder="e.g. Accel, Sequoia, or paste a URL…" autofocus autocomplete="off"/>
        <button type="submit">
          Generate
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
      <div class="input-wrap" style="box-shadow:none;padding:4px 4px 4px 14px;">
        <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="color:#94a3b8;flex-shrink:0;"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
        <input name="meeting_url" type="url" placeholder="Meeting link (e.g. https://calendly.com/…)" autocomplete="off" style="font-size:13px;"/>
      </div>
    </form>
    <div class="examples">
      <span class="ex-pill" onclick="setQ('co','Index Ventures')">Index Ventures</span>
      <span class="ex-pill" onclick="setQ('co','Lightrock')">Lightrock</span>
      <span class="ex-pill" onclick="setQ('co','Accel')">Accel</span>
      <span class="ex-pill" onclick="setQ('co','Sequoia Capital')">Sequoia Capital</span>
      <span class="ex-pill" onclick="setQ('co','Balderton Capital')">Balderton Capital</span>
    </div>
  </div>

  <div class="panel" id="panel-lp">
    <p class="panel-desc">Enter a VC fund name — we'll match LPs based on their previous investment activity.</p>
    <form id="lp-form" action="/lp/generate" method="POST" style="width:100%;display:flex;flex-direction:column;gap:8px;">
      <div class="input-wrap">
        <input name="q" id="q-lp" type="text" placeholder="e.g. The Twenty Minute VC, Sequoia…" autocomplete="off"/>
        <button type="submit">
          Find LPs
          <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        </button>
      </div>
      <div class="input-wrap" style="box-shadow:none;padding:4px 4px 4px 14px;">
        <svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" style="color:#94a3b8;flex-shrink:0;"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>
        <input name="meeting_url" id="meeting-url" type="url" placeholder="Meeting link (e.g. https://calendly.com/…)" autocomplete="off" style="font-size:13px;"/>
      </div>
    </form>
    <div class="examples">
      <span class="ex-pill" onclick="setQ('lp','The Twenty Minute VC')">20VC</span>
      <span class="ex-pill" onclick="setQ('lp','Sequoia Capital')">Sequoia</span>
      <span class="ex-pill" onclick="setQ('lp','Lightrock')">Lightrock</span>
      <span class="ex-pill" onclick="setQ('lp','Accel')">Accel</span>
    </div>
  </div>

  {{GALLERY}}
</main>

<script>
  function switchTab(mode) {
    document.getElementById('tab-co').classList.toggle('active', mode === 'co');
    document.getElementById('tab-lp').classList.toggle('active', mode === 'lp');
    document.getElementById('panel-co').classList.toggle('active', mode === 'co');
    document.getElementById('panel-lp').classList.toggle('active', mode === 'lp');
    if (mode === 'co') document.getElementById('q-co').focus();
    else document.getElementById('q-lp').focus();
  }
  function setQ(panel, v) {
    document.getElementById('q-' + panel).value = v;
    document.getElementById('q-' + panel).focus();
  }
</script>
</body>
</html>"""


LOADING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Generating page…</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    :root{--bg:#f6f8fa;--white:#fff;--border:#e3e8ef;--text:#111827;--muted:#6b7280;--blue:#3662e3;--blue-dim:rgba(54,98,227,.1);--green:#16a34a;}
    body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px;}

    nav{position:fixed;top:0;left:0;right:0;height:52px;display:flex;align-items:center;padding:0 28px;border-bottom:1px solid var(--border);background:var(--white);z-index:100;}
    .nav-logo{display:flex;align-items:center;gap:8px;text-decoration:none;}
    .nav-mark{width:26px;height:26px;background:var(--blue);border-radius:6px;display:flex;align-items:center;justify-content:center;}
    .nav-mark svg{display:block;}
    .nav-name{font-size:14px;font-weight:700;color:#111827;letter-spacing:-.2px;}

    .card{background:var(--white);border:1px solid var(--border);border-radius:16px;padding:40px;width:100%;max-width:520px;margin-top:52px;box-shadow:0 1px 8px rgba(0,0,0,.06);}
    .card-top{display:flex;align-items:center;gap:14px;margin-bottom:28px;}
    .spinner{width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite;flex-shrink:0;}
    @keyframes spin{to{transform:rotate(360deg);}}
    .card-top-text h2{font-size:16px;font-weight:700;color:var(--text);margin-bottom:3px;}
    .card-top-text p{font-size:12px;color:var(--muted);}

    .steps{display:flex;flex-direction:column;gap:10px;}
    .step{display:flex;align-items:flex-start;gap:12px;font-size:13px;color:var(--muted);opacity:0;transform:translateY(6px);transition:opacity .4s,transform .4s;}
    .step.visible{opacity:1;transform:none;}
    .step.done .step-icon{background:var(--green);border-color:var(--green);color:#fff;}
    .step.active .step-icon{background:var(--blue);border-color:var(--blue);color:#fff;animation:pulse 1s ease-in-out infinite;}
    @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.6;}}
    .step-icon{width:20px;height:20px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;font-size:10px;font-weight:700;}
    .step-text{line-height:1.5;padding-top:1px;}
    .step-text b{color:var(--text);}

    .done-banner{display:none;background:rgba(22,163,74,.08);border:1px solid rgba(22,163,74,.25);border-radius:10px;padding:14px 18px;margin-top:20px;font-size:13px;color:var(--green);align-items:center;gap:10px;}
    .done-banner.show{display:flex;}
    .done-banner a{color:var(--green);font-weight:600;text-decoration:none;border-bottom:1px solid rgba(22,163,74,.35);}

    .error-banner{display:none;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.25);border-radius:10px;padding:14px 18px;margin-top:20px;font-size:13px;color:#dc2626;}
    .error-banner.show{display:block;}
  </style>
</head>
<body>
<nav>
  <a class="nav-logo" href="/">
    <div class="nav-mark">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 2h5a4 4 0 010 8H3V2z" fill="white"/><rect x="3" y="7" width="2" height="3" fill="white"/></svg>
    </div>
    <span class="nav-name">dealroom.co</span>
  </a>
</nav>

<div class="card">
  <div class="card-top">
    <div class="spinner" id="spinner"></div>
    <div class="card-top-text">
      <h2>Building your page</h2>
      <p>Researching <strong>{{INPUT}}</strong></p>
    </div>
  </div>
  <div class="steps" id="steps"></div>
  <div class="done-banner" id="done">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
    Page ready — <a id="done-link" href="#">open it</a> (redirecting…)
  </div>
  <div class="error-banner" id="err"></div>
</div>

<script>
const src = new EventSource('/stream/{{JOB_ID}}');
let stepCount = 0;

src.onmessage = function(e) {
  const [type, ...rest] = e.data.split('|');
  const text = rest.join('|');

  if (type === 'step') {
    const prev = document.querySelector('.step.active');
    if (prev) { prev.classList.remove('active'); prev.classList.add('done'); prev.querySelector('.step-icon').textContent = '✓'; }

    const el = document.createElement('div');
    el.className = 'step active';
    el.innerHTML = `<div class="step-icon">${++stepCount}</div><div class="step-text">${text}</div>`;
    document.getElementById('steps').appendChild(el);
    requestAnimationFrame(() => el.classList.add('visible'));
  }

  if (type === 'done') {
    const prev = document.querySelector('.step.active');
    if (prev) { prev.classList.remove('active'); prev.classList.add('done'); prev.querySelector('.step-icon').textContent = '✓'; }

    document.getElementById('spinner').style.borderTopColor = '#16a34a';
    document.getElementById('spinner').style.animationDuration = '0s';
    document.getElementById('spinner').style.borderColor = '#16a34a';

    const slug = text;
    const url  = '/view/' + slug;
    const banner = document.getElementById('done');
    banner.classList.add('show');
    document.getElementById('done-link').href = url;
    src.close();
    setTimeout(() => window.location.href = url, 1800);
  }

  if (type === 'error') {
    const el = document.getElementById('err');
    el.textContent = 'Error: ' + text;
    el.classList.add('show');
    src.close();
  }
};
</script>
</body>
</html>"""


LP_LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Dealroom · LP Recommendations</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    :root{
      --bg:#f6f8fa;--white:#fff;--border:#e3e8ef;
      --text:#111827;--muted:#6b7280;--muted2:#9ca3af;
      --blue:#3662e3;--blue-dim:rgba(54,98,227,.1);--blue-bdr:rgba(54,98,227,.25);
    }
    body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;}

    nav{height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;border-bottom:1px solid var(--border);background:var(--white);}
    .nav-logo{display:flex;align-items:center;gap:8px;text-decoration:none;}
    .nav-mark{width:26px;height:26px;background:var(--blue);border-radius:6px;display:flex;align-items:center;justify-content:center;}
    .nav-mark svg{display:block;}
    .nav-name{font-size:14px;font-weight:700;color:#111827;letter-spacing:-.2px;}
    .nav-right{display:flex;align-items:center;gap:12px;}
    .nav-tag{font-size:11px;background:var(--blue-dim);border:1px solid var(--blue-bdr);color:var(--blue);padding:3px 10px;border-radius:20px;font-weight:600;letter-spacing:.3px;}
    .nav-back{font-size:12px;color:var(--muted);text-decoration:none;display:flex;align-items:center;gap:5px;}
    .nav-back:hover{color:var(--text);}

    main{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:64px 24px;}

    .hero-label{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:var(--blue);margin-bottom:18px;}
    h1{font-size:clamp(26px,4.5vw,46px);font-weight:800;text-align:center;line-height:1.15;letter-spacing:-1.5px;color:var(--text);max-width:680px;margin-bottom:16px;}
    h1 .hl{color:var(--blue);}
    .sub{font-size:15px;color:var(--muted);text-align:center;max-width:460px;line-height:1.65;margin-bottom:40px;}

    .search-wrap{width:100%;max-width:560px;}
    .input-card{background:var(--white);border:1.5px solid var(--border);border-radius:14px;padding:5px 5px 5px 18px;display:flex;align-items:center;gap:8px;box-shadow:0 1px 6px rgba(0,0,0,.06);transition:border-color .15s,box-shadow .15s;}
    .input-card:focus-within{border-color:var(--blue);box-shadow:0 0 0 3px var(--blue-dim);}
    .input-card input{flex:1;background:transparent;border:none;outline:none;font-size:15px;font-family:inherit;color:var(--text);padding:10px 0;}
    .input-card input::placeholder{color:var(--muted2);}
    .input-card button{background:var(--blue);border:none;border-radius:10px;padding:11px 20px;font-size:13px;font-weight:600;color:#fff;cursor:pointer;font-family:inherit;white-space:nowrap;display:flex;align-items:center;gap:7px;transition:background .15s,opacity .15s;}
    .input-card button:hover{background:#2850c7;}

    .examples{display:flex;flex-wrap:wrap;gap:7px;margin-top:12px;justify-content:center;}
    .ex-pill{background:var(--white);border:1px solid var(--border);border-radius:20px;padding:5px 13px;font-size:12px;color:var(--muted);cursor:pointer;transition:border-color .15s,color .15s;}
    .ex-pill:hover{border-color:var(--blue-bdr);color:var(--blue);}

    .gallery-title{font-size:11px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:var(--muted2);text-align:center;margin-top:56px;margin-bottom:14px;}
    .gallery{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;max-width:560px;}
    .gcard{display:flex;align-items:center;gap:9px;background:var(--white);border:1px solid var(--border);border-radius:10px;padding:9px 15px;text-decoration:none;color:var(--text);font-size:13px;font-weight:500;transition:border-color .15s,box-shadow .15s;border-left:3px solid var(--c,var(--blue));}
    .gcard:hover{border-color:var(--c,var(--blue));box-shadow:0 2px 8px rgba(0,0,0,.07);}
    .gcard-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
    .gcard svg{color:var(--muted2);margin-left:3px;}
  </style>
</head>
<body>
<nav>
  <a class="nav-logo" href="/">
    <div class="nav-mark">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 2h5a4 4 0 010 8H3V2z" fill="white"/><rect x="3" y="7" width="2" height="3" fill="white"/></svg>
    </div>
    <span class="nav-name">dealroom.co</span>
  </a>
  <div class="nav-right">
    <a class="nav-back" href="/">
      <svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
      Home
    </a>
    <span class="nav-tag">LP Recommendations</span>
  </div>
</nav>
<main>
  <div class="hero-label">Powered by Dealroom × GPT-4o</div>
  <h1>Find the right <span class="hl">LPs</span><br>for your fund</h1>
  <p class="sub">Enter a VC fund name — we'll find the most relevant Limited Partners matched to their stage and thesis.</p>

  <div class="search-wrap">
    <form class="input-card" action="/lp/generate" method="POST">
      <input name="q" type="text" placeholder="e.g. The Twenty Minute VC, Sequoia, Accel…" autofocus autocomplete="off"/>
      <button type="submit">
        <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path d="M5 12h14M12 5l7 7-7 7"/></svg>
        Find LPs
      </button>
    </form>
    <div class="examples">
      <span class="ex-pill" onclick="setQ('The Twenty Minute VC')">20VC</span>
      <span class="ex-pill" onclick="setQ('Sequoia Capital')">Sequoia</span>
      <span class="ex-pill" onclick="setQ('Lightrock')">Lightrock</span>
      <span class="ex-pill" onclick="setQ('Accel')">Accel</span>
    </div>
  </div>

  {{GALLERY}}
</main>

<script>
  function setQ(v) {
    document.querySelector('input[name=q]').value = v;
    document.querySelector('input[name=q]').focus();
  }
</script>
</body>
</html>"""


LP_LOADING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Finding LPs…</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
    :root{--bg:#f6f8fa;--white:#fff;--border:#e3e8ef;--text:#111827;--muted:#6b7280;--blue:#3662e3;--blue-dim:rgba(54,98,227,.1);--green:#16a34a;}
    body{font-family:'Plus Jakarta Sans',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:32px;}

    nav{position:fixed;top:0;left:0;right:0;height:52px;display:flex;align-items:center;padding:0 28px;border-bottom:1px solid var(--border);background:var(--white);z-index:100;}
    .nav-logo{display:flex;align-items:center;gap:8px;text-decoration:none;}
    .nav-mark{width:26px;height:26px;background:var(--blue);border-radius:6px;display:flex;align-items:center;justify-content:center;}
    .nav-mark svg{display:block;}
    .nav-name{font-size:14px;font-weight:700;color:#111827;letter-spacing:-.2px;}

    .card{background:var(--white);border:1px solid var(--border);border-radius:16px;padding:40px;width:100%;max-width:520px;margin-top:52px;box-shadow:0 1px 8px rgba(0,0,0,.06);}
    .card-top{display:flex;align-items:center;gap:14px;margin-bottom:28px;}
    .spinner{width:36px;height:36px;border:3px solid var(--border);border-top-color:var(--blue);border-radius:50%;animation:spin .8s linear infinite;flex-shrink:0;}
    @keyframes spin{to{transform:rotate(360deg);}}
    .card-top-text h2{font-size:16px;font-weight:700;color:var(--text);margin-bottom:3px;}
    .card-top-text p{font-size:12px;color:var(--muted);}

    .steps{display:flex;flex-direction:column;gap:10px;}
    .step{display:flex;align-items:flex-start;gap:12px;font-size:13px;color:var(--muted);opacity:0;transform:translateY(6px);transition:opacity .4s,transform .4s;}
    .step.visible{opacity:1;transform:none;}
    .step.done .step-icon{background:var(--green);border-color:var(--green);color:#fff;}
    .step.active .step-icon{background:var(--blue);border-color:var(--blue);color:#fff;animation:pulse 1s ease-in-out infinite;}
    @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.6;}}
    .step-icon{width:20px;height:20px;border-radius:50%;border:2px solid var(--border);display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;font-size:10px;font-weight:700;}
    .step-text{line-height:1.5;padding-top:1px;}
    .step-text b{color:var(--text);}

    .done-banner{display:none;background:rgba(22,163,74,.08);border:1px solid rgba(22,163,74,.25);border-radius:10px;padding:14px 18px;margin-top:20px;font-size:13px;color:var(--green);align-items:center;gap:10px;}
    .done-banner.show{display:flex;}
    .done-banner a{color:var(--green);font-weight:600;text-decoration:none;border-bottom:1px solid rgba(22,163,74,.35);}

    .error-banner{display:none;background:rgba(239,68,68,.06);border:1px solid rgba(239,68,68,.25);border-radius:10px;padding:14px 18px;margin-top:20px;font-size:13px;color:#dc2626;}
    .error-banner.show{display:block;}
  </style>
</head>
<body>
<nav>
  <a class="nav-logo" href="/">
    <div class="nav-mark">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M3 2h5a4 4 0 010 8H3V2z" fill="white"/><rect x="3" y="7" width="2" height="3" fill="white"/></svg>
    </div>
    <span class="nav-name">dealroom.co</span>
  </a>
</nav>

<div class="card">
  <div class="card-top">
    <div class="spinner" id="spinner"></div>
    <div class="card-top-text">
      <h2>Finding LPs…</h2>
      <p>Matching investors for <strong>{{INPUT}}</strong></p>
    </div>
  </div>
  <div class="steps" id="steps"></div>
  <div class="done-banner" id="done">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M20 6L9 17l-5-5"/></svg>
    LP page ready — <a id="done-link" href="#">open it</a> (redirecting…)
  </div>
  <div class="error-banner" id="err"></div>
</div>

<script>
const src = new EventSource('/lp/stream/{{JOB_ID}}');
let stepCount = 0;

src.onmessage = function(e) {
  const [type, ...rest] = e.data.split('|');
  const text = rest.join('|');

  if (type === 'step') {
    const prev = document.querySelector('.step.active');
    if (prev) { prev.classList.remove('active'); prev.classList.add('done'); prev.querySelector('.step-icon').textContent = '✓'; }

    const el = document.createElement('div');
    el.className = 'step active';
    el.innerHTML = `<div class="step-icon">${++stepCount}</div><div class="step-text">${text}</div>`;
    document.getElementById('steps').appendChild(el);
    requestAnimationFrame(() => el.classList.add('visible'));
  }

  if (type === 'done') {
    const prev = document.querySelector('.step.active');
    if (prev) { prev.classList.remove('active'); prev.classList.add('done'); prev.querySelector('.step-icon').textContent = '✓'; }

    document.getElementById('spinner').style.borderTopColor = '#16a34a';
    document.getElementById('spinner').style.animationDuration = '0s';
    document.getElementById('spinner').style.borderColor = '#16a34a';

    const slug = text;
    const url  = '/lp/view/' + slug;
    const banner = document.getElementById('done');
    banner.classList.add('show');
    document.getElementById('done-link').href = url;
    src.close();
    setTimeout(() => window.location.href = url, 1800);
  }

  if (type === 'error') {
    const el = document.getElementById('err');
    el.textContent = 'Error: ' + text;
    el.classList.add('show');
    src.close();
  }
};
</script>
</body>
</html>"""


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("▸ Dealroom bespoke page generator running at http://localhost:5001")
    print("▸ LP recommendations at http://localhost:5001/lp")
    app.run(host="0.0.0.0", port=5001, threaded=True, debug=False)
