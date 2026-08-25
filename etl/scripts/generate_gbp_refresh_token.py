"""
Gera o refresh token OAuth2 para a Google Business Profile API.

Uso (ver docs/1.3-google-business-profile-setup.md, Passo 4):
    export GBP_CLIENT_ID=...
    export GBP_CLIENT_SECRET=...
    python3 etl/scripts/generate_gbp_refresh_token.py

Idêntico em estrutura a generate_google_ads_refresh_token.py, só muda o
escopo de autorização (business.manage em vez de adwords).
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/business.manage"]


def main() -> None:
    client_id = os.environ.get("GBP_CLIENT_ID")
    client_secret = os.environ.get("GBP_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "Defina GBP_CLIENT_ID e GBP_CLIENT_SECRET antes de rodar este "
            "script (ver Passo 3 do guia 1.3).",
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
    credentials = flow.run_local_server(prompt="consent", access_type="offline")

    print("\n--- Autorização concluída ---")
    print(f"Refresh token: {credentials.refresh_token}")
    print("\nCole este valor em GBP_REFRESH_TOKEN no seu .env.")


if __name__ == "__main__":
    main()
