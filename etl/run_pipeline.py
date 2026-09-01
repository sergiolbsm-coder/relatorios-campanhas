"""
Orquestra o pipeline completo pra gerar 1 relatório: extrai as 3 fontes
(Google Ads, Meta Ads, Instagram — diário e overview), recarrega o SQLite, e
gera o PDF da marca pedida. É o que a interface web (web/app.py) chama.

Sempre extrai as 3 marcas (as fontes não filtram por marca individualmente
ainda — ver CLAUDE.md, "conhecido, não otimizado"), mas só gera PDF da
marca pedida.

Uso:
    python3 etl/run_pipeline.py --brand associacao_luto_uniao --days 30

Imprime na última linha: PDF_PATH:<caminho absoluto> — é isso que o app
web faz parse pra saber onde está o arquivo gerado.
"""

import argparse
import datetime
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from etl.common import PROJECT_ROOT

SCRIPTS_DIR = PROJECT_ROOT / "etl"


def run(cmd: list[str], step: str) -> None:
    print(f"--- {step} ---", flush=True)
    result = subprocess.run(
        [sys.executable, *cmd],
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )
    print(result.stdout, flush=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, flush=True)
        raise RuntimeError(f"Passo '{step}' falhou (exit {result.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    today = datetime.date.today()
    ig_end = today - datetime.timedelta(days=1)  # Instagram: API não aceita "hoje" na janela
    ig_start = ig_end - datetime.timedelta(days=min(args.days, 27) - 1)  # limite ~28 dias da API

    run(["etl/extract_google_ads.py", "--days", str(args.days)], "Google Ads (diário)")
    run(["etl/extract_meta_ads.py", "--days", str(args.days)], "Meta Ads (diário)")
    run(["etl/extract_instagram_insights.py", "--start", ig_start.isoformat(), "--end", ig_end.isoformat()],
        "Instagram (diário)")
    run(["etl/extract_meta_ads_overview.py", "--days", str(args.days)], "Meta Ads (overview)")
    run(["etl/extract_google_ads_overview.py", "--days", str(args.days)], "Google Ads (overview)")
    run(["etl/extract_instagram_demographics.py"], "Instagram (demografia)")
    run(["etl/load_to_sqlite.py"], "Carregar no banco")
    run(["etl/extract_leads_funnel.py", "--brand", args.brand, "--days", str(args.days)],
        "Funil de vendas (se planilha de leads configurada)")
    run(["etl/generate_pdf_report.py", "--brand", args.brand, "--days", str(args.days)], "Gerar PDF")

    # Acha o PDF mais recente dessa marca
    import glob
    pattern = str(PROJECT_ROOT / "etl" / "data" / f"relatorio_{args.brand}_*.pdf")
    matches = sorted(glob.glob(pattern))
    if not matches:
        raise RuntimeError("PDF não encontrado após a geração — algo falhou silenciosamente.")
    print(f"PDF_PATH:{matches[-1]}")


if __name__ == "__main__":
    main()
