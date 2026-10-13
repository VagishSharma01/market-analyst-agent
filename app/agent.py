"""ReAct-style market analyst with OpenAI tool loop or deterministic mock."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.tools import get_company_news, get_stock_quote, run_tool, tool_catalog_json


@dataclass
class Step:
    thought: str
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    observation: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    query: str
    mode: str
    ticker: str | None
    steps: list[Step]
    report_markdown: str


def _extract_ticker(query: str) -> str | None:
    # Prefer explicit $TICKER or all-caps 1–5 letter tokens common for US equities
    m = re.search(r"\$([A-Za-z]{1,5})\b", query)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b([A-Z]{1,5})\b", query)
    if m and m.group(1) not in {"A", "I", "CEO", "USD", "API", "LLM"}:
        return m.group(1)
    # common lowercase mentions
    for tok in re.findall(r"\b([A-Za-z]{1,5})\b", query):
        if tok.lower() in {"aapl", "msft", "googl", "amzn", "tsla", "nvda", "meta", "infy", "tcs"}:
            return tok.upper()
    return None


def _mock_run(query: str) -> AgentResult:
    ticker = _extract_ticker(query) or "AAPL"
    steps: list[Step] = []

    steps.append(
        Step(
            thought=f"User asked about {ticker}. Fetch a live quote first.",
            tool="get_stock_quote",
            args={"ticker": ticker},
        )
    )
    quote = run_tool("get_stock_quote", {"ticker": ticker})
    steps[-1].observation = quote

    steps.append(
        Step(
            thought="Pull recent headlines for context beyond price.",
            tool="get_company_news",
            args={"ticker": ticker, "limit": 5},
        )
    )
    news = run_tool("get_company_news", {"ticker": ticker, "limit": 5})
    steps[-1].observation = news

    prices = []
    # synthesize a tiny series from quote for metrics demo when possible
    if isinstance(quote.get("previous_close"), (int, float)) and isinstance(quote.get("price"), (int, float)):
        prices = [float(quote["previous_close"]), float(quote["price"])]
        steps.append(
            Step(
                thought="Compute simple return stats from available closes.",
                tool="calculate_metrics",
                args={"prices": prices},
            )
        )
        metrics = run_tool("calculate_metrics", {"prices": prices})
        steps[-1].observation = metrics
    else:
        metrics = {"note": "insufficient price points"}

    headlines = news.get("headlines") or []
    hl_md = "\n".join(
        f"- {h.get('title')} _{h.get('publisher') or ''}_" for h in headlines[:5]
    ) or "- No headlines returned."

    err = quote.get("error")
    price_line = (
        f"**Error fetching quote:** `{err}`"
        if err
        else f"**Last price:** {quote.get('price')} {quote.get('currency') or ''} "
        f"({quote.get('change_pct')}% vs prior close) · {quote.get('exchange')}"
    )

    report = f"""# Investment briefing — {ticker}

**Query:** {query}

## Price snapshot
{price_line}

## Computed metrics
```json
{json.dumps(metrics, indent=2)}
```

## Recent headlines
{hl_md}

## Agent notes
- Mode: **mock / rule-based planner** (no LLM key required).
- Tools called: quote → news → metrics.
- This is research tooling, not financial advice.
"""
    steps.append(Step(thought="Compose structured investment briefing from tool outputs."))
    return AgentResult(query=query, mode="mock", ticker=ticker, steps=steps, report_markdown=report)


def _openai_run(query: str) -> AgentResult:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    tools_spec = [
        {
            "type": "function",
            "function": {
                "name": "get_stock_quote",
                "description": "Get latest stock quote for a ticker.",
                "parameters": {
                    "type": "object",
                    "properties": {"ticker": {"type": "string"}},
                    "required": ["ticker"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_company_news",
                "description": "Get recent news headlines for a ticker.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["ticker"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculate_metrics",
                "description": "Compute return/volatility from close prices.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prices": {"type": "array", "items": {"type": "number"}},
                    },
                    "required": ["prices"],
                },
            },
        },
    ]

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a careful market research agent. Use tools to gather live data, "
                "then write a concise markdown investment briefing. Not financial advice. "
                f"Available tools catalog:\n{tool_catalog_json()}"
            ),
        },
        {"role": "user", "content": query},
    ]

    steps: list[Step] = []
    ticker = _extract_ticker(query)

    for _ in range(6):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools_spec,
            tool_choice="auto",
            temperature=0.2,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                obs = run_tool(tc.function.name, args)
                if tc.function.name == "get_stock_quote" and args.get("ticker"):
                    ticker = str(args["ticker"]).upper()
                steps.append(
                    Step(
                        thought=msg.content or f"Call {tc.function.name}",
                        tool=tc.function.name,
                        args=args,
                        observation=obs,
                    )
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(obs),
                    }
                )
            continue

        report = msg.content or "_No report produced._"
        steps.append(Step(thought="Final report composed."))
        return AgentResult(
            query=query,
            mode="openai",
            ticker=ticker,
            steps=steps,
            report_markdown=report,
        )

    return AgentResult(
        query=query,
        mode="openai",
        ticker=ticker,
        steps=steps,
        report_markdown="_Stopped after max tool iterations._",
    )


def run_agent(query: str) -> AgentResult:
    force_mock = os.getenv("FORCE_MOCK", "0") == "1"
    has_key = bool(os.getenv("OPENAI_API_KEY"))
    if force_mock or not has_key:
        return _mock_run(query)
    try:
        return _openai_run(query)
    except Exception as exc:  # noqa: BLE001
        fallback = _mock_run(query)
        fallback.report_markdown = (
            f"> OpenAI path failed (`{exc}`); fell back to mock planner.\n\n"
            + fallback.report_markdown
        )
        fallback.mode = "mock-fallback"
        return fallback


# Keep imports used for typing clarity in tools module side effects
_ = (get_stock_quote, get_company_news)