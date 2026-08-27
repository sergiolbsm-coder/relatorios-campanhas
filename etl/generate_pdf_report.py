"""
Gera um relatório em PDF por marca, no estilo do relatório de referência
(mLabs): visão geral com comparação de período, funil, série temporal,
tabelas de campanha, demografia — por canal (Meta Ads, Google Ads,
Instagram). GMB fica de fora — pendente de aprovação da API (item 1.3).

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

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    PageBreak, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.common import DATA_DIR, DB_PATH, PROJECT_ROOT, load_config

ORANGE = colors.HexColor("#F4762A")
DARK = colors.HexColor("#1C1C1E")
GRAY_BG = colors.HexColor("#F2F2F2")
GREEN = colors.HexColor("#1E8E3E")
RED = colors.HexColor("#D93025")

CHART_DIR = PROJECT_ROOT / "etl" / "data" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=DARK, fontSize=18, spaceAfter=2)
h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=DARK, fontSize=13, spaceBefore=10, spaceAfter=6)
small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.gray)
normal = ParagraphStyle("normal", parent=styles["Normal"], fontSize=9)


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


def scorecard_table(cards):
    """cards: list of (label, value, pct_change_str). 3 por linha."""
    rows, row = [], []
    for i, (label, value, pct) in enumerate(cards):
        pct_color_hex = "#1e8e3e" if (pct.startswith("↑") or pct == "novo") else ("#d93025" if pct.startswith("↓") else "#888888")
        cell = Table(
            [[Paragraph(f"<font size=8 color='#666666'>{label}</font>")],
             [Paragraph(f"<font size=15><b>{value}</b></font>")],
             [Paragraph(f"<font size=8 color='{pct_color_hex}'>{pct}</font>")]],
            colWidths=[55 * mm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), GRAY_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
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
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, GRAY_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def line_chart(dates, series: dict, title, filename, fmt_y=None):
    fig, ax = plt.subplots(figsize=(6.8, 2.6), dpi=150)
    for label, values in series.items():
        ax.plot(dates, values, label=label, linewidth=1.6)
    ax.legend(fontsize=7, loc="upper left", frameon=False)
    ax.set_title(title, fontsize=9, loc="left", color="#333333")
    ax.tick_params(axis="x", labelsize=6, rotation=45)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def bar_chart(labels, values, title, filename, horizontal=False):
    fig, ax = plt.subplots(figsize=(6.8, 2.6), dpi=150)
    if horizontal:
        ax.barh(labels, values, color=ORANGE.hexval()[2:] and "#F4762A")
        ax.invert_yaxis()
    else:
        ax.bar(labels, values, color="#F4762A")
        ax.tick_params(axis="x", labelsize=7, rotation=30)
    ax.set_title(title, fontsize=9, loc="left", color="#333333")
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


def pie_chart(labels, values, title, filename):
    fig, ax = plt.subplots(figsize=(4, 3), dpi=150)
    ax.pie(values, labels=labels, autopct="%1.0f%%", textprops={"fontsize": 7},
           colors=["#F4762A", "#FBB584", "#FDE4CE", "#8C8C8C", "#C7C7C7"])
    ax.set_title(title, fontsize=9, color="#333333")
    fig.tight_layout()
    path = CHART_DIR / filename
    fig.savefig(path)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------

def build_meta_section(story, brand_key, brand_display, start, end):
    story.append(Paragraph("∞ Meta Ads — Visão Geral", h2))

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

    # Série temporal (custo e cliques por dia) via SQLite
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

    # Top campanhas (agregado do período, via SQLite)
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

    # Demografia
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

    # Top anúncios
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
    story.append(Paragraph("G Google Ads — Visão Geral", h2))

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
    story.append(Paragraph("○ Instagram Insights — Visão Geral", h2))

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

    story = []
    story.append(Paragraph(f"Relatório {brand_display}", h1))
    story.append(Paragraph(f"Período: {start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}", small))
    story.append(Spacer(1, 6 * mm))

    if brand.get("meta_ads", {}).get("status") == "confirmed":
        build_meta_section(story, args.brand, brand_display, start, end)
    if brand.get("google_ads", {}).get("status") == "confirmed":
        build_google_section(story, args.brand, brand_display, start, end)
    if brand.get("instagram_insights", {}).get("status") == "confirmed":
        build_instagram_section(story, args.brand, brand_display, start, end)
    build_gmb_note(story)

    doc.build(story)
    print(f"PDF gerado: {out_path}")


if __name__ == "__main__":
    main()
