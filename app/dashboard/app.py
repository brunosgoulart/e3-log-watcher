from __future__ import annotations

from math import isfinite
import os
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.config.models import AppConfig
from app.domain.models import OperationalLabel
from app.phase5.service import ShadowModelComparisonService
from app.storage.sqlite import SqliteRepository


def create_dashboard_app(repository: SqliteRepository, config: AppConfig) -> FastAPI:
    app = FastAPI(title="E3 Predictive Monitor - Phase 1", version="0.1.0")

    @app.get("/api/groups")
    def groups() -> list[dict]:
        return _group_cards(repository, config)

    @app.get("/api/groups/{group_id}/metrics")
    def metrics(group_id: str) -> list[dict]:
        _assert_group(config, group_id)
        return repository.metric_history(group_id)

    @app.get("/api/analysis")
    def analysis() -> dict:
        return repository.latest_analysis_by_group()

    @app.get("/api/forecasts")
    def forecasts(group_id: str | None = None) -> list[dict]:
        if group_id:
            _assert_group(config, group_id)
        return repository.latest_forecasts(group_id)

    @app.get("/health")
    def health() -> dict:
        latest = repository.latest_acquisition()
        if latest is None:
            return {"status": "degraded", "reason": "no acquisition recorded"}
        acquired_at = datetime.fromisoformat(latest["acquired_at"])
        age = max(0, int((datetime.now(timezone.utc) - acquired_at).total_seconds()))
        limit = config.acquisition.online_interval_seconds * 3
        status = "ok" if latest["success"] and age <= limit else "degraded"
        return {"status": status, "last_acquisition_at": latest["acquired_at"], "age_seconds": age}

    @app.get("/api/labels")
    def labels(group_id: str | None = None) -> list[dict]:
        if group_id:
            _assert_group(config, group_id)
        return repository.list_operational_labels(group_id)

    @app.get("/api/quality")
    def quality() -> list[dict]:
        return [
            report.model_dump(mode="json")
            for report in repository.historical_quality_reports(
                config.phase5.minimum_valid_ratio, config.phase5.minimum_feature_rows
            )
        ]

    @app.get("/api/model-experiments")
    def model_experiments() -> list[dict]:
        return repository.latest_model_experiments()

    @app.get("/api/supervised-readiness")
    def supervised_readiness() -> dict:
        return ShadowModelComparisonService(config.phase5).supervised_readiness(repository)

    @app.post("/api/admin/labels", status_code=201)
    def create_label(payload: LabelRequest, x_api_key: str | None = Header(default=None)) -> dict:
        _require_admin(config, x_api_key)
        _assert_group(config, payload.group_id)
        label = OperationalLabel(
            group_id=payload.group_id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            label_type=payload.label_type,
            note=payload.note,
            created_at=datetime.now(timezone.utc),
        )
        repository.create_operational_label(label)
        return label.model_dump(mode="json")

    @app.get("/api/alarms")
    def alarms(group_id: str | None = None, status: str | None = None) -> list[dict]:
        if group_id:
            _assert_group(config, group_id)
        if status and status not in {"OPEN", "RESOLVED"}:
            raise HTTPException(status_code=422, detail="Alarm status must be OPEN or RESOLVED")
        return repository.list_alarms(group_id, status)

    @app.get("/api/alarms/active")
    def active_alarms() -> list[dict]:
        return repository.list_alarms(status="OPEN")

    @app.get("/", response_class=HTMLResponse)
    def overview() -> str:
        cards = _group_cards(repository, config)
        active_alarms = repository.list_alarms(status="OPEN")
        analysis_by_group = repository.latest_analysis_by_group()
        return _page(
            "Visão geral",
            f"<section><h2>Alarmes ativos ({len(active_alarms)})</h2>{_active_alarms_html(active_alarms, repository, config)}</section>"
            f"<section><h2>Principais desvios e incrementos em observação</h2>"
            f"<p class='hint'>Sinais estatísticos mais recentes. Eles só se tornam alarmes após as regras compostas e a persistência configuradas.</p>"
            f"{_deviations_html(_current_deviations(analysis_by_group))}</section>"
            f"{_health_summary_html(_health_summary(cards, active_alarms, repository.latest_acquisition(), config))}"
            f"<section class='group-overview'><h2>Visão operacional por grupo</h2><p class='hint'>Resumo atual da coleta, qualidade e risco. Abra um grupo para explorar as métricas.</p>"
            f"<div class='grid'>{''.join(_card_html(card) for card in cards)}</div></section>",
        )

    @app.get("/groups/{group_id}", response_class=HTMLResponse)
    def detail(group_id: str) -> str:
        _assert_group(config, group_id)
        card = next(card for card in _group_cards(repository, config) if card["group_id"] == group_id)
        metric_rows = repository.metric_history(group_id)
        metrics_html = _metrics_html(metric_rows, config)
        alarms_html = _alarms_html(repository.list_alarms(group_id), config)
        return _page(
            f"{group_id} — detalhe",
            f"<div class='detail-hero'>{_card_html(card)}</div>"
            f"<section><h2>Métricas recentes</h2><p class='hint'>Use a busca, os filtros e os títulos das colunas para explorar os dados.</p>"
            f"{_metric_highlights_html(metric_rows, config)}{metrics_html}</section>"
            f"<section><h2>Alarmes</h2>{alarms_html}</section>",
        )

    return app


class LabelRequest(BaseModel):
    group_id: str
    started_at: datetime
    ended_at: datetime | None = None
    label_type: str = Field(min_length=1, max_length=100)
    note: str | None = Field(default=None, max_length=2000)


def _require_admin(config: AppConfig, supplied_key: str | None) -> None:
    expected_key = os.getenv(config.api.admin_api_key_env)
    if not expected_key:
        raise HTTPException(status_code=503, detail="Administrative API is not configured")
    if not supplied_key or supplied_key != expected_key:
        raise HTTPException(status_code=403, detail="Administrative API authentication failed")


def _assert_group(config: AppConfig, group_id: str) -> None:
    if group_id not in {group.group_id for group in config.server_groups}:
        raise HTTPException(status_code=404, detail="Unknown logical group")


def _group_cards(repository: SqliteRepository, config: AppConfig) -> list[dict]:
    states = {row["group_id"]: row for row in repository.latest_state_cards()}
    analysis_by_group = repository.latest_analysis_by_group()
    open_alarm_count = {group.group_id: 0 for group in config.server_groups}
    for alarm in repository.list_alarms():
        if alarm["status"] == "OPEN":
            open_alarm_count[alarm["group_id"]] += 1
    now = datetime.now(timezone.utc)
    cards: list[dict] = []
    for group in config.server_groups:
        state = states.get(group.group_id)
        analysis = analysis_by_group.get(group.group_id, {})
        runtime = state["runtime"] if state else {}
        source_timestamp = runtime.get("previous_source_timestamp")
        age_seconds = None
        if source_timestamp:
            timestamp = datetime.fromisoformat(source_timestamp)
            age_seconds = max(0, int((now - timestamp).total_seconds()))
        cards.append(
            {
                "group_id": group.group_id,
                "display_name": "/".join(group.physical_servers),
                "state": state["state"] if state else "INITIALIZING",
                "state_label": _state_label(state["state"] if state else "INITIALIZING"),
                "acquisition_state": state["state"] if state else "INITIALIZING",
                "last_valid_collection": source_timestamp,
                "last_valid_collection_label": _format_timestamp(source_timestamp, config.pi_system.timezone),
                "data_age_seconds": age_seconds,
                "session_id": runtime.get("session_id"),
                "uptime": runtime.get("previous_metrics", {}).get("E3Run.UpTimeMinutes"),
                "risk_index": analysis.get("risk_index"),
                "analysis_confidence": analysis.get("confidence", state["confidence"] if state else 0),
                "baseline_ready": analysis.get("baseline_ready", False),
                "quality_ratio": runtime.get("last_quality_ratio", 0),
                "active_alarms": open_alarm_count[group.group_id],
                "possible_switchover": state is not None and state["state"] in {"SWITCHOVER_SUSPECTED", "POST_SWITCHOVER_STABILIZING"},
                "e3server_status": runtime.get("previous_metrics", {}).get("E3Server.Status"),
                "active_physical_server": "unknown",
            }
        )
    return cards


def _health_summary(
    cards: list[dict], active_alarms: list[dict], latest_acquisition: dict | None, config: AppConfig
) -> dict:
    critical_states = {"ACQUISITION_FAILURE", "APPLICATION_UNAVAILABLE"}
    critical_alarm_groups = {alarm["group_id"] for alarm in active_alarms if alarm["severity"] == "critical"}
    critical_groups = [card for card in cards if card["state"] in critical_states or card["group_id"] in critical_alarm_groups]
    attention_groups = [
        card
        for card in cards
        if card not in critical_groups
        and (
            card["state"] != "ACTIVE_COLLECTING"
            or card["data_age_seconds"] is None
            or card["data_age_seconds"] > config.acquisition.delayed_after_seconds
            or card["active_alarms"] > 0
        )
    ]
    healthy_groups = [card for card in cards if card not in critical_groups and card not in attention_groups]
    if not cards:
        status, label = "unknown", "Aguardando a primeira aquisição"
    elif critical_groups:
        status, label = "critical", "Ação necessária"
    elif attention_groups:
        status, label = "attention", "Requer acompanhamento"
    else:
        status, label = "healthy", "Operação saudável"
    acquisition_ok = bool(latest_acquisition and latest_acquisition["success"])
    acquisition_time = _format_timestamp(
        latest_acquisition["acquired_at"] if latest_acquisition else None, config.pi_system.timezone
    )
    return {
        "status": status,
        "label": label,
        "total_groups": len(cards),
        "healthy_groups": len(healthy_groups),
        "attention_groups": len(attention_groups),
        "critical_groups": len(critical_groups),
        "active_alarms": len(active_alarms),
        "acquisition": "Concluída" if acquisition_ok else "Sem aquisição bem-sucedida recente",
        "acquisition_time": acquisition_time,
    }


def _current_deviations(analysis_by_group: dict[str, dict]) -> list[dict]:
    deviations: list[dict] = []
    for group_id, analysis in analysis_by_group.items():
        for signal in analysis.get("signals", []):
            if not (signal["high_anomaly"] or signal["rising_trend"]):
                continue
            deviations.append({"group_id": group_id, **signal})
    return sorted(
        deviations,
        key=lambda signal: (
            not signal["high_anomaly"],
            -abs(float(signal["robust_z_score"])),
            -abs(float(signal["trend_relative_per_hour"] or 0)),
        ),
    )[:12]


def _card_html(card: dict) -> str:
    risk = card["risk_index"]
    risk_text = f"{risk} / 100" if risk is not None else "Aguardando baseline"
    risk_class = "risk-high" if isinstance(risk, int) and risk >= 60 else "risk-attention" if isinstance(risk, int) and risk >= 30 else "risk-normal"
    key_items = [
        ("Última leitura válida", card["last_valid_collection_label"], ""),
        ("Idade dos dados", _format_age(card["data_age_seconds"]), ""),
        ("Risco atual", risk_text, risk_class),
        ("Qualidade dos dados", f"{card['quality_ratio']:.0%}", ""),
        ("Baseline", "Pronta" if card["baseline_ready"] else "Em formação", ""),
        ("Alarmes ativos", card["active_alarms"], "risk-attention" if card["active_alarms"] else ""),
        ("Tempo ligado", _format_measurement(card["uptime"]) if card["uptime"] is not None else "Indisponível", ""),
        ("Confiança da análise", f"{card['analysis_confidence']:.0%}", ""),
    ]
    detail = "".join(
        f"<div class='group-stat {style}'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"
        for label, value, style in key_items
    )
    context = (
        f"<p class='group-context'>Servidor ativo: <strong>não identificado pelas tags disponíveis</strong>"
        f" · Estado E3Server: <strong>{escape(str(card['e3server_status'])) if card['e3server_status'] is not None else 'não informado'}</strong>"
        f" · Troca de servidor: <strong>{'em investigação' if card['possible_switchover'] else 'não indicada'}</strong></p>"
    )
    state_class = escape(card["state"].lower().replace("_", "-"))
    return (
        f"<article class='card group-card'><div class='card-title'><div><span class='group-id'>{escape(card['group_id'])}</span><h2>{escape(card['display_name'])}</h2></div>"
        f"<span class='state-chip {state_class}'>{escape(card['state_label'])}</span></div><div class='group-stats'>{detail}</div>{context}"
        f"<a class='group-link' href='/groups/{escape(card['group_id'])}'>Ver métricas e alarmes →</a></article>"
    )


def _metrics_html(rows: list[dict], config: AppConfig) -> str:
    if not rows:
        return "<p class='empty-state'>Nenhuma métrica adquirida.</p>"
    metric_options = "".join(
        f"<option value='{escape(metric)}'>{escape(metric)}</option>" for metric in sorted({row["metric_suffix"] for row in rows})
    )
    body = "".join(
        f"<tr class='metric-row {_metric_limit_level(row, config)}' data-metric='{escape(row['metric_suffix'])}' data-quality='{escape(str(row['quality'] or 'Sem qualidade'))}' "
        f"data-valid='{str(bool(row['valid_for_analysis'])).lower()}' data-timestamp='{escape(str(row['pi_event_timestamp']))}' "
        f"data-value='{escape(str(row['converted_value']))}'>"
        f"<td>{escape(str(row['metric_suffix']))}</td>"
        f"<td>{escape(_format_timestamp(row['pi_event_timestamp'], config.pi_system.timezone))}</td>"
        f"<td>{escape(_format_measurement(row['converted_value']))}</td>"
        f"<td><span class='quality-chip {_quality_class(row['quality'])}'>{escape(_quality_label(row['quality']))}</span></td>"
        f"<td><span class='eligibility {'eligible' if row['valid_for_analysis'] else 'rejected'}'>{'Elegível' if row['valid_for_analysis'] else 'Fora da análise'}</span></td></tr>"
        for row in rows
    )
    return (
        "<div class='metrics-controls'>"
        "<label>Buscar <input id='metric-search' type='search' placeholder='Nome, valor ou qualidade'></label>"
        f"<label>Métrica <select id='metric-filter'><option value=''>Todas</option>{metric_options}</select></label>"
        "<label>Qualidade <select id='quality-filter'><option value=''>Todas</option><option value='Good'>Boa</option><option value='Bad'>Ruim</option></select></label>"
        "<label>Participação <select id='eligibility-filter'><option value=''>Todas</option><option value='true'>Elegíveis</option><option value='false'>Fora da análise</option></select></label>"
        "<output id='metric-count'></output></div>"
        "<div class='table-wrap'><table id='metrics-table'><thead><tr>"
        "<th><button data-sort='metric'>Métrica</button></th><th><button data-sort='timestamp'>Timestamp PI</button></th>"
        "<th><button data-sort='value'>Valor normalizado</button></th><th><button data-sort='quality'>Qualidade</button></th><th>Participação</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>{_metrics_script()}"
    )


def _metric_highlights_html(rows: list[dict], config: AppConfig) -> str:
    latest_by_metric: dict[str, dict] = {}
    for row in rows:
        latest_by_metric.setdefault(row["metric_suffix"], row)
    highlights = "".join(_metric_highlight(metric, row, config) for metric, row in sorted(latest_by_metric.items()))
    return f"<div class='metric-highlights'>{highlights}</div>"


def _metric_highlight(metric: str, row: dict, config: AppConfig) -> str:
    limit_text = _configured_limits_text(metric, config)
    level = _metric_limit_level(row, config)
    return (
        f"<article class='metric-highlight {level}' data-limits='{escape(limit_text)}' title='{escape(limit_text)}'>"
        f"<span>{escape(metric)}</span><strong>{escape(_format_measurement(row['converted_value']))}</strong>"
        f"<small>{escape(_quality_label(row['quality']))} · {'elegível' if row['valid_for_analysis'] else 'fora da análise'}</small></article>"
    )


def _metric_limit_level(row: dict, config: AppConfig) -> str:
    limit = config.analysis.operational_limits.get(row["metric_suffix"])
    value = row.get("converted_value")
    if limit is None or not isinstance(value, (int, float)) or isinstance(value, bool):
        return ""
    if float(value) > limit.critical_above:
        return "limit-critical"
    if float(value) > limit.attention_above:
        return "limit-attention"
    return ""


def _configured_limits_text(metric: str, config: AppConfig) -> str:
    limit = config.analysis.operational_limits.get(metric)
    if limit is None:
        return "Sem limite estático aprovado; monitoramento por baseline dinâmico."
    return (
        f"Limites configurados: normal até {_format_measurement(limit.normal_upper)} {limit.unit}; "
        f"atenção acima de {_format_measurement(limit.attention_above)} {limit.unit}; "
        f"crítico acima de {_format_measurement(limit.critical_above)} {limit.unit}."
    )


def _metrics_script() -> str:
    return """<script>
    (() => {
      const table = document.getElementById('metrics-table'); if (!table) return;
      const body = table.tBodies[0], rows = Array.from(body.rows);
      const search = document.getElementById('metric-search'), metric = document.getElementById('metric-filter');
      const quality = document.getElementById('quality-filter'), eligible = document.getElementById('eligibility-filter');
      const count = document.getElementById('metric-count');
      const filter = () => { const query = search.value.toLowerCase(); let visible = 0; rows.forEach(row => {
        const match = (!query || row.textContent.toLowerCase().includes(query)) && (!metric.value || row.dataset.metric === metric.value)
          && (!quality.value || row.dataset.quality === quality.value) && (!eligible.value || row.dataset.valid === eligible.value);
        row.hidden = !match; if (match) visible += 1;
      }); count.textContent = `${visible} de ${rows.length} medições`; };
      [search, metric, quality, eligible].forEach(control => control.addEventListener('input', filter));
      let ascending = {timestamp: false};
      table.querySelectorAll('[data-sort]').forEach(button => button.addEventListener('click', () => {
        const key = button.dataset.sort; ascending[key] = !ascending[key]; const direction = ascending[key] ? 1 : -1;
        rows.sort((left, right) => { const a = left.dataset[key], b = right.dataset[key];
          const compare = key === 'value' ? Number(a) - Number(b) : a.localeCompare(b); return compare * direction; });
        rows.forEach(row => body.appendChild(row)); filter();
      })); filter();
    })();</script>"""


def _alarms_html(rows: list[dict], config: AppConfig) -> str:
    if not rows:
        return "<p>Não há alarmes registrados.</p>"
    body = "".join(
        f"<article class='alarm {escape(row['severity'])}'><strong>{escape(row['title'])}</strong>"
        f"<span>{escape(row['group_id'])} · {_alarm_status_label(row['status'])} · atualizado {_format_timestamp(row['updated_at'], config.pi_system.timezone)} · confiança {row['confidence']:.0%}</span>"
        f"<p>{escape(row['condition'])}</p><small>{escape('; '.join(row['evidence']))}</small></article>"
        for row in rows
    )
    return body


def _health_summary_html(summary: dict) -> str:
    items = [
        ("Grupos saudáveis", f"{summary['healthy_groups']}/{summary['total_groups']}"),
        ("Em acompanhamento", summary["attention_groups"]),
        ("Críticos", summary["critical_groups"]),
        ("Alarmes ativos", summary["active_alarms"]),
        ("Coleta PI", summary["acquisition"]),
        ("Horário da coleta", summary["acquisition_time"]),
    ]
    cards = "".join(
        f"<div class='health-item'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"
        for label, value in items
    )
    return (
        f"<section class='health {escape(summary['status'])}'><h2>Resumo de saúde do sistema</h2>"
        f"<p class='health-status'>{escape(summary['label'])}</p><div class='health-grid'>{cards}</div></section>"
    )


def _active_alarms_html(rows: list[dict], repository: SqliteRepository, config: AppConfig) -> str:
    if not rows:
        return "<p class='empty-state'>Nenhum alarme ativo. A monitoração continua avaliando a qualidade, os estados e os desvios estatísticos.</p>"
    ordered = sorted(rows, key=lambda alarm: alarm["updated_at"], reverse=True)
    body = "".join(_active_alarm_row(row, repository, config) for row in ordered)
    return (
        "<div class='table-wrap active-alarms-wrap'><table id='active-alarms-table'><thead><tr>"
        "<th><button class='sort-active' data-alarm-sort='updated'>Atualizado ↓</button></th><th><button data-alarm-sort='group'>Grupo</button></th>"
        "<th><button data-alarm-sort='severity'>Severidade</button></th><th><button data-alarm-sort='priority'>Prioridade</button></th>"
        "<th><button data-alarm-sort='diagnosis'>Diagnóstico</button></th><th><button data-alarm-sort='risk'>Risco</button></th><th>Medições recentes</th>"
        f"</tr></thead><tbody>{body}</tbody></table></div>{_active_alarms_script()}"
    )


def _active_alarm_row(alarm: dict, repository: SqliteRepository, config: AppConfig) -> str:
    priority = next((item.removeprefix("prioridade=") for item in alarm["evidence"] if item.startswith("prioridade=")), "não definida")
    measurements = "<br>".join(
        _recent_measurements_html(metric, repository.recent_metric_values(alarm["group_id"], metric), config)
        for metric in _alarm_metric_suffixes(alarm, config)
    )
    if not measurements:
        measurements = "<span class='hint'>Alarme de estado, sem métrica numérica.</span>"
    return (
        f"<tr class='alarm-row {escape(alarm['severity'])}' data-updated='{escape(alarm['updated_at'])}' data-group='{escape(alarm['group_id'])}' "
        f"data-severity='{escape(alarm['severity'])}' data-priority='{escape(priority)}' data-diagnosis='{escape(alarm['title'])}' "
        f"data-risk='{escape(str(alarm['risk_index'] if alarm['risk_index'] is not None else -1))}'>"
        f"<td>{escape(_format_timestamp(alarm['updated_at'], config.pi_system.timezone))}</td><td>{escape(alarm['group_id'])}</td>"
        f"<td><span class='severity-chip {escape(alarm['severity'])}'>{escape(_severity_label(alarm['severity']))}</span></td>"
        f"<td>{escape(priority.title())}</td><td><strong>{escape(alarm['title'])}</strong></td>"
        f"<td>{escape(str(alarm['risk_index'] if alarm['risk_index'] is not None else 'n/a'))}</td><td>{measurements}</td></tr>"
    )


def _active_alarms_script() -> str:
    return """<script>
    (() => { const table = document.getElementById('active-alarms-table'); if (!table) return;
      const body = table.tBodies[0], rows = Array.from(body.rows), ascending = {updated: false};
      table.querySelectorAll('[data-alarm-sort]').forEach(button => button.addEventListener('click', () => {
        const key = button.dataset.alarmSort; ascending[key] = !ascending[key]; const direction = ascending[key] ? 1 : -1;
        rows.sort((left, right) => { const a = left.dataset[key], b = right.dataset[key];
          const compare = key === 'risk' ? Number(a) - Number(b) : a.localeCompare(b); return compare * direction; });
        rows.forEach(row => body.appendChild(row));
        table.querySelectorAll('[data-alarm-sort]').forEach(item => { item.classList.remove('sort-active'); item.textContent = item.textContent.replace(/ [↑↓]$/, ''); });
        button.classList.add('sort-active'); button.textContent = button.textContent + ' ' + (ascending[key] ? '↑' : '↓');
      }));
    })();</script>"""


def _alarm_metric_suffixes(alarm: dict, config: AppConfig) -> list[str]:
    suffixes: list[str] = []
    for evidence in alarm["evidence"]:
        metric_suffix = evidence.split("=", 1)[0].strip()
        if metric_suffix in config.metric_catalog and metric_suffix not in suffixes:
            suffixes.append(metric_suffix)
    return suffixes


def _recent_measurements_html(metric_suffix: str, measurements: list[dict], config: AppConfig) -> str:
    if not measurements:
        return f"<p><strong>{escape(metric_suffix)}</strong>: sem medições numéricas elegíveis recentes.</p>"
    unit = config.metric_catalog.get(metric_suffix)
    unit_label = unit.unit if unit else None
    values = " · ".join(
        f"{_format_measurement(item['value'])}{f' {unit_label}' if unit_label else ''}" for item in measurements
    )
    return f"<p><strong>{escape(metric_suffix)}</strong>: {values}</p>"


def _format_timestamp(value: str | datetime | None, timezone_name: str) -> str:
    if value is None:
        return "indisponível"
    timestamp = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    local_time = timestamp.astimezone(ZoneInfo(timezone_name))
    return local_time.strftime("%d/%m/%Y - %H:%M:%S")


def _format_age(value: int | None) -> str:
    if value is None:
        return "indisponível"
    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes} min"
    if minutes:
        return f"{minutes} min {seconds} s"
    return f"{seconds} s"


def _state_label(state: str) -> str:
    return {
        "INITIALIZING": "Inicializando coleta",
        "ACTIVE_COLLECTING": "Coleta ativa",
        "STALE": "Dados desatualizados",
        "SWITCHOVER_SUSPECTED": "Possível troca de servidor",
        "POST_SWITCHOVER_STABILIZING": "Estabilizando após troca",
        "ACQUISITION_FAILURE": "Falha na coleta PI",
        "APPLICATION_UNAVAILABLE": "Aplicação possivelmente indisponível",
        "UNKNOWN": "Estado desconhecido",
    }.get(state, state.replace("_", " ").title())


def _quality_label(quality: str | None) -> str:
    return {"Good": "Boa", "Bad": "Ruim"}.get(quality, quality or "Não informada")


def _quality_class(quality: str | None) -> str:
    return {"Good": "good", "Bad": "bad"}.get(quality, "unknown")


def _alarm_status_label(status: str) -> str:
    return {"OPEN": "Ativo", "RESOLVED": "Resolvido"}.get(status, status.title())


def _severity_label(severity: str) -> str:
    return {"critical": "Crítico", "warning": "Atenção", "info": "Informativo"}.get(severity, severity.title())


def _expected_range(lower_bound: float, upper_bound: float) -> str:
    return f"{_format_measurement(max(0.0, float(lower_bound)))} à {_format_measurement(upper_bound)}"


def _format_measurement(value: object) -> str:
    """Render numerical values without scientific notation, using pt-BR separators."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return str(value)
    numeric_value = float(value)
    if not isfinite(numeric_value):
        return str(value)
    rendered = f"{numeric_value:,.6f}".rstrip("0").rstrip(".")
    if rendered == "-0":
        rendered = "0"
    return rendered.replace(",", "X").replace(".", ",").replace("X", ".")


def _deviations_html(rows: list[dict]) -> str:
    if not rows:
        return "<p class='empty-state'>Nenhum desvio ou tendência anormal identificado na última análise elegível.</p>"
    body = "".join(
        "<tr>"
        f"<td>{escape(row['group_id'])}</td><td>{escape(row['metric_suffix'])}</td>"
        f"<td>{escape(_signal_status(row))}</td><td>{_format_measurement(row['value'])}</td>"
        f"<td>{_expected_range(row['lower_bound'], row['upper_bound'])}</td>"
        f"<td>{_trend_text(row['trend_relative_per_hour'])}</td>"
        "</tr>"
        for row in rows
    )
    return (
        "<table><thead><tr><th>Grupo</th><th>Métrica</th><th>Sinal</th><th>Valor atual</th>"
        "<th>Faixa esperada</th><th>Tendência</th></tr></thead><tbody>"
        f"{body}</tbody></table>"
    )


def _signal_status(signal: dict) -> str:
    if signal["high_anomaly"] and signal["rising_trend"]:
        return "Acima da faixa e em elevação"
    if signal["high_anomaly"]:
        return "Acima da faixa esperada"
    return "Incremento anormal"


def _trend_text(value: float | None) -> str:
    return f"{value:.1%}/h" if value is not None else "sem janela suficiente"


def _page(title: str, content: str) -> str:
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <meta http-equiv='refresh' content='30'><title>{escape(title)}</title>
    <style>
    body{{font-family:Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top,#173653 0,#0c1622 42rem);color:#e8eef5;max-width:1360px;margin:auto;padding:24px}}
    header{{padding:12px 2px 6px;border-bottom:1px solid #2a425a}} h1,h2,h3{{color:#fff}} h1{{margin-bottom:6px}} h2{{margin-top:0}} a{{color:#9fd4ff;text-decoration:none}} a:hover{{text-decoration:underline}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:16px}}
    .card,section,.alarm{{background:linear-gradient(145deg,#162b42,#102033);border:1px solid #2a425a;border-radius:14px;padding:18px;margin:18px 0;box-shadow:0 10px 24px #050b121f}}
    .card{{transition:transform .15s,border-color .15s}} .card:hover{{transform:translateY(-2px);border-color:#4d7fa7}} .card-title{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}} .card-title h2{{font-size:1.1rem;margin:3px 0 14px}} .group-id{{color:#9fd4ff;font-size:.78rem;font-weight:700;letter-spacing:.03em}} .group-card{{margin:0}} .group-stats{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}} .group-stat{{background:#0c1622;border:1px solid #233e58;border-radius:9px;padding:9px}} .group-stat span{{display:block;color:#a8bacb;font-size:.75rem}} .group-stat strong{{display:block;margin-top:4px;font-size:.95rem}} .group-stat.risk-normal{{border-left:3px solid #4bc980}} .group-stat.risk-attention{{border-left:3px solid #e6b34a}} .group-stat.risk-high{{border-left:3px solid #ef6767}} .group-context{{color:#b9cbe0;font-size:.78rem;line-height:1.45;margin:13px 0 10px}} .group-link{{display:inline-block;font-size:.85rem;font-weight:700}} .group-overview{{margin-bottom:28px}}
    .health{{border-left:5px solid #60b9e8}} .health.healthy{{border-left-color:#4bc980}} .health.attention{{border-left-color:#e6b34a}} .health.critical{{border-left-color:#ef6767}}
    .health-status{{font-size:1.2rem;font-weight:600;margin:0 0 14px}} .health-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}} .health-item{{background:#0c1622;border-radius:10px;padding:13px}} .health-item span{{display:block;color:#a8bacb;font-size:.82rem}} .health-item strong{{display:block;margin-top:5px;font-size:1.05rem}}
    dl{{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:0}} dt{{color:#a8bacb;font-size:.86rem}} dd{{margin:0;overflow-wrap:anywhere;font-weight:600}} .state-chip,.quality-chip,.eligibility{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:.78rem;font-weight:700;white-space:nowrap}} .state-chip{{background:#274965;color:#d7edff}} .state-chip.active-collecting{{background:#164c38;color:#a7f3d0}} .state-chip.stale,.state-chip.switchover-suspected,.state-chip.post-switchover-stabilizing{{background:#614912;color:#ffe49c}} .state-chip.acquisition-failure,.state-chip.application-unavailable{{background:#622d36;color:#ffc9cf}}
    .table-wrap{{overflow:auto;border:1px solid #2a425a;border-radius:10px;max-height:580px}} table{{width:100%;border-collapse:collapse;font-size:.9rem}} th,td{{padding:10px;text-align:left;border-bottom:1px solid #2a425a;white-space:nowrap}} th{{position:sticky;top:0;background:#183149;z-index:1}} th button{{background:transparent;border:0;color:#e8eef5;font:inherit;font-weight:700;padding:0;cursor:pointer}} th button:hover{{color:#9fd4ff}} tbody tr:hover{{background:#1b3650}} .quality-chip.good,.eligibility.eligible{{background:#164c38;color:#a7f3d0}} .quality-chip.bad,.eligibility.rejected{{background:#622d36;color:#ffc9cf}} .quality-chip.unknown{{background:#3d4651;color:#e2e8f0}}
    .metric-highlight{{position:relative}} .metric-highlight[data-limits]::after{{content:attr(data-limits);position:absolute;z-index:3;left:0;right:0;bottom:calc(100% + 8px);padding:9px 10px;background:#07111c;border:1px solid #4d7fa7;border-radius:8px;color:#e8eef5;font-size:.78rem;line-height:1.35;opacity:0;visibility:hidden;pointer-events:none;transition:.15s;box-shadow:0 8px 20px #0008}} .metric-highlight:hover::after{{opacity:1;visibility:visible}} .metric-highlight.limit-attention{{background:#4d3912;border-color:#d5a737}} .metric-highlight.limit-critical{{background:#5a252e;border-color:#e86b78}} tr.limit-attention td{{background:#3f3118}} tr.limit-critical td{{background:#4e252d}} .severity-chip{{display:inline-block;border-radius:999px;padding:4px 9px;font-size:.78rem;font-weight:700}} .severity-chip.warning{{background:#614912;color:#ffe49c}} .severity-chip.critical{{background:#622d36;color:#ffc9cf}} .severity-chip.info{{background:#274965;color:#d7edff}}
    .alarm.warning{{border-left:5px solid #e6b34a}} .alarm.critical{{border-left:5px solid #ef6767}} .alarm.info{{border-left:5px solid #60b9e8}}
    .alarm span{{display:block;color:#a8bacb;margin-top:7px;font-size:.86rem}} .alarm-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}} .alarm-list .alarm{{margin:0}} .hint,.empty-state{{color:#a8bacb}} .metrics-controls{{display:flex;gap:10px;align-items:end;flex-wrap:wrap;margin:14px 0}} .metrics-controls label{{display:grid;gap:5px;color:#b9cbe0;font-size:.82rem;font-weight:600}} input,select{{background:#0c1622;color:#e8eef5;border:1px solid #385976;border-radius:7px;padding:8px;min-width:150px}} output{{color:#9fd4ff;font-weight:700;padding:8px 0}} .sort-status{{display:block;color:#9fd4ff;padding:0 0 10px}} .metric-highlights{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}} .metric-highlight{{padding:12px;background:#0c1622;border:1px solid #2a425a;border-radius:10px}} .metric-highlight span,.metric-highlight small{{display:block;color:#a8bacb;font-size:.78rem;overflow-wrap:anywhere}} .metric-highlight strong{{display:block;font-size:1.15rem;margin:6px 0}} .recent-measurements{{margin-top:14px;padding:10px 12px;background:#0c1622;border-radius:9px}} .recent-measurements h3{{font-size:.9rem;margin:0 0 7px}} .recent-measurements p{{margin:6px 0}} @media(max-width:600px){{body{{padding:12px}} dl{{grid-template-columns:1fr}} .card-title{{display:block}} .state-chip{{margin-bottom:10px}} .group-stats{{grid-template-columns:1fr}} .metrics-controls label,input,select{{width:100%;box-sizing:border-box}}}}
    </style></head><body><header><h1>E3 Predictive Monitor — Fase 2</h1><p>Dados PI, qualidade, redundância e análise estatística explicável. Sem machine learning.</p></header>{content}</body></html>"""
