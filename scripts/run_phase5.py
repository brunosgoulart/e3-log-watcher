from __future__ import annotations

import argparse
import json

from app.config.loader import load_config
from app.phase5.service import PhaseFiveUnavailable, ShadowModelComparisonService
from app.storage.sqlite import SqliteRepository


def main() -> None:
    parser = argparse.ArgumentParser(description="Run controlled Phase 5 shadow comparison")
    parser.add_argument("--config", default="configs/phase1.yaml")
    args = parser.parse_args()
    config = load_config(args.config)
    repository = SqliteRepository(config.storage.sqlite_path)
    try:
        service = ShadowModelComparisonService(config.phase5)
        reports, results = service.run(repository)
        print(json.dumps({"quality_reports": [report.model_dump(mode="json") for report in reports], "experiments": [result.model_dump(mode="json") for result in results], "supervised_readiness": service.supervised_readiness(repository)}, ensure_ascii=False, indent=2))
    except PhaseFiveUnavailable as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        repository.close()


if __name__ == "__main__":
    main()
