"""
Gera o refresh token OAuth2 com escopo de Google Sheets (item 4.1).

Uso (ver docs/4.1-looker-studio-setup.md, Passo 2):
    export GOOGLE_ADS_CLIENT_ID=...        # reaproveita o do item 1.1
    export GOOGLE_ADS_CLIENT_SECRET=...
    python3 etl/scripts/generate_sheets_refresh_token.py

Escopos: spreadsheets (ler/escrever) + drive.file (criar a planilha via API,
restrito a arquivos criados pelo próprio app — não dá acesso ao Drive todo).
"""

import os
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def main() -> None:
    client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "Defina GOOGLE_ADS_CLIENT_ID e GOOGLE_ADS_CLIENT_SECRET (mesmo "
            "client do item 1.1) antes de rodar este script.",
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
    print("\nCole este valor em GOOGLE_SHEETS_REFRESH_TOKEN no seu .env.")


if __name__ == "__main__":
    main()
