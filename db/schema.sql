-- Schema unificado — Sistema de Análise de Campanhas e Métricas (Fase 3.1)
--
-- Duas tabelas fato, grãos diferentes:
--   fact_metrics_daily   — 1 linha por (data, marca, canal, conta, campanha,
--                           posicionamento). Cobre Google Ads (2.1), Meta Ads
--                           (2.2) e Instagram orgânico agregado por conta/dia
--                           (2.3) — é o que permite comparar os 3 canais lado
--                           a lado por período.
--   fact_instagram_media — 1 linha por post/reel (grão de vida inteira do
--                           post, não por dia — reach/likes são cumulativos).
--                           Grão diferente demais pra caber na tabela acima
--                           sem distorcer comparação por dia.
--
-- Dimensões: dim_brand, dim_channel. campaign_id/campaign_name/placement
-- ficam desnormalizados dentro da fato (baixo volume, ~3 marcas × poucas
-- dezenas de campanhas — normalizar em tabela própria seria over-engineering
-- neste estágio).

CREATE TABLE IF NOT EXISTS dim_brand (
    brand_key    TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_channel (
    channel_key  TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_metrics_daily (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    natural_key   TEXT NOT NULL UNIQUE,  -- date|brand_key|channel|account_id|campaign_id|placement
    date          TEXT NOT NULL,
    brand_key     TEXT NOT NULL REFERENCES dim_brand(brand_key),
    channel       TEXT NOT NULL REFERENCES dim_channel(channel_key),
    account_id    TEXT,
    campaign_id   TEXT,
    campaign_name TEXT,
    placement     TEXT,   -- ex: "facebook/feed", "instagram/reels" (Meta Ads); NULL para Google Ads e Instagram orgânico
    impressions   INTEGER,
    clicks        INTEGER,
    cost          REAL,
    conversions   REAL,
    reach         INTEGER,  -- Instagram orgânico
    new_followers INTEGER,  -- Instagram orgânico
    loaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_fmd_date ON fact_metrics_daily(date);
CREATE INDEX IF NOT EXISTS idx_fmd_brand_channel ON fact_metrics_daily(brand_key, channel);

CREATE TABLE IF NOT EXISTS fact_instagram_media (
    media_id            TEXT PRIMARY KEY,
    brand_key           TEXT NOT NULL REFERENCES dim_brand(brand_key),
    account_id          TEXT NOT NULL,
    media_type          TEXT,
    media_product_type  TEXT,   -- FEED, REELS, CAROUSEL_ALBUM, ...
    published_at        TEXT,
    permalink            TEXT,
    reach               INTEGER,
    likes               INTEGER,
    comments            INTEGER,
    shares              INTEGER,
    saved               INTEGER,
    total_interactions  INTEGER,
    views               INTEGER,  -- só se aplica a REELS
    loaded_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_fim_brand ON fact_instagram_media(brand_key);
