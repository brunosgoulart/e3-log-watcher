"""Run a reproducible, chronological backtest from validated JSON samples."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.backtesting.service import BacktestSample, BacktestService
from app.config.loader import load_config
from app.detection.service import PhaseTwoAnalysisService
from app.domain.models import GroupObservation, RedundancyState
from app.reporting.service import backtest_markdown_report
from app.storage.sqlite import SqliteRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="E3 monitor chronological backtest")
    parser.add_argument("samples", help="Path to a JSON array of synthetic or exported samples")
    parser.add_argument("--config", default="configs/phase1.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    payload = json.loads(Path(args.samples).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Backtest file must contain a JSON array")
    samples = [
        BacktestSample(
            group_id=item["group_id"],
            session_id=item["session_id"],
            state=RedundancyState(item["state"]),
            observation=GroupObservation.model_validate(item["observation"]),
        )
        for item in payload
    ]
    run = BacktestService(config.backtesting, PhaseTwoAnalysisService(config.analysis)).run(samples)
    repository = SqliteRepository(config.storage.sqlite_path)
    try:
        repository.record_backtest_run(
            run.run_id,
            run.started_at,
            run.ended_at,
            {"backtesting": config.backtesting.model_dump(mode="json"), "analysis": config.analysis.model_dump(mode="json")},
            run.summary,
        )
        repository.record_backtest_events(run.run_id, run.events)
    finally:
        repository.close()
    print(backtest_markdown_report(run))


if __name__ == "__main__":
    main()
