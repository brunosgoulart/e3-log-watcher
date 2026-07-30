from __future__ import annotations

import argparse
import threading
from datetime import datetime

import uvicorn

from app.acquisition.pi_af_sdk import PiAfSdkClient
from app.acquisition.simulated import SimulatedPiClient
from app.config.loader import load_config
from app.dashboard.app import create_dashboard_app
from app.monitoring.service import ContinuousAcquisitionRunner, MonitoringService
from app.observability.logging import configure_logging
from app.storage.sqlite import SqliteRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="E3 predictive monitor - Phase 1")
    parser.add_argument("--config", default="configs/phase1.yaml")
    parser.add_argument("--simulate", action="store_true", help="Use clearly identified synthetic PI data")
    parser.add_argument("--once", action="store_true", help="Execute one current-value acquisition")
    parser.add_argument("--historical-start", help="ISO-8601 start for a historical import")
    parser.add_argument("--historical-end", help="ISO-8601 end for a historical import")
    parser.add_argument("--serve", action="store_true", help="Run acquisition worker and the local dashboard")
    args = parser.parse_args()

    config = load_config(args.config)
    logger = configure_logging(config.logging.level)
    repository = SqliteRepository(config.storage.sqlite_path)
    client = SimulatedPiClient(config) if args.simulate else PiAfSdkClient(config)
    service = MonitoringService(config, client, repository, logger)

    if args.historical_start or args.historical_end:
        if not (args.historical_start and args.historical_end):
            parser.error("--historical-start and --historical-end must be supplied together")
        service.import_historical(datetime.fromisoformat(args.historical_start), datetime.fromisoformat(args.historical_end))
    if args.once:
        service.run_once()
    if args.serve:
        stop_event = threading.Event()
        runner = ContinuousAcquisitionRunner(service, config.acquisition.online_interval_seconds)
        thread = threading.Thread(target=runner.run, args=(stop_event,), daemon=True)
        thread.start()
        try:
            uvicorn.run(create_dashboard_app(repository, config), host="127.0.0.1", port=8080)
        finally:
            stop_event.set()
    elif not args.once and not args.historical_start:
        parser.error("choose --once, historical import, or --serve")


if __name__ == "__main__":
    main()
