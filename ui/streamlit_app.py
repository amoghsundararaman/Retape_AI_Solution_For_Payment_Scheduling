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
# CSS
# Lesson learned: Streamlit overrides class-based text colors on heading tags.
# All critical text colors are set via inline style= on the HTML elements.
# CSS here handles structural chrome only.
# ─────────────────────────────────────────────────────────────────────────────

CSS = """
<style>
#MainMenu, footer, .stDeployButton, header { display: none !important; }
.block-container { padding-top: 1.2rem !important; padding-bottom: 2rem !important; }

/* Page background */
.stApp { background: #F0F4FA !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #0D1117 !important;
    border-right: 1px solid #21262D !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }

/* All sidebar text forced light */
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] label {
    color: #8B949E !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] > div > div {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    border-radius: 6px !important;
    color: #E6EDF3 !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb] span {
    color: #E6EDF3 !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] svg { fill: #8B949E !important; }
[data-testid="stSidebar"] textarea {
    background: #161B22 !important;
    border: 1px solid #30363D !important;
    color: #E6EDF3 !important;
    font-family: 'SF Mono', 'Menlo', 'Monaco', 'Courier New', monospace !important;
    font-size: 11.5px !important;
    line-height: 1.6 !important;
    border-radius: 6px !important;
    caret-color: #E6EDF3 !important;
}
[data-testid="stSidebar"] textarea:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.2) !important;
}
[data-testid="stSidebar"] .stButton > button {
    background: #2563EB !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    width: 100% !important;
    padding: 0.6rem 1rem !important;
    letter-spacing: 0.01em !important;
    transition: background 0.15s ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover { background: #1D4ED8 !important; }

/* ── Metrics grid ── */
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
    border-top: 3px solid transparent;
}
.rp-metric.c-blue   { border-top-color: #2563EB; }
.rp-metric.c-green  { border-top-color: #16A34A; }
.rp-metric.c-slate  { border-top-color: #64748B; }
.rp-metric.c-amber  { border-top-color: #D97706; }
.rp-metric.c-teal   { border-top-color: #0891B2; }
.rp-metric.c-violet { border-top-color: #7C3AED; }

/* ── Section heading ── */
.rp-section {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #94A3B8;
    margin: 24px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #E2E8F0;
}

/* ── Timeline ── */
.rp-timeline {
    display: flex;
    align-items: center;
    overflow-x: auto;
    padding: 4px 0 8px;
    scrollbar-width: thin;
    scrollbar-color: #E2E8F0 transparent;
}
.rp-tnode { flex-shrink: 0; display: flex; flex-direction: column; align-items: center; gap: 4px; min-width: 50px; }
.rp-tdot {
    width: 34px; height: 34px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 9px; font-weight: 800; letter-spacing: -0.02em;
}
.rp-tdot.p { background: #EFF6FF; color: #1D4ED8; border: 1.5px solid #BFDBFE; }
.rp-tdot.f { background: #FEFCE8; color: #854D0E; border: 1.5px solid #FDE68A; }
.rp-tdate { font-size: 9px; color: #94A3B8; font-weight: 600; }
.rp-tarrow { color: #CBD5E1; font-size: 14px; margin: 0 1px; padding-bottom: 22px; flex-shrink: 0; }

/* ── Funds cards ── */
.rp-funds { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
.rp-fund {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.rp-fund.ok   { border-top: 3px solid #16A34A; }
.rp-fund.warn { border-top: 3px solid #D97706; }

/* ── Download button ── */
.stDownloadButton > button {
    background: #0D1117 !important;
    color: #F0F6FC !important;
    border: 1px solid #30363D !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
}
.stDownloadButton > button:hover { background: #161B22 !important; }

/* ── Expander ── */
[data-testid="stExpander"] summary {
    background: #FFFFFF !important;
    border-radius: 8px !important;
    font-size: 13px !important;
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
    return (
        json.dumps(json.loads((d / "client.json").read_text()), indent=2),
        json.dumps(json.loads((d / "offer.json").read_text()), indent=2),
        json.dumps(json.loads((d / "creditor_rules.json").read_text()), indent=2),
    )

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
        "offer_total": ot,
        "program_fee": fee,
        "bank_fees":   bank,
        "total_cost":  ot + fee + bank,
        "savings":     sav,
        "savings_pct": round(sav / orig * 100, 1) if orig else 0.0,
        "n_payments":  sum(1 for r in sc if r["creditor_payment_cents"] > 0),
        "duration":    len(sc),
        "first_pay":   sc[0]["date"] if sc else None,
        "last_pay":    max((r["date"] for r in sc if r["creditor_payment_cents"] > 0), default=None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF
# ─────────────────────────────────────────────────────────────────────────────

def _build_pdf(rd: dict, an: dict, creditor: str) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    )

    buf   = BytesIO()
    doc   = SimpleDocTemplate(buf, pagesize=letter,
                               topMargin=0.8*inch, bottomMargin=0.8*inch,
                               leftMargin=0.85*inch, rightMargin=0.85*inch)
    ss    = getSampleStyleSheet()
    NAVY  = colors.HexColor("#0D1117")
    BLUE  = colors.HexColor("#2563EB")
    GRAY  = colors.HexColor("#6B7280")
    LGRAY = colors.HexColor("#F8FAFF")
    BDR   = colors.HexColor("#E2E8F0")

    h1   = ParagraphStyle("h1",  parent=ss["Heading1"], fontSize=19, textColor=NAVY,
                           spaceAfter=4, fontName="Helvetica-Bold")
    h2   = ParagraphStyle("h2",  parent=ss["Heading2"], fontSize=12, textColor=NAVY,
                           spaceBefore=14, spaceAfter=6, fontName="Helvetica-Bold")
    body = ParagraphStyle("body",parent=ss["BodyText"], fontSize=9,  leading=13,
                           textColor=colors.HexColor("#374151"))
    cap  = ParagraphStyle("cap", parent=body, textColor=GRAY, fontSize=8)

    story   = []
    feasible = rd["feasible"]

    story.append(Paragraph(f"Settlement Report — {creditor}", h1))
    ok_str = "FEASIBLE ✓" if feasible else "INFEASIBLE ✗"
    story.append(Paragraph(
        f"Status: <b>{ok_str}</b>  ·  Shape: {rd.get('pay_shape_used','—')}  ·  {an['duration']} months",
        body,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=12, spaceBefore=8))

    story.append(Paragraph("Financial Summary", h2))
    rows = [
        ["Offer Total",  _fmt(an["offer_total"])],
        ["Program Fee",  _fmt(an["program_fee"])],
        ["Bank Fees",    _fmt(an["bank_fees"])],
        ["Total Cost",   _fmt(an["total_cost"])],
        ["Savings",      f"{_fmt(an['savings'])} ({an['savings_pct']}%)"],
    ]
    t1 = Table(rows, colWidths=[2.0*inch, 2.4*inch])
    t1.setStyle(TableStyle([
        ("FONTSIZE",      (0,0),(-1,-1), 9),
        ("FONTNAME",      (0,0),(0,-1),  "Helvetica-Bold"),
        ("TEXTCOLOR",     (0,0),(0,-1),  GRAY),
        ("ROWBACKGROUNDS",(0,0),(-1,-1), [LGRAY, colors.white]),
        ("GRID",          (0,0),(-1,-1), 0.3, BDR),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
    ]))
    story.append(t1)

    if feasible and rd.get("schedule"):
        story.append(Paragraph("Payment Schedule", h2))
        sc   = rd["schedule"]
        data = [["Date", "Creditor", "Program Fee", "Bank Fee", "Balance"]]
        for r in sc:
            data.append([
                r["date"], _fmt(r["creditor_payment_cents"]),
                _fmt(r["program_fee_cents"]), _fmt(r["bank_fee_cents"]),
                _fmt(r["balance_cents"]),
            ])
        data.append([
            "TOTAL",
            _fmt(sum(r["creditor_payment_cents"] for r in sc)),
            _fmt(sum(r["program_fee_cents"]       for r in sc)),
            _fmt(sum(r["bank_fee_cents"]           for r in sc)),
            "—",
        ])
        t2 = Table(data, colWidths=[1.1*inch, 1.2*inch, 1.1*inch, 0.9*inch, 1.1*inch])
        t2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  NAVY),
            ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTNAME",      (0,-1),(-1,-1),"Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,-1), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-2), [colors.white, LGRAY]),
            ("BACKGROUND",    (0,-1),(-1,-1),LGRAY),
            ("GRID",          (0,0),(-1,-1), 0.3, BDR),
            ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        story.append(t2)

    story.append(Spacer(1, 16))
    story.append(Paragraph("Generated by Retape AI Settlement Feasibility Engine", cap))
    doc.build(story)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def _sidebar() -> tuple[str, str, str, bool]:
    with st.sidebar:
        # Logo — inline styles guaranteed visible against dark background
        st.markdown(
            '<div style="padding:22px 16px 18px;border-bottom:1px solid #21262D;margin-bottom:18px">'
            '<div style="font-size:15px;font-weight:800;color:#F0F6FC;letter-spacing:-0.02em">Retape AI</div>'
            '<div style="font-size:10px;font-weight:600;color:#6B7280;text-transform:uppercase;'
            'letter-spacing:0.12em;margin-top:3px">Settlement Engine</div>'
            '</div>',
            unsafe_allow_html=True,
        )

        cases  = _discover_cases()
        choice = st.selectbox(
            "LOAD DEMO CASE",
            options=["— or paste below —"] + cases,
            format_func=lambda x: x.replace("_", " "),
            key="case_selector",
        )

        # ── THE FIX ──────────────────────────────────────────────────────────
        # Streamlit text_area with key= reads from session_state; value= is
        # only the initial default and is ignored on subsequent renders.
        # Writing to session_state BEFORE the widget creation forces the update.
        # ─────────────────────────────────────────────────────────────────────
        if choice != st.session_state.get("_prev_case"):
            st.session_state["_prev_case"] = choice
            if choice not in (None, "— or paste below —"):
                c, o, r = _load_case_texts(choice)
                st.session_state["_ta_c"] = c
                st.session_state["_ta_o"] = o
                st.session_state["_ta_r"] = r

        st.markdown(
            '<div style="margin-top:12px;margin-bottom:3px;font-size:10px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.1em;color:#6B7280">Client</div>',
            unsafe_allow_html=True,
        )
        client_txt = st.text_area(
            "client", key="_ta_c", height=185, label_visibility="collapsed",
            placeholder='{"draft_amount_cents": 20000, "draft_day": 1, …}',
        )

        st.markdown(
            '<div style="margin-top:8px;margin-bottom:3px;font-size:10px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.1em;color:#6B7280">Offer</div>',
            unsafe_allow_html=True,
        )
        offer_txt = st.text_area(
            "offer", key="_ta_o", height=155, label_visibility="collapsed",
            placeholder='{"creditor": "Acme", "settlement_pct": 0.5, …}',
        )

        st.markdown(
            '<div style="margin-top:8px;margin-bottom:3px;font-size:10px;font-weight:700;'
            'text-transform:uppercase;letter-spacing:0.1em;color:#6B7280">Creditor Rules</div>',
            unsafe_allow_html=True,
        )
        rules_txt = st.text_area(
            "rules", key="_ta_r", height=185, label_visibility="collapsed",
            placeholder='{"max_terms": 12, "even_pays": false, …}',
        )

        st.markdown('<div style="height:10px"></div>', unsafe_allow_html=True)
        run = st.button("Evaluate →", use_container_width=True)

    return client_txt or "", offer_txt or "", rules_txt or "", run


# ─────────────────────────────────────────────────────────────────────────────
# Render — all text in inline styles to guarantee contrast
# ─────────────────────────────────────────────────────────────────────────────

def _render_hero() -> None:
    # White card with strong accent border — no dark background = no contrast problems.
    # Inline styles on every text element so Streamlit CSS can't override them.
    st.markdown(
        '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-top:4px solid #2563EB;'
        'border-radius:12px;padding:26px 30px 22px;margin-bottom:22px;'
        'box-shadow:0 1px 4px rgba(0,0,0,0.05)">'

        '<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
        'letter-spacing:0.12em;color:#2563EB;margin-bottom:10px">'
        'Retape AI · Settlement Feasibility Engine</div>'

        '<div style="font-size:30px;font-weight:800;color:#0D1117;'
        'letter-spacing:-0.03em;line-height:1.1;margin-bottom:8px">'
        'Can this deal close?</div>'

        '<div style="font-size:14px;color:#475569;line-height:1.6;max-width:580px">'
        'Simulate the escrow account forward in time. Find the cheapest valid schedule. '
        'Know exactly how much more is needed if the numbers don\'t work.'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_status(rd: dict, an: dict) -> None:
    feasible = rd["feasible"]
    shape    = rd.get("pay_shape_used", "")
    k        = rd.get("diagnostics", {}).get("selected_k", "?") if feasible else "—"

    pill = (
        f'<span style="display:inline-block;background:#EFF6FF;color:#1D4ED8;'
        f'border:1px solid #BFDBFE;border-radius:20px;padding:1px 10px;'
        f'font-size:10px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.06em;margin-left:8px;vertical-align:middle">{shape}</span>'
        if shape else ""
    )

    if feasible:
        detail = (
            f"{k} payment{'s' if k != 1 else ''} &nbsp;·&nbsp; "
            f"{an['duration']} month{'s' if an['duration'] != 1 else ''} &nbsp;·&nbsp; "
            f"{an['first_pay']} → {an['last_pay']}"
        )
        st.markdown(
            '<div style="background:#F0FDF4;border:1px solid #86EFAC;border-left:4px solid #16A34A;'
            'border-radius:10px;padding:16px 20px;margin-bottom:18px;display:flex;align-items:center;gap:14px">'
            '<div style="font-size:26px;flex-shrink:0">✅</div>'
            '<div>'
            f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.1em;color:#15803D;margin-bottom:3px">Feasible{pill}</div>'
            '<div style="font-size:16px;font-weight:700;color:#14532D;margin-bottom:3px">'
            'This offer works — schedule generated</div>'
            f'<div style="font-size:12px;color:#166534">{detail}</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        diag  = rd.get("diagnostics") or {}
        short = (diag.get("reason") or "")[:160]
        if len(diag.get("reason", "")) > 160:
            short += "…"
        st.markdown(
            '<div style="background:#FFF1F2;border:1px solid #FDA4AF;border-left:4px solid #DC2626;'
            'border-radius:10px;padding:16px 20px;margin-bottom:18px;display:flex;align-items:center;gap:14px">'
            '<div style="font-size:26px;flex-shrink:0">🚫</div>'
            '<div>'
            '<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.1em;color:#DC2626;margin-bottom:3px">Infeasible</div>'
            '<div style="font-size:16px;font-weight:700;color:#7F1D1D;margin-bottom:3px">'
            "Doesn't fit — see gap analysis below</div>"
            f'<div style="font-size:12px;color:#991B1B">{short}</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_metrics(an: dict, slack: int | None) -> None:
    slk_val = _fmt(slack) if slack is not None else "—"
    tiles = [
        ("c-blue",   "Offer Total",  _fmt(an["offer_total"]), "creditor receives"),
        ("c-violet", "Program Fee",  _fmt(an["program_fee"]), "fee on original balance"),
        ("c-slate",  "Total Cost",   _fmt(an["total_cost"]),  "creditor + fee + bank"),
        ("c-green",  "Savings",      _fmt(an["savings"]),     f"{an['savings_pct']}% of original balance"),
        ("c-amber",  "Bank Fees",    _fmt(an["bank_fees"]),   f"{an['n_payments']} payment(s) × bank fee"),
        ("c-teal",   "Min Balance",  slk_val,                  "tightest buffer (schedule slack)"),
    ]
    html = '<div class="rp-metrics">'
    for cls, lbl, val, sub in tiles:
        html += (
            f'<div class="rp-metric {cls}">'
            f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.08em;color:#94A3B8;margin-bottom:8px">{lbl}</div>'
            f'<div style="font-size:22px;font-weight:800;color:#0D1117;line-height:1;margin-bottom:3px">{val}</div>'
            f'<div style="font-size:11px;color:#94A3B8">{sub}</div>'
            f'</div>'
        )
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def _render_timeline(schedule: list) -> None:
    st.markdown('<div class="rp-section">Payment Timeline</div>', unsafe_allow_html=True)
    nodes, sep = [], '<span class="rp-tarrow">›</span>'
    for i, r in enumerate(schedule):
        is_pay = r["creditor_payment_cents"] > 0
        label  = f"P{i+1}" if is_pay else "fee"
        cls    = "p" if is_pay else "f"
        dt     = r["date"][5:]
        nodes.append(
            f'<div class="rp-tnode">'
            f'<div class="rp-tdot {cls}">{label}</div>'
            f'<div class="rp-tdate">{dt}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="rp-timeline">{sep.join(nodes)}</div>',
        unsafe_allow_html=True,
    )


def _balance_chart(schedule: list) -> go.Figure:
    dates = [r["date"] for r in schedule]
    bals  = [r["balance_cents"] / 100 for r in schedule]
    mkr_c = ["#D97706" if b == 0 else "#2563EB" for b in bals]
    fig   = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=bals, mode="lines+markers",
        line=dict(color="#2563EB", width=2.5),
        fill="tozeroy", fillcolor="rgba(37,99,235,0.06)",
        marker=dict(size=8, color=mkr_c, line=dict(width=2, color="#fff")),
        hovertemplate="<b>%{x}</b><br>$%{y:,.2f}<extra></extra>",
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="#FDA4AF", line_width=1.5)
    fig.update_layout(
        height=230, margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="white", plot_bgcolor="white", showlegend=False,
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9", zeroline=False),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui, sans-serif", size=11, color="#374151"),
    )
    return fig


def _breakdown_chart(schedule: list) -> go.Figure:
    dates = [r["date"] for r in schedule]
    fig   = go.Figure()
    for label, key, color in [
        ("Creditor Payment", "creditor_payment_cents", "#2563EB"),
        ("Program Fee",      "program_fee_cents",      "#0891B2"),
        ("Bank Fee",         "bank_fee_cents",          "#D97706"),
    ]:
        fig.add_trace(go.Bar(
            name=label, x=dates,
            y=[r[key] / 100 for r in schedule],
            marker_color=color, marker_line_width=0,
        ))
    fig.update_layout(
        barmode="stack", height=230, margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="white", plot_bgcolor="white",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=11),
        ),
        yaxis=dict(tickprefix="$", tickformat=",.0f", gridcolor="#F1F5F9"),
        xaxis=dict(gridcolor="#F1F5F9"),
        font=dict(family="system-ui, sans-serif", size=11, color="#374151"),
    )
    return fig


def _render_charts(schedule: list) -> None:
    st.markdown('<div class="rp-section">Charts</div>', unsafe_allow_html=True)
    cl, cr = st.columns(2)
    with cl:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;'
            'padding:16px 16px 6px;box-shadow:0 1px 3px rgba(0,0,0,0.04);margin-bottom:4px">'
            '<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.09em;color:#64748B;margin-bottom:4px">Running Balance</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_balance_chart(schedule), use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)
    with cr:
        st.markdown(
            '<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:10px;'
            'padding:16px 16px 6px;box-shadow:0 1px 3px rgba(0,0,0,0.04);margin-bottom:4px">'
            '<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            'letter-spacing:0.09em;color:#64748B;margin-bottom:4px">Payment Breakdown</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(_breakdown_chart(schedule), use_container_width=True, config={"displayModeBar": False})
        st.markdown("</div>", unsafe_allow_html=True)


def _render_schedule_table(schedule: list) -> None:
    import pandas as pd
    st.markdown('<div class="rp-section">Full Schedule</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="rp-section">Minimum Funding to Close the Gap</div>', unsafe_allow_html=True)
    ls  = af["lump_sum"]
    inc = af["monthly_increment"]

    def _card(opt: dict, kind: str, detail: str) -> str:
        cls    = "ok" if opt["within_guardrail"] else "warn"
        b_bg   = "#F0FDF4" if opt["within_guardrail"] else "#FFFBEB"
        b_col  = "#15803D" if opt["within_guardrail"] else "#92400E"
        b_bdr  = "#BBF7D0" if opt["within_guardrail"] else "#FDE68A"
        b_icon = "✓" if opt["within_guardrail"] else "⚠"
        b_text = "Within guardrail" if opt["within_guardrail"] else "Exceeds guardrail"
        reason = (
            f'<div style="font-size:11px;color:#DC2626;margin-top:7px;line-height:1.5">'
            f'{opt["reason"]}</div>'
            if opt.get("reason") else ""
        )
        return (
            f'<div class="rp-fund {cls}">'
            f'<div style="font-size:10px;font-weight:700;text-transform:uppercase;'
            f'letter-spacing:0.08em;color:#94A3B8;margin-bottom:8px">{kind}</div>'
            f'<div style="font-size:30px;font-weight:900;color:#0D1117;line-height:1;margin-bottom:6px">'
            f'{_fmt(opt["amount_cents"])}</div>'
            f'<div style="font-size:12px;color:#64748B;margin-bottom:10px">{detail}</div>'
            f'<span style="display:inline-flex;align-items:center;gap:4px;background:{b_bg};'
            f'color:{b_col};border:1px solid {b_bdr};border-radius:20px;'
            f'padding:3px 10px;font-size:11px;font-weight:700">{b_icon} {b_text}</span>'
            f'{reason}'
            f'</div>'
        )

    lump_d = f"Single credit on {ls.get('date', '—')}"
    inc_d  = f"{_fmt(inc['amount_cents'])} × {inc.get('num_drafts', '?')} future draft(s)"
    st.markdown(
        f'<div class="rp-funds">{_card(ls, "Lump Sum", lump_d)}{_card(inc, "Monthly Increment", inc_d)}</div>',
        unsafe_allow_html=True,
    )


def _render_diagnosis(diag: dict) -> None:
    kind   = diag.get("kind", "unknown")
    reason = diag.get("reason", "")
    meta   = []
    if diag.get("binding_date"):
        meta.append(f"Binding date: <b>{diag['binding_date']}</b>")
    if diag.get("shortfall_cents") is not None:
        meta.append(f"Shortfall: <b>{_fmt(diag['shortfall_cents'])}</b>")
    meta_html = (
        f'<div style="font-size:11px;color:#6B7280;margin-top:8px">{" &nbsp;·&nbsp; ".join(meta)}</div>'
        if meta else ""
    )
    st.markdown(
        '<div style="background:#FFFFFF;border:1px solid #FECACA;border-left:4px solid #DC2626;'
        'border-radius:10px;padding:18px 22px;margin-top:10px">'
        f'<span style="display:inline-block;background:#FEE2E2;color:#991B1B;'
        f'font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:0.1em;'
        f'padding:2px 9px;border-radius:4px;margin-bottom:8px">{kind}</span>'
        f'<div style="font-size:13px;color:#374151;line-height:1.65">{reason}</div>'
        f'{meta_html}'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_results(rd: dict, an: dict, offer_d: dict) -> None:
    schedule = rd.get("schedule") or []
    slack    = rd.get("diagnostics", {}).get("min_balance_cents") if rd["feasible"] else None

    _render_status(rd, an)
    _render_metrics(an, slack)

    if rd["feasible"] and schedule:
        _render_timeline(schedule)
        _render_charts(schedule)
        _render_schedule_table(schedule)
    else:
        if rd.get("additional_funds"):
            _render_additional_funds(rd["additional_funds"])
        if rd.get("diagnostics"):
            _render_diagnosis(rd["diagnostics"])

    with st.expander("Raw JSON output", expanded=False):
        st.code(json.dumps(rd, indent=2), language="json")

    # PDF — stored in session_state to avoid clearing results on download click
    creditor = offer_d.get("creditor", "settlement")
    try:
        if "_pdf_cache_key" not in st.session_state or st.session_state["_pdf_cache_key"] != id(rd):
            st.session_state["_pdf_bytes"] = _build_pdf(rd, an, creditor)
            st.session_state["_pdf_cache_key"] = id(rd)
        pdf_bytes = st.session_state["_pdf_bytes"]
        st.markdown("<div style='margin-top:16px'></div>", unsafe_allow_html=True)
        st.download_button(
            "⬇  Download PDF report",
            data=pdf_bytes,
            file_name=f"retape_{creditor.lower().replace(' ', '_')}_report.pdf",
            mime="application/pdf",
        )
    except Exception:
        st.caption("Install `reportlab` for PDF export.")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    client_txt, offer_txt, rules_txt, run = _sidebar()
    _render_hero()

    # ── Persist results in session_state so PDF download re-run doesn't clear them ──
    if run:
        errors: list[str] = []
        client_d = offer_d = rules_d = None

        for txt, label in [
            (client_txt, "Client JSON"),
            (offer_txt,  "Offer JSON"),
            (rules_txt,  "Rules JSON"),
        ]:
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
            for e in errors:
                st.error(e)
        else:
            try:
                client = client_from_dict(client_d)
                offer  = offer_from_dict(offer_d)
                rules  = rules_from_dict(rules_d)
                validate_inputs(client, offer, rules)
            except (KeyError, TypeError, ValueError) as e:
                st.error(str(e))
            else:
                with st.spinner("Simulating…"):
                    result = evaluate_offer(client, offer, rules)
                rd = result.to_dict()
                an = _analytics(offer_d, rd)
                # Store so re-runs from PDF download don't wipe the output
                st.session_state["_stored_rd"]      = rd
                st.session_state["_stored_an"]      = an
                st.session_state["_stored_offer_d"] = offer_d
                # Invalidate cached PDF on new evaluation
                st.session_state.pop("_pdf_cache_key", None)

    # Render whatever is in session_state (survives PDF download re-run)
    if "_stored_rd" in st.session_state:
        _render_results(
            st.session_state["_stored_rd"],
            st.session_state["_stored_an"],
            st.session_state["_stored_offer_d"],
        )
    elif not run:
        st.markdown(
            '<div style="text-align:center;padding:72px 40px 80px">'
            '<div style="font-size:52px;margin-bottom:18px;opacity:0.2">⚖</div>'
            '<div style="font-size:20px;font-weight:700;color:#374151;margin-bottom:8px">'
            'Load a case or paste your JSON</div>'
            '<div style="font-size:14px;color:#9CA3AF;max-width:400px;margin:0 auto;line-height:1.6">'
            'Pick one of the four demo cases from the sidebar, or drop in your own '
            'client, offer, and creditor rules. Hit <strong>Evaluate →</strong> to see '
            'the full schedule, balance chart, and minimum funding options.'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
