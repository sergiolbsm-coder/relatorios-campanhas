"""
Gera um relatório em PDF por marca, na identidade visual do Instituto da
Liderança (agência por trás da ferramenta): visão geral com comparação de
período, funil, série temporal, tabelas de campanha, demografia — por canal
(Meta Ads, Google Ads, Instagram) + funil de vendas (se a marca tiver uma
planilha de leads configurada). GMB fica de fora — pendente de aprovação da
API (item 1.3).

Uso:
    set -a && source .env && set +a
    python3 etl/generate_pdf_report.py --brand associacao_luto_uniao --days 30

O nome da marca é a chave do config.yaml (ex: associacao_luto_uniao,
instituto_da_lideranca, trainer_sergio_moura).
"""

import argparse
import csv
import datetime
import glob
import os
import sqlite3
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.font_manager as fm

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, KeepTogether, HRFlowable,
)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.common import DATA_DIR, DB_PATH, PROJECT_ROOT, load_config

# ---------------------------------------------------------------------------
# Identidade visual — Instituto da Liderança (ver skill idl-design)
# ---------------------------------------------------------------------------
MAGENTA = colors.HexColor("#FF0060")
PURPLE = colors.HexColor("#391694")
PURPLE_DARK = colors.HexColor("#261062")
TEXT = colors.HexColor("#24153E")
TEXT_MUTED = colors.HexColor("#6F667E")
BG_SOFT = colors.HexColor("#F4F0FB")
WHITE = colors.HexColor("#FFFFFF")
GREEN = colors.HexColor("#1E8E3E")
RED = colors.HexColor("#D93025")

FONTS_DIR = PROJECT_ROOT / "etl" / "assets" / "fonts"
LOGO_PATH = PROJECT_ROOT / "etl" / "assets" / "idl_logo.png"
CHART_DIR = PROJECT_ROOT / "etl" / "data" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

# Registra as fontes reais do IDL no reportlab (PDF) e no matplotlib (gráficos)
pdfmetrics.registerFont(TTFont("DMSans", str(FONTS_DIR / "DMSans-Regular.ttf")))
pdfmetrics.registerFont(TTFont("DMSans-Bold", str(FONTS_DIR / "DMSans-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Cormorant-SemiBold", str(FONTS_DIR / "CormorantGaramond-SemiBold.ttf")))
pdfmetrics.registerFont(TTFont("Cormorant-Bold", str(FONTS_DIR / "CormorantGaramond-Bold.ttf")))
pdfmetrics.registerFont(TTFont("JetBrainsMono", str(FONTS_DIR / "JetBrainsMono-Medium.ttf")))

for f in FONTS_DIR.glob("*.ttf"):
    fm.fontManager.addfont(str(f))
plt.rcParams["font.family"] = "DM Sans"

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName="Cormorant-Bold",
                     textColor=PURPLE_DARK, fontSize=26, leading=30, spaceAfter=2)
h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Cormorant-Bold",
                     textColor=PURPLE_DARK, fontSize=16, spaceBefore=10, spaceAfter=6)
small = ParagraphStyle("small", parent=styles["Normal"], fontName="JetBrainsMono",
                        fontSize=8, textColor=TEXT_MUTED)
normal = ParagraphStyle("normal", parent=styles["Normal"], fontName="DMSans-Bold",
                         fontSize=9, textColor=TEXT)


def latest_csv(pattern: str):
    matches = sorted(glob.glob(str(DATA_DIR / pattern)))
    return matches[-1] if matches else None


def read_csv_filtered(pattern: str, brand_display: str):
    path = latest_csv(pattern)
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        return [row for row in csv.DictReader(f) if row.get("brand") == brand_display]


def fmt_num(v, decimals=0):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if decimals == 0:
        return f"{v:,.0f}".replace(",", ".")
    return f"{v:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(v):
    if v in ("", None, "novo"):
        return "novo" if v == "novo" else "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    arrow = "↑" if v >= 0 else "↓"
    return f"{arrow} {abs(v):.1f}%"


def report_header(brand_display, start, end):
    """Cabeçalho no padrão IDL: logo + moldura magenta (ver skill idl-design,
    seção 6 — 'Relatórios')."""
    logo = Image(str(LOGO_PATH), width=32 * mm, height=32 * mm) if LOGO_PATH.exists() else ""
    title_cell = [
        Paragraph(f"Relatório de Campanhas — {brand_display}", h1),
        Paragraph(f"Período: {start.strftime('%d/%m/%Y')} a {end.strftime('%d/%m/%Y')}", small),
    ]
    t = Table([[logo, title_cell]], colWidths=[38 * mm, 132 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 1.4, MAGENTA),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
    ]))
    return t


def scorecard_table(cards):
    """cards: list of (label, value, pct_change_str). 3 por linha."""
    rows, row = [], []
    for i, (label, value, pct) in enumerate(cards):
        pct_color_hex = "#1e8e3e" if (pct.startswith("↑") or pct == "novo") else ("#d93025" if pct.startswith("↓") else "#6f667e")
        cell = Table(
            [[Paragraph(f"<font name='JetBrainsMono' size=7 color='#6F667E'>{label}</font>")],
             [Paragraph(f"<font name='Cormorant-Bold' size=18 color='#24153E'>{value}</font>")],
             [Paragraph(f"<font name='JetBrainsMono' size=8 color='{pct_color_hex}'>{pct}</font>")]],
            colWidths=[55 * mm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BG_SOFT),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 2, MAGENTA),
        ]))
        row.append(cell)
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append("")
        rows.append(row)
    t = Table(rows, colWidths=[57 * mm] * 3, spaceBefore=4, spaceAfter=4)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def data_table(header, rows, col_widths=None):
    data = [header] + rows
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "DMSans-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "DMSans"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 1), (-1, -1), TEXT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BG_SOFT]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#391694").clone(alpha=0.13)),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


FIELD_LABELS_META = [
    ("clicks", "Cliques"), ("impressions", "Impressões"), ("spend", "Investimento"),
    ("reach", "Alcance"), ("frequency", "Frequência"), ("cpc", "CPC médio"),
    ("cpm", "CPM médio"), ("ctr", "CTR"),
]
FIELD_LABELS_GOOGLE = [
    ("clicks", "Cliques"), ("impressions", "Impressões"),
    ("cost", "Investimento"), ("conversions", "Conversões"),
]
GOOD_WHEN_UP = {"clicks", "impressions", "reach", "conversions", "ctr", "new_followers"}
GOOD_WHEN_DOWN = {"spend", "cost", "cpc", "cpm", "frequency"}
PLURAL_FIELDS = {"clicks", "impressions", "conversions", "new_followers"}  # concordância do verbo


def fmt_field_value(field, v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "—"
    if field in ("spend", "cost", "cpc", "cpm"):
        return f"R$ {fmt_num(v, 2)}"
    if field == "ctr":
        return f"{fmt_num(v, 2)}%"
    if field == "frequency":
        return fmt_num(v, 2)
    return fmt_num(v)


def comparison_table(overview_row, fields_labels):
    """Tabela período atual x período anterior x variação — o comparativo
    explícito (não só a setinha do card) pedido pro relatório."""
    rows = []
    for field, label in fields_labels:
        cur = overview_row.get(field)
        prev = overview_row.get(f"{field}_prev")
        pct = overview_row.get(f"{field}_pct_change")
        rows.append([label, fmt_field_value(field, cur), fmt_field_value(field, prev), fmt_pct(pct)])
    return data_table(
        ["Métrica", "Período atual", "Período anterior", "Variação"],
        rows, col_widths=[55 * mm, 40 * mm, 40 * mm, 35 * mm],
    )


def interpret_change(field, pct):
    if pct in ("", None, "novo"):
        return None
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return None
    magnitude = abs(pct)
    if magnitude < 1:
        return None  # variação irrelevante pra citar em texto
    plural = field in PLURAL_FIELDS
    if pct >= 0:
        direction = "subiram" if plural else "subiu"
    else:
        direction = "caíram" if plural else "caiu"
    qualifier = "leve" if magnitude < 15 else ("expressiva" if magnitude < 40 else "forte")
    is_good = (pct >= 0) == (field in GOOD_WHEN_UP)
    return {"direction": direction, "magnitude": magnitude, "qualifier": qualifier, "is_good": is_good}


def build_channel_narrative(overview_row, fields_labels, max_points=3):
    """Gera 2-3 frases em português interpretando as maiores variações do
    período — não é texto fixo, é calculado em cima do pct_change real."""
    changes = []
    for field, label in fields_labels:
        info = interpret_change(field, overview_row.get(f"{field}_pct_change"))
        if info:
            changes.append((label, info))
    if not changes:
        return None
    changes.sort(key=lambda x: -x[1]["magnitude"])
    sentences = []
    for label, info in changes[:max_points]:
        tone = "o que é positivo" if info["is_good"] else "o que pede atenção"
        sentences.append(
            f"{label} {info['direction']} {fmt_num(info['magnitude'], 1)}% em relação ao "
            f"período anterior ({info['qualifier']}) — {tone}."
        )
    return " ".join(sentences)


def _mpl_style(ax, title):
    ax.set_title(title, fontsize=9, loc="left", color="#24153E", fontweight="bold")
    ax.tick_params(axis="x", labelsize=6, rotation=45, colors="#6F667E")
    ax.tick_params(axis="y", labelsize=7, colors="#6F667E")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#391694")
    ax.spines[["left", "bottom"]].set_alpha(0.2)


def line_chart(dates, series: dict, title, filename):
    palette = ["#FF0060", "#391694", "#00D0C9"]
    fig, ax = plt.subplots(figsize=(6.8, 2.6), dpi=150)
    for i, (label, values) in enumerate(series.items()):
        ax.plot(dates, values, label=label, linewidth=1.8, color=palette[i % len(palette)])
    if len(series) > 1:
        ax.legend(fontsize=7, loc="upper left", frameon=False)
    _mpl_style(ax, title)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def bar_chart(labels, values, title, filename, horizontal=False):
    fig, ax = plt.subplots(figsize=(6.8, 2.6), dpi=150)
    if horizontal:
        ax.barh(labels, values, color="#FF0060")
        ax.invert_yaxis()
    else:
        ax.bar(labels, values, color="#FF0060")
        ax.tick_params(axis="x", labelsize=7, rotation=30)
    _mpl_style(ax, title)
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def pie_chart(labels, values, title, filename):
    fig, ax = plt.subplots(figsize=(4, 3), dpi=150)
    ax.pie(values, labels=labels, autopct="%1.0f%%", textprops={"fontsize": 7, "color": "#24153E"},
           colors=["#FF0060", "#391694", "#00D0C9", "#4D1DBF", "#6F667E"])
    ax.set_title(title, fontsize=9, color="#24153E", fontweight="bold")
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------

def build_meta_section(story, brand_key, brand_display, start, end):
    story.append(Paragraph("Meta Ads — Visão Geral", h2))

    overview = read_csv_filtered("meta_ads_overview_*.csv", brand_display)
    if overview:
        o = overview[0]
        cards = [
            ("Cliques", fmt_num(o["clicks"]), fmt_pct(o["clicks_pct_change"])),
            ("Alcance", fmt_num(o["reach"]), fmt_pct(o["reach_pct_change"])),
            ("Impressões", fmt_num(o["impressions"]), fmt_pct(o["impressions_pct_change"])),
            ("Valor gasto", f"R$ {fmt_num(o['spend'], 2)}", fmt_pct(o["spend_pct_change"])),
            ("CPC médio", f"R$ {fmt_num(o['cpc'], 2)}", fmt_pct(o["cpc_pct_change"])),
            ("CPM médio", f"R$ {fmt_num(o['cpm'], 2)}", fmt_pct(o["cpm_pct_change"])),
            ("CTR", f"{fmt_num(o['ctr'], 2)}%", fmt_pct(o["ctr_pct_change"])),
            ("Frequência", fmt_num(o["frequency"], 2), fmt_pct(o["frequency_pct_change"])),
        ]
        story.append(scorecard_table(cards))

        narrative = build_channel_narrative(o, FIELD_LABELS_META)
        if narrative:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(narrative, normal))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Comparativo com o período anterior", normal))
        story.append(comparison_table(o, FIELD_LABELS_META))
        story.append(Spacer(1, 4 * mm))

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT f.date, SUM(f.clicks), SUM(f.cost)
        FROM fact_metrics_daily f
        JOIN dim_brand b ON b.brand_key = f.brand_key
        WHERE b.brand_key = ? AND f.channel = 'meta_ads'
        GROUP BY f.date ORDER BY f.date
        """,
        (brand_key,),
    ).fetchall()
    if rows:
        dates = [datetime.date.fromisoformat(r[0]) for r in rows]
        clicks = [r[1] for r in rows]
        cost = [r[2] for r in rows]
        chart_path = line_chart(dates, {"Cliques": clicks}, "Cliques por dia", f"{brand_key}_meta_clicks.png")
        story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))
        chart_path2 = line_chart(dates, {"Custo (R$)": cost}, "Custo por dia", f"{brand_key}_meta_cost.png")
        story.append(Image(chart_path2, width=170 * mm, height=170 * mm * 2.6 / 6.8))

    camp_rows = conn.execute(
        """
        SELECT f.campaign_name, SUM(f.clicks), SUM(f.impressions), SUM(f.cost)
        FROM fact_metrics_daily f
        WHERE f.brand_key = ? AND f.channel = 'meta_ads' AND f.campaign_name IS NOT NULL
        GROUP BY f.campaign_name ORDER BY SUM(f.clicks) DESC LIMIT 8
        """,
        (brand_key,),
    ).fetchall()
    conn.close()
    if camp_rows:
        story.append(Paragraph("Principais campanhas", normal))
        table_rows = [[name or "(sem nome)", fmt_num(clk), fmt_num(imp), f"R$ {fmt_num(cst, 2)}"]
                      for name, clk, imp, cst in camp_rows]
        story.append(data_table(
            ["Campanha", "Cliques", "Impressões", "Custo"],
            table_rows, col_widths=[80 * mm, 30 * mm, 30 * mm, 30 * mm],
        ))

    demo = read_csv_filtered("meta_ads_demographics_*.csv", brand_display)
    if demo:
        agg = {}
        for row in demo:
            key = row["age"]
            agg[key] = agg.get(key, 0) + int(row["impressions"] or 0)
        if agg:
            labels = sorted(agg.keys())
            values = [agg[k] for k in labels]
            chart_path = bar_chart(labels, values, "Impressões por faixa etária", f"{brand_key}_meta_age.png")
            story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))

    ads = read_csv_filtered("meta_ads_top_ads_*.csv", brand_display)
    if ads:
        ads_sorted = sorted(ads, key=lambda r: int(r["clicks"] or 0), reverse=True)[:8]
        story.append(Paragraph("Principais anúncios", normal))
        table_rows = [[a["ad_name"][:40] if a["ad_name"] else "(sem nome)", fmt_num(a["clicks"]),
                       f"R$ {fmt_num(a['cpc'], 2)}", fmt_num(a["reach"])]
                      for a in ads_sorted]
        story.append(data_table(
            ["Anúncio", "Cliques", "CPC", "Alcance"],
            table_rows, col_widths=[90 * mm, 25 * mm, 25 * mm, 30 * mm],
        ))

    story.append(PageBreak())


def build_google_section(story, brand_key, brand_display, start, end):
    story.append(Paragraph("Google Ads — Visão Geral", h2))

    overview = read_csv_filtered("google_ads_overview_*.csv", brand_display)
    if overview:
        o = overview[0]
        cards = [
            ("Cliques", fmt_num(o["clicks"]), fmt_pct(o["clicks_pct_change"])),
            ("Impressões", fmt_num(o["impressions"]), fmt_pct(o["impressions_pct_change"])),
            ("Custo", f"R$ {fmt_num(o['cost'], 2)}", fmt_pct(o["cost_pct_change"])),
            ("Conversões", fmt_num(o["conversions"]), fmt_pct(o["conversions_pct_change"])),
        ]
        story.append(scorecard_table(cards))

        narrative = build_channel_narrative(o, FIELD_LABELS_GOOGLE)
        if narrative:
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(narrative, normal))
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph("Comparativo com o período anterior", normal))
        story.append(comparison_table(o, FIELD_LABELS_GOOGLE))
        story.append(Spacer(1, 4 * mm))

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT f.date, SUM(f.clicks), SUM(f.cost)
        FROM fact_metrics_daily f
        WHERE f.brand_key = ? AND f.channel = 'google_ads'
        GROUP BY f.date ORDER BY f.date
        """,
        (brand_key,),
    ).fetchall()
    if rows:
        dates = [datetime.date.fromisoformat(r[0]) for r in rows]
        clicks = [r[1] for r in rows]
        cost = [r[2] for r in rows]
        chart_path = line_chart(dates, {"Cliques": clicks}, "Cliques por dia", f"{brand_key}_google_clicks.png")
        story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))
        chart_path2 = line_chart(dates, {"Custo (R$)": cost}, "Custo por dia", f"{brand_key}_google_cost.png")
        story.append(Image(chart_path2, width=170 * mm, height=170 * mm * 2.6 / 6.8))

    camp_rows = conn.execute(
        """
        SELECT f.campaign_name, SUM(f.clicks), SUM(f.impressions), SUM(f.cost), SUM(f.conversions)
        FROM fact_metrics_daily f
        WHERE f.brand_key = ? AND f.channel = 'google_ads' AND f.campaign_name IS NOT NULL
        GROUP BY f.campaign_name ORDER BY SUM(f.clicks) DESC LIMIT 8
        """,
        (brand_key,),
    ).fetchall()
    conn.close()
    if camp_rows:
        story.append(Paragraph("Principais campanhas", normal))
        table_rows = [[name or "(sem nome)", fmt_num(clk), fmt_num(imp), f"R$ {fmt_num(cst, 2)}", fmt_num(conv)]
                      for name, clk, imp, cst, conv in camp_rows]
        story.append(data_table(
            ["Campanha", "Cliques", "Impressões", "Custo", "Conversões"],
            table_rows, col_widths=[65 * mm, 25 * mm, 27 * mm, 27 * mm, 26 * mm],
        ))

    device_rows = read_csv_filtered("google_ads_device_*.csv", brand_display)
    if device_rows:
        agg = {}
        for row in device_rows:
            agg[row["device"]] = agg.get(row["device"], 0) + int(row["clicks"] or 0)
        agg = {k: v for k, v in agg.items() if v > 0}
        if agg:
            chart_path = pie_chart(list(agg.keys()), list(agg.values()), "Cliques por dispositivo", f"{brand_key}_google_device.png")
            story.append(Image(chart_path, width=90 * mm, height=67.5 * mm))

    dow_rows = read_csv_filtered("google_ads_day_of_week_*.csv", brand_display)
    if dow_rows:
        order = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        pt = {"MONDAY": "Seg", "TUESDAY": "Ter", "WEDNESDAY": "Qua", "THURSDAY": "Qui",
              "FRIDAY": "Sex", "SATURDAY": "Sáb", "SUNDAY": "Dom"}
        agg = {d: 0 for d in order}
        for row in dow_rows:
            if row["day_of_week"] in agg:
                agg[row["day_of_week"]] += int(row["clicks"] or 0)
        chart_path = bar_chart([pt[d] for d in order], [agg[d] for d in order],
                                "Cliques por dia da semana", f"{brand_key}_google_dow.png")
        story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))

    kw_rows = read_csv_filtered("google_ads_keywords_*.csv", brand_display)
    if kw_rows:
        kw_sorted = sorted(kw_rows, key=lambda r: int(r["clicks"] or 0), reverse=True)[:10]
        story.append(Paragraph("Principais palavras-chave", normal))
        table_rows = [[k["keyword"], fmt_num(k["clicks"]), fmt_num(k["impressions"]), f"R$ {fmt_num(k['cost'], 2)}"]
                      for k in kw_sorted]
        story.append(data_table(
            ["Palavra-chave", "Cliques", "Impressões", "Custo"],
            table_rows, col_widths=[80 * mm, 30 * mm, 30 * mm, 30 * mm],
        ))

    story.append(PageBreak())


def build_instagram_section(story, brand_key, brand_display, start, end):
    story.append(Paragraph("Instagram Insights — Visão Geral", h2))

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT f.date, f.reach, f.new_followers
        FROM fact_metrics_daily f
        WHERE f.brand_key = ? AND f.channel = 'instagram_organic'
        ORDER BY f.date
        """,
        (brand_key,),
    ).fetchall()
    if rows:
        dates = [datetime.date.fromisoformat(r[0]) for r in rows]
        reach = [r[1] or 0 for r in rows]
        new_followers = [r[2] or 0 for r in rows]
        total_reach = sum(reach)
        total_new_followers = sum(new_followers)

        # Período anterior de mesma duração, se já tiver dado carregado no banco
        days = (end - start).days + 1
        prev_end = start - datetime.timedelta(days=1)
        prev_start = prev_end - datetime.timedelta(days=days - 1)
        conn2 = sqlite3.connect(DB_PATH)
        prev_reach, prev_followers, prev_count = conn2.execute(
            """
            SELECT SUM(f.reach), SUM(f.new_followers), COUNT(*)
            FROM fact_metrics_daily f
            WHERE f.brand_key = ? AND f.channel = 'instagram_organic'
              AND f.date >= ? AND f.date <= ?
            """,
            (brand_key, prev_start.isoformat(), prev_end.isoformat()),
        ).fetchone()
        conn2.close()
        prev_reach = prev_reach or 0
        prev_followers = prev_followers or 0

        def _pct(cur, prev):
            if not prev:
                return None
            return (cur - prev) / prev * 100

        # Só compara se o período anterior tem cobertura de dias parecida com
        # a do atual — poucos dias soltos no banco (ex.: 2 de 27) produzem uma
        # variação % tecnicamente real mas enganosa, então tratamos como "sem
        # dado" nesse caso.
        has_comparable_prev = prev_count and prev_count >= max(1, len(rows) * 0.6)
        reach_pct = _pct(total_reach, prev_reach) if has_comparable_prev else None
        followers_pct = _pct(total_new_followers, prev_followers) if has_comparable_prev else None

        cards = [
            ("Alcance no período", fmt_num(total_reach), fmt_pct(reach_pct) if reach_pct is not None else "—"),
            ("Novos seguidores", fmt_num(total_new_followers), fmt_pct(followers_pct) if followers_pct is not None else "—"),
        ]
        story.append(scorecard_table(cards))

        if has_comparable_prev:
            story.append(Spacer(1, 3 * mm))
            bits = []
            if reach_pct is not None:
                arrow = "cresceu" if reach_pct >= 0 else "caiu"
                bits.append(
                    f"O alcance orgânico {arrow} {abs(reach_pct):.1f}% frente ao período anterior "
                    f"({fmt_num(prev_reach)} → {fmt_num(total_reach)})."
                )
            if followers_pct is not None:
                arrow = "aumentaram" if followers_pct >= 0 else "diminuíram"
                bits.append(
                    f"Novos seguidores {arrow} {abs(followers_pct):.1f}% "
                    f"({fmt_num(prev_followers)} → {fmt_num(total_new_followers)})."
                )
            if bits:
                story.append(Paragraph(" ".join(bits), normal))
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph("Comparativo com o período anterior", normal))
            story.append(data_table(
                ["Métrica", "Período atual", "Período anterior", "Variação"],
                [
                    ["Alcance", fmt_num(total_reach), fmt_num(prev_reach), fmt_pct(reach_pct)],
                    ["Novos seguidores", fmt_num(total_new_followers), fmt_num(prev_followers), fmt_pct(followers_pct)],
                ],
                col_widths=[55 * mm, 40 * mm, 40 * mm, 35 * mm],
            ))
        else:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(
                "Ainda não há dado do período anterior no banco para comparar — "
                "isso se resolve nos próximos relatórios, conforme o histórico acumula.",
                small,
            ))
        story.append(Spacer(1, 4 * mm))

        chart_path = line_chart(dates, {"Alcance": reach}, "Alcance diário", f"{brand_key}_ig_reach.png")
        story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))
        chart_path2 = bar_chart([d.strftime("%d/%m") for d in dates], new_followers,
                                 "Novos seguidores por dia", f"{brand_key}_ig_followers.png")
        story.append(Image(chart_path2, width=170 * mm, height=170 * mm * 2.6 / 6.8))
    conn.close()

    demo = read_csv_filtered("instagram_demographics_age_gender.csv", brand_display)
    if demo:
        agg = {}
        for row in demo:
            agg[row["age"]] = agg.get(row["age"], 0) + int(row["followers"] or 0)
        if agg:
            labels = sorted(agg.keys())
            values = [agg[k] for k in labels]
            chart_path = bar_chart(labels, values, "Seguidores por faixa etária", f"{brand_key}_ig_age.png")
            story.append(Image(chart_path, width=170 * mm, height=170 * mm * 2.6 / 6.8))

    cities = read_csv_filtered("instagram_demographics_city.csv", brand_display)
    if cities:
        cities_sorted = sorted(cities, key=lambda r: int(r["followers"] or 0), reverse=True)[:10]
        story.append(Paragraph("Seguidores por cidade", normal))
        table_rows = [[c["city"], fmt_num(c["followers"])] for c in cities_sorted]
        story.append(data_table(["Cidade", "Seguidores"], table_rows, col_widths=[120 * mm, 40 * mm]))

    story.append(PageBreak())


def build_leads_narrative(m, cpl):
    """Texto interpretando o funil — mesma lógica da skill de diagnóstico de
    funil de leads: nomear o maior vazamento, não só reportar percentuais."""
    total_leads = int(m.get("total_leads") or 0)
    pct_no_owner = float(m.get("pct_no_owner") or 0)
    pct_not_contacted = float(m.get("pct_not_contacted") or 0)
    closed_won = int(m.get("closed_won") or 0)
    close_rate_decided = float(m.get("close_rate_decided_pct") or 0)

    sentences = []
    if total_leads:
        sentences.append(
            f"A campanha gerou {total_leads} leads no período" +
            (f", a um custo médio de R$ {fmt_num(cpl, 2)} por lead." if cpl else ".")
        )
    if total_leads and pct_not_contacted >= 20:
        sentences.append(
            f"{fmt_num(pct_not_contacted, 1)}% desses leads ainda não foram contatados — "
            "esse é hoje o maior vazamento do funil, e é 100% operacional (não depende de "
            "mais investimento em anúncio para ser corrigido)."
        )
    elif total_leads:
        sentences.append(
            f"Apenas {fmt_num(pct_not_contacted, 1)}% dos leads seguem sem contato, um bom sinal de atendimento."
        )
    if total_leads and pct_no_owner >= 50:
        sentences.append(
            f"{fmt_num(pct_no_owner, 1)}% dos leads não têm um responsável atribuído na planilha, "
            "o que dificulta cobrar o acompanhamento de cada um."
        )
    if total_leads:
        if closed_won:
            plural = "leads viraram vendas fechadas" if closed_won > 1 else "lead virou venda fechada"
            sentences.append(
                f"{closed_won} {plural} — uma taxa de fechamento de "
                f"{fmt_num(close_rate_decided, 1)}% entre os leads já decididos (ganhos ou perdidos)."
            )
        else:
            sentences.append(
                "Nenhum lead do período foi fechado como venda até agora — vale checar se o "
                "gargalo está no atendimento, na oferta, ou se ainda é cedo no ciclo de decisão."
            )
    return " ".join(sentences) if sentences else "Sem leads registrados nesse período."


def build_executive_summary(story, brand_key, brand_display, start, end):
    """Leitura em texto do período inteiro, antes do detalhe por canal — soma
    Meta + Google, aponta a maior variação e conecta com o funil de vendas
    quando a marca tem planilha de leads configurada."""
    meta_rows = read_csv_filtered("meta_ads_overview_*.csv", brand_display)
    google_rows = read_csv_filtered("google_ads_overview_*.csv", brand_display)
    meta_o = meta_rows[0] if meta_rows else None
    google_o = google_rows[0] if google_rows else None
    if not meta_o and not google_o:
        return

    def _f(row, field):
        try:
            return float(row.get(field) or 0) if row else 0.0
        except (TypeError, ValueError):
            return 0.0

    total_spend = _f(meta_o, "spend") + _f(google_o, "cost")
    total_spend_prev = _f(meta_o, "spend_prev") + _f(google_o, "cost_prev")
    total_clicks = _f(meta_o, "clicks") + _f(google_o, "clicks")
    total_clicks_prev = _f(meta_o, "clicks_prev") + _f(google_o, "clicks_prev")

    spend_pct = ((total_spend - total_spend_prev) / total_spend_prev * 100) if total_spend_prev else None
    clicks_pct = ((total_clicks - total_clicks_prev) / total_clicks_prev * 100) if total_clicks_prev else None

    days = (end - start).days + 1
    prev_start = start - datetime.timedelta(days=days)
    prev_end = start - datetime.timedelta(days=1)

    story.append(Paragraph("Resumo Executivo", h2))
    story.append(Paragraph(
        f"Comparando os últimos {days} dias ({start.strftime('%d/%m')} a {end.strftime('%d/%m')}) "
        f"com o período imediatamente anterior de mesma duração "
        f"({prev_start.strftime('%d/%m')} a {prev_end.strftime('%d/%m')}):",
        normal,
    ))
    story.append(Spacer(1, 2 * mm))

    if spend_pct is not None:
        arrow = "aumentou" if spend_pct >= 0 else "caiu"
        story.append(Paragraph(
            f"• Investimento total em anúncios (Meta + Google) {arrow} {abs(spend_pct):.1f}%, "
            f"de R$ {fmt_num(total_spend_prev, 2)} para R$ {fmt_num(total_spend, 2)}.",
            normal,
        ))
    if clicks_pct is not None:
        arrow = "cresceu" if clicks_pct >= 0 else "caiu"
        story.append(Paragraph(
            f"• Total de cliques {arrow} {abs(clicks_pct):.1f}%, "
            f"de {fmt_num(total_clicks_prev)} para {fmt_num(total_clicks)}.",
            normal,
        ))

    # Maior variação isolada entre os dois canais, pra apontar onde olhar primeiro
    candidates = []
    if meta_o:
        for field, label in FIELD_LABELS_META:
            info = interpret_change(field, meta_o.get(f"{field}_pct_change"))
            if info:
                candidates.append(("Meta Ads", label, info))
    if google_o:
        for field, label in FIELD_LABELS_GOOGLE:
            info = interpret_change(field, google_o.get(f"{field}_pct_change"))
            if info:
                candidates.append(("Google Ads", label, info))
    if candidates:
        candidates.sort(key=lambda x: -x[2]["magnitude"])
        channel, label, info = candidates[0]
        tone = "vale manter/ampliar o investimento nessa frente" if info["is_good"] else "vale investigar antes de aumentar orçamento aí"
        story.append(Paragraph(
            f"• A maior variação do período foi em {channel}: {label.lower()} {info['direction']} "
            f"{fmt_num(info['magnitude'], 1)}% — {tone}.",
            normal,
        ))

    # Funil de vendas, se a marca tiver planilha configurada
    leads_path = latest_csv(f"leads_funnel_{brand_key}_*.csv")
    if leads_path:
        with open(leads_path, encoding="utf-8") as f:
            leads_rows = list(csv.DictReader(f))
        if leads_rows:
            m = leads_rows[0]
            total_leads = int(m.get("total_leads") or 0)
            if total_leads:
                cpl = (total_spend / total_leads) if total_leads else 0
                story.append(Paragraph(
                    f"• No mesmo período, a planilha de leads registrou {total_leads} novos contatos "
                    f"vindos da campanha — custo por lead de R$ {fmt_num(cpl, 2)} "
                    f"(detalhe do funil na seção \"Funil de Vendas\", mais adiante).",
                    normal,
                ))

    story.append(Spacer(1, 6 * mm))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#391694").clone(alpha=0.13), thickness=1))
    story.append(Spacer(1, 4 * mm))


def build_leads_section(story, brand_key, brand_display, start, end):
    """Funil de vendas — só aparece se a marca tiver uma planilha de leads
    configurada (ver etl/leads_config.py e etl/extract_leads_funnel.py)."""
    path = latest_csv(f"leads_funnel_{brand_key}_*.csv")
    if not path:
        return
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    m = rows[0]

    story.append(Paragraph("Funil de Vendas", h2))
    story.append(Paragraph(
        "Conecta o investimento em anúncio ao resultado comercial — dado lido "
        "direto da planilha de gestão de leads da marca.", small,
    ))
    story.append(Spacer(1, 3 * mm))

    total_leads = int(m.get("total_leads") or 0)
    total_cost = float(m.get("ad_cost_period") or 0)
    cpl = (total_cost / total_leads) if total_leads else 0

    cards = [
        ("Leads no período", fmt_num(total_leads), "—"),
        ("Custo por lead (CPL)", f"R$ {fmt_num(cpl, 2)}" if total_leads else "—", "—"),
        ("Taxa de fechamento (decididos)", f"{fmt_num(m.get('close_rate_decided_pct'), 1)}%", "—"),
        ("Vendas fechadas", fmt_num(m.get("closed_won")), "—"),
        ("% sem proprietário", f"{fmt_num(m.get('pct_no_owner'), 1)}%", "—"),
        ("% nunca contatado", f"{fmt_num(m.get('pct_not_contacted'), 1)}%", "—"),
    ]
    story.append(scorecard_table(cards))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(build_leads_narrative(m, cpl), normal))

    if m.get("value_data_available") != "True":
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            "<font color='#D93025'><b>Nota:</b></font> a planilha de leads não "
            "tem valor de venda registrado nas linhas fechadas — por isso este "
            "relatório mostra custo por lead e taxa de conversão, mas não "
            "retorno em reais (CAC/ROI). Preencher \"Valor Proposta Negociada\" "
            "nas vendas fechadas destrava essa métrica nos próximos relatórios.",
            normal,
        ))

    story.append(PageBreak())


def build_gmb_note(story):
    story.append(Paragraph("Google Meu Negócio", h2))
    story.append(Paragraph(
        "Pendente: a Business Profile API exige aprovação manual da Google "
        "(formulário enviado, resposta pode levar dias — ver item 1.3 do "
        "roadmap). Assim que aprovado, esta seção passa a trazer visualizações, "
        "buscas e ações do perfil, no mesmo padrão das demais.",
        normal,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", required=True, help="Chave da marca no config.yaml")
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    config = load_config()
    brand = config["brands"].get(args.brand)
    if not brand:
        print(f"Marca '{args.brand}' não encontrada em config.yaml.", file=sys.stderr)
        sys.exit(1)
    brand_display = brand["display_name"]

    end = datetime.date.today()
    start = end - datetime.timedelta(days=args.days)

    out_path = PROJECT_ROOT / "etl" / "data" / f"relatorio_{args.brand}_{end.isoformat()}.pdf"
    doc = SimpleDocTemplate(str(out_path), pagesize=A4,
                             leftMargin=15 * mm, rightMargin=15 * mm,
                             topMargin=15 * mm, bottomMargin=15 * mm)

    story = [report_header(brand_display, start, end), Spacer(1, 8 * mm)]
    build_executive_summary(story, args.brand, brand_display, start, end)

    if brand.get("meta_ads", {}).get("status") == "confirmed":
        build_meta_section(story, args.brand, brand_display, start, end)
    if brand.get("google_ads", {}).get("status") == "confirmed":
        build_google_section(story, args.brand, brand_display, start, end)
    if brand.get("instagram_insights", {}).get("status") == "confirmed":
        build_instagram_section(story, args.brand, brand_display, start, end)
    build_leads_section(story, args.brand, brand_display, start, end)
    build_gmb_note(story)

    doc.build(story)
    print(f"PDF gerado: {out_path}")


if __name__ == "__main__":
    main()
