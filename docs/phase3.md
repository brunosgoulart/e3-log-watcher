# Fase 3 — backtesting, rotulagem e projeções

## Backtesting temporal

`scripts/run_backtest.py` recebe amostras em JSON, ordena-as por tempo e só
acrescenta uma observação ao histórico após analisá-la. Isto impede vazamento de
dados futuros. Amostras fora de `ACTIVE_COLLECTING` são excluídas por padrão;
períodos de estabilização só entram mediante configuração explícita.

O resultado persistido registra alarmes por grupo e regra, quantidade de
amostras elegíveis e distribuição dos estados. Eventos confirmados, falsos
positivos e falsos negativos continuam dependentes de rótulos operacionais; não
são inventados pelo sistema.

Exemplo:

```powershell
python scripts/run_backtest.py .\dados-sinteticos.json
```

## Rotulagem e calibração

`POST /api/admin/labels` registra switchover, reinicialização, manutenção,
falha PI, pico esperado, falso positivo e outras categorias operacionais. A
chave de administração fica exclusivamente na variável
`E3_MONITOR_ADMIN_API_KEY`.

Os parâmetros por grupo permanecem no YAML até haver histórico rotulado
suficiente. Uma calibração automática sem rótulos seria uma inferência não
auditável; a Fase 3 fornece o dado necessário para essa decisão, não altera
pesos por conta própria.

## Projeções

As projeções são lineares, de horizonte curto e geradas apenas para uma sessão
ativa com pelo menos 30 pontos e R² de 0,70. Elas mostram inclinação, projeção,
intervalo e limitações. Limites operacionais ficam vazios até que unidades e
limites aprovados sejam fornecidos; portanto não há estimativa fictícia de
tempo até saturação.
