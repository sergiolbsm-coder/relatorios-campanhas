"""
Lê a planilha de leads/CRM configurada pra uma marca (etl/leads_config.py) e
calcula as métricas do funil de vendas pro período do relatório: total de
leads, % sem contato, % sem proprietário, taxa de fechamento, e se há valor
de venda registrado (pré-requisito pra CAC/ROI real).

Metodologia igual à usada no diagnóstico de funil feito manualmente pra Luto
União: deduplica leads por nome entre abas, ignora abas com "cópia"/"copy"
no nome (sinal de cópia desatualizada), casa nomes de coluna por palavra-
chave (não por posição fixa) pra tolerar pequenas variações entre clientes.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_leads_funnel.py --brand associacao_luto_uniao --days 30
"""

from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from google.oauth2.credentials import Credentials

from etl.common import DB_PATH, date_range_args, resolve_date_range, write_csv
from etl.leads_config import extract_sheet_id, get_leads_sheet_url

# palavras-chave pra achar a coluna certa mesmo que o nome exato varie
COLUMN_HINTS = {
    "lead": ["lead"],
    "data_entrada": ["data de entrada", "data entrada"],
    "status": ["status"],
    "proprietario": ["proprietário", "proprietario", "responsável", "responsavel"],
    "proximo_contato": ["retornar contato", "próximo contato", "proximo contato"],
    "email": ["e-mail", "email"],
    "valor": ["valor proposta", "valor da venda", "valor fechado", "valor negociado"],
}

WON_HINTS = ["fechado"]
WON_EXCLUDE_HINTS = ["outra emp"]  # "-Fechou c/ outra empr" não é venda ganha
LOST_HINTS = ["declinado", "perdid", "concorrente", "cancelad"]
NOT_CONTACTED_HINTS = ["não iniciado", "nao iniciado"]


def _client() -> gspread.Client:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_SHEETS_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_ADS_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
    )
    return gspread.authorize(creds)


def _find_column(header: list[str], hints: list[str]) -> int | None:
    header_lower = [h.strip().lower() for h in header]
    for hint in hints:
        for i, h in enumerate(header_lower):
            if hint in h:
                return i
    return None


def _contains_any(text: str, hints: list[str]) -> bool:
    text = (text or "").strip().lower()
    return any(h in text for h in hints)


def read_leads(sheet_id: str) -> list[dict]:
    gc = _client()
    sh = gc.open_by_key(sheet_id)

    combined: dict[str, dict] = {}
    for ws in sh.worksheets():
        if "cópia" in ws.title.lower() or "copy" in ws.title.lower():
            continue  # aba de cópia — sinal de dado desatualizado, ignora

        values = ws.get_all_values()
        if not values:
            continue
        header = values[0]
        idx = {key: _find_column(header, hints) for key, hints in COLUMN_HINTS.items()}
        if idx["lead"] is None:
            continue  # essa aba não parece ter os dados esperados

        for row in values[1:]:
            if idx["lead"] >= len(row) or not row[idx["lead"]].strip():
                continue
            name = row[idx["lead"]].strip()
            if name in combined:
                continue  # mantém a 1a ocorrência (mesma regra do diagnóstico manual)

            def get(field):
                i = idx.get(field)
                return row[i].strip() if i is not None and i < len(row) else ""

            combined[name] = {
                "lead": name,
                "data_entrada": get("data_entrada"),
                "status": get("status"),
                "proprietario": get("proprietario"),
                "proximo_contato": get("proximo_contato"),
                "email": get("email"),
                "valor": get("valor"),
            }
    return list(combined.values())


def compute_metrics(leads: list[dict], start: datetime.date, end: datetime.date) -> dict:
    in_period = []
    for lead in leads:
        d = lead["data_entrada"]
        try:
            parsed = datetime.datetime.strptime(d, "%d/%m/%Y").date()
        except ValueError:
            continue
        if start <= parsed <= end:
            in_period.append(lead)

    total = len(in_period)
    if total == 0:
        return {"total_leads": 0}

    no_owner = sum(1 for l in in_period if not l["proprietario"])
    not_contacted = sum(1 for l in in_period if _contains_any(l["status"], NOT_CONTACTED_HINTS))
    won = [l for l in in_period if _contains_any(l["status"], WON_HINTS) and not _contains_any(l["status"], WON_EXCLUDE_HINTS)]
    lost = [l for l in in_period if _contains_any(l["status"], LOST_HINTS)]
    decided = len(won) + len(lost)
    value_available = any(l["valor"] for l in won)

    return {
        "total_leads": total,
        "pct_no_owner": round(no_owner / total * 100, 1),
        "pct_not_contacted": round(not_contacted / total * 100, 1),
        "closed_won": len(won),
        "closed_lost": len(lost),
        "close_rate_total_pct": round(len(won) / total * 100, 1),
        "close_rate_decided_pct": round(len(won) / decided * 100, 1) if decided else 0,
        "value_data_available": value_available,
    }


def ad_cost_for_period(brand_key: str, start: datetime.date, end: datetime.date) -> float:
    if not DB_PATH.exists():
        return 0.0
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        """
        SELECT SUM(cost) FROM fact_metrics_daily
        WHERE brand_key = ? AND channel IN ('google_ads', 'meta_ads')
          AND date BETWEEN ? AND ?
        """,
        (brand_key, start.isoformat(), end.isoformat()),
    ).fetchone()
    conn.close()
    return row[0] or 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", required=True)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    sheet_url = get_leads_sheet_url(args.brand)
    if not sheet_url:
        print(f"Nenhuma planilha de leads configurada para '{args.brand}' — pulando funil de vendas.")
        return

    print(f"Extraindo funil de leads de {args.brand} ({start} a {end})...")
    sheet_id = extract_sheet_id(sheet_url)
    leads = read_leads(sheet_id)
    print(f"  {len(leads)} leads únicos encontrados na planilha (todas as abas, deduplicado)")

    metrics = compute_metrics(leads, start, end)
    metrics["ad_cost_period"] = round(ad_cost_for_period(args.brand, start, end), 2)
    metrics["period_start"] = start.isoformat()
    metrics["period_end"] = end.isoformat()

    header = ["total_leads", "pct_no_owner", "pct_not_contacted", "closed_won", "closed_lost",
              "close_rate_total_pct", "close_rate_decided_pct", "value_data_available",
              "ad_cost_period", "period_start", "period_end"]
    row = {k: metrics.get(k, "") for k in header}
    write_csv([row], f"leads_funnel_{args.brand}_{start.isoformat()}_a_{end.isoformat()}.csv", header)


if __name__ == "__main__":
    main()
