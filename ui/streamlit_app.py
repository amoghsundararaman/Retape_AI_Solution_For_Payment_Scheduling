from __future__ import annotations

import json
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.graph_objects as go
import streamlit as st

CASES_DIR = ROOT / "cases"

st.set_page_config(
    page_title="Retape AI — Settlement Engine",
    page_icon="⚖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from feasibility.engine import evaluate_offer
from feasibility.models import client_from_dict, offer_from_dict, rules_from_dict
from feasibility.validation import validate_inputs, ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# CSS  ·  Retape AI design language: dark sidebar, clean white main, blue accent
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
/* ── Reset Streamlit chrome ── */
#MainMenu, footer, .stDeployButton { display: none !important; }
.block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

/* ── Page background ── */
.stApp { background: #F0F4FA; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* Sidebar text and labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] .stMarkdown span {
    color: #8B949E !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
}

/* Sidebar selectbox */
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    color: #E6EDF3 !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg { fill: #8B949E !important; }

/* Sidebar text areas */
[data-testid="stSidebar"] textarea {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    color: #E6EDF3 !important;
    font-family: 'SF Mono', 'Menlo', 'Monaco', monospace !important;
    font-size: 11.5px !important;
    line-height: 1.6 !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] textarea:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.25) !important;
    outline: none !important;
}

/* Sidebar button */
[data-testid="stSidebar"] .stButton > button {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    letter-spacing: 0.01em !important;
    padding: 0.6rem 1rem !important;
    transition: background 0.15s !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #1D4ED8 !important;
}

/* ── Main content area ── */

/* Hero banner */
.rp-hero {
    background: #0D1117;
    border-radius: 14px;
    padding: 28px 32px 24px;
    margin-bottom: 24px;
    border: 1px solid #21262D;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.rp-hero-left { max-width: 600px; }
.rp-hero-eyebrow {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: #2563EB;
    margin-bottom: 8px;
}
.rp-hero-title {
    font-size: 28px;
    font-weight: 800;
    color: #F0F6FC;
    margin: 0 0 6px;
    line-height: 1.15;
    letter-spacing: -0.03em;
}
.rp-hero-sub { font-size: 14px; color: #8B949E; margin: 0; line-height: 1.5; }
.rp-hero-badge {
    background: rgba(37,99,235,0.12);
    border: 1px solid rgba(37,99,235,0.3);
    border-radius: 8px;
    padding: 10px 18px;
    text-align: center;
    flex-shrink: 0;
}
.rp-hero-badge-label { font-size: 10px; color: #8B949E; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; }
.rp-hero-badge-value { font-size: 22px; font-weight: 900; color: #2563EB; margin-top: 2px; }

/* Status cards */
.rp-status-ok {
    background: #0D1117;
    border: 1px solid #21262D;
    border-left: 4px solid #238636;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.rp-status-fail {
    background: #0D1117;
    border: 1px solid #21262D;
    border-left: 4px solid #DA3633;
    border-radius: 10px;
    padding: 18px 22px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    gap: 16px;
}
.rp-status-icon { font-size: 28px; flex-shrink: 0; }
.rp-status-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 3px;
}
.rp-status-label.ok  { color: #3FB950; }
.rp-status-label.fail { color: #F85149; }
.rp-status-title { font-size: 17px; font-weight: 700; color: #F0F6FC; margin-bottom: 3px; }
.rp-status-detail { font-size: 13px; color: #8B949E; }
.rp-pill {
    display: inline-block;
    background: rgba(37,99,235,0.15);
    color: #58A6FF;
    border: 1px solid rgba(88,166,255,0.25);
    border-radius: 20px;
    padding: 2px 10px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-left: 8px;
    vertical-align: middle;
}

/* Metric grid */
.rp-metrics {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 20px;
}
.rp-metric {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    border-top: 2px solid transparent;
}
.rp-metric.blue   { border-top-color: #2563EB; }
.rp-metric.green  { border-top-color: #16A34A; }
.rp-metric.slate  { border-top-color: #64748B; }
.rp-metric.amber  { border-top-color: #D97706; }
.rp-metric.teal   { border-top-color: #0891B2; }
.rp-metric.violet { border-top-color: #7C3AED; }
.rp-metric-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #94A3B8;
    margin-bottom: 8px;
}
.rp-metric-value { font-size: 22px; font-weight: 800; color: #0D1117; line-height: 1; margin-bottom: 3px; }
.rp-metric-sub   { font-size: 11px; color: #94A3B8; }

/* Section heading */
.rp-section {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: #64748B;
    margin: 24px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #E2E8F0;
}

/* Timeline */
.rp-timeline {
    display: flex;
    align-items: center;
    overflow-x: auto;
    padding: 4px 2px 8px;
    gap: 0;
    scrollbar-width: thin;
    scrollbar-color: #E2E8F0 transparent;
}
.rp-tnode { display: flex; flex-direction: column; align-items: center; gap: 4px; flex-shrink: 0; min-width: 52px; }
.rp-tdot {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 9px; font-weight: 800; letter-spacing: -0.02em;
}
.rp-tdot.pay  { background: #EFF6FF; color: #1D4ED8; border: 1.5px solid #BFDBFE; }
.rp-tdot.fee  { background: #FEFCE8; color: #854D0E; border: 1.5px solid #FDE68A; }
.rp-tdate     { font-size: 9px; color: #94A3B8; font-weight: 600; text-align: center; }
.rp-tarrow    { color: #CBD5E1; font-size: 14px; margin: 0 1px; padding-bottom: 20px; flex-shrink: 0; }

/* Chart wrapper */
.rp-chart {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px 18px 10px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    margin-bottom: 16px;
}
.rp-chart-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #64748B; margin-bottom: 8px; }

/* Funds cards */
.rp-funds { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
.rp-fund {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.rp-fund.pass { border-top: 3px solid #16A34A; }
.rp-fund.warn { border-top: 3px solid #D97706; }
.rp-fund-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #94A3B8; margin-bottom: 8px; }
.rp-fund-amount { font-size: 30px; font-weight: 900; color: #0D1117; line-height: 1; margin-bottom: 6px; }
.rp-fund-detail { font-size: 12px; color: #64748B; margin-bottom: 10px; }
.rp-badge-pass {
    display: inline-flex; align-items: center; gap: 4px;
    background: #F0FDF4; color: #15803D;
    border: 1px solid #BBF7D0; border-radius: 20px;
    padding: 3px 10px; font-size: 11px; font-weight: 700;
}
.rp-badge-warn {
    display: inline-flex; align-items: center; gap: 4px;
    background: #FFFBEB; color: #92400E;
    border: 1px solid #FDE68A; border-radius: 20px;
    padding: 3px 10px; font-size: 11px; font-weight: 700;
}
.rp-fund-reason { font-size: 11px; color: #DC2626; margin-top: 7px; line-height: 1.5; }

/* Diagnostics */
.rp-diag {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-left: 4px solid #DC2626;
    border-radius: 10px;
    padding: 18px 22px;
    margin-top: 8px;
}
.rp-diag-kind {
    display: inline-block;
    background: #FEE2E2; color: #991B1B;
    font-size: 10px; font-weight: 800;
    text-transform: uppercase; letter-spacing: 0.1em;
    padding: 2px 9px; border-radius: 4px; margin-bottom: 8px;
}
.rp-diag-text { font-size: 13px; color: #374151; line-height: 1.65; }
.rp-diag-meta { font-size: 11px; color: #6B7280; margin-top: 8px; }

/* Empty state */
.rp-empty {
    text-align: center;
    padding: 72px 40px 80px;
}
.rp-empty-icon  { font-size: 52px; margin-bottom: 18px; opacity: 0.25; }
.rp-empty-title { font-size: 20px; font-weight: 700; color: #374151; margin-bottom: 8px; }
.rp-empty-sub   { font-size: 14px; color: #9CA3AF; max-width: 400px; margin: 0 auto; line-height: 1.6; }

/* Download button */
.stDownloadButton > button {
    background: #0D1117 !important;
    color: #F0F6FC !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.45rem 1.1rem !important;
}
.stDownloadButton > button:hover {
    background: #161B22 !important;
    border-color: #8B949E !important;
}

/* Expander */
.streamlit-expanderHeader {
    background: #FFFFFF !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    color: #374151 !important;
}
</style>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"

def _discover_cases() -> list[str]:
    if not CASES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in CASES_DIR.iterdir()
        if d.is_dir() and all(
            (d / f).exists()
            for f in ("client.json", "offer.json", "creditor_rules.json")
        )
    )

def _load_case_texts(name: str) -> tuple[str, str, str]:
    d = CASES_DIR / name
    c = json.dumps(json.loads((d / "client.json").read_text()), indent=2)
    o = json.dumps(json.loads((d / "offer.json").read_text()), indent=2)
    r = json.dumps(json.loads((d / "creditor_rules.json").read_text()), indent=2)
    return c, o, r

def _analytics(offer_d: dict, rd: dict) -> dict:
    from decimal import Decimal, ROUND_HALF_UP
    bal = offer_d.get("creditor_balance_cents", offer_d.get("current_balance_cents", 0))
    ot  = int(
        (Decimal(str(offer_d.get("settlement_pct", 0))) * Decimal(str(bal)))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    orig = offer_d.get("original_balance_cents", 0)
    sc   = rd.get("schedule") or []
    bank = sum(r["bank_fee_cents"] for r in sc)
    fee  = sum(r["program_fee_cents"] for r in sc)
    sav  = orig - ot
    return {
        "offer_total": ot, "program_fee": fee, "bank_fees": bank,
        "total_cost": ot + fee + bank,
        "savings": sav, "savings_pct": round(sav / orig * 100, 1) if orig else 0.0,
        "n_payments": sum(1 for r in sc if r["creditor_payment_cents"] > 0),
        "duration": len(sc),
        "first_pay": sc[0]["date"] if sc else None,
        "last_pay": max((r["date"] for r in sc if r["creditor_payment_cents"] > 0), default=None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def _pdf(rd: dict, an: dict, creditor: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            topMargin=0.75*inch, bottomMargin=0.75*inch,
                            leftMargin=0.8*inch, rightMargin=0.8*inch)
    ss    = getSampleStyleSheet()
    NAVY  = colors.HexColor("#0D1117")
    BLUE  = colors.HexColor("#2563EB")
    GRAY  = colors.HexColor("#6B7280")
    LGRAY = colors.HexColor("#F8FAFF")
    BDR   = colors.HexColor("#E2E8F0")
    GREEN = colors.HexColor("#16A34A")
    RED   = colors.HexColor("#DC2626")

    h1   = ParagraphStyle("h1",  parent=ss["Heading1"], fontSize=20, textColor=NAVY, spaceAfter=4, fontName="Helvetica-Bold", leading=24)
    h2   = ParagraphStyle("h2",  parent=ss["Heading2"], fontSize=13, textColor=NAVY, spaceBefore=16, spaceAfter=6, fontName="Helvetica-Bold")
    body = ParagraphStyle("body",parent=ss["BodyText"], fontSize=9, leading=13, textColor=colors.HexColor("#374151"))
    cap  = ParagraphStyle("cap", parent=body, textColor=GRAY, fontSize=8)

    story = []
    feasible = rd["feasible"]

    # Header
    story.append(Paragraph(f"Settlement Report — {creditor}", h1))
    status_color = GREEN if feasible else RED
    story.append(Paragraph(
        f"<font color='{'#16A34A' if feasible else '#DC2626'}'>{'FEASIBLE' if feasible else 'INFEASIBLE'}</font>"
        f"  ·  Shape: {rd.get('pay_shape_used','—')}  ·  {an['duration']} months",
        body
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=14, spaceBefore=8))

    # Summary
    story.append(Paragraph("Financial Summary", h2))
    rows = [
        ["Offer Total",  _fmt(an["offer_total"])],
        ["Program Fee",  _fmt(an["program_fee"])],
        ["Bank Fees",    _fmt(an["bank_fees"])],
        ["Total Cost",   _fmt(an["total_cost"])],
        ["Savings",      f"{_fmt(an['savings'])} ({an['savings_pct']}%)"],
    ]
    tbl = Table(rows, colWidths=[2.2*inch, 2.5*inch])
    tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("FONTNAME",      (0,0),(0,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0,0),(0,-1),  GRAY),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [LGRAY, colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.3, BDR),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(tbl)

    if feasible and rd.get("schedule"):
        story.append(Paragraph("Payment Schedule", h2))
        sc   = rd["schedule"]
        data = [["Date","Creditor","Fee","Bank","Balance"]] + [
            [r["date"],_fmt(r["creditor_payment_cents"]),_fmt(r["program_fee_cents"]),
             _fmt(r["bank_fee_cents"]),_fmt(r["balance_cents"])] for r in sc
        ] + [["TOTAL",
              _fmt(sum(r["creditor_payment_cents"] for r in sc)),
              _fmt(sum(r["program_fee_cents"] for r in sc)),
              _fmt(sum(r["bank_fee_cents"] for r in sc)), "—"]]
        t2 = Table(data, colWidths=[1.1*inch, 1.2*inch, 1.1*inch, 0.9*inch, 1.1*inch])
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  NAVY),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.white, LGRAY]),
            ("BACKGROUND",    (0,-1),(-1,-1),LGRAY),
            ("FONTNAME",      (0,-1),(-1,-1),"Helvetica-Bold"),
            ("GRID",          (0,0),(-1,-1), 0.3, BDR),
            ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        story.append(t2)

    story.append(Spacer(1, 18))
    story.append(Paragraph("Generated by Retape AI Settlement Feasibility Engine", cap))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar  —  CRITICAL: session state must be set BEFORE text_area widgets
# ─────────────────────────────────────────────────────────────────────────────

def _sidebar() -> tuple[str, str, str, bool]:
    with st.sidebar:
        # Logo
        st.markdown("""
        <div style="padding:24px 16px 20px;border-bottom:1px solid #21262D;margin-bottom:20px">
          <div style="font-size:15px;font-weight:800;color:#F0F6FC;letter-spacing:-0.02em">
            Retape AI
          </div>
          <div style="font-size:10px;font-weight:600;color:#8B949E;text-transform:uppercase;
                      letter-spacing:0.1em;margin-top:3px">Settlement Engine</div>
        </div>
        """, unsafe_allow_html=True)

        # Case selector
        cases  = _discover_cases()
        choice = st.selectbox(
            "DEMO CASE",
            options=["— or paste your own below —"] + cases,
            format_func=lambda x: x.replace("_", " ") if x != "— or paste your own below —" else x,
            key="case_selector",
        )

        # ── THE FIX: write to session_state BEFORE creating text_area widgets ──
        # Streamlit text_area with a key reads from session_state; value= only
        # sets the initial default. Explicitly updating session_state here forces
        # the text areas to reflect the chosen demo case on every selection change.
        _prev = st.session_state.get("_prev_case_choice")
        if choice != _prev:
            st.session_state["_prev_case_choice"] = choice
            if choice != "— or paste your own below —":
                c, o, r = _load_case_texts(choice)
                st.session_state["_ta_client"] = c
                st.session_state["_ta_offer"]  = o
                st.session_state["_ta_rules"]  = r

        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.markdown("CLIENT")
        client_txt = st.text_area("client", key="_ta_client", height=185,
                                  label_visibility="collapsed",
                                  placeholder='{"draft_amount_cents": 20000, …}')
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        st.markdown("OFFER")
        offer_txt  = st.text_area("offer",  key="_ta_offer",  height=160,
                                  label_visibility="collapsed",
                                  placeholder='{"creditor": "Acme", …}')
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        st.markdown("CREDITOR RULES")
        rules_txt  = st.text_area("rules",  key="_ta_rules",  height=185,
                                  label_visibility="collapsed",
                                  placeholder='{"max_terms": 12, …}')
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        run = st.button("Evaluate →", use_container_width=True)

    return client_txt or "", offer_txt or "", rules_txt or "", run


# ─────────────────────────────────────────────────────────────────────────────
# Render helpers
# ─────────────────────────────────────────────────────────────────────────────

def _hero(n_tests: int = 76) -> None:
    st.markdown(f"""
    <div class="rp-hero">
      <div class="rp-hero-left">
        <div class="rp-hero-eyebrow">Retape AI · Settlement Feasibility Engine</div>
        <h1 class="rp-hero-title">Can this deal close?</h1>
        <p class="rp-hero-sub">
          Simulate the escrow account forward in time. Find the cheapest valid schedule.
          Know exactly how much more is needed if the numbers don't work.
        </p>
      </div>
      <div class="rp-hero-badge">
        <div class="rp-hero-badge-label">Test suite</div>
        <div class="rp-hero-badge-value">{n_tests}</div>
        <div style="font-size:10px;color:#8B949E;margin-top:2px">tests passing</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def _status(rd: dict, an: dict) -> None:
    feasible = rd["feasible"]
    shape    = rd.get("pay_shape_used", "")
    pill     = f'<span class="rp-pill">{shape}</span>' if shape else ""
    k        = rd.get("diagnostics", {}).get("selected_k", "?") if feasible else "—"

    if feasible:
        detail = (
            f"{k} payments &nbsp;·&nbsp; {an['duration']} months &nbsp;·&nbsp; "
            f"{an['first_pay']} → {an['last_pay']}"
        )
        st.markdown(f"""
        <div class="rp-status-ok">
          <div class="rp-status-icon">✅</div>
          <div>
            <div class="rp-status-label ok">Feasible{pill}</div>
            <div class="rp-status-title">This offer works — schedule generated</div>
            <div class="rp-status-detail">{detail}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        diag   = rd.get("diagnostics") or {}
        reason = diag.get("reason", "")
        short  = reason[:160] + ("…" if len(reason) > 160 else "")
        st.markdown(f"""
        <div class="rp-status-fail">
          <div class="rp-status-icon">🚫</div>
          <div>
            <div class="rp-status-label fail">Infeasible</div>
            <div class="rp-status-title">Doesn't fit — see gap analysis below</div>
            <div class="rp-status-detail">{short}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)


def _metrics(an: dict, slack: int | None) -> None:
    slk_val = _fmt(slack) if slack is not None else "—"
    tiles = [
        ("blue",   "Offer Total",    _fmt(an["offer_total"]), "creditor receives"),
        ("violet", "Program Fee",    _fmt(an["program_fee"]), "fee on original balance"),
        ("slate",  "Total Cost",     _fmt(an["total_cost"]),  "creditor + fee + bank"),
        ("green",  "Savings",        _fmt(an["savings"]),     f"{an['savings_pct']}% of original"),
        ("amber",  "Bank Fees",      _fmt(an["bank_fees"]),   f"{an['n_payments']} payment(s)"),
        ("teal",   "Min Balance",    slk_val,                  "tightest slack in schedule"),
    ]
    html = '<div class="rp-metrics">'
    for cls, lbl, val, sub in tiles:
        html += (
            f'<div class="rp-metric {cls}">'
            f'<div class="rp-metric-label">{lbl}</div>'
            f'<div class="rp-metric-value">{val}</div>'
            f'<div class="rp-metric-sub">{sub}</div>'
            f'</div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _timeline(schedule: list) -> None:
    st.markdown('<div class="rp-section">Payment Timeline</div>', unsafe_allow_html=True)
    nodes = []
    for i, r in enumerate(schedule):
        is_pay = r["creditor_payment_cents"] > 0
        label  = f"P{i+1}" if is_pay else "fee"
        cls    = "pay" if is_pay else "fee"
        dt     = r["date"][5:]
        nodes.append(
            f'<div class="rp-tnode">'
            f'<div class="rp-tdot {cls}">{label}</div>'
            f'<div class="rp-tdate">{dt}</div>'
            f'</div>'
        )
    sep   = '<span class="rp-tarrow">›</span>'
    inner = sep.join(nodes)
    st.markdown(f'<div class="rp-timeline">{inner}</div>', unsafe_allow_html=True)


def _balance_chart(schedule: list) -> go.Figure:
    dates  = [r["date"] for r in schedule]
    bals   = [r["balance_cents"] / 100 for r in schedule]
    mkr_c  = ["#D97706" if b == 0 else "#2563EB" for b in bals]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=bals,
        mode="lines+markers",
        line=dict(color="#2563EB", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(37,99,235,0.06)",
        marker=dict(size=8, color=mkr_c, line=dict(width=2, color="#fff")),
        hovertemplate="<b>%{x}</b><br>$%{y:,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#FDA4AF", line_width=1.5)
    fig.update_layout(
        height=220, margin=dict(l=0,r=0,t=0,b=0),
        paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9", zeroline=False),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui,sans-serif", size=11, color="#374151"),
    )
    return fig


def _breakdown_chart(schedule: list) -> go.Figure:
    dates = [r["date"] for r in schedule]
    fig   = go.Figure()
    for label, key, color in [
        ("Creditor", "creditor_payment_cents", "#2563EB"),
        ("Program Fee", "program_fee_cents",   "#0891B2"),
        ("Bank Fee",  "bank_fee_cents",         "#D97706"),
    ]:
        fig.add_trace(go.Bar(
            name=label, x=dates,
            y=[r[key] / 100 for r in schedule],
            marker_color=color, marker_line_width=0,
        ))
    fig.update_layout(
        barmode="stack", height=220,
        margin=dict(l=0,r=0,t=0,b=0),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, font=dict(size=11)),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9"),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui,sans-serif", size=11, color="#374151"),
    )
    return fig


def _schedule_table(schedule: list) -> None:
    import pandas as pd
    st.markdown('<div class="rp-section">Payment Schedule</div>', unsafe_allow_html=True)
    df = pd.DataFrame([
        {
            "Date":        r["date"],
            "Creditor":    _fmt(r["creditor_payment_cents"]),
            "Program Fee": _fmt(r["program_fee_cents"]),
            "Bank Fee":    _fmt(r["bank_fee_cents"]),
            "Balance":     _fmt(r["balance_cents"]),
        }
        for r in schedule
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _additional_funds(af: dict) -> None:
    st.markdown('<div class="rp-section">How to Close the Gap</div>', unsafe_allow_html=True)
    ls  = af["lump_sum"]
    inc = af["monthly_increment"]

    def _card(opt: dict, kind: str, detail: str) -> str:
        cls   = "pass" if opt["within_guardrail"] else "warn"
        badge = (
            '<span class="rp-badge-pass">✓ Within guardrail</span>'
            if opt["within_guardrail"]
            else '<span class="rp-badge-warn">⚠ Exceeds guardrail</span>'
        )
        reason = (
            f'<div class="rp-fund-reason">{opt["reason"]}</div>'
            if opt.get("reason") else ""
        )
        return (
            f'<div class="rp-fund {cls}">'
            f'<div class="rp-fund-label">{kind}</div>'
            f'<div class="rp-fund-amount">{_fmt(opt["amount_cents"])}</div>'
            f'<div class="rp-fund-detail">{detail}</div>'
            f'{badge}{reason}'
            f'</div>'
        )

    lump_d = f"One credit on {ls.get('date','—')}"
    inc_d  = f"{_fmt(inc['amount_cents'])} × {inc.get('num_drafts','?')} future drafts"

    st.markdown(
        f'<div class="rp-funds">{_card(ls,"Lump Sum",lump_d)}{_card(inc,"Monthly Increment",inc_d)}</div>',
        unsafe_allow_html=True,
    )


def _diagnosis(diag: dict) -> None:
    kind   = diag.get("kind", "unknown")
    reason = diag.get("reason", "")
    meta   = []
    if diag.get("binding_date"):
        meta.append(f"Binding date: {diag['binding_date']}")
    if diag.get("shortfall_cents") is not None:
        meta.append(f"Shortfall: {_fmt(diag['shortfall_cents'])}")
    meta_html = (
        f'<div class="rp-diag-meta">{" &nbsp;·&nbsp; ".join(meta)}</div>'
        if meta else ""
    )
    st.markdown(f"""
    <div class="rp-diag">
      <span class="rp-diag-kind">{kind}</span>
      <div class="rp-diag-text">{reason}</div>
      {meta_html}
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    client_txt, offer_txt, rules_txt, run = _sidebar()
    _hero()

    if not run:
        st.markdown("""
        <div class="rp-empty">
          <div class="rp-empty-icon">⚖</div>
          <div class="rp-empty-title">Load a case or paste your JSON</div>
          <div class="rp-empty-sub">
            Pick one of the four demo cases from the sidebar, or drop in your own
            client, offer, and creditor rules. Hit <strong>Evaluate →</strong> to
            see the full schedule, balance chart, and minimum funding options.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Parse ──
    errors: list[str] = []
    client_d = offer_d = rules_d = None

    for txt, label in [(client_txt, "Client JSON"), (offer_txt, "Offer JSON"), (rules_txt, "Rules JSON")]:
        if not txt.strip():
            errors.append(f"{label} is empty")
            continue
        try:
            parsed = json.loads(txt)
        except json.JSONDecodeError as e:
            errors.append(f"{label}: {e}")
            continue
        if label == "Client JSON":
            client_d = parsed
        elif label == "Offer JSON":
            offer_d = parsed
        else:
            rules_d = parsed

    if errors:
        for err in errors:
            st.error(err)
        return

    try:
        client = client_from_dict(client_d)
        offer  = offer_from_dict(offer_d)
        rules  = rules_from_dict(rules_d)
        validate_inputs(client, offer, rules)
    except (KeyError, TypeError, ValueError) as e:
        st.error(str(e))
        return

    with st.spinner("Simulating…"):
        result = evaluate_offer(client, offer, rules)

    rd       = result.to_dict()
    an       = _analytics(offer_d, rd)
    schedule = rd.get("schedule") or []
    slack    = rd.get("diagnostics", {}).get("min_balance_cents") if rd["feasible"] else None

    _status(rd, an)
    _metrics(an, slack)

    if rd["feasible"] and schedule:
        _timeline(schedule)
        st.markdown('<div class="rp-section">Charts</div>', unsafe_allow_html=True)
        col_l, col_r = st.columns(2)
        with col_l:
            st.markdown('<div class="rp-chart"><div class="rp-chart-title">Running Balance</div>', unsafe_allow_html=True)
            st.plotly_chart(_balance_chart(schedule), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        with col_r:
            st.markdown('<div class="rp-chart"><div class="rp-chart-title">Payment Breakdown</div>', unsafe_allow_html=True)
            st.plotly_chart(_breakdown_chart(schedule), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        _schedule_table(schedule)
    else:
        if rd.get("additional_funds"):
            _additional_funds(rd["additional_funds"])
        if rd.get("diagnostics"):
            _diagnosis(rd["diagnostics"])

    with st.expander("Raw JSON output", expanded=False):
        st.code(json.dumps(rd, indent=2), language="json")

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)
    creditor = offer_d.get("creditor", "settlement")
    try:
        pdf_bytes = _pdf(rd, an, creditor)
        st.download_button(
            "⬇  Download PDF report",
            data=pdf_bytes,
            file_name=f"retape_{creditor.lower().replace(' ','_')}_report.pdf",
            mime="application/pdf",
        )
    except Exception:
        st.caption("Install `reportlab` to enable PDF export.")


if __name__ == "__main__":
    main()
