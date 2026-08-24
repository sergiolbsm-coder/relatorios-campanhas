# Sistema de Análise de Campanhas e Métricas

Projeto: Instituto da Liderança · Associação de Luto União (Curitiba) · Trainer
Sergio Moura. Trainer: Sergio Moura (sergiolbsm@gmail.com).

## O que é

Pipeline de BI que consolida Google Ads, Meta Ads (Facebook + Instagram),
Google Meu Negócio, GA4 e GTM das 3 marcas acima num dashboard único.

## Arquitetura

**B — custom**: scripts Python direto nas APIs oficiais de cada plataforma
(não Supermetrics/no-code — ver [docs/architecture-decision.md](docs/architecture-decision.md)
para o porquê). Motivo: o trial da Supermetrics usado para validar acessos
expirou em 16/05/2026, e a decisão do time foi não assinar plano pago.

## Estrutura

- `config.yaml` — IDs de conta confirmados das 3 marcas, por plataforma. Fonte
  única de verdade — não redescobrir contas, só ler daqui.
- `.env` (não versionado, ver `.env.example`) — credenciais de API.
- `etl/` — scripts de extração por plataforma (Fase 2).
- `dashboard/` — camada de visualização (Fase 4).
- `docs/` — decisões de projeto e documentação.

## Estado atual (24/08/2026)

- **Fase 0** (diagnóstico/arquitetura): decisão de arquitetura fechada (B).
  KPIs por canal ainda não formalizados (item 0.3 pendente).
- **Fase 1** (acessos): IDs de conta das 3 marcas confirmados em `config.yaml`.
  Credenciais de API própria (Google Cloud project, Meta app, service account
  GA4, Business Profile API) ainda **não criadas**.
  - Item 1.1 (Google Ads): guia passo a passo pronto em
    [docs/1.1-google-ads-api-setup.md](docs/1.1-google-ads-api-setup.md) +
    script de geração de refresh token em
    [etl/scripts/generate_google_ads_refresh_token.py](etl/scripts/generate_google_ads_refresh_token.py).
    Aguardando o usuário (sergiolbsm@gmail.com) executar os passos no console
    do Google Cloud — requer login próprio, não pode ser automatizado por mim.
  - Itens 1.2 (Meta Ads), 1.3 (GMB), 1.4 (GA4), 1.6 (GTM): ainda não iniciados.
- Gaps aceitos conscientemente: sem GA4 para Associação de Luto União nem para
  Trainer Sergio Moura; sem Google Ads para Trainer Sergio Moura; GTM sem
  conector pronto, pendente para Fase 2/6.

## Convenções

- Progressão por fases — não pular fase sem fechar o critério de saída da
  anterior (evita retrabalho).
- Um prompt/tarefa por vez, uma fase por sessão de contexto.
- IDs de conta sempre vêm de `config.yaml`, nunca redescobertos manualmente.
