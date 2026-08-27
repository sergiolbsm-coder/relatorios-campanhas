"""
Extração complementar do Instagram — demografia de seguidores (idade/gênero,
cidade). Métrica lifetime (situação atual da base de seguidores, não
histórico diário) — por isso fica fora da fato diária.

Uso:
    set -a && source .env && set +a
    python3 etl/extract_instagram_demographics.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from etl.common import brands_with, write_csv

GRAPH_API_VERSION = "v21.0"


def get_breakdown(token: str, account_id: str, breakdown: str):
    resp = requests.get(
        f"https://graph.facebook.com/{GRAPH_API_VERSION}/{account_id}/insights",
        params={
            "access_token": token,
            "metric": "follower_demographics",
            "period": "lifetime",
            "metric_type": "total_value",
            "breakdown": breakdown,
        },
    )
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data["data"][0]["total_value"]["breakdowns"][0]["results"]


def extract_age_gender(token, brand_name, account_id):
    try:
        results = get_breakdown(token, account_id, "age,gender")
    except RuntimeError as ex:
        print(f"  [ERRO age,gender] {brand_name}: {ex}", file=sys.stderr)
        return
    for r in results:
        age, gender = r["dimension_values"]
        yield {"brand": brand_name, "age": age, "gender": gender, "followers": r["value"]}


def extract_city(token, brand_name, account_id):
    try:
        results = get_breakdown(token, account_id, "city")
    except RuntimeError as ex:
        print(f"  [ERRO city] {brand_name}: {ex}", file=sys.stderr)
        return
    # top 15 por marca, ordenado
    results = sorted(results, key=lambda r: r["value"], reverse=True)[:15]
    for r in results:
        yield {"brand": brand_name, "city": r["dimension_values"][0], "followers": r["value"]}


def main() -> None:
    token = os.environ["META_ACCESS_TOKEN"]
    accounts = brands_with("instagram_insights")
    if not accounts:
        print("Nenhuma conta Instagram confirmada em config.yaml.", file=sys.stderr)
        sys.exit(1)

    age_gender_rows, city_rows = [], []
    for _, brand_name, platform in accounts:
        account_id = platform["account_id"]
        print(f"  {brand_name} ({account_id})...")
        age_gender_rows.extend(extract_age_gender(token, brand_name, account_id))
        city_rows.extend(extract_city(token, brand_name, account_id))

    write_csv(age_gender_rows, "instagram_demographics_age_gender.csv", ["brand", "age", "gender", "followers"])
    write_csv(city_rows, "instagram_demographics_city.csv", ["brand", "city", "followers"])


if __name__ == "__main__":
    main()
