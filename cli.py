#!/usr/bin/env python3
"""CLI entry: python cli.py \"Analyze MSFT\""""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.agent import run_agent  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Market Analyst Agent CLI")
    p.add_argument("query", nargs="?", default="Analyze AAPL for a quick investment briefing")
    p.add_argument("--json", action="store_true", help="Print full JSON trace")
    args = p.parse_args()
    result = run_agent(args.query)
    if args.json:
        print(
            json.dumps(
                {
                    "mode": result.mode,
                    "ticker": result.ticker,
                    "steps": [
                        {
                            "thought": s.thought,
                            "tool": s.tool,
                            "args": s.args,
                            "observation": s.observation,
                        }
                        for s in result.steps
                    ],
                    "report_markdown": result.report_markdown,
                },
                indent=2,
            )
        )
    else:
        print(result.report_markdown)


if __name__ == "__main__":
    main()