# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI AI microservice (Valura AI) that classifies user financial queries, routes them to specialist agents, and streams responses via SSE. The goal is a "spine" system: safety guard → classifier → router → agent → streamed response.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Set OPENAI_API_KEY and OPENAI_MODEL in .env
```

Use `gpt-4o-mini` during development; evaluation runs against `gpt-4.1`.

## Running Tests

```bash
pytest tests/ -v          # run all tests
pytest tests/test_safety_pairs.py -v   # run a single test file
pytest tests/ -k "test_safety_recall"  # run a specific test by name
```

Tests must pass without `OPENAI_API_KEY` set — all LLM calls must be mocked. The `mock_llm` fixture in `conftest.py` provides a `MagicMock` for this purpose.

## Architecture

The system is built as four sequential layers:

### 1. Safety Guard (`src/safety.py`)
- Synchronous, no LLM, no network — must complete in <10ms
- Returns a verdict with `blocked: bool` and a `message: str`
- Each blocked category (insider trading, market manipulation, money laundering, guaranteed-return claims, reckless advice) returns a **distinct** response — not a generic refusal
- Educational queries about harmful topics should NOT be blocked (this is a documented tradeoff)
- Gold queries: `fixtures/test_queries/safety_pairs.json` — thresholds: ≥95% recall on harmful, ≥90% pass-through on educational

### 2. Intent Classifier (`src/classifier.py`)
- Single LLM call per query using structured output
- Returns: `agent` (string from taxonomy), `entities` (dict), `safety_verdict` (informational only)
- Must handle follow-up queries with prior conversation context (pronoun/entity carryover)
- LLM failure must not crash the request — define a fallback
- Gold queries: `fixtures/test_queries/intent_classification.json` — threshold: ≥85% routing accuracy

**Agent taxonomy** (exact strings the classifier must output):
`portfolio_health`, `market_research`, `investment_strategy`, `financial_planning`, `financial_calculator`, `risk_assessment`, `product_recommendation`, `predictive_analysis`, `customer_support`, `general_query`

### 3. Portfolio Health Agent (`src/agents/portfolio_health.py`)
- The only fully-implemented agent; all others return structured "not implemented" stubs
- Receives user profile dict (from fixtures) — does not fetch portfolio data itself
- Must fetch live market data via `yfinance` or MCP — do not hardcode prices
- Structured output must include: `concentration_risk`, `performance`, `benchmark_comparison`, `observations[]`, `disclaimer`
- `user_004_empty` (zero positions) must not crash — return a BUILD-oriented response
- Every response must include a regulatory disclaimer containing "not investment advice"

### 4. HTTP Layer (`src/main.py`)
- FastAPI app with one primary endpoint
- Pipeline: safety guard → classifier → router → agent → SSE stream
- Safety guard blocks first; classifier safety verdict is informational only and does not re-block
- Errors stream as structured SSE error events, not stack traces
- Enforce a request timeout (document the chosen value)

## Key Files and Fixtures

- `fixtures/users/` — 5 user profiles (usr_001 through usr_008); load by `user_id` field
- `fixtures/test_queries/intent_classification.json` — ~60 gold classification queries with `expected_agent` and `expected_entities`
- `fixtures/test_queries/safety_pairs.json` — ~45 gold safety queries with `should_block` and `category`
- `fixtures/conversations/` — 3 multi-turn test cases for follow-up and topic-switch handling
- `tests/conftest.py` — shared fixtures: `load_user`, `gold_classifier_queries`, `gold_safety_queries`, `conversation_test_cases`, `mock_llm`
- `tests/test_classifier_routing.py` — contains the `matches_entities()` matcher; extend it to cover all entity vocabulary fields

## Entity Matching Rules

When testing classifier output against gold fixtures, apply these normalization rules:
- `tickers`: case-folded, exchange suffix optional (`AAPL` matches `aapl`, `ASML.AS`)
- `topics`/`sectors`: case-folded substring match per element
- `amount`/`rate`: within ±5%
- `period_years`: exact integer
- `currency`: ISO 4217 exact
- `index`: exact match (`S&P 500`, `FTSE 100`, `NIKKEI 225`, `MSCI World`)
- `action`, `goal`, `frequency`, `horizon`, `time_period`: exact match against vocabulary tokens

## Test Skeleton Pattern

All three test files ship with `@pytest.mark.skip` decorators. To activate a test:
1. Remove the `@pytest.mark.skip` decorator
2. Uncomment and adjust the import line at the top of the test function
3. Wire up your implementation's actual function signature

## User Profile Shape

```json
{
  "user_id": "usr_001",
  "name": "...",
  "country": "US",
  "base_currency": "USD",
  "kyc": {"status": "verified"},
  "risk_profile": "aggressive",
  "positions": [
    {"ticker": "AAPL", "exchange": "NASDAQ", "quantity": 60, "avg_cost": 142.30, "currency": "USD", "purchased_at": "2023-08-04"}
  ],
  "preferences": {"preferred_benchmark": "QQQ"}
}
```

## Constraints

- All code goes in `src/`; all tests in `tests/`
- Streaming via SSE only — no JSON fallback response path
- Do not hardcode market data (prices, benchmarks, sector data) — fetch live from `yfinance` or MCP
- Session memory persistence is your choice (in-memory is acceptable for the assignment if defended in README)
- CI runs `pytest tests/ -v` without `OPENAI_API_KEY` — every LLM-touching test must mock
