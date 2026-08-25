"""
Teste de acesso à Google Business Profile API — lista contas e locais
visíveis, e puxa métricas de performance dos últimos 7 dias de cada local.

Uso:
    set -a && source .env && set +a
    python3 etl/scripts/test_gbp_access.py

Requer: GBP_CLIENT_ID, GBP_CLIENT_SECRET, GBP_REFRESH_TOKEN no ambiente.
"""

import datetime
import os
import sys

import requests
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

ACCOUNT_MGMT_BASE = "https://mybusinessaccountmanagement.googleapis.com/v1"
BUSINESS_INFO_BASE = "https://mybusinessbusinessinformation.googleapis.com/v1"
PERFORMANCE_BASE = "https://businessprofileperformance.googleapis.com/v1"


def get_access_token() -> str:
    creds = Credentials(
        token=None,
        refresh_token=os.environ["GBP_REFRESH_TOKEN"],
        client_id=os.environ["GBP_CLIENT_ID"],
        client_secret=os.environ["GBP_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return creds.token


def main() -> None:
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    print("--- Contas visíveis ---")
    resp = requests.get(f"{ACCOUNT_MGMT_BASE}/accounts", headers=headers)
    resp.raise_for_status()
    accounts = resp.json().get("accounts", [])
    if not accounts:
        print("Nenhuma conta encontrada — verifique se a aprovação da API já saiu.")
        sys.exit(1)
    for acc in accounts:
        print(f"  {acc['name']} | {acc.get('accountName', '?')}")

    account_name = accounts[0]["name"]  # ex: accounts/113796278757314846456

    print(f"\n--- Locais em {account_name} ---")
    resp = requests.get(
        f"{BUSINESS_INFO_BASE}/{account_name}/locations",
        headers=headers,
        params={"readMask": "name,title"},
    )
    resp.raise_for_status()
    locations = resp.json().get("locations", [])
    for loc in locations:
        print(f"  {loc['name']} | {loc.get('title', '?')}")

    if not locations:
        print("Nenhum local encontrado.")
        sys.exit(1)

    location_id = locations[0]["name"].split("/")[-1]
    end = datetime.date.today()
    start = end - datetime.timedelta(days=7)

    print(f"\n--- Métricas dos últimos 7 dias: {locations[0].get('title')} ---")
    resp = requests.get(
        f"{PERFORMANCE_BASE}/locations/{location_id}:fetchMultiDailyMetricsTimeSeries",
        headers=headers,
        params={
            "dailyMetrics": ["BUSINESS_IMPRESSIONS_DESKTOP_MAPS", "CALL_CLICKS"],
            "dailyRange.start_date.year": start.year,
            "dailyRange.start_date.month": start.month,
            "dailyRange.start_date.day": start.day,
            "dailyRange.end_date.year": end.year,
            "dailyRange.end_date.month": end.month,
            "dailyRange.end_date.day": end.day,
        },
    )
    if resp.status_code == 200:
        print(resp.json())
    else:
        print(f"Aviso: métricas retornaram {resp.status_code}: {resp.text[:300]}")
        print("(acesso a contas/locais já está confirmado acima; isso pode só ser um ajuste de parâmetro)")


if __name__ == "__main__":
    main()
