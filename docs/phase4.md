# Fase 4 — operação contínua e integração

## API e saúde

- `GET /health`: estado da própria aplicação e idade da última aquisição.
- `GET /api/groups`, `/api/analysis`, `/api/forecasts`, `/api/alarms` e
  `/api/labels`: endpoints de leitura.
- `POST /api/admin/labels`: endpoint administrativo protegido por chave em
  variável de ambiente.

O acesso ao PI permanece Windows Integrated Authentication pelo PI AF SDK. A
autenticação do dashboard deve ser aplicada pelo mecanismo corporativo de borda
(por exemplo, IIS com Windows Authentication ou proxy corporativo); ela não
deve ser simulada por senha no código Python.

## Execução contínua no Windows

```powershell
$env:E3_MONITOR_ADMIN_API_KEY = "segredo-gerenciado"
python -m app.main --serve
```

O processo de aquisição roda em thread independente do dashboard e utiliza
SQLite/WAL. Para produção, execute a aplicação com uma conta de serviço de
privilégio mínimo e configure o agendador corporativo ou serviço Windows para
reinício supervisionado. Não exponha a porta local diretamente fora da rede
corporativa.

## Notificações e monitoramento próprio

Notificações ficam desligadas por padrão. A implementação atual é um sink de
log desacoplado, pronto para receber adaptador corporativo aprovado sem alterar
regras ou alarmes. `/health`, logs estruturados e a tabela de aquisições
permitem monitorar a saúde da própria solução.
