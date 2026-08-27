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
- **Fase 4** (dashboard): item 4.1 fechado (26/08/2026). Decisão do usuário:
  **Looker Studio + Google Sheets** (não SQLite direto — Looker Studio não
  conecta nativamente em SQLite).
  - [docs/4.1-looker-studio-setup.md](docs/4.1-looker-studio-setup.md) —
    guia completo. Fluxo: `db/analise_campanhas.db` →
    [etl/export_to_sheets.py](etl/export_to_sheets.py) → Google Sheets →
    Looker Studio.
  - Reaproveita `GOOGLE_ADS_CLIENT_ID/SECRET` (mesmo client OAuth do item
    1.1) com escopo novo (`spreadsheets` + `drive.file`), token próprio em
    `GOOGLE_SHEETS_REFRESH_TOKEN`. Script de geração:
    `etl/scripts/generate_sheets_refresh_token.py`.
  - Planilha criada e populada:
    https://docs.google.com/spreadsheets/d/1RoIQ7lFwbxTPHokGTzeJ_X84P5EUNqWXjBsK4AQVw7w
    (ID em `GOOGLE_SHEETS_SPREADSHEET_ID`). 1137 linhas exportadas
    (`fact_metrics_daily` completo), testado idempotente (reexecução
    reaproveita a mesma planilha, não cria outra).
  - **Ainda falta o usuário conectar essa planilha no Looker Studio**
    (Passo 4 do guia) e criar o relatório — isso não pode ser automatizado
    daqui, é interação manual na UI do Looker Studio.
  - Pendência descoberta durante o setup: além da Sheets API, o `gspread`
    também precisa da **Google Drive API** habilitada (usa Drive por baixo
    pra criar o arquivo) — ambas ativadas no projeto `campanha-instituto`.
  - **Bug corrigido no processo**: o `.env` tinha ficado dessincronizado do
    `.env.example` por várias rodadas (ainda tinha `GTM_*` removido, faltava
    `GA4_SERVICE_ACCOUNT_JSON_PATH`/`GOOGLE_SHEETS_*`) porque um script antigo
    só fazia `pattern.sub` sem fallback de append quando a chave não existia
    ainda no arquivo — o `print` de sucesso rodava incondicionalmente mesmo
    sem ter escrito nada. Corrigido via merge (.env.example como template +
    valores reais do .env antigo preservados). Ao adicionar uma nova
    variável de ambiente a `.env.example` no futuro, **sempre conferir que
    ela também existe no `.env` real** antes de assumir que está tudo
    sincronizado — não confiar só na mensagem de print de scripts one-off.

- **Fase 3** (modelagem e banco): itens 3.1, 3.2, 3.3 e 3.4 prontos e
  validados (26/08/2026). Decisão: **SQLite** em vez de Postgres/planilha —
  zero servidor, ainda SQL de verdade com upsert/índices, suficiente pra essa
  escala (3 marcas, poucas dezenas de campanhas).
  - [db/schema.sql](db/schema.sql) — 2 tabelas fato (grãos diferentes):
    `fact_metrics_daily` (Google Ads + Meta Ads + Instagram orgânico
    agregado por conta/dia — o que permite comparar canais lado a lado) e
    `fact_instagram_media` (post/reel individual, métricas de vida inteira,
    grão incompatível com a fato diária). Dimensões: `dim_brand`,
    `dim_channel`.
  - [etl/load_to_sqlite.py](etl/load_to_sqlite.py) — lê o CSV mais recente
    de cada fonte em `etl/data/`, normaliza nome de marca pra `brand_key`
    (`brand_key_by_display_name()` em `etl/common.py`), e faz upsert via
    `natural_key` (date|brand|channel|account|campaign|placement) —
    **testado idempotente**: rodar 2x não duplica (1141 linhas processadas,
    1141 no banco nas duas rodadas).
  - Banco fica em `db/analise_campanhas.db` (gitignored — só o schema.sql
    é versionado). Rebuild do zero: `python3 etl/load_to_sqlite.py --rebuild`.
  - Ajuste retroativo: `extract_meta_ads.py` (2.2) passou a capturar
    `campaign_id` (faltava, só tinha `campaign_name`) — necessário pra chave
    natural do banco.
  - Item 3.5 (testes automatizados de qualidade) ainda não iniciado.

- **Fase 2** (extração): itens 2.1 (Google Ads), 2.2 (Meta Ads) e 2.3
  (Instagram Insights) prontos e validados com dado real (25/08/2026).
  - [etl/common.py](etl/common.py) — utilitário compartilhado: lê contas
    confirmadas do `config.yaml` (`brands_with(platform_key)`), parsing de
    período via CLI (`--start`/`--end`/`--days`), escrita de CSV padronizada
    em `etl/data/` (gitignored).
  - [etl/extract_google_ads.py](etl/extract_google_ads.py) — métricas diárias
    de campanha (impressões, cliques, custo, conversões), todas as contas
    confirmadas. Testado: 87 linhas/30 dias, 2 marcas.
  - [etl/extract_meta_ads.py](etl/extract_meta_ads.py) — idem + quebra por
    posicionamento (`publisher_platform`, `platform_position`). Testado:
    1000 linhas/30 dias, 3 marcas (paginação da Graph API funcionando).
  - [etl/extract_instagram_insights.py](etl/extract_instagram_insights.py) —
    reaproveita o mesmo `META_ACCESS_TOKEN` do Meta Ads (não precisa de novo
    setup de credencial). Gera 2 CSVs: conta/dia (alcance, novos seguidores)
    e mídia (posts/reels — reach, likes, comments, shares, saved, views).
    Stories ficam fora de propósito: expiram em 24h, a API só expõe insights
    delas em tempo real, incompatível com extração histórica retroativa.
    Testado: 30 linhas/10 dias (conta), 4 posts/reels, 3 marcas.
  - Padrão pra próximos scripts de extração (2.5 GA4 quando 1.4 for
    retomado): reusar `etl/common.py`, mesma assinatura de CLI, mesmo padrão
    de nome de arquivo `{fonte}_{start}_a_{end}.csv`.
  - Itens 2.4 (GMB) e 2.6 (auditoria GTM) dependem de 1.3 (pausado) e foram
    descartados (GTM) — não iniciar sem eles.
  - Itens 2.7 (agendamento) e 2.8 (retry/alertas) ainda não iniciados —
    fazem mais sentido depois de ter mais fontes extraindo.

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
  - **Item 1.3 (GMB): guia pronto, execução pausada por decisão do usuário
    (25/08/2026)** — retomar quando priorizado, [docs/1.3-google-business-profile-setup.md](docs/1.3-google-business-profile-setup.md).
    Diferente dos outros, exige aprovação manual da Google antes de tudo
    (formulário em support.google.com/business/contact/api_default) —
    é o passo bloqueante, disparar cedo. Scripts:
    `generate_gbp_refresh_token.py`, `test_gbp_access.py`. Os IDs de location
    no `config.yaml` vieram do Supermetrics e precisam ser confirmados via
    API real no Passo 5 do guia (podem não bater 100% no formato).
  - **Item 1.4 (GA4): guia pronto, execução pausada por decisão do usuário
    (25/08/2026)** — retomar quando priorizado, [docs/1.4-ga4-api-setup.md](docs/1.4-ga4-api-setup.md).
    Usa service account (não passa pela tela de consentimento OAuth — mais
    simples que Google Ads/Meta/GMB). Script: `test_ga4_access.py`.
  - **Item 1.6 (GTM): removido do escopo do projeto (25/08/2026)** — decisão
    do usuário. Sem conector pronto e sem valor claro de métrica de campanha.
    Ver nota no topo do `config.yaml` se precisar reavaliar depois.
  - Scripts de teste em `etl/scripts/` seguem um padrão: script
    `generate_*_refresh_token.py` (quando usa OAuth) + `test_*_access.py`
    que lê do `.env`/ambiente e confirma dado real, não só token válido.
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
