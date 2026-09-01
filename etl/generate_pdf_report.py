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
        cards = [
            ("Alcance no período", fmt_num(total_reach), "—"),
            ("Novos seguidores", fmt_num(total_new_followers), "—"),
        ]
        story.append(scorecard_table(cards))
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
