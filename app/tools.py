"""Deterministic tools the agent can call."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx


def get_stock_quote(ticker: str) -> dict[str, Any]:
    """Fetch a live (or best-effort) quote via Yahoo Finance chart API."""
    symbol = ticker.strip().upper()
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    headers = {"User-Agent": "market-analyst-agent/1.0"}
    try:
        with httpx.Client(timeout=12.0, headers=headers) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        prev = closes[-2] if len(closes) >= 2 else meta.get("previousClose")
        price = meta.get("regularMarketPrice") or (closes[-1] if closes else None)
        change_pct = None
        if price is not None and prev:
            change_pct = round(((price - prev) / prev) * 100, 2)
        return {
            "ticker": symbol,
            "price": price,
            "currency": meta.get("currency"),
            "exchange": meta.get("exchangeName"),
            "previous_close": prev,
            "change_pct": change_pct,
            "instrument": meta.get("instrumentType"),
            "as_of": datetime.now(timezone.utc).isoformat(),
            "source": "yahoo-finance-chart",
        }
    except Exception as exc:  # noqa: BLE001 — tool must never crash the agent
        return {"ticker": symbol, "error": str(exc), "source": "yahoo-finance-chart"}


def get_company_news(ticker: str, limit: int = 5) -> dict[str, Any]:
    """Fetch recent headlines for a ticker (Yahoo search RSS-less JSON endpoint)."""
    symbol = ticker.strip().upper()
    url = "https://query1.finance.yahoo.com/v1/finance/search"
    params = {"q": symbol, "newsCount": limit, "quotesCount": 1}
    headers = {"User-Agent": "market-analyst-agent/1.0"}
    try:
        with httpx.Client(timeout=12.0, headers=headers) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
        news = []
        for item in (data.get("news") or [])[:limit]:
            news.append(
                {
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "link": item.get("link"),
                    "published": item.get("providerPublishTime"),
                }
            )
        return {"ticker": symbol, "headlines": news, "count": len(news), "source": "yahoo-search"}
    except Exception as exc:  # noqa: BLE001
        return {"ticker": symbol, "error": str(exc), "headlines": [], "source": "yahoo-search"}


def calculate_metrics(prices: list[float]) -> dict[str, Any]:
    """Simple return / volatility helpers from a close series."""
    if len(prices) < 2:
        return {"error": "need at least 2 prices", "prices": prices}
    rets = [(prices[i] / prices[i - 1]) - 1 for i in range(1, len(prices))]
    avg = sum(rets) / len(rets)
    var = sum((x - avg) ** 2 for x in rets) / len(rets)
    return {
        "n": len(prices),
        "total_return_pct": round((prices[-1] / prices[0] - 1) * 100, 2),
        "avg_daily_return_pct": round(avg * 100, 3),
        "daily_vol_pct": round(var**0.5 * 100, 3),
        "last": prices[-1],
        "first": prices[0],
    }


TOOLS = {
    "get_stock_quote": {
        "description": "Get the latest price and basic quote metadata for a stock ticker.",
        "fn": get_stock_quote,
        "params": {"ticker": "string"},
    },
    "get_company_news": {
        "description": "Get recent news headlines related to a ticker.",
        "fn": get_company_news,
        "params": {"ticker": "string", "limit": "int optional"},
    },
    "calculate_metrics": {
        "description": "Compute return and volatility stats from a list of closing prices.",
        "fn": calculate_metrics,
        "params": {"prices": "list[float]"},
    },
}


def run_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name not in TOOLS:
        return {"error": f"unknown tool: {name}"}
    try:
        return TOOLS[name]["fn"](**args)
    except TypeError as exc:
        return {"error": f"bad args for {name}: {exc}"}


def tool_catalog_json() -> str:
    return json.dumps(
        {k: {"description": v["description"], "params": v["params"]} for k, v in TOOLS.items()},
        indent=2,
    )