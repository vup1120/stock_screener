# CLAUDE.md — Stock Screener Codebase Guide

This file provides context for AI assistants working in this repository.

## Project Overview

A Python CLI application that screens Taiwan (TWSE/TPEX) and US stocks using technical indicators (UT Bot, Smart Money Concepts), institutional chip analysis, AI-powered suggestions via Google Gemini, Line push notifications, and interactive TradingView-style charts.

## Repository Structure

```
stock_screener/
├── CLAUDE.md                      # This file
├── README.md                      # Brief project description
└── tw_stock_screener/             # Main application package
    ├── main.py                    # Entry point — StockScreener orchestrator
    ├── config.py                  # All configuration parameters and API keys
    ├── data_fetcher.py            # Data source abstraction (TWSE/FinMind/yfinance)
    ├── ai_analyzer.py             # Google Gemini Pro integration
    ├── notifications.py           # Line Notify push notifications
    ├── visualization.py           # Plotly + mplfinance charting (largest module)
    ├── chart_viewer.py            # CLI wrapper for chart viewing
    ├── requirements.txt           # Python dependencies
    ├── SETUP_GUIDE.md             # Environment setup documentation
    ├── README.md                  # Detailed Chinese user documentation
    ├── indicators/                # Technical indicator modules
    │   ├── __init__.py
    │   ├── ut_bot.py              # UT Bot Alerts (ATR trailing stop)
    │   ├── smc.py                 # Smart Money Concepts (BOS, CHoCH, OB, FVG)
    │   ├── chip_analysis.py       # Institutional investor chip analysis
    │   └── combo_indicator.py     # Combined indicator calculator
    ├── tests/
    │   ├── conftest.py            # pytest config + integration mark registration
    │   └── test_data_fetcher.py   # Integration tests for data fetching
    ├── logs/                      # Runtime logs (gitkeep, not committed)
    └── output/                    # Screening results CSV/JSON (gitkeep)
```

## Architecture

Data flows in a pipeline:

```
CLI args → main.py (StockScreener)
  ↓
DataFetcher (TWSE / FinMind / yfinance fallback)
  ↓
Indicators: UT Bot + SMC + Chip Analysis + EMA Ribbon
  ↓
Optional: GeminiAnalyzer (AI suggestions)
  ↓
_apply_filters() → matching stocks
  ↓
Output: CSV/JSON files + Line Notify + interactive charts
```

### Key Classes

| Class | File | Purpose |
|---|---|---|
| `StockScreener` | `main.py` | Main orchestrator |
| `UnifiedDataFetcher` | `data_fetcher.py` | Selects best data source with fallback |
| `TWSEDataFetcher` | `data_fetcher.py` | Official TWSE/TPEX API |
| `FinMindDataFetcher` | `data_fetcher.py` | FinMind API |
| `YFinanceDataFetcher` | `data_fetcher.py` | Yahoo Finance wrapper |
| `UTBotCalculator` | `indicators/ut_bot.py` | ATR trailing stop + Heikin Ashi |
| `SMCCalculator` | `indicators/smc.py` | BOS/CHoCH/OrderBlock/FVG detection |
| `ChipAnalyzer` | `indicators/chip_analysis.py` | Institutional position signals |
| `GeminiAnalyzer` | `ai_analyzer.py` | Gemini Pro AI analysis |
| `LineNotifier` | `notifications.py` | Line Notify push messages |

## Running the Application

All commands run from `tw_stock_screener/`:

```bash
# Screen Taiwan market with defaults
python main.py --market tw

# Screen a single stock with AI analysis and notification
python main.py --stock 2330 --ai --notify --verbose

# Screen US market
python main.py --market us

# View a chart for a stock
python chart_viewer.py --stock 2330
```

## Running Tests

Tests are in `tw_stock_screener/tests/`. Run from the repo root or the `tw_stock_screener/` directory:

```bash
# Unit tests only (no external API calls)
pytest -m 'not integration'

# All tests including integration (requires live internet + real stock codes)
pytest

# Verbose output
pytest -v -m 'not integration'
```

Integration tests hit real external APIs (TWSE, FinMind, yfinance) and are marked with `@pytest.mark.integration`. Skip them in CI or offline environments.

## Configuration (`config.py`)

All tunable parameters live in `tw_stock_screener/config.py`. **Do not hardcode values in other modules.**

### API Keys (set before running)
```python
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"       # Google AI Studio
LINE_NOTIFY_TOKEN = "YOUR_LINE_NOTIFY_TOKEN"  # notify-bot.line.me
FINMIND_TOKEN = ""                            # Optional, free tier limited
```

### Data Source
```python
TW_DATA_SOURCE = 'twse'  # Options: 'twse', 'finmind', 'yfinance'
```

### Indicator Parameters
- `UT_BOT_CONFIG` — `key_value` (sensitivity), `atr_period`, `use_heikin_ashi`
- `SMC_CONFIG` — `swing_length`, `internal_length`, `show_order_blocks`, `show_fvg`, `equal_hl_threshold`
- `EMA_CONFIG` — `periods` list (default: `[5, 20, 60, 120, 240]`)
- `CHIP_CONFIG` — thresholds for foreign/investment trust/dealer buy signals, `consecutive_days`

### Screening Criteria
```python
SCREENING_CRITERIA = {
    'smc_signals': ['CHoCH_bull', 'BOS_bull'],  # SMC signals to match
    'min_signal_strength': 70,                   # 0–100
    'ut_bot_signal': 'buy',                      # 'buy', 'sell', 'any'
    'chip_condition': 'foreign_buy',             # 'foreign_buy', 'all_buy', 'any'
    'volume_spike': True,
    'volume_ratio': 1.5,
}
```

### Stock Lists
- `TW_STOCK_LIST` — 50 Taiwan stocks (electronics, financials, ETFs)
- `US_STOCK_LIST` — 19 US stocks and indices

## Data Model

There is no database. The app is stateless — data is fetched fresh per run and written to `output/`.

All internal data uses pandas DataFrames with required columns: `date, open, high, low, close, volume`.

Screening results are dicts with this shape:
```python
{
    'stock_id': str,
    'price': float,
    'price_change': float,
    'ut_signal': str,          # 'buy' | 'sell' | 'hold'
    'ut_trend': str,           # 'bullish' | 'bearish' | 'neutral'
    'ut_summary': dict,
    'smc_signal': str,         # 'CHoCH_bull' | 'BOS_bull' | ...
    'smc_trend': str,
    'smc_strength': int,       # 0–100
    'smc_summary': dict,
    'chip_signal': str,        # 'strong_buy' | 'buy' | 'accumulating' | ...
    'chip_summary': dict,
    'volume_ratio': float,
    'volume_spike': bool,
    'ai_suggestion': {
        'action': str,         # 'BUY' | 'SELL' | 'HOLD'
        'score': int,
        'confidence': str,
        'reasons': list,
    }
}
```

## External APIs

| API | URL | Purpose |
|---|---|---|
| TWSE | `https://www.twse.com.tw/exchangeReport/STOCK_DAY` | Listed TW stock prices |
| TPEX | `https://www.tpex.org.tw/...` | OTC TW stock prices |
| FinMind | `https://api.finmindtrade.com/api/v4/data` | Alternative TW data |
| yfinance | Python library | Yahoo Finance (US + TW fallback) |
| Gemini | `google-generativeai` SDK | AI analysis (model: `gemini-pro`) |
| Line Notify | `https://notify-api.line.me/api/notify` | Push notifications |

**Rate limiting:** TWSE requests include 0.2–0.3s delays. Batch screening adds 0.3s per stock. SSL verification is disabled for TWSE requests (Python 3.13 compatibility workaround).

## Code Conventions

- **Language:** Python 3.9+. Chinese comments and docstrings are normal in this codebase (Taiwan-focused project).
- **Type hints:** Used throughout. Use `Optional`, `List`, `Dict`, `Tuple` from `typing`.
- **Dataclasses:** Prefer `@dataclass` for structured results (see `ChipAnalysisResult`, `StructureSignal`).
- **Error handling:** Use `try/except` with graceful fallback; log errors via the `logging` module. Don't raise unhandled exceptions in indicator calculations.
- **Config:** All parameters go in `config.py`. Modules import from config, never define their own magic numbers.
- **Logging:** Use `logging.getLogger(__name__)` in each module. Log directory is `logs/`.
- **Output:** Results saved to `output/` as CSV and/or JSON depending on `OUTPUT_CONFIG`.

## Indicator Signal Reference

### UT Bot (`indicators/ut_bot.py`)
- Signals: `'buy'`, `'sell'`, `'hold'`
- Trend: `'bullish'`, `'bearish'`, `'neutral'`
- Logic: Price crosses above/below ATR trailing stop (with optional Heikin Ashi smoothing)

### SMC (`indicators/smc.py`)
- Signals: `'BOS_bull'`, `'BOS_bear'`, `'CHoCH_bull'`, `'CHoCH_bear'`
- BOS = Break of Structure (trend continuation)
- CHoCH = Change of Character (trend reversal)
- Also detects: Order Blocks (OB), Fair Value Gaps (FVG)
- Strength: 0–100

### Chip Analysis (`indicators/chip_analysis.py`)
- Signals: `'strong_buy'`, `'buy'`, `'accumulating'`, `'neutral'`, `'distributing'`, `'sell'`, `'strong_sell'`
- Based on net positions of: foreign investors, investment trusts, dealers
- `consecutive_days` config controls accumulation/distribution detection

### Combo (`indicators/combo_indicator.py`)
- Combines UT Bot + SMC + Chip signals into a unified score

## Visualization (`visualization.py`)

Two rendering backends:
- **Plotly** — interactive HTML charts (primary, TradingView-style). Use for development and end-user output.
- **mplfinance** — static PNG charts. Faster, use when Plotly is unavailable.

Key functions:
- `plot_stock_with_indicators(df, ...)` — full chart with all overlays
- `plot_ut_bot(df, ...)` — UT Bot trailing stop overlay
- `plot_smc(df, ...)` — SMC components (BOS, CHoCH, OB, FVG)

## Dependencies

Install with:
```bash
pip install pandas numpy requests yfinance plotly mplfinance matplotlib google-generativeai schedule
```

Core (required): `pandas`, `numpy`, `requests`, `yfinance`
Visualization (recommended): `plotly`, `mplfinance`, `matplotlib`
AI (optional): `google-generativeai`
Scheduling (optional): `schedule`

## Development Branch

Active development branch: `claude/claude-md-mmaukjhlt1pudfv6-i9owb`

There is no CI/CD pipeline configured. No `.github/workflows/` exists.
