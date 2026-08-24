"""
Gera o refresh token OAuth2 para a Google Ads API.

Uso (ver docs/1.1-google-ads-api-setup.md, Passo 5):
    pip install google-auth-oauthlib
    export GOOGLE_ADS_CLIENT_ID=...        # do Passo 4
    export GOOGLE_ADS_CLIENT_SECRET=...    # do Passo 4
    python3 etl/scripts/generate_google_ads_refresh_token.py

Abre uma janela do navegador para você logar com a conta Google que tem
acesso ao Google Ads (sergiolbsm@gmail.com) e autorizar o app. Ao final,
imprime o refresh token — cole em GOOGLE_ADS_REFRESH_TOKEN no .env.

Baseado no fluxo oficial documentado em:
https://developers.google.com/google-ads/api/docs/get-started/oauth-cloud-project
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

# Escopo mínimo necessário para ler dados via Google Ads API.
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> None:
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "Defina GOOGLE_ADS_CLIENT_ID e GOOGLE_ADS_CLIENT_SECRET antes de "
            "rodar este script (ver Passo 4 do guia).",
            file=sys.stderr,
        )
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    # run_local_server abre o navegador, captura o redirect e troca o code
    # pelo access_token + refresh_token automaticamente.
    credentials = flow.run_local_server(
        prompt="consent",
        access_type="offline",  # necessário para receber o refresh_token
    )

    print("\n--- Autorização concluída ---")
    print(f"Refresh token: {credentials.refresh_token}")
    print("\nCole este valor em GOOGLE_ADS_REFRESH_TOKEN no seu .env.")


if __name__ == "__main__":
    main()
