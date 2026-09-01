"""
Guarda o link da planilha de leads/CRM de cada marca. Persistido numa aba
("config_marcas") da mesma planilha Google já usada pelo projeto — não no
disco do Render, que é temporário e reseta a cada deploy.

Funções pensadas pra serem chamadas tanto pelo pipeline (leitura) quanto
pela interface web (leitura/escrita, via uma tela de configurações).
"""

from __future__ import annotations

import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.credentials import Credentials

CONFIG_SHEET_NAME = "config_marcas"
HEADER = ["brand_key", "leads_sheet_url", "updated_at"]

REQUIRED_ENV_VARS = ["GOOGLE_SHEETS_REFRESH_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                     "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_SHEETS_SPREADSHEET_ID"]


class NotConfigured(RuntimeError):
    """Faltam variáveis de ambiente pro acesso ao Google Sheets — tratado como
    'funcionalidade de funil de vendas indisponível', nunca deve derrubar o
    pipeline de relatório nem a interface web."""


def _require_env() -> None:
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise NotConfigured(
            f"Variáveis de ambiente faltando pro funil de leads: {', '.join(missing)} "
            "(configurar no Render, aba Environment)."
        )


def _client() -> gspread.Client:
    _require_env()
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_SHEETS_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_ADS_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
    )
    return gspread.authorize(creds)


def _config_worksheet():
    gc = _client()
    sh = gc.open_by_key(os.environ["GOOGLE_SHEETS_SPREADSHEET_ID"])
    try:
        return sh.worksheet(CONFIG_SHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=CONFIG_SHEET_NAME, rows=20, cols=len(HEADER))
        ws.update(values=[HEADER], range_name="A1")
        return ws


def list_all() -> dict:
    """brand_key -> leads_sheet_url, só das marcas com link configurado.
    Retorna vazio (não quebra) se as credenciais do Google Sheets não
    estiverem configuradas no ambiente."""
    try:
        ws = _config_worksheet()
    except NotConfigured:
        return {}
    rows = ws.get_all_records()
    return {r["brand_key"]: r["leads_sheet_url"] for r in rows if r.get("leads_sheet_url")}


def get_leads_sheet_url(brand_key: str) -> str | None:
    return list_all().get(brand_key)


def is_configured() -> bool:
    """True se as variáveis de ambiente do Google Sheets estão presentes —
    usado pra avisar o admin em vez de simplesmente mostrar tudo vazio."""
    return not [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]


def set_leads_sheet_url(brand_key: str, url: str) -> None:
    ws = _config_worksheet()
    rows = ws.get_all_values()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for i, row in enumerate(rows[1:], start=2):  # linha 1 é o header
        if row and row[0] == brand_key:
            ws.update(values=[[brand_key, url, now]], range_name=f"A{i}:C{i}")
            return
    ws.append_row([brand_key, url, now])


def extract_sheet_id(url_or_id: str) -> str:
    """Aceita tanto uma URL completa do Google Sheets quanto o ID puro."""
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    return match.group(1) if match else url_or_id.strip()
