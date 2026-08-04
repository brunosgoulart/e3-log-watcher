# Fase 2 — baseline e alarmes explicáveis

## Método

Para cada grupo lógico e sessão operacional, a aplicação forma um perfil por
métrica numérica apenas com eventos PI válidos anteriores à aquisição atual.
São necessários 30 pontos válidos por padrão. O centro é a mediana e a dispersão
é o MAD; o intervalo é calculado com z-score robusto e uma largura relativa
mínima para evitar alarmes artificiais em sinais sem variação observável.

Uma tendência é a inclinação da regressão dos últimos 12 pontos, expressa de
forma relativa à mediana por hora. Não há previsão nem extrapolação nesta fase.

## Regras compostas

As regras configuradas não afirmam causa; usam linguagem de possibilidade:

- pressão de scripts: ocupação, tempo médio e CPU;
- fila de I/O: pendência e atraso;
- pressão de memória: memória, page faults e PVT;
- represamento de eventos: pendências, remotos pendentes e descartes.

Cada regra exige duas confirmações entre suas métricas. A pontuação é a soma
limitada de pesos das regras acionadas. O alarme só abre após três avaliações
consecutivas e só fecha depois de duas avaliações limpas.

## Gatilhos de segurança

Não é calculado risco quando o grupo não está em `ACTIVE_COLLECTING`, não há
sessão, a qualidade é insuficiente ou não há baseline. Isso evita confundir
startup, switchover, dados stale, valores `Configure`/`Scan Off` e falha de
aquisição com degradação.

## Validação real inicial

Foi confirmada leitura com autenticação integrada do Windows em
`\\PIDATAPRO\CSEO.COGCGPRO34.E3Run.TRD`: a consulta retornou valor numérico,
timestamp PI e qualidade `Good`. A allow-list foi revisada para 75 tags numéricas;
`CollectionTimeStamp` foi retirada por ser textual. Alguns sinais apresentaram `Bad` com valores textuais `Configure` ou
`Scan Off`. Eles são preservados como dados brutos e excluídos corretamente do
baseline, sem diagnóstico de indisponibilidade.
