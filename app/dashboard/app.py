from __future__ import annotations

import os
from datetime import datetime, timezone
from html import escape

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
    def alarms(group_id: str | None = None) -> list[dict]:
        if group_id:
            _assert_group(config, group_id)
        return repository.list_alarms(group_id)

    @app.get("/", response_class=HTMLResponse)
    def overview() -> str:
        cards = "".join(_card_html(card) for card in _group_cards(repository, config))
        alarms_html = _alarms_html(repository.list_alarms())
        return _page("Visão geral", f"<section class='grid'>{cards}</section><section><h2>Alarmes textuais</h2>{alarms_html}</section>")

    @app.get("/groups/{group_id}", response_class=HTMLResponse)
    def detail(group_id: str) -> str:
        _assert_group(config, group_id)
        card = next(card for card in _group_cards(repository, config) if card["group_id"] == group_id)
        metrics_html = _metrics_html(repository.metric_history(group_id))
        alarms_html = _alarms_html(repository.list_alarms(group_id))
        return _page(
            f"{group_id} — detalhe",
            f"{_card_html(card)}<section><h2>Métricas recentes</h2>{metrics_html}</section>"
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
                "acquisition_state": state["state"] if state else "INITIALIZING",
                "last_valid_collection": source_timestamp,
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


def _card_html(card: dict) -> str:
    items = [
        ("Estado", card["state"]),
        ("Última atualização PI válida", card["last_valid_collection"] or "indisponível"),
        ("Idade dos dados", f"{card['data_age_seconds']} s" if card["data_age_seconds"] is not None else "indisponível"),
        ("Sessão", card["session_id"] or "não iniciada"),
        ("Uptime", card["uptime"] if card["uptime"] is not None else "indisponível"),
        ("Risco", card["risk_index"] if card["risk_index"] is not None else "baseline ainda insuficiente"),
        ("Baseline", "pronta" if card["baseline_ready"] else "aguardando amostras válidas"),
        ("Confiança", f"{card['analysis_confidence']:.0%}"),
        ("Qualidade", f"{card['quality_ratio']:.0%}"),
        ("Alarmes ativos", card["active_alarms"]),
        ("Possível switchover", "sim" if card["possible_switchover"] else "não"),
        ("Estado E3Server", card["e3server_status"] or "desconhecido"),
        ("Servidor físico ativo", "desconhecido"),
    ]
    detail = "".join(f"<dt>{escape(str(label))}</dt><dd>{escape(str(value))}</dd>" for label, value in items)
    return f"<article class='card'><h2><a href='/groups/{escape(card['group_id'])}'>{escape(card['display_name'])}</a></h2><dl>{detail}</dl></article>"


def _metrics_html(rows: list[dict]) -> str:
    if not rows:
        return "<p>Nenhuma métrica adquirida.</p>"
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row[key]))}</td>" for key in ("metric_suffix", "pi_event_timestamp", "converted_value", "quality", "valid_for_analysis")) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr><th>Métrica</th><th>Timestamp PI</th><th>Valor normalizado</th><th>Qualidade</th><th>Elegível</th></tr></thead><tbody>" + body + "</tbody></table>"


def _alarms_html(rows: list[dict]) -> str:
    if not rows:
        return "<p>Não há alarmes registrados.</p>"
    body = "".join(
        f"<article class='alarm {escape(row['severity'])}'><strong>{escape(row['title'])}</strong>"
        f"<span>{escape(row['group_id'])} · {escape(row['status'])} · confiança {row['confidence']:.0%}</span>"
        f"<p>{escape(row['condition'])}</p><small>{escape('; '.join(row['evidence']))}</small></article>"
        for row in rows
    )
    return body


def _page(title: str, content: str) -> str:
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <meta http-equiv='refresh' content='30'><title>{escape(title)}</title>
    <style>
    body{{font-family:Segoe UI,Arial,sans-serif;background:#0c1622;color:#e8eef5;max-width:1280px;margin:auto;padding:24px}}
    h1,h2{{color:#fff}} a{{color:#9fd4ff}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(285px,1fr));gap:16px}}
    .card,section,.alarm{{background:#132438;border:1px solid #2a425a;border-radius:10px;padding:16px;margin:16px 0}}
    dl{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0}} dt{{color:#a8bacb}} dd{{margin:0;overflow-wrap:anywhere}}
    table{{width:100%;border-collapse:collapse;font-size:.9rem}} th,td{{padding:8px;text-align:left;border-bottom:1px solid #2a425a}}
    .alarm.warning{{border-left:5px solid #e6b34a}} .alarm.critical{{border-left:5px solid #ef6767}} .alarm.info{{border-left:5px solid #60b9e8}}
    .alarm span{{display:block;color:#a8bacb;margin-top:6px}} @media(max-width:600px){{body{{padding:12px}} dl{{grid-template-columns:1fr}} table{{display:block;overflow-x:auto}}}}
    </style></head><body><header><h1>E3 Predictive Monitor — Fase 2</h1><p>Dados PI, qualidade, redundância e análise estatística explicável. Sem machine learning.</p></header>{content}</body></html>"""
