"""
Extração complementar do Meta Ads — métricas de período (não-diárias) que não
cabem na tabela fato diária porque reach/frequency não são somáveis por dia
sem gerar contagem duplicada:

  - Visão geral do período por marca: reach, frequency, cpc, cpm, ctr,
    impressions, clicks, spend + comparação com o período anterior de mesmo
    tamanho (replica os cards "↑ X%" do relatório de referência do mLabs)
  - Demografia (idade/gênero) por marca
  - Top anúncios (nível ad, não campanha) por marca

Uso:
    set -a && source .env && set +a
    python3 etl/extract_meta_ads_overview.py --days 30
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from etl.common import brands_with, date_range_args, resolve_date_range, write_csv

GRAPH_API_VERSION = "v21.0"


def api_get(access_token: str, path: str, params: dict) -> dict:
    params = {**params, "access_token": access_token}
    resp = requests.get(f"https://graph.facebook.com/{GRAPH_API_VERSION}/{path}", params=params)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def period_summary(access_token, account_id, start, end):
    data = api_get(access_token, f"{account_id}/insights", {
        "level": "account",
        "fields": "impressions,clicks,spend,reach,frequency,cpc,cpm,ctr",
        "time_range": f'{{"since":"{start.isoformat()}","until":"{end.isoformat()}"}}',
    })
    rows = data.get("data", [])
    return rows[0] if rows else {}


def extract_overview(access_token, brand_name, account_id, start, end):
    days = (end - start).days + 1
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=days - 1)

    try:
        current = period_summary(access_token, account_id, start, end)
        previous = period_summary(access_token, account_id, prev_start, prev_end)
    except RuntimeError as ex:
        print(f"  [ERRO overview] {brand_name}: {ex}", file=sys.stderr)
        return None

    def pct_change(cur, prev):
        cur, prev = float(cur or 0), float(prev or 0)
        if prev == 0:
            return "" if cur == 0 else "novo"
        return round((cur - prev) / prev * 100, 2)

    row = {"brand": brand_name, "period_start": start.isoformat(), "period_end": end.isoformat()}
    for field in ["impressions", "clicks", "spend", "reach", "frequency", "cpc", "cpm", "ctr"]:
        row[field] = current.get(field, 0)
        row[f"{field}_prev"] = previous.get(field, 0)
        row[f"{field}_pct_change"] = pct_change(current.get(field), previous.get(field))
    return row


def extract_demographics(access_token, brand_name, account_id, start, end):
    try:
        data = api_get(access_token, f"{account_id}/insights", {
            "level": "account",
            "fields": "impressions,clicks,spend,reach",
            "breakdowns": "age,gender",
            "time_range": f'{{"since":"{start.isoformat()}","until":"{end.isoformat()}"}}',
            "limit": 100,
        })
    except RuntimeError as ex:
        print(f"  [ERRO demografia] {brand_name}: {ex}", file=sys.stderr)
        return

    for row in data.get("data", []):
        yield {
            "brand": brand_name,
            "age": row.get("age"),
            "gender": row.get("gender"),
            "impressions": row.get("impressions", 0),
            "clicks": row.get("clicks", 0),
            "spend": row.get("spend", 0),
            "reach": row.get("reach", 0),
        }


def extract_top_ads(access_token, brand_name, account_id, start, end):
    try:
        data = api_get(access_token, f"{account_id}/insights", {
            "level": "ad",
            "fields": "ad_name,campaign_name,impressions,clicks,spend,reach,frequency,cpc,cpm",
            "time_range": f'{{"since":"{start.isoformat()}","until":"{end.isoformat()}"}}',
            "limit": 500,
            "sort": "clicks_descending",
        })
    except RuntimeError as ex:
        print(f"  [ERRO top ads] {brand_name}: {ex}", file=sys.stderr)
        return

    for row in data.get("data", []):
        yield {
            "brand": brand_name,
            "ad_name": row.get("ad_name"),
            "campaign_name": row.get("campaign_name"),
            "impressions": row.get("impressions", 0),
            "clicks": row.get("clicks", 0),
            "spend": row.get("spend", 0),
            "reach": row.get("reach", 0),
            "frequency": row.get("frequency", 0),
            "cpc": row.get("cpc", 0),
            "cpm": row.get("cpm", 0),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    print(f"Extraindo overview Meta Ads de {start} a {end}...")
    access_token = os.environ["META_ACCESS_TOKEN"]

    accounts = brands_with("meta_ads")
    if not accounts:
        print("Nenhuma conta Meta Ads confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    overview_rows, demo_rows, ads_rows = [], [], []
    for _, brand_name, platform in accounts:
        account_id = platform["account_id"]
        print(f"  {brand_name} ({account_id})...")
        overview = extract_overview(access_token, brand_name, account_id, start, end)
        if overview:
            overview_rows.append(overview)
        demo_rows.extend(extract_demographics(access_token, brand_name, account_id, start, end))
        ads_rows.extend(extract_top_ads(access_token, brand_name, account_id, start, end))

    write_csv(
        overview_rows,
        f"meta_ads_overview_{start.isoformat()}_a_{end.isoformat()}.csv",
        ["brand", "period_start", "period_end",
         "impressions", "impressions_prev", "impressions_pct_change",
         "clicks", "clicks_prev", "clicks_pct_change",
         "spend", "spend_prev", "spend_pct_change",
         "reach", "reach_prev", "reach_pct_change",
         "frequency", "frequency_prev", "frequency_pct_change",
         "cpc", "cpc_prev", "cpc_pct_change",
         "cpm", "cpm_prev", "cpm_pct_change",
         "ctr", "ctr_prev", "ctr_pct_change"],
    )
    write_csv(
        demo_rows,
        f"meta_ads_demographics_{start.isoformat()}_a_{end.isoformat()}.csv",
        ["brand", "age", "gender", "impressions", "clicks", "spend", "reach"],
    )
    write_csv(
        ads_rows,
        f"meta_ads_top_ads_{start.isoformat()}_a_{end.isoformat()}.csv",
        ["brand", "ad_name", "campaign_name", "impressions", "clicks", "spend",
         "reach", "frequency", "cpc", "cpm"],
    )


if __name__ == "__main__":
    main()
