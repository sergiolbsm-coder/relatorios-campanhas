"""
Extração complementar do Google Ads — visão de período (com comparação),
dispositivo, dia da semana e principais palavras-chave. Mesmo raciocínio do
extract_meta_ads_overview.py: agregados de período não cabem na fato diária.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_google_ads_overview.py --days 30
"""

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from etl.common import brands_with, date_range_args, resolve_date_range, write_csv


def build_client() -> GoogleAdsClient:
    config = {
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "use_proto_plus": True,
    }
    login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").replace("-", "")
    if login_customer_id:
        config["login_customer_id"] = login_customer_id
    return GoogleAdsClient.load_from_dict(config)


def period_totals(ga_service, customer_id, start, end):
    query = f"""
        SELECT metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM customer
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    impressions = clicks = cost = conversions = 0
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            impressions += row.metrics.impressions
            clicks += row.metrics.clicks
            cost += row.metrics.cost_micros / 1_000_000
            conversions += row.metrics.conversions
    except GoogleAdsException as ex:
        print(f"    [ERRO period_totals] {ex}", file=sys.stderr)
    return {"impressions": impressions, "clicks": clicks, "cost": cost, "conversions": conversions}


def extract_overview(ga_service, brand_name, customer_id, start, end):
    days = (end - start).days + 1
    prev_end = start - datetime.timedelta(days=1)
    prev_start = prev_end - datetime.timedelta(days=days - 1)

    current = period_totals(ga_service, customer_id, start, end)
    previous = period_totals(ga_service, customer_id, prev_start, prev_end)

    def pct_change(cur, prev):
        cur, prev = float(cur or 0), float(prev or 0)
        if prev == 0:
            return "" if cur == 0 else "novo"
        return round((cur - prev) / prev * 100, 2)

    row = {"brand": brand_name, "period_start": start.isoformat(), "period_end": end.isoformat()}
    for field in ["impressions", "clicks", "cost", "conversions"]:
        row[field] = current[field]
        row[f"{field}_prev"] = previous[field]
        row[f"{field}_pct_change"] = pct_change(current[field], previous[field])
    return row


def extract_device(ga_service, brand_name, customer_id, start, end):
    query = f"""
        SELECT segments.device, metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
        FROM customer
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            yield {
                "brand": brand_name,
                "device": row.segments.device.name,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost": row.metrics.cost_micros / 1_000_000,
                "conversions": row.metrics.conversions,
            }
    except GoogleAdsException as ex:
        print(f"    [ERRO device] {ex}", file=sys.stderr)


def extract_day_of_week(ga_service, brand_name, customer_id, start, end):
    query = f"""
        SELECT segments.day_of_week, metrics.impressions, metrics.clicks, metrics.conversions
        FROM customer
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            yield {
                "brand": brand_name,
                "day_of_week": row.segments.day_of_week.name,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "conversions": row.metrics.conversions,
            }
    except GoogleAdsException as ex:
        print(f"    [ERRO day_of_week] {ex}", file=sys.stderr)


def extract_keywords(ga_service, brand_name, customer_id, start, end):
    query = f"""
        SELECT ad_group_criterion.keyword.text, metrics.clicks, metrics.impressions, metrics.cost_micros
        FROM keyword_view
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
        ORDER BY metrics.clicks DESC
        LIMIT 30
    """
    try:
        for row in ga_service.search(customer_id=customer_id, query=query):
            yield {
                "brand": brand_name,
                "keyword": row.ad_group_criterion.keyword.text,
                "clicks": row.metrics.clicks,
                "impressions": row.metrics.impressions,
                "cost": row.metrics.cost_micros / 1_000_000,
            }
    except GoogleAdsException as ex:
        print(f"    [ERRO keywords] {ex}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    print(f"Extraindo overview Google Ads de {start} a {end}...")
    client = build_client()
    ga_service = client.get_service("GoogleAdsService")

    accounts = brands_with("google_ads")
    if not accounts:
        print("Nenhuma conta Google Ads confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    overview_rows, device_rows, dow_rows, kw_rows = [], [], [], []
    for _, brand_name, platform in accounts:
        customer_id = platform["account_id"]
        print(f"  {brand_name} ({customer_id})...")
        overview_rows.append(extract_overview(ga_service, brand_name, customer_id, start, end))
        device_rows.extend(extract_device(ga_service, brand_name, customer_id, start, end))
        dow_rows.extend(extract_day_of_week(ga_service, brand_name, customer_id, start, end))
        kw_rows.extend(extract_keywords(ga_service, brand_name, customer_id, start, end))

    write_csv(
        overview_rows,
        f"google_ads_overview_{start.isoformat()}_a_{end.isoformat()}.csv",
        ["brand", "period_start", "period_end",
         "impressions", "impressions_prev", "impressions_pct_change",
         "clicks", "clicks_prev", "clicks_pct_change",
         "cost", "cost_prev", "cost_pct_change",
         "conversions", "conversions_prev", "conversions_pct_change"],
    )
    write_csv(device_rows, f"google_ads_device_{start.isoformat()}_a_{end.isoformat()}.csv",
              ["brand", "device", "impressions", "clicks", "cost", "conversions"])
    write_csv(dow_rows, f"google_ads_day_of_week_{start.isoformat()}_a_{end.isoformat()}.csv",
              ["brand", "day_of_week", "impressions", "clicks", "conversions"])
    write_csv(kw_rows, f"google_ads_keywords_{start.isoformat()}_a_{end.isoformat()}.csv",
              ["brand", "keyword", "clicks", "impressions", "cost"])


if __name__ == "__main__":
    main()
