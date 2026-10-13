"""FastAPI app — Market Analyst Agent."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.agent import run_agent

load_dotenv()

ROOT = Path(__file__).resolve().parent
app = FastAPI(
    title="Market Analyst Agent",
    description="Tool-calling agent that researches tickers and writes briefings.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=str(ROOT / "templates"))


class AnalyzeRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=500, examples=["Analyze AAPL for the last week"])


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    mode = "mock" if os.getenv("FORCE_MOCK") == "1" or not os.getenv("OPENAI_API_KEY") else "openai"
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "mode": mode},
    )


@app.get("/health")
async def health():
    return {
        "ok": True,
        "mode": "mock" if os.getenv("FORCE_MOCK") == "1" or not os.getenv("OPENAI_API_KEY") else "openai",
    }


@app.post("/api/analyze")
async def analyze(body: AnalyzeRequest):
    result = run_agent(body.query.strip())
    return JSONResponse(
        {
            "query": result.query,
            "mode": result.mode,
            "ticker": result.ticker,
            "report_markdown": result.report_markdown,
            "steps": [
                {
                    "thought": s.thought,
                    "tool": s.tool,
                    "args": s.args,
                    "observation": s.observation,
                }
                for s in result.steps
            ],
        }
    )


# ASGI app for uvicorn / vercel adapters
application = app