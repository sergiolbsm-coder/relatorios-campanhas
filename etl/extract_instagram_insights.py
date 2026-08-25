"""
2.3 — Extração Instagram Insights (orgânico): alcance diário, crescimento de
seguidores, e desempenho de posts/reels, para todas as marcas confirmadas em
config.yaml. Reaproveita o mesmo META_ACCESS_TOKEN do Meta Ads (item 1.2).

Gera 2 CSVs:
  - instagram_account_daily_{start}_a_{end}.csv  (1 linha por dia por conta:
    alcance e novos seguidores)
  - instagram_media_{start}_a_{end}.csv          (1 linha por post/reel
    publicado no período: alcance, curtidas, comentários, etc.)

Nota: Stories não entram aqui — expiram em 24h e a Graph API só expõe
insights delas enquanto estão no ar, o que não é compatível com uma
extração histórica retroativa.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_instagram_insights.py
    python3 etl/extract_instagram_insights.py --days 30
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from etl.common import brands_with, date_range_args, resolve_date_range, write_csv

GRAPH_API_VERSION = "v21.0"

ACCOUNT_DAILY_FIELDNAMES = ["date", "brand", "account_id", "reach", "new_followers"]
MEDIA_FIELDNAMES = [
    "brand", "account_id", "media_id", "media_type", "media_product_type",
    "timestamp", "permalink", "reach", "likes", "comments", "shares",
    "saved", "total_interactions", "views",
]


def get(url: str, params: dict) -> dict:
    resp = requests.get(url, params=params)
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def extract_account_daily(token: str, brand_name: str, account_id: str, start, end):
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{account_id}/insights"
    try:
        reach_data = get(url, {
            "metric": "reach", "period": "day", "metric_type": "time_series",
            "since": start.isoformat(), "until": end.isoformat(), "access_token": token,
        })
        followers_data = get(url, {
            "metric": "follower_count", "period": "day", "metric_type": "time_series",
            "since": start.isoformat(), "until": end.isoformat(), "access_token": token,
        })
    except RuntimeError as ex:
        print(f"  [ERRO] {brand_name} ({account_id}): {ex}", file=sys.stderr)
        return

    reach_by_date = {v["end_time"][:10]: v["value"] for v in reach_data["data"][0]["values"]}
    followers_by_date = {v["end_time"][:10]: v["value"] for v in followers_data["data"][0]["values"]}
    all_dates = sorted(set(reach_by_date) | set(followers_by_date))

    count = 0
    for date in all_dates:
        yield {
            "date": date,
            "brand": brand_name,
            "account_id": account_id,
            "reach": reach_by_date.get(date, ""),
            "new_followers": followers_by_date.get(date, ""),
        }
        count += 1
    print(f"  [conta/dia] {brand_name} ({account_id}): {count} linha(s)")


def extract_media(token: str, brand_name: str, account_id: str, start, end):
    media_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{account_id}/media"
    try:
        media_list = get(media_url, {
            "fields": "id,media_type,media_product_type,timestamp,permalink",
            "since": start.isoformat(), "until": end.isoformat(),
            "limit": 100, "access_token": token,
        })
    except RuntimeError as ex:
        print(f"  [ERRO] {brand_name} ({account_id}) media list: {ex}", file=sys.stderr)
        return

    count = 0
    for media in media_list.get("data", []):
        metrics = ["reach", "likes", "comments", "shares", "saved", "total_interactions"]
        if media.get("media_product_type") == "REELS":
            metrics.append("views")

        insights_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{media['id']}/insights"
        try:
            insights = get(insights_url, {"metric": ",".join(metrics), "access_token": token})
        except RuntimeError as ex:
            print(f"    [aviso] media {media['id']} sem insights: {ex}", file=sys.stderr)
            continue

        values = {item["name"]: item["values"][0]["value"] for item in insights.get("data", [])}
        yield {
            "brand": brand_name,
            "account_id": account_id,
            "media_id": media["id"],
            "media_type": media.get("media_type"),
            "media_product_type": media.get("media_product_type"),
            "timestamp": media.get("timestamp"),
            "permalink": media.get("permalink"),
            "reach": values.get("reach", ""),
            "likes": values.get("likes", ""),
            "comments": values.get("comments", ""),
            "shares": values.get("shares", ""),
            "saved": values.get("saved", ""),
            "total_interactions": values.get("total_interactions", ""),
            "views": values.get("views", ""),
        }
        count += 1
    print(f"  [mídia] {brand_name} ({account_id}): {count} post(s)/reel(s)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    date_range_args(parser)
    args = parser.parse_args()
    start, end = resolve_date_range(args)

    print(f"Extraindo Instagram Insights de {start} a {end}...")
    token = os.environ["META_ACCESS_TOKEN"]

    accounts = brands_with("instagram_insights")
    if not accounts:
        print("Nenhuma conta Instagram Insights confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    daily_rows, media_rows = [], []
    for _, brand_name, platform in accounts:
        account_id = platform["account_id"]
        daily_rows.extend(extract_account_daily(token, brand_name, account_id, start, end))
        media_rows.extend(extract_media(token, brand_name, account_id, start, end))

    write_csv(daily_rows, f"instagram_account_daily_{start.isoformat()}_a_{end.isoformat()}.csv", ACCOUNT_DAILY_FIELDNAMES)
    write_csv(media_rows, f"instagram_media_{start.isoformat()}_a_{end.isoformat()}.csv", MEDIA_FIELDNAMES)


if __name__ == "__main__":
    main()
