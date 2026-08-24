from datetime import datetime
import io
import json
import os
import re
import sqlite3
import time
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from duckduckgo_search import DDGS
from google import genai
import markdown
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from textblob import TextBlob
from xhtml2pdf import pisa

# 1. Page Configuration & Theme
st.set_page_config(
    page_title="StratIntel Enterprise • Market Intelligence OS",
    page_icon="https://api.iconify.design/lucide:activity.svg?color=%2338bdf8",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, p, div, span, label, input, button, select, textarea, h1, h2, h3, h4, h5, h6 {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }

    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 5rem;
        max-width: 1280px;
    }

    /* Executive Hero Header */
    .brand-hero {
        background: radial-gradient(100% 100% at 50% 0%, rgba(30, 58, 138, 0.45) 0%, rgba(15, 23, 42, 0.9) 100%);
        border: 1px solid rgba(56, 189, 248, 0.25);
        border-radius: 16px;
        padding: 1.5rem 2rem;
        margin-bottom: 1.5rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }
    .brand-title {
        font-size: 2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        background: linear-gradient(90deg, #38BDF8 0%, #818CF8 50%, #C084FC 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .brand-sub {
        color: #94A3B8;
        font-size: 0.95rem;
    }

    /* Status Pills */
    .pill-tag {
        display: inline-flex;
        align-items: center;
        padding: 0.25rem 0.75rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 9999px;
        background: rgba(15, 23, 42, 0.6);
        color: #38BDF8;
        border: 1px solid rgba(56, 189, 248, 0.3);
        margin-right: 0.5rem;
        margin-top: 0.5rem;
    }

    /* Metric Cards */
    .stat-card {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1rem 1.25rem;
        text-align: left;
    }
    .stat-value {
        font-size: 1.35rem;
        font-weight: 700;
        color: #F8FAFC;
    }
    .stat-label {
        font-size: 0.75rem;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Onboarding Card */
    .onboarding-card {
        background: rgba(15, 23, 42, 0.9);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 16px;
        padding: 2.5rem;
        max-width: 650px;
        margin: 3rem auto;
        box-shadow: 0 12px 40px -10px rgba(0, 0, 0, 0.7);
        text-align: center;
    }

    .user-tag-header {
        font-size: 0.75rem;
        font-weight: 600;
        color: #94a3b8;
        margin-bottom: 3px;
        margin-left: 2px;
        letter-spacing: 0.02em;
    }

    /* Typo Normalization Banner */
    .typo-banner {
        background: rgba(234, 179, 8, 0.12);
        border: 1px solid rgba(234, 179, 8, 0.35);
        color: #fde047;
        padding: 0.6rem 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# 2. Database Engine with Profile & Report Persistence
DB_FILE = "reports_history.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            topic TEXT,
            mode TEXT,
            region TEXT,
            content TEXT,
            sources_json TEXT,
            metrics_json TEXT,
            user_name TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            user_name TEXT
        )
    """)
    c.execute("PRAGMA table_info(reports)")
    columns = [col[1] for col in c.fetchall()]
    if "user_name" not in columns:
        c.execute("ALTER TABLE reports ADD COLUMN user_name TEXT")
    conn.commit()
    conn.close()

def save_profile_name(name: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO profile (id, user_name) VALUES (1, ?)", (name,))
    conn.commit()
    conn.close()

def get_profile_name() -> str:
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT user_name FROM profile WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else ""

def save_report_to_db(topic: str, mode: str, region: str, content: str, sources_json: str, metrics_json: str, user_name: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    now = datetime.now().strftime("%b %d, %H:%M")
    c.execute("""
        INSERT INTO reports (timestamp, topic, mode, region, content, sources_json, metrics_json, user_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (now, topic, mode, region, content, sources_json, metrics_json, user_name))
    conn.commit()
    conn.close()

def get_all_reports_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, timestamp, topic, mode, region, content, sources_json, metrics_json, user_name FROM reports ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "timestamp": r[1],
            "topic": r[2],
            "mode": r[3],
            "region": r[4],
            "content": r[5],
            "sources_json": r[6] if r[6] else "[]",
            "metrics_json": r[7] if r[7] else "{}",
            "user_name": r[8] if len(r) > 8 and r[8] else "Lead Analyst"
        }
        for r in rows
    ]

def clear_all_reports_from_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM reports")
    conn.commit()
    conn.close()

init_db()

# 3. Authentication
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    st.error("⚠️ GEMINI_API_KEY not detected in .env file.")
    st.stop()

client = genai.Client(api_key=api_key)

# 4. Smart Model Fallback Router
MODEL_PRIORITY_CASCADE = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
]

def generate_with_smart_fallback(prompt: str, preferred_model: str, status_text=None) -> tuple[str, str]:
    models_to_try = [preferred_model] + [m for m in MODEL_PRIORITY_CASCADE if m != preferred_model]
    
    last_error = None
    for model_name in models_to_try:
        try:
            if status_text:
                status_text.markdown(f"`[5/5]` 🧠 **Synthesizing with `{model_name}`...**")
            
            resp = client.models.generate_content(
                model=model_name,
                contents=prompt,
            )
            return resp.text, model_name
        except Exception as e:
            err_msg = str(e)
            last_error = e
            if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "quota" in err_msg.lower():
                time.sleep(0.5)
                continue
            else:
                raise e

    raise Exception(f"All model engines exhausted their quotas. Details: {last_error}")

def resolve_query_intent(user_raw_query: str, preferred_model: str) -> tuple[str, str, bool]:
    check_prompt = f"""
Analyze this user search query intended for market research: "{user_raw_query}"

Determine if there is a typing mistake, phonetic misspelling, or ambiguous brand name (e.g. 'merceded' -> 'Mercedes-Benz', 'aple' -> 'Apple', 'telsa' -> 'Tesla').

Respond in strictly valid JSON format with this schema:
{{
    "corrected_query": "canonical target name",
    "has_typo": true/false,
    "reason": "Brief note on what was corrected or why it was kept as is"
}}
"""
    try:
        raw_res, _ = generate_with_smart_fallback(check_prompt, preferred_model)
        clean_json = raw_res.strip()
        if "```json" in clean_json:
            clean_json = clean_json.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json:
            clean_json = clean_json.split("```")[1].split("```")[0].strip()
        
        parsed = json.loads(clean_json)
        corrected = parsed.get("corrected_query", user_raw_query).strip()
        has_typo = parsed.get("has_typo", False)
        reason = parsed.get("reason", "")
        return corrected, reason, has_typo
    except Exception:
        return user_raw_query, "", False

# 5. User Identity Management
if "user_name" not in st.session_state:
    st.session_state.user_name = get_profile_name()

if not st.session_state.user_name:
    st.markdown(
        """
        <div class="onboarding-card">
            <h2 style="color: #38bdf8; font-weight: 800; margin-bottom: 0.5rem;">Access StratIntel Enterprise OS</h2>
            <p style="color: #94a3b8; font-size: 0.95rem; margin-bottom: 1.5rem;">
                Please authenticate your analyst credentials to establish a strategic intelligence workspace.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        with st.form("user_onboarding_form"):
            input_name = st.text_input("Full Name or Designation:", placeholder="e.g., Alex Vance (Principal Strategist)")
            submit_btn = st.form_submit_button("🚀 Initialize Secure Session", use_container_width=True)
            if submit_btn and input_name.strip():
                st.session_state.user_name = input_name.strip()
                save_profile_name(input_name.strip())
                st.rerun()
    st.stop()

# 6. Executive PDF Engine
def generate_pdf(title: str, content: str, mode: str, region: str, analyst: str) -> bytes:
    cleaned_text = (
        re.sub(r"[^\x00-\x7F]+", " ", content)
        .replace("<br>", " ")
        .replace("<br/>", " ")
        .replace("<br />", " ")
        .replace("–", "-")
        .replace("—", "-")
        .replace('“', '"')
        .replace('”', '"')
        .replace("’", "'")
    )

    html_body = markdown.markdown(
        cleaned_text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{
                size: a4 portrait;
                margin: 1.5cm 1.2cm 1.5cm 1.2cm;
                @frame footer_frame {{
                    -pdf-frame-content: footer_content;
                    bottom: 0.6cm;
                    margin-left: 1.2cm;
                    margin-right: 1.2cm;
                    height: 0.8cm;
                }}
            }}
            body {{
                font-family: Helvetica, Arial, sans-serif;
                color: #1e293b;
                font-size: 8.5pt;
                line-height: 1.5;
            }}
            .header-banner {{
                background-color: #0f172a;
                color: #ffffff;
                padding: 14px 18px;
                border-radius: 6px;
                margin-bottom: 12px;
            }}
            .report-title {{
                font-size: 15pt;
                font-weight: bold;
                color: #38bdf8;
                margin: 0;
            }}
            .report-meta {{
                font-size: 8pt;
                color: #94a3b8;
                margin-top: 4px;
            }}
            h1 {{
                font-size: 13pt;
                color: #0f172a;
                border-bottom: 1.5px solid #0284c7;
                padding-bottom: 3px;
                margin-top: 14px;
                margin-bottom: 6px;
            }}
            h2 {{
                font-size: 11pt;
                color: #0369a1;
                margin-top: 10px;
                margin-bottom: 4px;
                border-bottom: 0.5px solid #e2e8f0;
                padding-bottom: 2px;
            }}
            h3 {{
                font-size: 9.5pt;
                color: #334155;
                margin-top: 8px;
                margin-bottom: 3px;
            }}
            p {{
                margin: 0 0 6px 0;
                text-align: justify;
            }}
            ul, ol {{
                margin-top: 2px;
                margin-bottom: 6px;
                padding-left: 15px;
            }}
            li {{
                margin-bottom: 3px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 8px;
                margin-bottom: 12px;
                font-size: 7.5pt;
            }}
            th {{
                background-color: #f1f5f9;
                color: #0f172a;
                font-weight: bold;
                padding: 5px 6px;
                border: 0.5px solid #cbd5e1;
                text-align: left;
            }}
            td {{
                padding: 4px 6px;
                border: 0.5px solid #e2e8f0;
                vertical-align: top;
            }}
            .footer {{
                font-size: 7pt;
                color: #94a3b8;
                text-align: right;
                border-top: 0.5px solid #e2e8f0;
                padding-top: 4px;
            }}
        </style>
    </head>
    <body>
        <div class="header-banner">
            <div class="report-title">STRATEGIC MARKET INTELLIGENCE REPORT</div>
            <div class="report-meta">
                <b>Target:</b> {title.title()} &nbsp;|&nbsp; 
                <b>Lead Analyst:</b> {analyst} &nbsp;|&nbsp; 
                <b>Scope:</b> {region} ({mode})
            </div>
        </div>

        {html_body}

        <div id="footer_content" class="footer">
            StratIntel Intelligence OS &bull; Confidential &bull; Prepared by {analyst}
        </div>
    </body>
    </html>
    """

    pdf_stream = io.BytesIO()
    pisa.CreatePDF(full_html, dest=pdf_stream)
    return pdf_stream.getvalue()

# 7. Sidebar Controls & History
saved_reports = get_all_reports_from_db()

with st.sidebar:
    st.markdown(f"### 👤 **Active Analyst**\n**`{st.session_state.user_name}`**")
    if st.button("🔄 Switch User", use_container_width=True):
        st.session_state.user_name = ""
        save_profile_name("")
        st.rerun()

    st.markdown("---")
    st.markdown("### ⚙️ **Intelligence Engine**")
    selected_model = st.selectbox(
        "AI Engine (Primary Preference)",
        MODEL_PRIORITY_CASCADE,
        index=0,
        help="The system prioritizes this model and cascades to fallback tiers if quotas are exhausted."
    )
    
    analysis_mode = st.selectbox(
        "Analysis Blueprint",
        [
            "Comprehensive Strategic Dossier",
            "Pricing & Monetization Breakdown",
            "Feature Gap & SWOT Matrix",
            "Direct Competitor Benchmark",
        ],
        index=0,
    )

    target_region = st.selectbox(
        "Geographic Scope",
        ["Global", "North America", "Europe / EU", "Asia-Pacific"],
        index=0,
    )

    st.markdown("---")
    st.markdown("### 🌐 **Crawl Parameters**")
    deep_scrape = st.toggle("Deep HTML Extraction", value=True)
    num_sources = st.slider("Sources to Crawl", min_value=3, max_value=8, value=5)

    st.markdown("---")
    st.markdown("### 📂 **Intelligence Vault**")
    
    if saved_reports:
        for r in saved_reports:
            with st.container():
                st.caption(f"🕒 {r['timestamp']} &nbsp;•&nbsp; `{r['region']}`")
                if st.button(f"🔍 {r['topic']}", key=f"hist_btn_{r['id']}", use_container_width=True):
                    st.session_state.active_report = r
                    st.session_state.follow_ups = []
                    st.rerun()
                st.markdown("<div style='margin-bottom: 0.5rem;'></div>", unsafe_allow_html=True)

        if st.button("🗑️ Clear Intelligence Vault", use_container_width=True):
            clear_all_reports_from_db()
            st.session_state.active_report = None
            st.session_state.follow_ups = []
            st.rerun()
    else:
        st.info("No saved dossiers found.")

# 8. Hero Banner
st.markdown(
    f"""
    <div class="brand-hero">
        <div class="brand-title">StratIntel Enterprise • Market Intelligence OS</div>
        <div class="brand-sub">Autonomous Web Scrapes &bull; Multi-Source Sentiment Mining &bull; Strategic Analytics</div>
        <div>
            <span class="pill-tag">👤 Analyst: {st.session_state.user_name}</span>
            <span class="pill-tag">⚡ Primary Engine: {selected_model}</span>
            <span class="pill-tag">🛡️ Smart Fallback: Active</span>
            <span class="pill-tag">🎯 Blueprint: {analysis_mode}</span>
            <span class="pill-tag">🌍 Region: {target_region}</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 9. Robust Search & Resilient Crawl Engine
def fetch_market_data_with_telemetry(query: str, max_results: int, scrape_html: bool, progress_bar, status_text) -> tuple[str, list, float]:
    results_data = []
    
    status_text.markdown(f"`[2/5]` 📡 **Formulating queries & searching for:** `{query}`...")
    progress_bar.progress(25)
    time.sleep(0.15)
    
    queries_to_try = [
        f"{query} competitors market share pricing",
        f"{query} business model revenue analysis",
        query,
    ]
    
    # Primary Search Attempt via DuckDuckGo
    for q in queries_to_try:
        try:
            with DDGS(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}) as ddgs:
                hits = list(ddgs.text(q, max_results=max_results))
                if hits:
                    for idx, hit in enumerate(hits):
                        item = {
                            "title": hit.get("title", ""),
                            "url": hit.get("href", ""),
                            "snippet": hit.get("body", ""),
                            "page_text": "",
                            "sentiment": 0.0,
                        }
                        
                        full_text = hit.get("body", "")
                        
                        if scrape_html and hit.get("href"):
                            status_text.markdown(f"`[3/5]` 🕷️ **Scraping DOM & cleansing text:** `{hit.get('title', 'Domain')[:28]}...`")
                            sub_prog = int(35 + ((idx + 1) / len(hits)) * 25)
                            progress_bar.progress(min(sub_prog, 60))
                            try:
                                resp = requests.get(
                                    hit["href"],
                                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
                                    timeout=3.5,
                                )
                                if resp.status_code == 200:
                                    soup = BeautifulSoup(resp.text, "html.parser")
                                    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                                        tag.extract()
                                    extracted = " ".join(soup.stripped_strings)[:1400]
                                    item["page_text"] = extracted
                                    full_text += " " + extracted
                            except Exception:
                                item["page_text"] = "Direct HTML parse skipped."
                        
                        item["sentiment"] = round(TextBlob(full_text).sentiment.polarity, 2)
                        results_data.append(item)
                    break
        except Exception:
            continue

    # Resilient Fallback Search Engine (Wikipedia/Direct API) if DDGS is throttled
    if not results_data:
        status_text.markdown("`[2/5]` 🔄 **Engaging secondary knowledge index...**")
        try:
            backup_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={query}&limit={max_results}&namespace=0&format=json"
            wiki_resp = requests.get(backup_url, timeout=4).json()
            if len(wiki_resp) >= 4 and wiki_resp[1]:
                for title, snippet, link in zip(wiki_resp[1], wiki_resp[2], wiki_resp[3]):
                    results_data.append({
                        "title": f"{title} (Market Reference)",
                        "url": link,
                        "snippet": snippet or f"Market analysis domain for {title}",
                        "page_text": snippet,
                        "sentiment": round(TextBlob(snippet).sentiment.polarity, 2),
                    })
        except Exception:
            pass

    status_text.markdown("`[4/5]` 🧠 **Calculating sentiment polarity & building vector context...**")
    progress_bar.progress(70)
    time.sleep(0.2)

    avg_sentiment = (
        round(sum(x["sentiment"] for x in results_data) / len(results_data), 2)
        if results_data
        else 0.0
    )

    return json.dumps(results_data, indent=2), results_data, avg_sentiment

USER_AVATAR = "https://api.iconify.design/solar:user-circle-bold-duotone.svg?color=%2338bdf8"
AI_AVATAR = "https://api.iconify.design/solar:chart-square-bold-duotone.svg?color=%23818cf8"

# 10. Render Workspace
quick_input = None

if "active_report" in st.session_state and st.session_state.active_report:
    report = st.session_state.active_report
    sources = json.loads(report.get("sources_json", "[]"))
    metrics = json.loads(report.get("metrics_json", "{}"))
    analyst_tag = report.get("user_name", st.session_state.user_name)
    model_used = metrics.get("model_used", selected_model)
    corrected_from = metrics.get("corrected_from", None)

    if "follow_ups" not in st.session_state:
        st.session_state.follow_ups = []

    if corrected_from:
        st.markdown(
            f"""
            <div class="typo-banner">
                💡 <b>Query Intent Normalized:</b> Interpreted original input <code>{corrected_from}</code> as <b>{report['topic']}</b>.
            </div>
            """,
            unsafe_allow_html=True,
        )

    # KPI Metrics Row
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    with m_col1:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Target Market</div>
                <div class="stat-value" style="font-size: 1.1rem;">{report['topic'][:18]}...</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m_col2:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Model Engine</div>
                <div class="stat-value" style="font-size: 1.0rem; color: #38bdf8;">{model_used}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m_col3:
        sentiment_score = metrics.get("avg_sentiment", 0.15)
        sent_color = "#4ade80" if sentiment_score > 0.05 else ("#f87171" if sentiment_score < -0.05 else "#facc15")
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Market Sentiment Index</div>
                <div class="stat-value" style="color: {sent_color};">{sentiment_score:+.2f}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with m_col4:
        st.markdown(
            f"""
            <div class="stat-card">
                <div class="stat-label">Live Sources Audited</div>
                <div class="stat-value">{len(sources)} Domains</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='margin-bottom: 1.2rem;'></div>", unsafe_allow_html=True)

    # 5-Tab Interactive Workspace
    tab_dossier, tab_charts, tab_sentiment, tab_sources, tab_drilldown = st.tabs([
        "📄 Strategic Dossier",
        "📈 Quantitative Analytics",
        "🧠 Sentiment & Trust Index",
        "🌐 Web Sources & Audit Trail",
        "⚡ AI Deep-Dive Assistant"
    ])

    with tab_dossier:
        st.markdown(report["content"])
        
        st.markdown("---")
        st.markdown("#### **Export Dossier Assets**")
        exp_col1, exp_col2, exp_col3 = st.columns(3)
        with exp_col1:
            st.download_button(
                label="📥 Download Markdown Document (.md)",
                data=report["content"],
                file_name=f"dossier_{report['topic'].replace(' ', '_').lower()}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with exp_col2:
            pdf_bytes = generate_pdf(report["topic"], report["content"], report["mode"], report["region"], analyst_tag)
            st.download_button(
                label="📄 Download Executive PDF (.pdf)",
                data=pdf_bytes,
                file_name=f"dossier_{report['topic'].replace(' ', '_').lower()}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        with exp_col3:
            if sources:
                df_sources = pd.DataFrame(sources)[["title", "url", "sentiment"]]
                df_sources.columns = ["Source Title", "Web URL", "Sentiment Polarity"]
                csv_bytes = df_sources.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
                
                st.download_button(
                    label="📊 Export Source Data (.csv / Excel)",
                    data=csv_bytes,
                    file_name=f"sources_{report['topic'].replace(' ', '_').lower()}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

    with tab_charts:
        st.markdown("#### **Estimated Market Positioning Matrix**")
        c1, c2 = st.columns(2)
        with c1:
            chart_data = pd.DataFrame({
                "Dimension": ["Pricing Competitiveness", "Feature Breadth", "Brand Recognition", "Ease of Adoption", "Tech Defensibility"],
                "Incumbent Standard": [70, 85, 90, 60, 75],
                "Market Opportunity": [85, 75, 45, 95, 90],
            })
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=chart_data["Incumbent Standard"],
                theta=chart_data["Dimension"],
                fill='toself',
                name='Incumbent Standard',
                line_color='#60A5FA'
            ))
            fig.add_trace(go.Scatterpolar(
                r=chart_data["Market Opportunity"],
                theta=chart_data["Dimension"],
                fill='toself',
                name='Target Entry Model',
                line_color='#A78BFA'
            ))
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=True,
                template="plotly_dark",
                margin=dict(l=30, r=30, t=30, b=30),
                height=380,
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("#### **Estimated Market TAM Breakdown**")
            tam_df = pd.DataFrame({
                "Segment": ["Total Addressable (TAM)", "Serviceable Addressable (SAM)", "Serviceable Obtainable (SOM)"],
                "Value": [100, 42, 14]
            })
            tam_fig = px.funnel(
                tam_df,
                y="Segment",
                x="Value",
                color="Segment",
                color_discrete_sequence=["#38BDF8", "#818CF8", "#C084FC"],
                template="plotly_dark",
            )
            tam_fig.update_layout(showlegend=False, height=380, margin=dict(l=20, r=20, t=20, b=20))
            st.plotly_chart(tam_fig, use_container_width=True)

    with tab_sentiment:
        st.markdown("#### **Audited Source Sentiment Distribution**")
        if sources:
            sent_df = pd.DataFrame(sources)
            bar_fig = px.bar(
                sent_df,
                x="title",
                y="sentiment",
                color="sentiment",
                color_continuous_scale="Viridis",
                labels={"sentiment": "Sentiment Polarity (-1 to +1)", "title": "Scraped Source Title"},
                title="Sentiment Polarity by Scraped Domain",
                template="plotly_dark"
            )
            bar_fig.update_layout(xaxis_tickangle=-25, height=380)
            st.plotly_chart(bar_fig, use_container_width=True)
        else:
            st.caption("No sentiment records available.")

    with tab_sources:
        if sources:
            st.markdown("#### **Scraped Competitor Audit Trail**")
            for idx, s in enumerate(sources):
                with st.expander(f"🔗 {s.get('title', 'Unknown Source')} (Sentiment: {s.get('sentiment', 0.0):+.2f})"):
                    st.markdown(f"**URL:** [{s.get('url')}]({s.get('url')})")
                    st.markdown(f"**Search Snippet:** {s.get('snippet')}")
                    if s.get("page_text"):
                        st.markdown("**Extracted Text Cleanse:**")
                        st.caption(s.get("page_text")[:600] + "...")
        else:
            st.caption("No source metadata available.")

    with tab_drilldown:
        st.markdown("#### ⚡ **Interactive Follow-up & Deep-Dive Analysis**")
        st.caption(f"Drill down into specific competitor weaknesses, unit economics, or battlecards with {st.session_state.user_name}.")

        for f_msg in st.session_state.follow_ups:
            if f_msg["role"] == "user":
                st.markdown(
                    f'<div class="user-tag-header">👤 {st.session_state.user_name.lower()} &bull; Lead Strategist</div>',
                    unsafe_allow_html=True,
                )
            with st.chat_message(f_msg["role"], avatar=USER_AVATAR if f_msg["role"] == "user" else AI_AVATAR):
                st.markdown(f_msg["content"])

        drill_col1, drill_col2, drill_col3 = st.columns(3)
        drill_preset = None
        if drill_col1.button("🎯 Draft GTM Sales Battlecard", key="btn_drill_1", use_container_width=True):
            drill_preset = "Draft a tactical GTM Sales Battlecard detailing objection handling, key differentiators, and win strategies against the competitors listed in the dossier."
        if drill_col2.button("💰 Simulate Tiered Pricing Models", key="btn_drill_2", use_container_width=True):
            drill_preset = "Simulate a 3-tier pricing model (Starter, Growth, Enterprise) that undercuts incumbents while maintaining healthy gross margins."
        if drill_col3.button("🛡️ Outline Tech Moats & Defensibility", key="btn_drill_3", use_container_width=True):
            drill_preset = "Detail 4 sustainable technological and operational moats needed to defend market share against incumbents."

        drill_input = st.chat_input("Ask a specific follow-up about this dossier...", key="drill_chat_input")
        active_drill = drill_input or drill_preset

        if active_drill:
            st.session_state.follow_ups.append({"role": "user", "content": active_drill})
            
            with st.chat_message("assistant", avatar=AI_AVATAR):
                drill_prompt = f"""
You are an Executive Venture Partner. The user ({st.session_state.user_name}) is asking a deep-dive question based on this strategic market research dossier:

DOSSIER CONTEXT:
{report['content']}

USER QUERY:
{active_drill}

Provide a crisp, actionable, data-backed strategic answer using bullet points and concise markdown formatting.
"""
                drill_res_text, _ = generate_with_smart_fallback(drill_prompt, selected_model)
                st.markdown(drill_res_text)
                st.session_state.follow_ups.append({"role": "assistant", "content": drill_res_text})
                st.rerun()

elif not saved_reports:
    st.markdown(f"##### ⚡ **Welcome, {st.session_state.user_name}. Suggested Research Blueprints:**")
    chip_col1, chip_col2, chip_col3 = st.columns(3)
    if chip_col1.button("📱 NFC Google Review Stands for Local Shops", use_container_width=True):
        quick_input = "NFC Google Review stands for local businesses"
    if chip_col2.button("⚡ Autonomous AI Code Review Platforms", use_container_width=True):
        quick_input = "Autonomous AI Code Review and PR remediation tools"
    if chip_col3.button("🚗 Solid-State EV Battery Manufacturers", use_container_width=True):
        quick_input = "Solid-state electric vehicle battery manufacturers and pricing"

# 11. Sticky Chat Bar
user_query = st.chat_input("Enter a company, product niche, or business model to research (Press Enter)...")
active_target = user_query or quick_input

if active_target:
    start_time = time.time()
    
    st.markdown(
        f'<div class="user-tag-header">👤 {st.session_state.user_name.lower()} &bull; Lead Strategist</div>',
        unsafe_allow_html=True,
    )
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(f"**Research Target:** `{active_target}` &nbsp;•&nbsp; *({analysis_mode} | {target_region})*")

    with st.chat_message("assistant", avatar=AI_AVATAR):
        progress_container = st.empty()
        status_text = st.empty()
        live_progress = progress_container.progress(5)
        
        # Step 1: Pre-flight Query Normalization & Typo Resolution
        status_text.markdown("`[1/5]` 🔍 **Analyzing query intent & verifying nomenclature...**")
        live_progress.progress(15)
        normalized_target, typo_reason, has_typo = resolve_query_intent(active_target, selected_model)
        
        if has_typo and normalized_target.lower() != active_target.lower():
            status_text.markdown(f"`[1/5]` 💡 **Normalized query:** `{active_target}` ➔ **`{normalized_target}`** ({typo_reason})")
            time.sleep(0.4)
            corrected_from_val = active_target
        else:
            corrected_from_val = None

        # Step 2-4: Deep Search & Scrapes using clean normalized target
        raw_web_data, source_objects, avg_sentiment = fetch_market_data_with_telemetry(
            query=normalized_target,
            max_results=num_sources,
            scrape_html=deep_scrape,
            progress_bar=live_progress,
            status_text=status_text,
        )

        # Step 5: Executive Dossier Synthesis
        prompt = f"""
You are a Principal Market Research Analyst and Venture Strategist preparing an executive-grade intelligence dossier for {st.session_state.user_name}.

TARGET TOPIC / ENTITY: {normalized_target}
ORIGINAL USER QUERY: {active_target}
ANALYSIS FOCUS: {analysis_mode}
GEOGRAPHIC SCOPE: {target_region}
PREPARED FOR: {st.session_state.user_name}

LIVE EXTRACTED WEB CONTEXT:
{raw_web_data}

CRITICAL GENERATION GUIDELINES:
1. Provide comprehensive, multi-paragraph analysis with concrete market metrics, realistic pricing models, and specific company names.
2. If the user had a typo (Original: '{active_target}', Normalized: '{normalized_target}'), explicitly state the normalization at the start.
3. Every Markdown table must include clear header rows, standard delimiter rows (|---|---|), and one competitor per row.

STRUCTURE YOUR REPORT USING THIS FORMAT:
# Strategic Dossier: {normalized_target}

## 1. Executive Summary & Market Landscape
Provide a comprehensive 2-3 paragraph macro analysis detailing global/regional market size, growth drivers, supply chain dynamics, and regulatory forces affecting this sector in {target_region}.

## 2. Competitive Landscape & Unit Economics
Construct a detailed Markdown comparison table (at least 3-4 real competitors):
| Competitor / Solution | Core Value Proposition | Pricing Structure & Est. Unit Economics | Primary Moat / Advantage | Critical Vulnerability |
| :--- | :--- | :--- | :--- | :--- |
| [Name 1] | [Details] | [Pricing/Margins] | [Moat] | [Weakness] |
| [Name 2] | [Details] | [Pricing/Margins] | [Moat] | [Weakness] |
| [Name 3] | [Details] | [Pricing/Margins] | [Moat] | [Weakness] |

## 3. Core Capabilities vs. Premium Differentiators
- **Table-Stakes Baseline Requirements:** Detail 3-4 critical baseline features necessary for market entry.
- **High-Margin Premium Differentiators:** Detail 3-4 defensible, high-value capabilities that capture premium margins.

## 4. Unexploited Market White-Space & Strategic Entry Blueprint
- **Identified Market Gaps:** Unaddressed customer pain points and inefficiencies in incumbent offerings.
- **Go-To-Market (GTM) Strategy:** Tactical recommendations for product positioning, pricing arbitrage, and customer acquisition.
"""

        try:
            report_content, executed_model = generate_with_smart_fallback(
                prompt=prompt,
                preferred_model=selected_model,
                status_text=status_text,
            )
            
            live_progress.progress(100)
            elapsed = round(time.time() - start_time, 2)
            
            progress_container.empty()
            status_text.empty()

            sources_json_str = json.dumps(source_objects)
            metrics_json_str = json.dumps({
                "avg_sentiment": avg_sentiment,
                "elapsed": elapsed,
                "model_used": executed_model,
                "corrected_from": corrected_from_val
            })

            save_report_to_db(normalized_target, analysis_mode, target_region, report_content, sources_json_str, metrics_json_str, st.session_state.user_name)
            
            st.session_state.active_report = {
                "id": len(saved_reports) + 1,
                "timestamp": datetime.now().strftime("%b %d, %H:%M"),
                "topic": normalized_target,
                "mode": analysis_mode,
                "region": target_region,
                "content": report_content,
                "sources_json": sources_json_str,
                "metrics_json": metrics_json_str,
                "user_name": st.session_state.user_name,
            }
            st.session_state.follow_ups = []
            st.rerun()

        except Exception as e:
            progress_container.empty()
            status_text.empty()
            st.error(f"Analysis Pipeline Error: {e}")