# Example output (mock mode)

Generated via:

```bash
python cli.py "Analyze AAPL for a quick investment briefing"
```

The agent calls `get_stock_quote` → `get_company_news` → `calculate_metrics`, then writes a markdown briefing.