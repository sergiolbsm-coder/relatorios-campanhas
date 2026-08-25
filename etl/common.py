"""
Utilitários compartilhados pelos scripts de extração da Fase 2.

Centraliza: leitura do config.yaml (IDs de conta por marca), parsing de
período via argumentos de linha de comando, e escrita de CSV padronizada.
"""

import argparse
import csv
import datetime
import os
from pathlib import Path
from typing import Iterable

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"
DATA_DIR = PROJECT_ROOT / "etl" / "data"


def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def brands_with(platform_key: str) -> list[tuple[str, str, dict]]:
    """
    Retorna [(brand_key, display_name, platform_config), ...] só para as
    marcas que têm essa plataforma configurada com status "confirmed"
    (ignora gaps aceitos e placeholders vazios).
    """
    config = load_config()
    result = []
    for brand_key, brand in config["brands"].items():
        platform = brand.get(platform_key)
        if not platform:
            continue
        if platform.get("status") != "confirmed":
            continue
        result.append((brand_key, brand["display_name"], platform))
    return result


def date_range_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--start", help="YYYY-MM-DD (default: hoje - --days)")
    parser.add_argument("--end", help="YYYY-MM-DD (default: hoje)")
    parser.add_argument("--days", type=int, default=90, help="janela em dias se --start não for informado (default 90)")


def resolve_date_range(args: argparse.Namespace) -> tuple[datetime.date, datetime.date]:
    end = datetime.date.fromisoformat(args.end) if args.end else datetime.date.today()
    start = datetime.date.fromisoformat(args.start) if args.start else end - datetime.timedelta(days=args.days)
    return start, end


def write_csv(rows: Iterable[dict], filename: str, fieldnames: list[str]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        count = 0
        for row in rows:
            writer.writerow(row)
            count += 1
    print(f"[{filename}] {count} linha(s) gravada(s) em {path}")
    return path
