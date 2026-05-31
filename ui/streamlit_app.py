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

CASES_DIR  = ROOT / "cases"
SAMPLE_DIR = ROOT / "sample_inputs"

st.set_page_config(
    page_title="Retape AI — Settlement Engine",
    page_icon="⚖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from feasibility.engine import evaluate_offer
from feasibility.models import client_from_dict, offer_from_dict, rules_from_dict
from feasibility.validation import validate_inputs, ValidationError


# CSS handles structural chrome only. Streamlit's theme overrides class-based
# text colors, so critical text colors are set inline on the elements instead.

CSS = """
<style>
/* Hide the menu / deploy / footer clutter only. The header element is kept —
   in Streamlit the control that reopens a collapsed sidebar lives inside it, so
   hiding `header` outright (the old bug) left no way to reopen the sidebar.
   Making it transparent blends it into the page while keeping it functional. */
#MainMenu, footer, .stDeployButton, [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent !important; }

/* Keep the sidebar collapse / reopen button clearly visible. */
[data-testid="stSidebarCollapseButton"] {
    display: inline-flex !important;
    visibility: visible !important;
}

/* Top padding clears the (now visible) header so the sidebar toggle does not
   overlap the hero card. */
.block-container { padding-top: 2.6rem !important; padding-bottom: 2rem !important; }

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

def _case_dirs() -> dict[str, "Path"]:
    """Map each demo-case label to its folder, scanning cases/ then sample_inputs/.

    Official cases are listed first; sample cases get a "sample · " prefix so
    they are visually distinct in the dropdown. Both directories use the same
    three-file layout, so loading is uniform.
    """
    required = ("client.json", "offer.json", "creditor_rules.json")
    mapping: dict[str, Path] = {}
    for root, prefix in ((CASES_DIR, ""), (SAMPLE_DIR, "sample · ")):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if d.is_dir() and all((d / f).exists() for f in required):
                mapping[f"{prefix}{d.name}"] = d
    return mapping

def _discover_cases() -> list[str]:
    return list(_case_dirs().keys())

def _load_case_texts(label: str) -> tuple[str, str, str]:
    d = _case_dirs()[label]
    return (
        json.dumps(json.loads((d / "client.json").read_text()), indent=2),
        json.dumps(json.loads((d / "offer.json").read_text()), indent=2),
        json.dumps(json.loads((d / "creditor_rules.json").read_text()), indent=2),
    )

def _analytics(client_d: dict, offer_d: dict, rules_d: dict, rd: dict) -> dict:
    """Report figures derived from the inputs and result.

    Plan-execution figures (collected fee, bank fees, total cost, net savings)
    are None when infeasible, so we never show numbers for a plan that does
    not exist.
    """
    from decimal import Decimal, ROUND_HALF_UP

    def rhu(pct, amount) -> int:
        return int((Decimal(str(pct)) * Decimal(str(amount)))
                   .quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    cred_bal = offer_d.get("creditor_balance_cents", offer_d.get("current_balance_cents", 0))
    orig_bal = offer_d.get("original_balance_cents", 0)
    pct      = offer_d.get("settlement_pct", 0)
    fee_pct  = rules_d.get("program_fee_pct", 0)
    draft    = client_d.get("draft_amount_cents", 0)

    feasible = rd.get("feasible", False)
    sc       = rd.get("schedule") or []
    diag     = rd.get("diagnostics") or {}

    # Offer economics — valid whether or not a plan can execute.
    offer_total      = rhu(pct, cred_bal)             # what the creditor receives
    program_fee_owed = rhu(fee_pct, orig_bal)         # Retape's fee if the plan runs
    settlement_savings = orig_bal - offer_total       # saved off the original balance

    # Plan execution — only real when feasible (schedule actually exists).
    bank_fees   = sum(r["bank_fee_cents"] for r in sc)
    fee_paid    = sum(r["program_fee_cents"] for r in sc)
    total_cost  = (offer_total + fee_paid + bank_fees) if feasible else None
    net_savings = (settlement_savings - fee_paid - bank_fees) if feasible else None

    # Guardrail caps — computed from the inputs, used in the infeasible report.
    lump_cap = rhu(0.65, offer_total)
    inc_cap  = max(10000, rhu(0.40, draft))

    return {
        "feasible":           feasible,
        # Offer economics
        "creditor_balance":   cred_bal,
        "original_balance":   orig_bal,
        "settlement_pct":     pct,
        "settlement_pct_disp": round(pct * 100, 2),
        "offer_total":        offer_total,
        "settlement_savings": settlement_savings,
        "savings_pct":        round(settlement_savings / orig_bal * 100, 1) if orig_bal else 0.0,
        "program_fee_owed":   program_fee_owed,
        # Plan execution (None when infeasible)
        "program_fee":        fee_paid if feasible else None,
        "bank_fees":          bank_fees if feasible else None,
        "total_cost":         total_cost,
        "net_savings":        net_savings,
        "n_payments":         sum(1 for r in sc if r["creditor_payment_cents"] > 0),
        "duration":           len(sc),
        "first_pay":          sc[0]["date"] if sc else None,
        "last_pay":           max((r["date"] for r in sc if r["creditor_payment_cents"] > 0), default=None),
        # Inputs echoed for the report
        "draft_amount":       draft,
        # Funding gap (infeasible only)
        "shortfall":          diag.get("shortfall_cents"),
        "lump_cap":           lump_cap,
        "inc_cap":            inc_cap,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF  —  multi-audience document: client, analyst, engineer, CEO
# ─────────────────────────────────────────────────────────────────────────────

def _build_pdf(rd: dict, an: dict, creditor: str) -> bytes:
    from datetime import date as _date
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        BaseDocTemplate, PageTemplate, Frame,
        Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether, PageBreak,
    )

    # ── Palette ──────────────────────────────────────────────────────────────
    NAVY  = colors.HexColor("#0D1117")
    BLUE  = colors.HexColor("#2563EB")
    LBLUE = colors.HexColor("#EFF6FF")
    GREEN = colors.HexColor("#16A34A")
    LGREEN= colors.HexColor("#F0FDF4")
    BGREEN= colors.HexColor("#86EFAC")
    RED   = colors.HexColor("#DC2626")
    LRED  = colors.HexColor("#FFF1F2")
    BRED  = colors.HexColor("#FDA4AF")
    AMBER = colors.HexColor("#D97706")
    GRAY  = colors.HexColor("#6B7280")
    LGRAY = colors.HexColor("#F8FAFF")
    MGRAY = colors.HexColor("#F1F5F9")
    BDR   = colors.HexColor("#E2E8F0")
    WHITE = colors.white

    PW, PH = letter
    LM = RM = 0.75 * inch
    TM = 0.9 * inch
    BM = 0.7 * inch

    # ── Header / footer drawn on every page ──────────────────────────────────
    def _on_page(canvas, doc):
        canvas.saveState()
        # Top bar
        canvas.setFillColor(NAVY)
        canvas.rect(0, PH - 0.44*inch, PW, 0.44*inch, fill=1, stroke=0)
        canvas.setFillColor(WHITE)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(LM, PH - 0.27*inch, "Retape AI  ·  Settlement Feasibility Engine")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#8B949E"))
        canvas.drawRightString(PW - RM, PH - 0.27*inch,
                               f"Settlement Analysis Report  ·  {creditor}")
        # Bottom bar
        canvas.setFillColor(MGRAY)
        canvas.rect(0, 0, PW, BM * 0.85, fill=1, stroke=0)
        canvas.setFillColor(GRAY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(LM, 0.28*inch,
                          f"Generated {_date.today().isoformat()}  ·  Confidential — Retape AI")
        canvas.drawRightString(PW - RM, 0.28*inch, f"Page {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = BaseDocTemplate(
        buf, pagesize=letter,
        leftMargin=LM, rightMargin=RM, topMargin=TM, bottomMargin=BM,
    )
    frame = Frame(LM, BM, PW - LM - RM, PH - TM - BM, id="body")
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_on_page)])

    # ── Styles ────────────────────────────────────────────────────────────────
    ss   = getSampleStyleSheet()
    def _s(name, **kw):
        base = kw.pop("parent", ss["Normal"])
        return ParagraphStyle(name, parent=base, **kw)

    S_h1   = _s("h1",   fontSize=20, fontName="Helvetica-Bold", textColor=NAVY,
                 spaceAfter=4, leading=24)
    S_h2   = _s("h2",   fontSize=12, fontName="Helvetica-Bold", textColor=NAVY,
                 spaceBefore=16, spaceAfter=5, leading=15)
    S_h3   = _s("h3",   fontSize=10, fontName="Helvetica-Bold", textColor=BLUE,
                 spaceBefore=10, spaceAfter=3)
    S_body = _s("body", fontSize=9,  leading=13, textColor=colors.HexColor("#374151"))
    S_small= _s("sm",   fontSize=8,  leading=11, textColor=GRAY, parent=S_body)
    S_mono = _s("mono", fontSize=8,  fontName="Courier", leading=11,
                 textColor=NAVY)
    S_lbl  = _s("lbl",  fontSize=8,  fontName="Helvetica-Bold", textColor=GRAY,
                 leading=10)
    S_cap  = _s("cap",  fontSize=7.5, textColor=GRAY, leading=10,
                 alignment=TA_CENTER)

    def P(txt, s=None): return Paragraph(txt, s or S_body)
    def SP(h=8):        return Spacer(1, h)
    def HR(color=BDR, thick=0.5, before=4, after=10):
        return HRFlowable(width="100%", thickness=thick, color=color,
                          spaceAfter=after, spaceBefore=before)

    def _two_col_table(rows, cw=None):
        """Label / value table, no header row."""
        cw = cw or [2.1*inch, 2.6*inch]
        t  = Table(rows, colWidths=cw)
        t.setStyle(TableStyle([
            ("FONTSIZE",      (0,0),(-1,-1), 9),
            ("FONTNAME",      (0,0),(0,-1),  "Helvetica-Bold"),
            ("TEXTCOLOR",     (0,0),(0,-1),  GRAY),
            ("ALIGN",         (1,0),(1,-1),  "RIGHT"),
            ("ROWBACKGROUNDS",(0,0),(-1,-1), [WHITE, LGRAY]),
            ("GRID",          (0,0),(-1,-1), 0.3, BDR),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ]))
        return t

    def _schedule_table(sc):
        hdrs = ["Date", "Creditor Payment", "Program Fee", "Bank Fee", "Running Balance"]
        data = [hdrs]
        for r in sc:
            data.append([
                r["date"],
                _fmt(r["creditor_payment_cents"]),
                _fmt(r["program_fee_cents"])   if r["program_fee_cents"]   else "—",
                _fmt(r["bank_fee_cents"])       if r["bank_fee_cents"]       else "—",
                _fmt(r["balance_cents"]),
            ])
        # Totals
        data.append([
            "TOTAL",
            _fmt(sum(r["creditor_payment_cents"] for r in sc)),
            _fmt(sum(r["program_fee_cents"]       for r in sc)),
            _fmt(sum(r["bank_fee_cents"]           for r in sc)),
            "—",
        ])
        cw = [1.05*inch, 1.3*inch, 1.05*inch, 0.85*inch, 1.25*inch]
        t  = Table(data, colWidths=cw, repeatRows=1)
        t.setStyle(TableStyle([
            # Header row
            ("BACKGROUND",    (0,0),(-1,0),  NAVY),
            ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
            ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0,0),(-1,0),  8),
            # Data rows
            ("FONTSIZE",      (0,1),(-1,-2), 8),
            ("ROWBACKGROUNDS",(0,1),(-1,-2), [WHITE, LGRAY]),
            # Totals row
            ("BACKGROUND",    (0,-1),(-1,-1), MGRAY),
            ("FONTNAME",      (0,-1),(-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,-1),(-1,-1), 8),
            # Alignment
            ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
            # Grid
            ("GRID",          (0,0),(-1,-1), 0.3, BDR),
            ("LINEBELOW",     (0,0),(-1,0),  1.0, BLUE),
            ("LINEABOVE",     (0,-1),(-1,-1),0.5, BDR),
            # Padding
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ]))
        return t

    def _status_banner(feasible: bool):
        bg    = LGREEN  if feasible else LRED
        bdr   = BGREEN  if feasible else BRED
        hexc  = "16A34A" if feasible else "DC2626"
        label = "FEASIBLE" if feasible else "INFEASIBLE"
        icon  = "✓" if feasible else "✗"
        sub   = (
            "A valid payment schedule exists. The escrow balance stays non-negative "
            "throughout and the full program fee is collected before the horizon."
            if feasible else
            "No valid payment schedule exists with the current funding level. "
            "See the Additional Funding section for the minimum required."
        )
        status_style = _s("status", fontSize=13, fontName="Helvetica-Bold",
                          textColor=colors.HexColor(f"#{hexc}"), leading=16)
        tbl = Table(
            [[
                P(f'{icon}&nbsp;{label}', status_style),
                P(sub, S_small),
            ]],
            colWidths=[1.85*inch, 5.15*inch],
        )
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), bg),
            ("BOX",           (0,0),(-1,-1), 1,   bdr),
            ("LEFTPADDING",   (0,0),(0,-1),  16),
            ("LEFTPADDING",   (1,0),(1,-1),  4),
            ("RIGHTPADDING",  (0,0),(-1,-1), 14),
            ("TOPPADDING",    (0,0),(-1,-1), 13),
            ("BOTTOMPADDING", (0,0),(-1,-1), 13),
            ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
        ]))
        return tbl

    def _kpi_grid(cells):
        """cells = [(label, value, sub), ...]  — rendered as a row of mini KPI boxes."""
        n  = len(cells)
        cw = [(PW - LM - RM) / n] * n
        header_row = [P(f"<b>{c[0]}</b>", S_lbl) for c in cells]
        value_row  = [
            P(f'<font size="14"><b>{c[1]}</b></font>', _s(f"kv{i}", fontSize=14,
              fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_LEFT))
            for i, c in enumerate(cells)
        ]
        sub_row    = [P(c[2], S_small) for c in cells]
        t = Table([header_row, value_row, sub_row], colWidths=cw)
        t.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), WHITE),
            ("BOX",           (0,0),(-1,-1), 0.5, BDR),
            ("INNERGRID",     (0,0),(-1,-1), 0.3, BDR),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("BACKGROUND",    (0,0),(-1,0),  MGRAY),
        ]))
        return t

    # ── Build story ───────────────────────────────────────────────────────────
    story    = []
    feasible = rd["feasible"]
    sc       = rd.get("schedule") or []
    diag     = rd.get("diagnostics") or {}
    af       = rd.get("additional_funds")
    shape    = rd.get("pay_shape_used", "—")
    k        = diag.get("selected_k", len([r for r in sc if r["creditor_payment_cents"] > 0]))

    # ──────────────────────────────────────────────────────────────────────────
    # PAGE 1  ·  Executive summary
    # ──────────────────────────────────────────────────────────────────────────
    story.append(P(f"Settlement Analysis — {creditor}", S_h1))
    story.append(P(
        f"Creditor: <b>{creditor}</b>  ·  "
        f"Settlement: <b>{an['settlement_pct_disp']}%</b> of current creditor balance  ·  "
        f"Generated: <b>{_date.today().isoformat()}</b>",
        S_body,
    ))
    story.append(SP(10))
    story.append(_status_banner(feasible))
    story.append(SP(14))

    # KPI strip — the three numbers that matter, adapted to the verdict.
    if feasible:
        story.append(_kpi_grid([
            ("Offer Total",  _fmt(an["offer_total"]),        "what creditor receives"),
            ("Client Saves", _fmt(an["settlement_savings"]), f"{an['savings_pct']}% off original"),
            ("Total Cost",   _fmt(an["total_cost"]),         "offer + program fee + bank fees"),
        ]))
    else:
        shortfall = _fmt(an["shortfall"]) if an["shortfall"] is not None else "—"
        story.append(_kpi_grid([
            ("Offer Total",       _fmt(an["offer_total"]), "what the deal asks for"),
            ("Funding Shortfall", shortfall,                "gap blocking the plan"),
            ("Settlement %",      f"{an['settlement_pct_disp']}%", "of creditor balance"),
        ]))
    story.append(SP(14))

    # Offer economics — true regardless of feasibility (describes the offer itself).
    econ_rows = [
        ["Original Balance (owed)",          _fmt(an["original_balance"])],
        ["Current Creditor Balance",         _fmt(an["creditor_balance"])],
        ["Settlement Percentage",            f"{an['settlement_pct_disp']}%  (of creditor balance)"],
        ["Offer Total (creditor receives)",  _fmt(an["offer_total"])],
        ["Settlement Savings vs Original",   f"{_fmt(an['settlement_savings'])}  ({an['savings_pct']}%)"],
    ]
    story.append(KeepTogether([
        P("Offer Economics", S_h2),
        HR(BLUE, thick=1, before=2, after=8),
        _two_col_table(econ_rows),
    ]))
    story.append(SP(10))

    # Plan cost — only present a cost breakdown when a plan actually executes.
    if feasible:
        story.append(KeepTogether([
            P("Plan Cost Breakdown", S_h2),
            HR(BLUE, thick=1, before=2, after=8),
            _two_col_table([
                ["Offer Total (to creditor)",     _fmt(an["offer_total"])],
                ["Program Fee (Retape AI)",       _fmt(an["program_fee"])],
                ["Bank Fees (per payment)",       _fmt(an["bank_fees"])],
                ["Total Program Cost",            _fmt(an["total_cost"])],
                ["Net Savings After All Fees",    _fmt(an["net_savings"])],
            ]),
        ]))
        story.append(SP(10))
    else:
        story.append(KeepTogether([
            P("Plan Cost Breakdown", S_h2),
            HR(BLUE, thick=1, before=2, after=8),
            P(
                "No payment plan executes at the current funding level, so there is no "
                f"realised program cost. If funded, the program fee would be "
                f"{_fmt(an['program_fee_owed'])} (round(program_fee_pct × original balance)). "
                "See the Infeasibility Analysis and Minimum Additional Funding sections "
                "for the gap and how to close it.",
                S_body,
            ),
        ]))
        story.append(SP(10))

    # Plan parameters
    if feasible:
        story.append(KeepTogether([
            P("Plan Parameters", S_h2),
            HR(BLUE, thick=1, before=2, after=8),
            _two_col_table([
                ["Payment Shape",        shape.capitalize()],
                ["Number of Payments (k)", str(k)],
                ["Plan Duration",         f"{an['duration']} month{'s' if an['duration'] != 1 else ''}"],
                ["First Payment Date",    an["first_pay"] or "—"],
                ["Last Payment Date",     an["last_pay"]  or "—"],
                ["Min Balance (Slack)",   _fmt(diag.get("min_balance_cents", 0))],
                ["Fee-Only Months",       str(sum(1 for r in sc if r["creditor_payment_cents"] == 0 and r["program_fee_cents"] > 0))],
                ["Total Bank Fees Paid",  _fmt(an["bank_fees"])],
            ]),
        ]))

    # ──────────────────────────────────────────────────────────────────────────
    # PAGE 2  ·  Full payment schedule (feasible) or gap analysis (infeasible)
    # ──────────────────────────────────────────────────────────────────────────
    story.append(PageBreak())

    if feasible and sc:
        story.append(P("Payment Schedule", S_h2))
        story.append(P(
            f"Each row is one cadence date. Credits (drafts) land on the draft day; "
            f"debits (creditor payment + bank fee + program fee) are applied on the cadence date. "
            f"<b>Running Balance</b> is after all debits on that date.",
            S_small,
        ))
        story.append(SP(6))
        story.append(_schedule_table(sc))
        story.append(SP(10))

        # Cumulative fee collection
        story.append(KeepTogether([
            P("Program Fee Collection", S_h2),
            HR(BLUE, thick=1, before=2, after=8),
        ]))
        fee_rows = [["Date", "Fee This Date", "Cumulative Fee Collected", "Remaining Fee"]]
        total_fee = an["program_fee"]
        running   = 0
        for r in sc:
            if r["program_fee_cents"] > 0:
                running += r["program_fee_cents"]
                fee_rows.append([
                    r["date"],
                    _fmt(r["program_fee_cents"]),
                    _fmt(running),
                    _fmt(max(0, total_fee - running)),
                ])
        if len(fee_rows) > 1:
            ft = Table(fee_rows, colWidths=[1.2*inch, 1.3*inch, 1.7*inch, 1.3*inch],
                       repeatRows=1)
            ft.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,0),  BLUE),
                ("TEXTCOLOR",     (0,0),(-1,0),  WHITE),
                ("FONTNAME",      (0,0),(-1,0),  "Helvetica-Bold"),
                ("FONTSIZE",      (0,0),(-1,-1), 8),
                ("ROWBACKGROUNDS",(0,1),(-1,-1), [WHITE, LGRAY]),
                ("ALIGN",         (1,0),(-1,-1), "RIGHT"),
                ("GRID",          (0,0),(-1,-1), 0.3, BDR),
                ("TOPPADDING",    (0,0),(-1,-1), 5),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
                ("LEFTPADDING",   (0,0),(-1,-1), 8),
            ]))
            story.append(ft)
        else:
            story.append(P("No program fee in this schedule (fee is zero).", S_small))
        story.append(SP(10))

        # Shape interpretation note
        shape_notes = {
            "even":      "Even shape: all creditor payments are equal (or as equal as possible with "
                         "remainder cents on the latest payments). Ballooning is irrelevant when "
                         "payments must be equal.",
            "balloon":   "Balloon shape: early payments sit at the per-position floor (minimum allowed). "
                         "The final payment absorbs the full remaining offer balance. Maximum deferral "
                         "of creditor obligation — maximises free cash early for fee front-loading.",
            "staircase": "Staircase shape: non-decreasing step function with at most max_segments distinct "
                         "payment levels. The lexicographically smallest valid vector was chosen — smallest "
                         "early payments leave the most free cash for fee collection early.",
        }
        story.append(KeepTogether([
            P("Shape &amp; Optimisation Notes", S_h2),
            HR(BLUE, thick=1, before=2, after=8),
            P(shape_notes.get(shape, f"Shape: {shape}"), S_body),
            SP(4),
            P(
                "The fee placement is greedy-earliest: at each cadence date the engine skims "
                "the maximum fee the balance allows before moving forward. This is provably optimal "
                "for front-loading — if any fee placement is feasible for a given payment vector, "
                "the greedy one is. The two layers (payment vector and fee placement) are independent "
                "and require no iteration.",
                S_body,
            ),
        ]))

    else:
        # ── Infeasible: gap analysis ──────────────────────────────────────────
        story.append(P("Infeasibility Analysis", S_h2))
        story.append(HR(RED, thick=1.5, before=2, after=8))

        kind   = diag.get("kind", "unknown")
        reason = diag.get("reason", "")
        bd     = diag.get("binding_date")
        sf     = diag.get("shortfall_cents")

        diag_tbl = Table(
            [
                [P("<b>Cause</b>",        S_lbl), P(kind,   S_mono)],
                [P("<b>Explanation</b>",  S_lbl), P(reason, S_body)],
                [P("<b>Binding Date</b>", S_lbl), P(str(bd) if bd else "—", S_body)],
                [P("<b>Shortfall</b>",    S_lbl), P(_fmt(sf) if sf is not None else "—", S_body)],
            ],
            colWidths=[1.3*inch, 5.2*inch],
        )
        diag_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,-1),  LRED),
            ("ROWBACKGROUNDS",(1,0),(1,-1),  [WHITE, LGRAY]),
            ("GRID",          (0,0),(-1,-1), 0.3, BDR),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ]))
        story.append(diag_tbl)
        story.append(SP(14))

        if af:
            story.append(P("Minimum Additional Funding", S_h2))
            story.append(P(
                "Two independent funding options that would make a valid schedule possible. "
                "They differ because a lump sum lands early (before the first usable cadence date) "
                "while the monthly increment is spread across all future drafts — including any that "
                "arrive too late to help, which is why the totals legitimately disagree.",
                S_small,
            ))
            story.append(SP(8))

            ls  = af["lump_sum"]
            inc = af["monthly_increment"]

            # Each card is a single-column stack sized to fit its half of the
            # row (≈ 3.05"), so the badge never overflows the page edge.
            CARD_W = 3.05 * inch

            def _fund_block(opt: dict, kind_label: str, detail: str) -> Table:
                ok       = opt["within_guardrail"]
                bg       = LGREEN if ok else colors.HexColor("#FFFBEB")
                badge    = "✓ Within guardrail" if ok else "✗ Exceeds guardrail"
                badge_hx = "16A34A" if ok else "D97706"
                reason   = opt.get("reason", "")
                amt_style = _s(f"amt_{kind_label}", fontSize=18, fontName="Helvetica-Bold",
                               textColor=NAVY, leading=21)
                rows = [
                    [P(kind_label.upper(), S_lbl)],
                    [P(f'{_fmt(opt["amount_cents"])}', amt_style)],
                    [P(detail, S_small)],
                    [P(f'<font color="#{badge_hx}"><b>{badge}</b></font>', S_lbl)],
                ]
                if reason:
                    rows.append([P(f'<font color="#DC2626">{reason}</font>', S_small)])
                t = Table(rows, colWidths=[CARD_W])
                t.setStyle(TableStyle([
                    ("BACKGROUND",    (0,0),(-1,-1), bg),
                    ("BOX",           (0,0),(-1,-1), 0.5, BDR),
                    ("LINEABOVE",     (0,0),(-1,0),  2.5, GREEN if ok else AMBER),
                    ("TOPPADDING",    (0,0),(-1,0),  12),
                    ("TOPPADDING",    (0,1),(-1,-1), 3),
                    ("BOTTOMPADDING", (0,0),(-1,-2), 3),
                    ("BOTTOMPADDING", (0,-1),(-1,-1),12),
                    ("LEFTPADDING",   (0,0),(-1,-1), 14),
                    ("RIGHTPADDING",  (0,0),(-1,-1), 14),
                ]))
                return t

            lump_detail = f"Single credit placed on {ls.get('date', '—')}"
            inc_detail  = (
                f"{_fmt(inc['amount_cents'])} added to each of "
                f"{inc.get('num_drafts', '?')} future drafts"
            )

            funds_outer = Table(
                [[_fund_block(ls, "Lump Sum", lump_detail),
                  _fund_block(inc, "Monthly Increment", inc_detail)]],
                colWidths=[CARD_W, CARD_W],
                hAlign="LEFT",
            )
            funds_outer.setStyle(TableStyle([
                ("LEFTPADDING",   (0,0),(0,-1),  0),
                ("RIGHTPADDING",  (0,0),(0,-1),  9),
                ("LEFTPADDING",   (1,0),(1,-1),  9),
                ("RIGHTPADDING",  (1,0),(1,-1),  0),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 0),
                ("VALIGN",        (0,0),(-1,-1), "TOP"),
            ]))
            story.append(funds_outer)
            story.append(SP(12))

            # Guardrail reference — every figure derived from the actual inputs.
            story.append(KeepTogether([
                P("Guardrail Reference", S_h3),
                _two_col_table([
                    ["Lump sum cap",
                     f"{_fmt(an['lump_cap'])}  =  round(0.65 × {_fmt(an['offer_total'])} offer total)"],
                    ["Lump sum required",
                     f"{_fmt(ls['amount_cents'])}  —  {'within' if ls['within_guardrail'] else 'exceeds'} cap"],
                    ["Monthly increment cap",
                     f"{_fmt(an['inc_cap'])}  =  max($100.00, round(0.40 × {_fmt(an['draft_amount'])} draft))"],
                    ["Monthly increment required",
                     f"{_fmt(inc['amount_cents'])}  —  {'within' if inc['within_guardrail'] else 'exceeds'} cap"],
                ], cw=[1.85*inch, 4.75*inch]),
            ]))

    # ──────────────────────────────────────────────────────────────────────────
    # LAST PAGE  ·  Technical notes (input parameters + methodology)
    # ──────────────────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(P("Technical Reference", S_h2))
    story.append(HR(BLUE, thick=1, before=2, after=8))
    story.append(P(
        "This section documents the engine inputs and methodology for audit, "
        "reproducibility, and AI/data engineering review.",
        S_small,
    ))
    story.append(SP(8))

    # Methodology
    story.append(P("Engine Methodology", S_h3))
    story.append(P(
        "The settlement feasibility engine simulates the client's escrow account forward in time. "
        "It works in two independent layers: (1) for each candidate payment count k, build the "
        "lexicographically smallest valid creditor-payment vector — smallest early payments maximise "
        "free cash for fee collection; (2) assign the program fee greedily from the earliest date "
        "forward, skimming only free cash. Greedy-earliest fee is provably the most front-loaded and "
        "most forgiving placement — if any fee schedule is feasible for a given payment vector, "
        "the greedy one is. The two layers never iterate. The best k is chosen by the front-load "
        "objective (cumulative fee collected at each cadence date, lexicographically). Ties break "
        "toward fewer payments.",
        S_body,
    ))
    story.append(SP(8))

    story.append(P("Rounding Policy", S_h3))
    story.append(P(
        "All money is integer cents. Every rounding operation uses half-up (a 0.5 rounds away "
        "from zero) implemented via Python's decimal.Decimal, not the language built-in round() "
        "which is half-to-even. Offer total = round_half_up(settlement_pct × creditor_balance). "
        "Program fee = round_half_up(program_fee_pct × original_balance).",
        S_body,
    ))
    story.append(SP(8))

    story.append(P("Assumptions", S_h3))
    assumptions = [
        "All future ledger credits are treated as client drafts for the monthly increment calculation.",
        "Committed debits after last_draft_date are outside the planning window and not simulated.",
        "The lump sum is placed on the earliest funded date (earliest date > as_of_date).",
        "num_drafts counts all future drafts including any that arrive too late to help.",
        "Same-date entries: credits are applied before debits on any given calendar date.",
    ]
    for a in assumptions:
        story.append(P(f"• {a}", S_body))
    story.append(SP(12))

    story.append(HR(BDR))
    story.append(P(
        f"Retape AI Settlement Feasibility Engine  ·  "
        f"Generated {_date.today().isoformat()}  ·  "
        f"Python 3.12 stdlib  ·  deterministic engine  ·  Confidential",
        S_cap,
    ))

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

        # A keyed text_area reads from session_state and ignores value= after
        # the first render, so write the chosen case into state before the
        # widgets are created.
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
    if an["feasible"]:
        # Executed-plan economics — every figure reflects a real schedule.
        slk_val = _fmt(slack) if slack is not None else "—"
        tiles = [
            ("c-blue",   "Offer Total",  _fmt(an["offer_total"]), "creditor receives"),
            ("c-violet", "Program Fee",  _fmt(an["program_fee"]), "collected across the plan"),
            ("c-amber",  "Bank Fees",    _fmt(an["bank_fees"]),   f"{an['n_payments']} payment(s)"),
            ("c-slate",  "Total Cost",   _fmt(an["total_cost"]),  "offer + fee + bank"),
            ("c-green",  "Client Saves", _fmt(an["settlement_savings"]), f"{an['savings_pct']}% off original"),
            ("c-teal",   "Min Balance",  slk_val,                  "tightest slack in schedule"),
        ]
    else:
        # No plan executes — show the offer terms and the funding gap, not
        # numbers from a schedule that doesn't exist.
        shortfall = _fmt(an["shortfall"]) if an["shortfall"] is not None else "—"
        tiles = [
            ("c-blue",   "Offer Total",       _fmt(an["offer_total"]),     "what the deal asks for"),
            ("c-slate",  "Original Balance",  _fmt(an["original_balance"]), "client's original debt"),
            ("c-violet", "Settlement %",      f"{an['settlement_pct_disp']}%", "of current creditor balance"),
            ("c-amber",  "Funding Shortfall", shortfall,                    "gap that blocks the plan"),
            ("c-teal",   "Program Fee",       _fmt(an["program_fee_owed"]), "fee if the plan ran"),
            ("c-green",  "Potential Savings", _fmt(an["settlement_savings"]), f"{an['savings_pct']}% — only if funded"),
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
                an = _analytics(client_d, offer_d, rules_d, rd)
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
