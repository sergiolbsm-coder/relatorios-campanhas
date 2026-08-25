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
- **Fase 1** (acessos):
  - **Item 1.1 (Google Ads): ✅ fechado (25/08/2026).** Credenciais completas
    no `.env` (client id/secret, refresh token, developer token nível Test).
    Acesso real validado com
    [etl/scripts/test_google_ads_access.py](etl/scripts/test_google_ads_access.py)
    contra as 2 contas do projeto (Instituto da Liderança `7613902765`,
    Associação de Luto União `4001041542` — funciona sem precisar de
    `GOOGLE_ADS_LOGIN_CUSTOMER_ID`, apesar do MCC). Pendência não bloqueante:
    solicitar nível Básico/Standard do developer token (nível Test já é
    suficiente pra extrair dado das contas reais, mas tem cotas menores).
  - **Item 1.2 (Meta Ads): ✅ fechado (25/08/2026).** `META_APP_ID`,
    `META_APP_SECRET`, `META_ACCESS_TOKEN` no `.env`. Acesso real validado via
    Graph API (`curl .../insights`) nas 3 contas de anúncio do projeto.
  - Itens 1.3 (GMB), 1.4 (GA4), 1.6 (GTM): ainda não iniciados.
  - Scripts de teste em `etl/scripts/` (`test_google_ads_access.py`,
    `generate_google_ads_refresh_token.py`) usam variáveis do `.env` —
    reaproveitar o padrão para os próximos setups (GA4, GMB).
  - Nota de fluxo: o usuário está executando os passos via uma sessão
    separada do Claude no Chrome (navegando o console de fato), e trazendo
    o resultado/dúvidas de volta pra esta sessão. Os guias em docs/ são o
    contrato entre as duas sessões — mantenha-os completos e autossuficientes.
- Gaps aceitos conscientemente: sem GA4 para Associação de Luto União nem para
  Trainer Sergio Moura; sem Google Ads para Trainer Sergio Moura; GTM sem
  conector pronto, pendente para Fase 2/6.

## Convenções

- Progressão por fases — não pular fase sem fechar o critério de saída da
  anterior (evita retrabalho).
- Um prompt/tarefa por vez, uma fase por sessão de contexto.
- IDs de conta sempre vêm de `config.yaml`, nunca redescobertos manualmente.
