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


# ── Custom CSS ──────────────────────────────────────────────────────────────

def _inject_css() -> None:
    st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer     {visibility: hidden;}
    .stDeployButton {display: none;}

    /* Page tone */
    .stApp { background: #F8FAFC; }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: #0F172A;
        border-right: 1px solid #1E293B;
    }
    section[data-testid="stSidebar"] * { color: #CBD5E1 !important; }
    section[data-testid="stSidebar"] .stTextArea textarea {
        background: #1E293B !important;
        border: 1px solid #334155 !important;
        color: #E2E8F0 !important;
        font-family: 'Menlo', monospace;
        font-size: 11px;
    }
    section[data-testid="stSidebar"] .stSelectbox select,
    section[data-testid="stSidebar"] .stSelectbox > div > div {
        background: #1E293B !important;
        border: 1px solid #334155 !important;
        color: #E2E8F0 !important;
    }
    section[data-testid="stSidebar"] label {
        color: #94A3B8 !important;
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    section[data-testid="stSidebar"] .stButton button {
        background: #6366F1 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em;
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        background: #4F46E5 !important;
    }

    /* Hero header */
    .hero {
        background: linear-gradient(135deg, #0F172A 0%, #1E3A5F 60%, #1E2A4A 100%);
        border-radius: 16px;
        padding: 28px 36px;
        margin-bottom: 24px;
        border: 1px solid #1E293B;
        position: relative;
        overflow: hidden;
    }
    .hero::before {
        content: '';
        position: absolute;
        top: -40px; right: -40px;
        width: 200px; height: 200px;
        background: radial-gradient(circle, rgba(99,102,241,0.15) 0%, transparent 70%);
    }
    .hero-eyebrow {
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #818CF8;
        margin-bottom: 8px;
    }
    .hero-title {
        font-size: 26px;
        font-weight: 800;
        color: #F1F5F9;
        margin: 0 0 6px 0;
        line-height: 1.2;
    }
    .hero-sub {
        font-size: 14px;
        color: #94A3B8;
        margin: 0;
    }

    /* Status cards */
    .status-feasible {
        background: linear-gradient(135deg, #ECFDF5, #D1FAE5);
        border: 1px solid #6EE7B7;
        border-left: 4px solid #059669;
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 20px;
    }
    .status-infeasible {
        background: linear-gradient(135deg, #FFF1F2, #FFE4E6);
        border: 1px solid #FDA4AF;
        border-left: 4px solid #E11D48;
        border-radius: 12px;
        padding: 18px 22px;
        margin-bottom: 20px;
    }
    .status-title {
        font-size: 18px;
        font-weight: 800;
        margin: 0 0 4px 0;
    }
    .status-detail {
        font-size: 13px;
        margin: 0;
        opacity: 0.8;
    }
    .shape-pill {
        display: inline-block;
        background: rgba(99,102,241,0.12);
        color: #6366F1;
        border: 1px solid rgba(99,102,241,0.3);
        border-radius: 20px;
        padding: 2px 10px;
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-left: 10px;
        vertical-align: middle;
    }

    /* Metric tiles */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 12px;
        margin-bottom: 20px;
    }
    .metric-tile {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .metric-tile-label {
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94A3B8;
        margin-bottom: 6px;
    }
    .metric-tile-value {
        font-size: 22px;
        font-weight: 800;
        color: #0F172A;
        line-height: 1;
        margin-bottom: 4px;
    }
    .metric-tile-sub {
        font-size: 11px;
        color: #94A3B8;
    }
    .metric-tile-value.green { color: #059669; }
    .metric-tile-value.indigo { color: #6366F1; }
    .metric-tile-value.amber  { color: #D97706; }

    /* Section headings */
    .section-heading {
        font-size: 13px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748B;
        margin: 24px 0 12px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .section-heading::after {
        content: '';
        flex: 1;
        height: 1px;
        background: #E2E8F0;
    }

    /* Flow nodes */
    .flow-wrap {
        display: flex;
        align-items: center;
        gap: 0;
        overflow-x: auto;
        padding: 12px 0 4px;
        scrollbar-width: thin;
    }
    .flow-node {
        flex-shrink: 0;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 5px;
    }
    .flow-dot {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: 800;
    }
    .flow-dot-pay  { background: #EEF2FF; color: #4F46E5; border: 2px solid #A5B4FC; }
    .flow-dot-fee  { background: #FFFBEB; color: #92400E; border: 2px solid #FCD34D; }
    .flow-date { font-size: 9px; color: #94A3B8; text-align: center; font-weight: 600; }
    .flow-arrow { color: #CBD5E1; font-size: 16px; margin: 0 2px; padding-bottom: 22px; flex-shrink: 0; }

    /* Chart container */
    .chart-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
        margin-bottom: 16px;
    }
    .chart-card-title {
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #64748B;
        margin-bottom: 14px;
    }

    /* Funds options */
    .funds-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 20px; }
    .funds-card {
        background: white;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }
    .funds-card.pass { border-top: 3px solid #059669; }
    .funds-card.fail { border-top: 3px solid #D97706; }
    .funds-card-label {
        font-size: 10px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94A3B8;
        margin-bottom: 8px;
    }
    .funds-card-amount { font-size: 28px; font-weight: 900; color: #0F172A; margin-bottom: 4px; }
    .funds-card-detail { font-size: 12px; color: #94A3B8; margin-bottom: 10px; }
    .guardrail-pass {
        display: inline-block;
        background: #D1FAE5; color: #065F46;
        border-radius: 20px; padding: 3px 10px;
        font-size: 11px; font-weight: 700;
    }
    .guardrail-fail {
        display: inline-block;
        background: #FEF3C7; color: #92400E;
        border-radius: 20px; padding: 3px 10px;
        font-size: 11px; font-weight: 700;
    }
    .guardrail-reason { font-size: 11px; color: #EF4444; margin-top: 6px; }

    /* Diagnostics */
    .diag-card {
        background: #FFF1F2;
        border: 1px solid #FDA4AF;
        border-radius: 12px;
        padding: 18px 22px;
        margin-top: 16px;
    }
    .diag-kind {
        display: inline-block;
        background: #E11D48;
        color: white;
        font-size: 10px;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        padding: 2px 9px;
        border-radius: 4px;
        margin-bottom: 8px;
    }
    .diag-text { font-size: 13px; color: #4C0519; line-height: 1.6; }
    .diag-meta { font-size: 11px; color: #BE123C; margin-top: 8px; }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 80px 40px;
        color: #94A3B8;
    }
    .empty-icon { font-size: 56px; margin-bottom: 16px; opacity: 0.5; }
    .empty-title { font-size: 20px; font-weight: 700; color: #64748B; margin-bottom: 8px; }
    .empty-sub { font-size: 14px; }

    /* Sidebar logo area */
    .sidebar-logo {
        padding: 24px 16px 16px;
        border-bottom: 1px solid #1E293B;
        margin-bottom: 20px;
    }
    .sidebar-logo-name {
        font-size: 15px;
        font-weight: 800;
        color: #E2E8F0 !important;
        letter-spacing: -0.02em;
    }
    .sidebar-logo-tag {
        font-size: 10px;
        color: #64748B !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        margin-top: 2px;
    }
    </style>
    """, unsafe_allow_html=True)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _fmt(cents: int) -> str:
    return f"${cents / 100:,.2f}"

def _discover_cases() -> list[str]:
    if not CASES_DIR.is_dir():
        return []
    return sorted(
        d.name for d in CASES_DIR.iterdir()
        if d.is_dir() and all(
            (d / f).exists() for f in ("client.json", "offer.json", "creditor_rules.json")
        )
    )

def _load_case_texts(name: str) -> tuple[str, str, str]:
    d = CASES_DIR / name
    return (
        (d / "client.json").read_text(),
        (d / "offer.json").read_text(),
        (d / "creditor_rules.json").read_text(),
    )

def _compute_analytics(offer_d: dict, result_dict: dict) -> dict:
    from decimal import Decimal, ROUND_HALF_UP
    bal = offer_d.get("creditor_balance_cents", offer_d.get("current_balance_cents", 0))
    ot  = int(
        (Decimal(str(offer_d.get("settlement_pct", 0))) * Decimal(str(bal)))
        .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    orig     = offer_d.get("original_balance_cents", 0)
    schedule = result_dict.get("schedule") or []
    bank     = sum(r["bank_fee_cents"] for r in schedule)
    fee      = sum(r["program_fee_cents"] for r in schedule)
    savings  = orig - ot
    return {
        "offer_total":   ot,
        "program_fee":   fee,
        "bank_fees":     bank,
        "total_cost":    ot + fee + bank,
        "savings":       savings,
        "savings_pct":   round(savings / orig * 100, 1) if orig else 0.0,
        "n_payments":    sum(1 for r in schedule if r["creditor_payment_cents"] > 0),
        "fee_only":      sum(1 for r in schedule if r["creditor_payment_cents"] == 0 and r["program_fee_cents"] > 0),
        "duration":      len(schedule),
        "first_pay":     schedule[0]["date"] if schedule else None,
        "last_pay":      max((r["date"] for r in schedule if r["creditor_payment_cents"] > 0), default=None),
    }


# ── PDF ─────────────────────────────────────────────────────────────────────

def _build_pdf(result_dict: dict, analytics: dict, creditor: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

    buf    = BytesIO()
    doc    = SimpleDocTemplate(buf, pagesize=letter,
                               topMargin=0.7*inch, bottomMargin=0.7*inch,
                               leftMargin=0.75*inch, rightMargin=0.75*inch)
    ss     = getSampleStyleSheet()
    INDIGO = colors.HexColor("#6366F1")
    SLATE  = colors.HexColor("#0F172A")
    GRAY   = colors.HexColor("#64748B")
    LGRAY  = colors.HexColor("#F8FAFC")
    BORDER = colors.HexColor("#E2E8F0")

    h1   = ParagraphStyle("h1",   parent=ss["Heading1"], fontSize=18, textColor=INDIGO, spaceAfter=4)
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9, leading=13)
    cap  = ParagraphStyle("cap",  parent=body, textColor=GRAY, fontSize=8)
    story = []

    feasible = result_dict["feasible"]
    story.append(Paragraph(f"Retape AI — Settlement Report: {creditor}", h1))
    story.append(Paragraph(
        f"{'FEASIBLE ✓' if feasible else 'INFEASIBLE ✗'}  ·  "
        f"Shape: {result_dict.get('pay_shape_used','—')}  ·  "
        f"{analytics['duration']} months",
        body
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=INDIGO, spaceAfter=10))

    # Summary table
    story.append(Paragraph("<b>Financial Summary</b>", body))
    story.append(Spacer(1, 6))
    rows = [
        ["Offer Total",    _fmt(analytics["offer_total"])],
        ["Program Fee",    _fmt(analytics["program_fee"])],
        ["Bank Fees",      _fmt(analytics["bank_fees"])],
        ["Total Cost",     _fmt(analytics["total_cost"])],
        ["Savings",        f"{_fmt(analytics['savings'])} ({analytics['savings_pct']}%)"],
    ]
    tbl = Table(rows, colWidths=[2.0*inch, 2.5*inch])
    tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("FONTNAME",      (0,0),(0,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0,0),(0,-1),  GRAY),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [LGRAY, colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.3, BORDER),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(tbl)

    if feasible and result_dict.get("schedule"):
        story.append(Spacer(1, 14))
        story.append(Paragraph("<b>Payment Schedule</b>", body))
        story.append(Spacer(1, 6))
        sc   = result_dict["schedule"]
        hdrs = [["Date", "Creditor", "Program Fee", "Bank Fee", "Balance"]]
        data = hdrs + [
            [r["date"], _fmt(r["creditor_payment_cents"]), _fmt(r["program_fee_cents"]),
             _fmt(r["bank_fee_cents"]), _fmt(r["balance_cents"])]
            for r in sc
        ] + [["TOTAL",
               _fmt(sum(r["creditor_payment_cents"] for r in sc)),
               _fmt(sum(r["program_fee_cents"] for r in sc)),
               _fmt(sum(r["bank_fee_cents"] for r in sc)),
               "—"]]
        t2 = Table(data, colWidths=[1.1*inch, 1.2*inch, 1.1*inch, 0.9*inch, 1.1*inch])
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  INDIGO),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.white, LGRAY]),
            ("BACKGROUND",    (0,-1),(-1,-1), LGRAY),
            ("FONTNAME",      (0,-1),(-1,-1), "Helvetica-Bold"),
            ("GRID",          (0,0),(-1,-1), 0.3, BORDER),
            ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        story.append(t2)

    story.append(Spacer(1, 20))
    story.append(Paragraph("Generated by Retape AI Settlement Feasibility Engine", cap))
    doc.build(story)
    return buf.getvalue()


# ── Sidebar ──────────────────────────────────────────────────────────────────

def _sidebar() -> tuple[str, str, str, bool]:
    with st.sidebar:
        st.markdown("""
        <div class="sidebar-logo">
          <div class="sidebar-logo-name">⚖ Retape AI</div>
          <div class="sidebar-logo-tag">Settlement Engine</div>
        </div>
        """, unsafe_allow_html=True)

        cases  = _discover_cases()
        choice = st.selectbox(
            "Demo case",
            ["— paste your own —"] + cases,
            format_func=lambda x: x.replace("_", " ") if x != "— paste your own —" else x,
            label_visibility="collapsed",
        )
        st.caption("or paste JSON directly below")
        st.markdown("---")

        if choice != "— paste your own —":
            c_str, o_str, r_str = _load_case_texts(choice)
        else:
            c_str = o_str = r_str = ""

        st.markdown("**Client**")
        client_txt = st.text_area("client", value=c_str, height=190, label_visibility="collapsed",
                                  key="client_json")
        st.markdown("**Offer**")
        offer_txt  = st.text_area("offer",  value=o_str, height=160, label_visibility="collapsed",
                                  key="offer_json")
        st.markdown("**Creditor Rules**")
        rules_txt  = st.text_area("rules",  value=r_str, height=190, label_visibility="collapsed",
                                  key="rules_json")
        st.markdown("")
        run = st.button("Run the numbers →", use_container_width=True)

    return client_txt, offer_txt, rules_txt, run


# ── Rendering helpers ────────────────────────────────────────────────────────

def _render_hero() -> None:
    st.markdown("""
    <div class="hero">
      <div class="hero-eyebrow">Retape AI · Settlement Feasibility Engine</div>
      <h1 class="hero-title">Can this deal close?</h1>
      <p class="hero-sub">
        Simulate the escrow account forward, find the minimum-cost schedule,
        and know exactly how much more is needed if the numbers don't work.
      </p>
    </div>
    """, unsafe_allow_html=True)


def _render_status(result_dict: dict, analytics: dict) -> None:
    feasible = result_dict["feasible"]
    shape    = result_dict.get("pay_shape_used", "")
    shape_pill = f'<span class="shape-pill">{shape}</span>' if shape else ""
    k        = result_dict.get("diagnostics", {}).get("selected_k", "?") if feasible else "—"

    if feasible:
        detail = f"{k} payments · {analytics['duration']} months · {analytics['first_pay']} → {analytics['last_pay']}"
        st.markdown(f"""
        <div class="status-feasible">
          <div class="status-title" style="color:#065F46">
            ✓ This offer works {shape_pill}
          </div>
          <p class="status-detail" style="color:#064E3B">{detail}</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        diag   = result_dict.get("diagnostics") or {}
        reason = diag.get("reason", "")[:140] + ("…" if len(diag.get("reason","")) > 140 else "")
        st.markdown(f"""
        <div class="status-infeasible">
          <div class="status-title" style="color:#9F1239">✗ Doesn't fit — here's the gap</div>
          <p class="status-detail" style="color:#881337">{reason}</p>
        </div>
        """, unsafe_allow_html=True)


def _render_metrics(analytics: dict, slack: int | None) -> None:
    sa  = analytics["savings"]
    sp  = analytics["savings_pct"]
    slk = _fmt(slack) if slack is not None else "—"
    slk_cls = "green" if (slack is not None and slack > 0) else ("amber" if slack == 0 else "")

    tiles = [
        ("Offer Total",   _fmt(analytics["offer_total"]),  "what creditor receives",     ""),
        ("Program Fee",   _fmt(analytics["program_fee"]),  "our fee on original balance", "indigo"),
        ("Total Cost",    _fmt(analytics["total_cost"]),   "creditor + fee + bank",       ""),
        ("Savings",       _fmt(sa),                         f"{sp}% of original balance",  "green"),
        ("Bank Fees",     _fmt(analytics["bank_fees"]),    f"${analytics['bank_fees']/100:.0f} × {analytics['n_payments']} payments", ""),
        ("Min Balance",   slk,                              "tightest buffer (slack)",     slk_cls),
    ]
    html = '<div class="metric-grid">'
    for label, value, sub, cls in tiles:
        html += f"""
        <div class="metric-tile">
          <div class="metric-tile-label">{label}</div>
          <div class="metric-tile-value {cls}">{value}</div>
          <div class="metric-tile-sub">{sub}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_timeline(schedule: list) -> None:
    st.markdown('<div class="section-heading">Payment Timeline</div>', unsafe_allow_html=True)
    nodes = []
    for i, r in enumerate(schedule):
        is_pay = r["creditor_payment_cents"] > 0
        label  = f"P{i+1}" if is_pay else "fee"
        cls    = "flow-dot-pay" if is_pay else "flow-dot-fee"
        dt     = r["date"][5:]  # MM-DD
        nodes.append(
            f'<div class="flow-node">'
            f'<div class="flow-dot {cls}">{label}</div>'
            f'<div class="flow-date">{dt}</div>'
            f'</div>'
        )
    arrow = '<div class="flow-arrow">›</div>'
    html  = '<div class="flow-wrap">' + arrow.join(nodes) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


def _render_balance_chart(schedule: list) -> None:
    dates  = [r["date"] for r in schedule]
    bals   = [r["balance_cents"] / 100 for r in schedule]
    colors = ["#D97706" if b == 0 else "#6366F1" for b in bals]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=bals,
        mode="lines+markers",
        line=dict(color="#6366F1", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(99,102,241,0.07)",
        marker=dict(size=8, color=colors, line=dict(width=2, color="#fff")),
        hovertemplate="<b>%{x}</b><br>Balance: $%{y:,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#FDA4AF", line_width=1.5)
    fig.update_layout(
        height=230,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        showlegend=False,
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9", zeroline=False),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui, sans-serif", size=11),
    )
    st.markdown('<div class="chart-card"><div class="chart-card-title">Running Balance</div>', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_breakdown_chart(schedule: list) -> None:
    dates = [r["date"] for r in schedule]
    fig   = go.Figure()
    fig.add_trace(go.Bar(name="Creditor", x=dates,
                         y=[r["creditor_payment_cents"]/100 for r in schedule],
                         marker_color="#6366F1", marker_line_width=0))
    fig.add_trace(go.Bar(name="Program Fee", x=dates,
                         y=[r["program_fee_cents"]/100 for r in schedule],
                         marker_color="#10B981", marker_line_width=0))
    fig.add_trace(go.Bar(name="Bank Fee", x=dates,
                         y=[r["bank_fee_cents"]/100 for r in schedule],
                         marker_color="#F59E0B", marker_line_width=0))
    fig.update_layout(
        barmode="stack",
        height=230,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="white",
        plot_bgcolor="white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    font=dict(size=11)),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9"),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui, sans-serif", size=11),
    )
    st.markdown('<div class="chart-card"><div class="chart-card-title">Payment Breakdown</div>', unsafe_allow_html=True)
    st.plotly_chart(fig, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)


def _render_schedule_table(schedule: list) -> None:
    import pandas as pd
    st.markdown('<div class="section-heading">Schedule</div>', unsafe_allow_html=True)
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


def _render_additional_funds(af: dict) -> None:
    st.markdown('<div class="section-heading">How to Close the Gap</div>', unsafe_allow_html=True)
    ls  = af["lump_sum"]
    inc = af["monthly_increment"]

    def _card(opt: dict, kind: str, detail: str) -> str:
        cls         = "pass" if opt["within_guardrail"] else "fail"
        badge_cls   = "guardrail-pass" if opt["within_guardrail"] else "guardrail-fail"
        badge_label = "✓ Within guardrail" if opt["within_guardrail"] else "✗ Exceeds guardrail"
        reason_html = f'<div class="guardrail-reason">{opt["reason"]}</div>' if opt.get("reason") else ""
        return f"""
        <div class="funds-card {cls}">
          <div class="funds-card-label">{kind}</div>
          <div class="funds-card-amount">{_fmt(opt["amount_cents"])}</div>
          <div class="funds-card-detail">{detail}</div>
          <span class="{badge_cls}">{badge_label}</span>
          {reason_html}
        </div>"""

    lump_detail = f"One credit on {ls.get('date','—')}"
    inc_detail  = f"{_fmt(inc['amount_cents'])} × {inc.get('num_drafts','?')} future drafts"

    st.markdown(
        f'<div class="funds-grid">{_card(ls, "Lump Sum", lump_detail)}{_card(inc, "Monthly Increment", inc_detail)}</div>',
        unsafe_allow_html=True
    )


def _render_diagnosis(diag: dict) -> None:
    kind   = diag.get("kind", "unknown")
    reason = diag.get("reason", "")
    meta   = []
    if diag.get("binding_date"):
        meta.append(f"Binding date: {diag['binding_date']}")
    if diag.get("shortfall_cents") is not None:
        meta.append(f"Shortfall: {_fmt(diag['shortfall_cents'])}")
    meta_html = " · ".join(meta)
    st.markdown(f"""
    <div class="diag-card">
      <span class="diag-kind">{kind}</span>
      <div class="diag-text">{reason}</div>
      {f'<div class="diag-meta">{meta_html}</div>' if meta_html else ''}
    </div>
    """, unsafe_allow_html=True)


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    _inject_css()
    _render_hero()
    client_txt, offer_txt, rules_txt, run = _sidebar()

    if not run:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">⚖</div>
          <div class="empty-title">Pick a case or paste your JSON</div>
          <div class="empty-sub">
            Use the sidebar to load one of the four demo cases, or drop in
            your own client, offer, and creditor rules. Hit <strong>Run the numbers</strong>
            and you'll see the full schedule, balance chart, and minimum funding options.
          </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Parse
    errors: list[str] = []
    client_d = offer_d = rules_d = None
    for txt, label, target in [
        (client_txt, "Client JSON",       "client_d"),
        (offer_txt,  "Offer JSON",        "offer_d"),
        (rules_txt,  "Creditor Rules JSON","rules_d"),
    ]:
        try:
            locals()[target]  # just a ref
            import builtins
        except Exception:
            pass
        try:
            parsed = json.loads(txt) if txt.strip() else None
            if parsed is None:
                errors.append(f"{label} is empty")
            else:
                if label == "Client JSON":      client_d = parsed
                elif label == "Offer JSON":     offer_d  = parsed
                else:                           rules_d  = parsed
        except json.JSONDecodeError as e:
            errors.append(f"{label}: {e}")

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

    rd        = result.to_dict()
    analytics = _compute_analytics(offer_d, rd)
    schedule  = rd.get("schedule") or []
    slack     = rd.get("diagnostics", {}).get("min_balance_cents") if rd["feasible"] else None

    _render_status(rd, analytics)
    _render_metrics(analytics, slack)

    if rd["feasible"] and schedule:
        _render_timeline(schedule)
        col_l, col_r = st.columns(2)
        with col_l:
            _render_balance_chart(schedule)
        with col_r:
            _render_breakdown_chart(schedule)
        _render_schedule_table(schedule)
    else:
        if rd.get("additional_funds"):
            _render_additional_funds(rd["additional_funds"])
        if rd.get("diagnostics"):
            _render_diagnosis(rd["diagnostics"])

    with st.expander("Raw JSON output", expanded=False):
        st.code(json.dumps(rd, indent=2), language="json")

    st.markdown("---")
    creditor = offer_d.get("creditor", "settlement")
    try:
        pdf = _build_pdf(rd, analytics, creditor)
        st.download_button(
            "⬇ Download report (PDF)",
            data=pdf,
            file_name=f"retape_{creditor.lower().replace(' ','_')}_report.pdf",
            mime="application/pdf",
        )
    except Exception:
        st.caption("Install `reportlab` for PDF export.")


if __name__ == "__main__":
    main()
