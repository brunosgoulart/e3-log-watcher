from __future__ import annotations

from app.backtesting.service import BacktestRun


def backtest_markdown_report(run: BacktestRun) -> str:
    summary = run.summary
    lines = [
        "# Relatório de backtesting",
        "",
        f"Período: {run.started_at.isoformat()} a {run.ended_at.isoformat()}",
        f"Amostras: {summary['samples']} (elegíveis: {summary['eligible_samples']})",
        f"Alarmes: {summary['alarms']}",
        "",
        "## Alarmes por regra",
    ]
    lines.extend(f"- {rule}: {count}" for rule, count in summary["alarms_by_rule"].items())
    lines.extend(["", "## Limitações"])
    lines.extend(f"- {item}" for item in summary["limitations"])
    return "\n".join(lines)
