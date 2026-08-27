"""
4.1 — Exporta fact_metrics_daily (db/analise_campanhas.db) pra uma aba
"dados_diarios" numa planilha Google, pronta pra conectar no Looker Studio.

Sobrescreve a aba inteira a cada execução (não incremental) — simples e
suficiente pro volume atual.

Uso:
    set -a && source .env && set +a
    python3 etl/export_to_sheets.py

Na primeira execução (sem GOOGLE_SHEETS_SPREADSHEET_ID no ambiente), cria
uma planilha nova e imprime o ID — cole em .env pra reutilizar nas próximas.
"""

import csv
import glob
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.credentials import Credentials

from etl.common import DATA_DIR, DB_PATH

SHEET_TITLE = "Análise de Campanhas — Dados"
WORKSHEET_NAME = "dados_diarios"

# Abas extras exportadas direto de CSV (não passam pelo SQLite — são
# agregados de período, não série diária, e não se encaixam no schema
# de fact_metrics_daily). padrão de arquivo -> nome da aba.
EXTRA_CSV_TABS = {
    "meta_ads_overview_*.csv": "meta_visao_geral",
    "meta_ads_demographics_*.csv": "meta_demografia",
    "meta_ads_top_ads_*.csv": "meta_top_anuncios",
    "google_ads_overview_*.csv": "google_visao_geral",
    "google_ads_device_*.csv": "google_dispositivo",
    "google_ads_day_of_week_*.csv": "google_dia_semana",
    "google_ads_keywords_*.csv": "google_palavras_chave",
    "instagram_demographics_age_gender.csv": "instagram_demografia",
    "instagram_demographics_city.csv": "instagram_cidades",
}

QUERY = """
    SELECT
        f.date, b.display_name AS brand, c.display_name AS channel,
        f.account_id, f.campaign_id, f.campaign_name, f.placement,
        f.impressions, f.clicks, f.cost, f.conversions, f.reach, f.new_followers
    FROM fact_metrics_daily f
    JOIN dim_brand b ON b.brand_key = f.brand_key
    JOIN dim_channel c ON c.channel_key = f.channel
    ORDER BY f.date, b.display_name, c.display_name
"""

HEADER = [
    "date", "brand", "channel", "account_id", "campaign_id", "campaign_name",
    "placement", "impressions", "clicks", "cost", "conversions", "reach", "new_followers",
]


def build_client() -> gspread.Client:
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_SHEETS_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_ADS_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
    )
    return gspread.authorize(credentials)


def load_rows() -> list[list]:
    if not DB_PATH.exists():
        print(f"Banco não encontrado em {DB_PATH}. Rode etl/load_to_sqlite.py primeiro.", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(QUERY)
    rows = [list(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def export_csv_tab(sh, pattern: str, worksheet_name: str) -> None:
    matches = sorted(glob.glob(str(DATA_DIR / pattern)))
    if not matches:
        print(f"  (nenhum CSV casando '{pattern}', pulando aba '{worksheet_name}')")
        return
    path = matches[-1]
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=worksheet_name, rows=1, cols=len(rows[0]) if rows else 10)

    ws.clear()
    ws.update(values=rows, range_name="A1")
    print(f"  '{worksheet_name}': {len(rows) - 1} linha(s) de {os.path.basename(path)}")


def main() -> None:
    gc = build_client()

    spreadsheet_id = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
    if spreadsheet_id:
        sh = gc.open_by_key(spreadsheet_id)
        print(f"Usando planilha existente: {sh.url}")
    else:
        sh = gc.create(SHEET_TITLE)
        print(f"Planilha criada: {sh.url}")
        print(f"\n>>> Cole isto no seu .env: GOOGLE_SHEETS_SPREADSHEET_ID={sh.id}\n")

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1, cols=len(HEADER))

    rows = load_rows()
    ws.clear()
    ws.update(values=[HEADER] + rows, range_name="A1")
    print(f"Exportado: {len(rows)} linha(s) para a aba '{WORKSHEET_NAME}'.")

    print("Exportando abas extras...")
    for pattern, worksheet_name in EXTRA_CSV_TABS.items():
        export_csv_tab(sh, pattern, worksheet_name)


if __name__ == "__main__":
    main()
