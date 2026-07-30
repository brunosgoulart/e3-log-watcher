# Decisões técnicas — Fase 1

## Contrato de acesso ao PI

`app.acquisition.interfaces.PiClient` é o único contrato aceito pela camada de
orquestração. Ele expõe `fetch_current(tags)` e `fetch_recorded(tags, start,
end)`, devolvendo eventos com nome original da tag, timestamp PI, valor original,
qualidade, flags questionável/substituído, unidade disponível e origem.

`PiAfSdkClient` usa PI AF SDK por `pythonnet`, importa o SDK somente no primeiro
uso e aplica `TagAuthorizer` antes de qualquer `PIPoint.FindPIPoint`. Assim,
testes e dashboard não exigem SDK e não existe consulta fora da allow-list.

O cliente real requer, antes da homologação:

1. AF Server, somente se ele for necessário para futura consulta a elementos AF; o PI Data Archive foi configurado como `PIDATAPRO`, conforme caminho `\\PIDATAPRO\CSEO.COGCGPRO34.E3Run.TRD` informado;
2. versão do PI AF SDK compatível com o Windows e Python corporativos;
3. conta Windows integrada e permissões de leitura somente nas tags fechadas;
4. exemplos reais, sem dados sensíveis, de timestamp, qualidade, status e valor;
5. intervalo esperado, histórico disponível, timezone e política de publicação do dashboard.

## Modelo de dados

| Entidade | Conteúdo | Finalidade |
|---|---|---|
| `acquisitions` | Consulta, origem, êxito e erro classificado | Auditoria de transporte |
| `raw_events` | Valor original e metadados PI | Rastreabilidade sem alteração |
| `normalized_events` | Conversão, validade e motivo de rejeição | Análise temporal futura |
| `operational_sessions` | Limites e motivo de sessões | Evitar cálculo entre reinicializações/switchovers |
| `redundancy_states` | Estado, evidências, confiança e runtime | Auditoria da máquina de estados |
| `alarms` | Alarme textual, evidências e ciclo aberto/resolvido | Supervisão operacional |
| `operational_labels` | Estrutura para rotulagem manual futura | Evolução supervisionada |

SQLite/WAL é propositalmente local e intercambiável. Antes da produção, medir
volume, retenção, concorrência, usuários e política corporativa para decidir se
um banco corporativo será necessário.

## Regras que não fazem inferências indevidas

- Um valor repetido não é novo só porque foi novamente consultado.
- `STALE` só é avaliado quando a consulta PI teve sucesso.
- Status E3 desconhecido não vira indisponibilidade.
- Qualidade baixa reduz a confiança e pode levar a `UNKNOWN`.
- Uma única mudança de métrica não é suficiente para switchover.
- Não há detecção de degradação, baseline, forecast ou ML na Fase 1.

## Limitações deliberadas

As tags consolidadas não identificam o nó físico hot. `FileRead` e
`E3Server.Status` são usados apenas como evidência de mudança, não como prova de
causa. As regras de contador resetável no YAML são hipóteses técnicas e devem ser
confirmadas contra o histórico. Unidades, domínios de status e padrões de
qualidade são preservados, mas não inventados.

## Preparação da Fase 2

A promoção para baseline estatístico dependerá da avaliação do histórico em
ordem temporal: integridade, frequência, lacunas, qualidade, estabilidade,
resets, switchovers, quantidade de sessões e representatividade. Nenhum dado
futuro deverá ser usado no cálculo de uma avaliação passada.
