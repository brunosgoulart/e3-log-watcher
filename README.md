# E3 Predictive Monitor — Fase 1

Aplicação Python para adquirir métricas publicadas no PI System, preservar sua
qualidade e organizar a supervisão dos grupos redundantes Elipse E3. Esta
primeira fase não lê ETL, não descobre tags, não determina o servidor físico
ativo e não executa modelos de machine learning.

## Escopo entregue

- Lista fechada, validada e explícita das 78 tags autorizadas (26 por grupo).
- Interface `PiClient`, cliente simulado e adaptador Windows para PI AF SDK.
- Aquisição atual, importação histórica e execução contínua com retentativas.
- Armazenamento separado de dados brutos, normalizados, sessões, estados e alarmes.
- Validação de tipos, timezone, qualidade, valores questionáveis/substituídos e timestamps.
- Estados `INITIALIZING`, `ACTIVE_COLLECTING`, `STALE`, `SWITCHOVER_SUSPECTED`,
  `POST_SWITCHOVER_STABILIZING`, `ACQUISITION_FAILURE`,
  `APPLICATION_UNAVAILABLE` e `UNKNOWN`.
- Dashboard local responsivo, com visão dos três grupos, detalhe de métricas e alarmes textuais.
- Testes unitários e de integração que usam exclusivamente dados sintéticos.

O código do coletor VBScript existente não é utilizado nem alterado pela aplicação.

## Dependências

| Dependência | Finalidade | Operação no Windows / offline | Alternativa simples |
|---|---|---|---|
| Python 3.12 | Runtime | Compatível; instalável por pacote corporativo offline | Não aplicável |
| Pydantic | Contratos e validação do YAML | Compatível; wheel pode vir de repositório corporativo | Validação manual, com menor segurança |
| PyYAML + tzdata | Configuração segura e fuso IANA `America/Sao_Paulo` | Compatíveis; wheels podem vir de repositório corporativo | JSON e timezone local, menos portáveis |
| FastAPI + Uvicorn | Dashboard local e API de leitura | Compatíveis; não exigem serviço externo | HTML estático, sem endpoints |
| SQLite (stdlib) | Persistência inicial local | Incluso no Python; sem serviço adicional | Arquivos CSV, sem integridade/concurrency |
| pythonnet (opcional) | Ponte Python/.NET para PI AF SDK | Windows; requer AF SDK instalado | Worker .NET isolado, se a política vedar pythonnet |
| pytest (desenvolvimento) | Testes automatizados | Compatível; não é necessário em produção | `unittest`, menos conveniente |

O runtime não precisa acessar a internet. As dependências podem ser instaladas
por wheels aprovadas, espelho corporativo ou mídia offline. O risco principal de
manutenção é a compatibilidade entre `pythonnet`, a versão do Python e o PI AF SDK;
por isso o adaptador é isolado da lógica analítica.

## Instalação no Windows

No PowerShell, a partir de `C:\dev\e3-log-reader`:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,pi-af-sdk]"
```

Antes de executar contra o PI real, instale a versão corporativamente aprovada
do PI AF SDK e defina apenas os identificadores não secretos:

```powershell
$env:PI_AF_SERVER = "nome-do-af-server" # opcional para a consulta direta de PIPoints
```

A autenticação é Windows Integrated Authentication. A conta de execução deve
ter somente leitura das 78 tags autorizadas. Senhas, tokens e certificados não
devem ser inseridos em `configs/phase1.yaml`, `.env.example` ou logs.

## Execução segura com dados sintéticos

Uma aquisição única, sem conexão PI:

```powershell
python -m app.main --simulate --once
```

Dashboard local e aquisição contínua sintética:

```powershell
python -m app.main --simulate --serve
```

Abra `http://127.0.0.1:8080`. A fonte sintética é marcada como `synthetic` em
cada evento persistido; ela não representa dado operacional real.

Importação histórica sintética:

```powershell
python -m app.main --simulate --historical-start "2026-01-01T00:00:00-03:00" --historical-end "2026-01-01T01:00:00-03:00"
```

Para PI real, retire `--simulate`. O adaptador consulta o PI AF SDK e falhará
de forma classificada como aquisição se o SDK, o ambiente ou as permissões não
estiverem disponíveis.

## Configuração

`configs/phase1.yaml` contém as 78 tags explícitas, grupos hot/standby,
parâmetros de aquisição, políticas de qualidade e regras iniciais de
switchover. Ele é validado na inicialização; a aplicação encerra caso haja
tags duplicadas, ausentes, externas à lista ou grupos inválidos.

O PI Data Archive foi configurado como `PIDATAPRO`, conforme o caminho
`\\PIDATAPRO\CSEO.COGCGPRO34.E3Run.TRD`: `CSEO.COGCGPRO34.E3Run.TRD` é o nome
da tag/PIPoint. Os tipos configurados para `CollectionTimeStamp`, `FileRead` e
`E3Server.Status` devem ser confirmados em homologação. Unidades permanecem
`null` até confirmação pelo PI. Os valores de `E3Server.Status` que representam
indisponibilidade também permanecem vazios por segurança: sem semântica
confirmada, a aplicação não declara indisponibilidade.

## Qualidade, estados e sessões

`CollectionTimeStamp` é o sinal principal de novidade. A aplicação distingue
evento PI, coleta E3 e instante de aquisição. Valores ruins, questionáveis ou
substituídos nunca são reescritos; a política YAML define somente se participam
da análise. `STALE` requer PI acessível e timestamp de coleta sem avanço.
`ACQUISITION_FAILURE` representa falha de consulta, não degradação E3.

Um possível switchover exige a quantidade configurada de evidências, como
retomada após stale, reset de uptime, mudança de arquivo ou reset de contador.
Ele cria sessão operacional nova e ativa estabilização. O servidor físico ativo
é exibido como desconhecido porque as tags consolidadas não o identificam.

## Testes

```powershell
pytest
```

Os cenários sintéticos estão em `tests/fixtures/scenarios.json`. Incluem dados
normais, stale, falha de aquisição, baixa qualidade, timestamp fora de ordem,
reset, possível switchover, degradação progressiva e recuperação. Os dois
últimos são reservados para a validação estatística da Fase 2; não geram
diagnóstico preditivo nesta fase.

## Critérios objetivos de conclusão da Fase 1

1. O YAML valida exatamente 78 tags, três grupos e 26 tags por grupo.
2. Uma solicitação não autorizada é bloqueada antes do adaptador PI.
3. Eventos brutos e normalizados são persistidos separadamente, sem zero-filling.
4. Falha de PI gera `ACQUISITION_FAILURE`, não alerta de desempenho.
5. Stale, baixa qualidade, timestamp fora de ordem e switchover possível seguem regras auditáveis.
6. Sessões são separadas em inicialização e possível switchover, sem cálculo entre sessões.
7. Dashboard exibe os três grupos, detalhe de métricas e alarmes de estado.
8. Testes executam sem PI real e os logs não incluem credenciais.

Veja [a documentação técnica da Fase 1](docs/phase1.md) para premissas,
limitações e o contrato do PI AF SDK.
