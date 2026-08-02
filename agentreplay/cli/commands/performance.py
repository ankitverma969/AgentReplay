"""Performance, optimization, and benchmark commands for AgentReplay."""

from __future__ import annotations

import argparse
import json

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import PerformanceError, StorageError
from agentreplay.performance import BenchmarkCase, BenchmarkSuite, SQLiteOptimizer
from agentreplay.performance.reports import (
    render_benchmark_json,
    render_benchmark_summary,
    render_sqlite_report,
)
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register performance-related commands."""
    benchmark = subparsers.add_parser(
        "benchmark", help="Benchmark large trace workloads."
    )
    benchmark.add_argument(
        "--events", type=int, default=10_000, help="Synthetic event count."
    )
    benchmark.add_argument(
        "--chunk-size", type=int, default=5_000, help="Benchmark chunk size."
    )
    benchmark.add_argument("--json", action="store_true", help="Emit JSON output.")
    benchmark.add_argument("--db-path", help="Optional benchmark database path.")
    benchmark.set_defaults(handler=handle_benchmark)

    optimize = subparsers.add_parser(
        "optimize", help="Optimize the AgentReplay SQLite database."
    )
    optimize.add_argument(
        "--vacuum", action="store_true", help="Also vacuum the database."
    )
    optimize.add_argument("--json", action="store_true", help="Emit JSON output.")
    add_storage_argument(optimize)
    optimize.set_defaults(handler=handle_optimize)

    analyze = subparsers.add_parser(
        "analyze-db", help="Analyze AgentReplay database performance."
    )
    analyze.add_argument("--json", action="store_true", help="Emit JSON output.")
    add_storage_argument(analyze)
    analyze.set_defaults(handler=handle_analyze_db)

    vacuum = subparsers.add_parser(
        "vacuum", help="Vacuum the AgentReplay SQLite database."
    )
    vacuum.add_argument("--json", action="store_true", help="Emit JSON output.")
    add_storage_argument(vacuum)
    vacuum.set_defaults(handler=handle_vacuum)


def handle_benchmark(args: argparse.Namespace) -> int:
    """Handle the ``benchmark`` command."""
    try:
        result = BenchmarkSuite(db_path=args.db_path).run(
            BenchmarkCase(event_count=args.events, chunk_size=args.chunk_size)
        )
        write_line(
            render_benchmark_json(result)
            if args.json
            else render_benchmark_summary(result)
        )
    except (PerformanceError, StorageError, ValueError) as exc:
        write_line(f"agentreplay benchmark: {exc}")
        return 1
    return 0


def handle_optimize(args: argparse.Namespace) -> int:
    """Handle the ``optimize`` command."""
    return _with_sqlite(args, vacuum=args.vacuum, optimize=True)


def handle_analyze_db(args: argparse.Namespace) -> int:
    """Handle the ``analyze-db`` command."""
    return _with_sqlite(args, vacuum=False, optimize=False)


def handle_vacuum(args: argparse.Namespace) -> int:
    """Handle the ``vacuum`` command."""
    return _with_sqlite(args, vacuum=True, optimize=True)


def _with_sqlite(args: argparse.Namespace, *, vacuum: bool, optimize: bool) -> int:
    """Run a SQLite optimization command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        optimizer = SQLiteOptimizer(storage)
        report = optimizer.optimize(vacuum=vacuum) if optimize else optimizer.analyze()
        write_line(
            json.dumps(report.to_dict(), sort_keys=True)
            if args.json
            else render_sqlite_report(report)
        )
    except (PerformanceError, StorageError) as exc:
        command = "vacuum" if vacuum else "optimize" if optimize else "analyze-db"
        write_line(f"agentreplay {command}: {exc}")
        return 1
    finally:
        storage.close()
    return 0


__all__ = [
    "handle_analyze_db",
    "handle_benchmark",
    "handle_optimize",
    "handle_vacuum",
    "register",
]
