# Decisão de arquitetura (Fase 0.2)

**Decisão: Arquitetura B — scripts próprios via API oficial de cada plataforma.**

## Histórico

- **24/08/2026, manhã**: Fase 1 marcada como fechada com base em autenticação
  OAuth feita direto no Cowork via Supermetrics (arquitetura A, no-code). 11 de
  15 pontos de conexão confirmados para as 3 marcas do projeto.
- **24/08/2026, tarde**: ao tentar validar o critério de saída real da Fase 1
  ("puxar 1 linha de dado real de cada plataforma"), toda chamada de
  `data_query` no Supermetrics retornou `TRIAL_EXPIRED` — o trial da conta
  (team "sergiolbsm", ID 1722854) expirou em **16/05/2026**. As chamadas de
  descoberta (contas, campos) funcionam normalmente porque não dependem do
  plano pago; só a extração de dado em si está bloqueada.
- Isso significa que a Fase 1 estava **parcialmente** fechada: acesso/auth
  confirmados, extração de dado não confirmada.

## Opções consideradas

1. Assinar um plano pago da Supermetrics e continuar na arquitetura A.
2. Migrar para arquitetura B: scripts Python direto nas APIs oficiais
   (Google Ads API, Meta Marketing API, GA4 Data API, Business Profile API),
   reaproveitando os IDs de conta já confirmados em `config.yaml`.

## Decisão

Optou-se pela **opção 2**. Os IDs de conta de todas as 3 marcas já estão
confirmados e centralizados em [`config.yaml`](../config.yaml), então a
migração de arquitetura não perde o trabalho de descoberta feito na Fase 1 —
só troca a camada de extração.

## Consequência prática para a Fase 1

O critério de saída da Fase 1 ainda **não está cumprido**. Falta, para cada
plataforma:

| Plataforma | O que falta agora |
|---|---|
| Google Ads | Criar projeto GCP, ativar API, gerar OAuth2 client + developer token (produção, não só teste) |
| Meta Ads / Instagram | Criar app no Meta for Developers, gerar token de longa duração |
| GA4 | Criar service account no GCP, dar acesso "Viewer" na propriedade 450305882 |
| Google Meu Negócio | Habilitar Business Profile API, configurar OAuth2 (aprovação pode demorar) |
| GTM | Segue pendente — sem conector pronto, precisa de API própria ou auditoria manual |

Isso volta a ser trabalho da Fase 1, itens 1.1–1.4 e 1.6, agora usando os
IDs já confirmados como ponto de partida (não é preciso redescobrir contas).
