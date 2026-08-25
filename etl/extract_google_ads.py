"""
2.1 — Extração Google Ads: métricas diárias de campanha (impressões, cliques,
custo, conversões) para todas as marcas confirmadas em config.yaml.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_google_ads.py                      # últimos 90 dias
    python3 etl/extract_google_ads.py --days 30             # últimos 30 dias
    python3 etl/extract_google_ads.py --start 2026-07-01 --end 2026-07-31
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

from etl.common import brands_with, date_range_args, resolve_date_range, write_csv

FIELDNAMES = [
    "date", "brand", "customer_id", "campaign_id", "campaign_name",
    "campaign_status", "impressions", "clicks", "cost", "conversions",
]


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


def extract_account(client: GoogleAdsClient, brand_name: str, customer_id: str, start, end):
    ga_service = client.get_service("GoogleAdsService")
    query = f"""
        SELECT
            segments.date,
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    try:
        response = ga_service.search(customer_id=customer_id, query=query)
    except GoogleAdsException as ex:
        print(f"  [ERRO] {brand_name} ({customer_id}):", file=sys.stderr)
        for error in ex.failure.errors:
            print(f"    {error.error_code}: {error.message}", file=sys.stderr)
        return

    count = 0
    for row in response:
        yield {
            "date": row.segments.date,
            "brand": brand_name,
            "customer_id": customer_id,
            "campaign_id": row.campaign.id,
            "campaign_name": row.campaign.name,
            "campaign_status": row.campaign.status.name,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": row.metrics.cost_micros / 1_000_000,
            "conversions": row.metrics.conversions,
        }
        count += 1
    print(f"  {brand_name} ({customer_id}): {count} linha(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    print(f"Extraindo Google Ads de {start} a {end}...")
    client = build_client()

    accounts = brands_with("google_ads")
    if not accounts:
        print("Nenhuma conta Google Ads confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    for _, brand_name, platform in accounts:
        all_rows.extend(extract_account(client, brand_name, platform["account_id"], start, end))

    filename = f"google_ads_{start.isoformat()}_a_{end.isoformat()}.csv"
    write_csv(all_rows, filename, FIELDNAMES)


if __name__ == "__main__":
    main()
