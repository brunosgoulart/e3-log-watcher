# Saidas OnRead - E3 Log Reader

Referencia das saidas publicadas pelo `main.vbs` (versao 1.7 - 2026-07-12).

| Variavel OnRead | Resumo |
|---|---|
| `trigger` | Dispara a rotina de leitura e atualizacao das metricas do ETL. |
| `runCPU` | Uso de CPU do processo E3Run, em percentual. |
| `runPVT` | Memoria virtual privada do processo E3Run, em KB. |
| `runHDL` | Quantidade de handles abertos pelo processo E3Run. |
| `runTRD` | Quantidade de threads em execucao no processo E3Run. |
| `runUptimeMinutes` | Tempo total de execucao do E3Run, convertido para minutos inteiros. |
| `runRestartDetected` | Indica se foi detectado reinicio do E3Run desde a coleta anterior (`0` ou `1`). |
| `runOccupancy` | Ocupacao dos scripts do E3Run, em percentual. |
| `runAvgScriptTime` | Tempo medio de execucao dos scripts do E3Run. |
| `runErrorsPerMinute` | Taxa de erros dos scripts do E3Run por minuto. |
| `runMemory` | Carga de memoria informada pelo registro de processo do E3Run. |
| `runPageFaults` | Total de page faults informado pelo processo E3Run. |
| `runLocalPending` | Quantidade atual de eventos locais pendentes. |
| `runRemotePending` | Quantidade atual de eventos remotos pendentes. |
| `runLocalQueuedPerMinute` | Taxa de entrada de eventos locais na fila, por minuto. |
| `runLocalHandledPerMinute` | Taxa de tratamento de eventos locais, por minuto. |
| `runLocalDiscardedPerMinute` | Taxa de descarte de eventos locais, por minuto. |
| `runRemoteQueuedPerMinute` | Taxa de entrada de eventos remotos na fila, por minuto. |
| `runRemoteHandledPerMinute` | Taxa de tratamento de eventos remotos, por minuto. |
| `runRemoteDiscardedPerMinute` | Taxa de descarte de eventos remotos, por minuto. |
| `runLocalQueueGrowthPerMinute` | Crescimento liquido da fila local por minuto: enfileirados menos tratados. |
| `runRemoteQueueGrowthPerMinute` | Crescimento liquido da fila remota por minuto: enfileirados menos tratados. |
| `runLocalDiscardPercent` | Percentual de eventos locais descartados em relacao aos enfileirados. |
| `runRemoteDiscardPercent` | Percentual de eventos remotos descartados em relacao aos enfileirados. |
| `linkEventsIntervalMinutes` | Intervalo, em minutos, entre as duas amostras de eventos usadas nos calculos de taxa. |
| `linkEventsIntervalAvailable` | Indica se ha intervalo valido entre amostras para calcular deltas e taxas (`0` ou `1`). |
| `runAnyCounterReset` | Indica se algum contador acumulado do E3Run reduziu desde a coleta anterior (`0` ou `1`). |
| `globalCPU` | Uso global de CPU informado pelo resumo de processos do ETL, em percentual. |
| `globalThreads` | Total de threads informado pelo resumo de processos do ETL. |
| `driveCFreeMB` | Espaco livre da unidade C: informado pelo ETL, em MB. |
| `ioQueuePending` | Quantidade de operacoes pendentes na fila de E/S informada pelo ETL. |
| `ioQueueAvgDelay` | Atraso medio das operacoes na fila de E/S, conforme informado pelo ETL. |
| `serverStatus` | Estado textual mais recente do E3Server encontrado no ETL. |
| `serverCPU` | Uso de CPU do processo E3Server, em percentual. |
| `serverPVT` | Memoria virtual privada do processo E3Server, em KB. |
| `serverHDL` | Quantidade de handles abertos pelo processo E3Server. |
| `collectionTimestamp` | Estampa de tempo do registro mais recente usado como referencia na coleta. |
| `sampleAgeSeconds` | Idade, em segundos, da amostra do ETL em relacao ao momento da leitura. |
| `etlFileSizeMB` | Tamanho do arquivo ETL selecionado, em MB. |
| `etlFileChanged` | Indica se o arquivo ETL selecionado mudou desde a coleta anterior (`0` ou `1`). |
| `foundProcessSummary` | Indica se o resumo de processos foi localizado no trecho lido do ETL (`0` ou `1`). |
| `foundE3RunProcess` | Indica se foi localizado o registro de processo do E3Run (`0` ou `1`). |
| `foundE3RunScripts` | Indica se foi localizado o registro de scripts do E3Run (`0` ou `1`). |
| `foundE3RunLinkEvents` | Indica se foi localizado o registro de eventos locais/remotos do E3Run (`0` ou `1`). |
| `foundIOQueue` | Indica se foi localizado o registro de fila de E/S (`0` ou `1`). |
| `foundE3Server` | Indica se foi localizado o registro de processo do E3Server (`0` ou `1`). |
| `status` | Estado geral da ultima execucao do leitor, para diagnostico da coleta. |
| `totalTime` | Tempo total de execucao do leitor, em segundos. |
