"""
Teste rápido de acesso à Google Analytics Data API (GA4) — valida a service
account do .env puxando sessões/usuários dos últimos 7 dias.

Uso:
    export GA4_SERVICE_ACCOUNT_JSON_PATH=./secrets/ga4-service-account.json
    python3 etl/scripts/test_ga4_access.py <property_id>

Exemplo:
    python3 etl/scripts/test_ga4_access.py 450305882
"""

import os
import sys

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from google.oauth2 import service_account


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python3 test_ga4_access.py <property_id>", file=sys.stderr)
        sys.exit(1)

    property_id = sys.argv[1]
    key_path = os.environ.get("GA4_SERVICE_ACCOUNT_JSON_PATH")
    if not key_path or not os.path.exists(key_path):
        print(
            f"GA4_SERVICE_ACCOUNT_JSON_PATH não definido ou arquivo não "
            f"encontrado ({key_path}). Ver Passo 3 do guia 1.4.",
            file=sys.stderr,
        )
        sys.exit(1)

    credentials = service_account.Credentials.from_service_account_file(key_path)
    client = BetaAnalyticsDataClient(credentials=credentials)

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="sessionDefaultChannelGrouping")],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers")],
        date_ranges=[DateRange(start_date="7daysAgo", end_date="today")],
    )

    try:
        response = client.run_report(request)
    except Exception as ex:  # noqa: BLE001 — queremos ver qualquer erro da API cru
        print(f"--- FALHA na propriedade {property_id} ---", file=sys.stderr)
        print(str(ex), file=sys.stderr)
        sys.exit(1)

    print(f"--- Sucesso: {len(response.rows)} linha(s) na propriedade {property_id} ---")
    for row in response.rows:
        date, channel = row.dimension_values[0].value, row.dimension_values[1].value
        sessions, users = row.metric_values[0].value, row.metric_values[1].value
        print(f"  {date} | {channel} | sessions={sessions} | users={users}")
    if not response.rows:
        print("  (acesso ok, mas sem dado no período)")


if __name__ == "__main__":
    main()
