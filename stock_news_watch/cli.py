from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

from .config import AppConfig, default_config_path
from .dashboard import serve_dashboard
from .engine import StockNewsWatchEngine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stock_news_watch", description="Codex-powered stock news watch demo")
    parser.add_argument("--config", default=str(default_config_path()), help="Path to the config JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Initialize runtime files")
    sub.add_parser("run-once", help="Run one monitoring cycle")
    sub.add_parser("status", help="Print current status JSON")

    p_loop = sub.add_parser("loop", help="Run the monitoring loop")
    p_loop.add_argument("--once", action="store_true", help="Run a single iteration and exit")

    sub.add_parser("serve", help="Run the dashboard server")
    p_demo = sub.add_parser("demo", help="Run the loop and dashboard together")
    p_demo.add_argument("--once", action="store_true", help="Run a single loop iteration then keep serving")

    return parser


def load_engine(config_path: str | Path) -> StockNewsWatchEngine:
    return StockNewsWatchEngine(AppConfig.from_file(Path(config_path)))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    engine = load_engine(args.config)

    if args.command == "init":
        print(json.dumps(engine.snapshot(), ensure_ascii=True, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(engine.snapshot(), ensure_ascii=True, indent=2))
        return 0

    if args.command == "run-once":
        snap = engine.run_cycle(force=True)
        print(json.dumps(snap, ensure_ascii=True, indent=2))
        return 0

    if args.command == "loop":
        if args.once:
            print(json.dumps(engine.run_cycle(force=False), ensure_ascii=True, indent=2))
            return 0
        print("starting loop; use STOP file in .runtime to stop")
        engine.run_forever()
        return 0

    if args.command == "serve":
        server = serve_dashboard(engine, engine.config.dashboard.host, engine.config.dashboard.port)
        print(f"dashboard listening on http://{engine.config.dashboard.host}:{engine.config.dashboard.port}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.shutdown()
        return 0

    if args.command == "demo":
        server = serve_dashboard(engine, engine.config.dashboard.host, engine.config.dashboard.port)
        print(f"dashboard listening on http://{engine.config.dashboard.host}:{engine.config.dashboard.port}")
        if args.once:
            engine.run_cycle(force=True)
        else:
            loop_thread = threading.Thread(target=engine.run_forever, name="stock_news_watch_loop", daemon=True)
            loop_thread.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            server.shutdown()
            engine.paths.stop_file.write_text("stop", encoding="utf-8")
        return 0

    raise RuntimeError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
