# Análise de Campanhas e Métricas

Pipeline de BI multi-marca (Instituto da Liderança, Associação de Luto União,
Trainer Sergio Moura) consolidando Google Ads, Meta Ads, Instagram, Google Meu
Negócio, GA4 e GTM num dashboard único.

Ver [`CLAUDE.md`](CLAUDE.md) para o estado atual do projeto e
[`docs/architecture-decision.md`](docs/architecture-decision.md) para o
porquê da escolha de arquitetura.

## Setup

```bash
cp .env.example .env
# preencher .env com as credenciais de cada API (ver comentários no arquivo)
```

## Estrutura

```
config.yaml     # IDs de conta confirmados por marca/plataforma
etl/            # scripts de extração (Fase 2)
dashboard/      # visualização (Fase 4)
docs/           # decisões e documentação de projeto
```
