"""
2.2 — Extração Meta Ads: métricas diárias por campanha e por posicionamento
(feed, stories, reels) para todas as marcas confirmadas em config.yaml.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_meta_ads.py                      # últimos 90 dias
    python3 etl/extract_meta_ads.py --days 30
    python3 etl/extract_meta_ads.py --start 2026-07-01 --end 2026-07-31
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from etl.common import brands_with, date_range_args, resolve_date_range, write_csv

GRAPH_API_VERSION = "v21.0"
FIELDNAMES = [
    "date", "brand", "account_id", "campaign_id", "campaign_name", "publisher_platform",
    "platform_position", "impressions", "clicks", "spend",
]


def extract_account(access_token: str, brand_name: str, account_id: str, start, end):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{account_id}/insights"
    params = {
        "access_token": access_token,
        "level": "campaign",
        "fields": "campaign_id,campaign_name,impressions,clicks,spend",
        "breakdowns": "publisher_platform,platform_position",
        "time_increment": 1,
        "time_range": f'{{"since":"{start.isoformat()}","until":"{end.isoformat()}"}}',
        "limit": 500,
    }

    count = 0
    while url:
        resp = requests.get(url, params=params if "?" not in url else None)
        data = resp.json()

        if "error" in data:
            print(f"  [ERRO] {brand_name} ({account_id}): {data['error'].get('message')}", file=sys.stderr)
            return

        for row in data.get("data", []):
            yield {
                "date": row.get("date_start"),
                "brand": brand_name,
                "account_id": account_id,
                "campaign_id": row.get("campaign_id"),
                "campaign_name": row.get("campaign_name"),
                "publisher_platform": row.get("publisher_platform"),
                "platform_position": row.get("platform_position"),
                "impressions": row.get("impressions", 0),
                "clicks": row.get("clicks", 0),
                "spend": row.get("spend", 0),
            }
            count += 1

        url = data.get("paging", {}).get("next")
        params = None  # a URL "next" já vem com todos os parâmetros embutidos

    print(f"  {brand_name} ({account_id}): {count} linha(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    print(f"Extraindo Meta Ads de {start} a {end}...")
    access_token = os.environ["META_ACCESS_TOKEN"]

    accounts = brands_with("meta_ads")
    if not accounts:
        print("Nenhuma conta Meta Ads confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    all_rows = []
    for _, brand_name, platform in accounts:
        all_rows.extend(extract_account(access_token, brand_name, platform["account_id"], start, end))

    filename = f"meta_ads_{start.isoformat()}_a_{end.isoformat()}.csv"
    write_csv(all_rows, filename, FIELDNAMES)


if __name__ == "__main__":
    main()
