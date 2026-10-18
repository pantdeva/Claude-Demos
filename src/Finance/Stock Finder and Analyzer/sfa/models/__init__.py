"""Milestone 2: which forecasting model works best where, and growth predictions."""

from __future__ import annotations


def run_all(con, jobs: int | None = None, only: list[int] | None = None, log=print) -> dict:
    from . import leaderboard, portfolio, predict, report, walkforward
    out = {"walk_forward": walkforward.run(con, jobs=jobs, only=only, log=log)}
    out["leaderboard"] = leaderboard.build(con, log=log)
    if only is None:
        out["portfolio"] = portfolio.run(con, log=log)
    out["predictions"] = predict.run(con, jobs=jobs, log=log)
    out["export"] = report.export(con)
    return out
