"""
Teste rápido de acesso à Google Ads API — valida as credenciais do .env
puxando 5 campanhas (id, nome) da conta indicada.

Uso:
    export $(grep -v '^#' .env | xargs)   # carrega o .env no shell
    python3 etl/scripts/test_google_ads_access.py <customer_id>

Exemplo:
    python3 etl/scripts/test_google_ads_access.py 7613902765
"""

import os
import sys

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python3 test_google_ads_access.py <customer_id>", file=sys.stderr)
        sys.exit(1)

    customer_id = sys.argv[1].replace("-", "")

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

    client = GoogleAdsClient.load_from_dict(config)
    ga_service = client.get_service("GoogleAdsService")

    query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign LIMIT 5"

    try:
        response = ga_service.search(customer_id=customer_id, query=query)
        rows = list(response)
        print(f"--- Sucesso: {len(rows)} campanha(s) encontrada(s) na conta {customer_id} ---")
        for row in rows:
            print(f"  {row.campaign.id} | {row.campaign.name} | {row.campaign.status.name}")
        if not rows:
            print("  (conta acessível, mas sem campanhas cadastradas)")
    except GoogleAdsException as ex:
        print(f"--- FALHA na conta {customer_id} ---", file=sys.stderr)
        for error in ex.failure.errors:
            print(f"  {error.error_code}: {error.message}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
