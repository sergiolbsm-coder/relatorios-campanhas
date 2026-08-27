"""
3.2/3.3/3.4 — Carrega os CSVs extraídos (etl/data/) no banco SQLite
(db/analise_campanhas.db), normalizando nomes/marca e fazendo upsert
idempotente (rodar de novo não duplica linha — natural_key/media_id como
chave de conflito).

Uso:
    python3 etl/load_to_sqlite.py
    python3 etl/load_to_sqlite.py --rebuild   # apaga e recria o banco do zero
"""

import argparse
import csv
import glob
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl.common import DATA_DIR, DB_PATH, SCHEMA_PATH, brand_key_by_display_name, load_config

CHANNELS = {
    "google_ads": "Google Ads",
    "meta_ads": "Meta Ads",
    "instagram_organic": "Instagram Insights (orgânico)",
}


def get_connection(rebuild: bool = False) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if rebuild and DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Banco anterior removido ({DB_PATH}).")

    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())
    return conn


def seed_dimensions(conn: sqlite3.Connection) -> None:
    config = load_config()
    for key, brand in config["brands"].items():
        conn.execute(
            "INSERT INTO dim_brand (brand_key, display_name) VALUES (?, ?) "
            "ON CONFLICT(brand_key) DO UPDATE SET display_name=excluded.display_name",
            (key, brand["display_name"]),
        )
    for key, name in CHANNELS.items():
        conn.execute(
            "INSERT INTO dim_channel (channel_key, display_name) VALUES (?, ?) "
            "ON CONFLICT(channel_key) DO UPDATE SET display_name=excluded.display_name",
            (key, name),
        )
    conn.commit()


def latest_csv(pattern: str):
    matches = sorted(glob.glob(str(DATA_DIR / pattern)))
    return matches[-1] if matches else None


def upsert_daily(conn, brand_key, channel, account_id, campaign_id, campaign_name,
                  placement, date, impressions=None, clicks=None, cost=None,
                  conversions=None, reach=None, new_followers=None):
    natural_key = "|".join([
        date, brand_key, channel, account_id or "", campaign_id or "", placement or "",
    ])
    conn.execute(
        """
        INSERT INTO fact_metrics_daily (
            natural_key, date, brand_key, channel, account_id, campaign_id,
            campaign_name, placement, impressions, clicks, cost, conversions,
            reach, new_followers
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(natural_key) DO UPDATE SET
            campaign_name=excluded.campaign_name,
            impressions=excluded.impressions,
            clicks=excluded.clicks,
            cost=excluded.cost,
            conversions=excluded.conversions,
            reach=excluded.reach,
            new_followers=excluded.new_followers,
            loaded_at=datetime('now')
        """,
        (natural_key, date, brand_key, channel, account_id, campaign_id, campaign_name,
         placement, impressions, clicks, cost, conversions, reach, new_followers),
    )


def load_google_ads(conn, brand_map) -> int:
    path = latest_csv("google_ads_*.csv")
    if not path:
        print("  (nenhum CSV de google_ads encontrado, pulando)")
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            upsert_daily(
                conn, brand_map[row["brand"]], "google_ads", row["customer_id"],
                row["campaign_id"], row["campaign_name"], None, row["date"],
                impressions=int(row["impressions"]), clicks=int(row["clicks"]),
                cost=float(row["cost"]), conversions=float(row["conversions"]),
            )
            count += 1
    print(f"  google_ads: {count} linha(s) de {os.path.basename(path)}")
    return count


def load_meta_ads(conn, brand_map) -> int:
    path = latest_csv("meta_ads_*.csv")
    if not path:
        print("  (nenhum CSV de meta_ads encontrado, pulando)")
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            placement = f"{row.get('publisher_platform', '')}/{row.get('platform_position', '')}"
            upsert_daily(
                conn, brand_map[row["brand"]], "meta_ads", row["account_id"],
                row.get("campaign_id"), row["campaign_name"], placement, row["date"],
                impressions=int(row["impressions"] or 0), clicks=int(row["clicks"] or 0),
                cost=float(row["spend"] or 0),
            )
            count += 1
    print(f"  meta_ads: {count} linha(s) de {os.path.basename(path)}")
    return count


def load_instagram_account_daily(conn, brand_map) -> int:
    path = latest_csv("instagram_account_daily_*.csv")
    if not path:
        print("  (nenhum CSV de instagram_account_daily encontrado, pulando)")
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            upsert_daily(
                conn, brand_map[row["brand"]], "instagram_organic", row["account_id"],
                None, None, None, row["date"],
                reach=int(row["reach"]) if row["reach"] else None,
                new_followers=int(row["new_followers"]) if row["new_followers"] else None,
            )
            count += 1
    print(f"  instagram_account_daily: {count} linha(s) de {os.path.basename(path)}")
    return count


def load_instagram_media(conn, brand_map) -> int:
    path = latest_csv("instagram_media_*.csv")
    if not path:
        print("  (nenhum CSV de instagram_media encontrado, pulando)")
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            conn.execute(
                """
                INSERT INTO fact_instagram_media (
                    media_id, brand_key, account_id, media_type, media_product_type,
                    published_at, permalink, reach, likes, comments, shares, saved,
                    total_interactions, views
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(media_id) DO UPDATE SET
                    reach=excluded.reach, likes=excluded.likes, comments=excluded.comments,
                    shares=excluded.shares, saved=excluded.saved,
                    total_interactions=excluded.total_interactions, views=excluded.views,
                    loaded_at=datetime('now')
                """,
                (
                    row["media_id"], brand_map[row["brand"]], row["account_id"],
                    row["media_type"], row["media_product_type"], row["timestamp"],
                    row["permalink"],
                    int(row["reach"]) if row["reach"] else None,
                    int(row["likes"]) if row["likes"] else None,
                    int(row["comments"]) if row["comments"] else None,
                    int(row["shares"]) if row["shares"] else None,
                    int(row["saved"]) if row["saved"] else None,
                    int(row["total_interactions"]) if row["total_interactions"] else None,
                    int(row["views"]) if row["views"] else None,
                ),
            )
            count += 1
    print(f"  instagram_media: {count} linha(s) de {os.path.basename(path)}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="apaga e recria o banco do zero")
    args = parser.parse_args()

    conn = get_connection(rebuild=args.rebuild)
    seed_dimensions(conn)
    brand_map = brand_key_by_display_name()

    print(f"Carregando CSVs de {DATA_DIR} em {DB_PATH}...")
    total = 0
    total += load_google_ads(conn, brand_map)
    total += load_meta_ads(conn, brand_map)
    total += load_instagram_account_daily(conn, brand_map)
    total += load_instagram_media(conn, brand_map)
    conn.commit()
    conn.close()
    print(f"Concluído: {total} linha(s) processada(s) (upsert idempotente).")


if __name__ == "__main__":
    main()
