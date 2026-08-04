# Fase 5 — comparação controlada de modelos

## Proteções obrigatórias

A Fase 5 opera exclusivamente em `shadow mode`. Ela não altera estados,
baseline, risco, alarmes ou notificações. A comparação só executa quando cada
grupo atende simultaneamente a qualidade mínima e 200 linhas completas,
temporalmente alinhadas, com as cinco métricas configuradas.

## Comparação e explicabilidade

O experimento compara:

1. detector robusto transparente, baseado em mediana/MAD;
2. Isolation Forest com seed fixa para reprodutibilidade.

Cada anomalia candidata identifica a métrica com maior contribuição robusta e
indica a concordância dos dois métodos. O resultado é evidência estatística,
não confirmação de causa ou indisponibilidade.

## Resultado da validação inicial

A consulta histórica real mostrou qualidade de 98,36% a 99,69% e as 25 métricas
em cada grupo. Apesar disso, não existem 200 linhas completas alinhadas entre as
cinco métricas selecionadas. Assim, nenhum experimento foi executado e nenhuma
decisão de produção foi alterada. Isso é o comportamento esperado do gate.

## Próximo requisito operacional

Executar a aquisição contínua até reunir snapshots válidos alinhados. Depois,
rodar:

```powershell
python scripts/run_phase5.py
```

O estudo supervisionado continua bloqueado até existirem pelo menos 50 rótulos
operacionais abrangendo períodos normais e incidentes confirmados, de no mínimo
três categorias.
