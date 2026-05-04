# Project Specification
> Generated: 2026-05-04    
> Repo: valura-ai-ai-engineer-assignment-deepd9137-main

---

## 1. Problem Statement

Valura is a global wealth management platform that needs an AI microservice acting as a financial co-investor for novice investors. The system must classify free-text financial queries, route them to specialist agents, and stream structured responses in real time via Server-Sent Events. The evaluators (Valura hiring team) will run `pytest tests/ -v` against the submission and use a hidden labeled query set to grade accuracy. Without a safety guard that correctly blocks harmful queries, a working classifier that routes with ≥85% accuracy, and a fully-implemented Portfolio Health agent, the submission fails outright.

---

## 2. Functional Requirements

### P0 — Must Have (assignment will fail without these)

- [ ] **Safety Guard** (`src/safety.py`): synchronous, no LLM, no network, blocks harmful queries in <10ms
- [ ] **Six blocked categories** with distinct professional responses (not generic): `insider_trading`, `market_manipulation`, `money_laundering`, `guaranteed_returns`, `reckless_advice`, `sanctions_evasion`
- [ ] **Educational pass-through**: queries that ask *about* harmful topics (e.g. "what is insider trading?") must NOT be blocked
- [ ] **Intent Classifier** (`src/classifier.py`): single LLM call returning structured output with `agent`, `entities`, and `safety_verdict`
- [ ] **10-agent taxonomy routing**: classifier output `agent` field must be one of the exact strings: `portfolio_health`, `market_research`, `investment_strategy`, `financial_planning`, `financial_calculator`, `risk_assessment`, `product_recommendation`, `predictive_analysis`, `customer_support`, `general_query`
- [ ] **Follow-up context carryover**: classifier must resolve "what about AMD?" after "tell me about Nvidia" using prior conversation turns
- [ ] **Portfolio Health Agent** (`src/agents/portfolio_health.py`): fully implemented, not a stub
- [ ] **Portfolio Health structured output** with at minimum: `concentration_risk`, `performance`, `benchmark_comparison`, `observations[]`, `disclaimer`
- [ ] **Empty portfolio (usr_004) does not crash**: returns a BUILD-oriented response
- [ ] **Disclaimer field** containing "not investment advice" in every Portfolio Health response
- [ ] **Stub agents**: all other 9 agents return a structured "not implemented" response — never crash, never error
- [ ] **FastAPI HTTP layer** (`src/main.py`): one primary endpoint running the full pipeline
- [ ] **SSE streaming only**: no JSON fallback; errors stream as structured SSE error events
- [ ] **Pipeline timeout**: configurable, enforced, documented in README
- [ ] **Tests pass without `OPENAI_API_KEY`**: all LLM calls mocked in tests
- [ ] **`pytest tests/ -v` passes in CI** (GitHub Actions, Python 3.11, no API key)
- [ ] **Incremental git history**: commits throughout development, not a single dump

### P1 — Should Have (expected for a good submission)

- [ ] **Session memory**: conversation history passed to classifier per session (in-memory is acceptable)
- [ ] **LLM failure fallback**: classifier LLM failure returns a structured fallback, not a 500
- [ ] **Live market data**: fetch prices/benchmarks from `yfinance` or MCP — never hardcoded
- [ ] **Multi-currency normalization**: `usr_006` has USD/EUR/GBP/JPY positions — Portfolio Health must handle correctly
- [ ] **Benchmark comparison**: use user's `preferred_benchmark` (e.g. QQQ for usr_001, S&P 500 for others)
- [ ] **Concentration risk flag**: surface "high" flag when top position > ~30–40% of portfolio
- [ ] **Entity extraction accuracy**: subset-match for tickers, amounts, rates, periods, vocabulary tokens
- [ ] **Type hints** throughout `src/`
- [ ] **README** with setup, env vars, decisions, video link
- [ ] **Defence video ≤ 10 minutes**, unlisted, URL in README

### P2 — Nice to Have (bonus, not graded as failures)

- [ ] **Identical-query dedupe cache** (intra-session): skip LLM call on repeated query
- [ ] **Embedding-based pre-classifier**: skip LLM when confidence is high
- [ ] **Per-tenant model selection**: premium → `gpt-4.1`, free → `gpt-4o-mini`
- [ ] **Multi-tenant rate limiting**
- [ ] **MCP server integration** for market data (instead of `yfinance`)

---

## 3. Non-Functional Requirements

### Latency / Performance
| Metric | Target |
|---|---|
| p95 streaming first-token latency | < 2s |
| p95 end-to-end response time | < 6s |
| Safety guard execution time | < 10ms |
| Cost per query at `gpt-4.1` pricing | < $0.05 |
| Model during development | `gpt-4o-mini` |
| Model during evaluation | `gpt-4.1` |

### Reliability
- Classifier LLM failure must not crash the request — define and return a structured fallback
- Portfolio Health agent must not crash on any of the 5 user fixtures
- Safety guard must never raise an exception — it must always return a verdict
- Request-level timeout must be enforced (document the chosen value)

### Security
- No secrets in the repo; use `.env` (gitignored); document all required variables in `.env.example`
- Do not expose stack traces in SSE error events — structured error payloads only

### Observability [ASSUMED]
- Log classifier routing decisions and safety verdicts per request at INFO level
- Log LLM call latency per request
- Log errors at ERROR level with enough context to reproduce

### Code Quality
- Python 3.11+ type hints on all public functions
- Pydantic models for all request/response schemas and agent output

---

## 4. System Architecture

### Components

| Component | File | Responsibility |
|---|---|---|
| Safety Guard | `src/safety.py` | Rule-based keyword/pattern filter; blocks 6 harm categories; returns `SafetyVerdict` |
| Intent Classifier | `src/classifier.py` | Single LLM call; returns structured `ClassificationResult` with agent, entities, safety_verdict |
| Router | `src/router.py` [ASSUMED] | Dispatches `ClassificationResult.agent` to the correct agent function |
| Portfolio Health Agent | `src/agents/portfolio_health.py` | Fetches live prices, computes metrics, returns `PortfolioHealthResult` |
| Stub Agents | `src/agents/stubs.py` [ASSUMED] | Returns structured "not implemented" payload for all other 9 agent types |
| HTTP Layer | `src/main.py` | FastAPI app; one SSE endpoint; wires pipeline; enforces timeout |
| Session Store | `src/session.py` [ASSUMED] | In-memory dict of `session_id → list[str]` (prior user turns) |

### Data Flow

```
Client HTTP POST /chat
        │
        ▼
┌───────────────────┐
│   Safety Guard    │  ← pure local, no LLM, <10ms
│  (src/safety.py)  │
└────────┬──────────┘
         │ blocked? → stream SSE error event, done
         │ passed?  ↓
┌───────────────────┐
│ Intent Classifier │  ← 1 LLM call (gpt-4o-mini / gpt-4.1)
│(src/classifier.py)│  ← receives query + prior_turns from session store
└────────┬──────────┘
         │ ClassificationResult{agent, entities, safety_verdict}
         ▼
┌───────────────────┐
│     Router        │  ← dispatches on result.agent
│  (src/router.py)  │
└────────┬──────────┘
         │
    ┌────┴────────────────────────────────────┐
    │                                         │
    ▼                                         ▼
┌──────────────────────┐         ┌───────────────────────┐
│ Portfolio Health Agent│         │    Stub Agents (×9)   │
│(fully implemented)   │         │ structured not-impl   │
└──────────┬───────────┘         └──────────┬────────────┘
           │                                │
           └──────────────┬─────────────────┘
                          ▼
               Stream SSE chunks to client
```

### External Services
- **OpenAI API**: Intent classifier LLM call (`gpt-4o-mini` dev, `gpt-4.1` eval)
- **yfinance** [ASSUMED]: Live price fetch for Portfolio Health agent (or MCP alternative)

---

## 5. API Contract

### `POST /chat`

**Description:** Main pipeline endpoint. Runs safety guard → classifier → agent → SSE stream.

**Input schema:**
| Field | Type | Required | Description |
|---|---|---|---|
| `query` | `str` | Yes | The user's natural-language query |
| `user_id` | `str` | Yes | User ID; maps to fixture profile (e.g. `usr_001`) |
| `session_id` | `str` | No | If provided, prior turns from this session are passed to classifier |
| `user_context` | `dict` | No [ASSUMED] | Full user profile dict (portfolio, risk profile, KYC) |

**Output:** SSE stream (`text/event-stream`)

SSE event types:
- `data: {"type": "chunk", "content": "..."}` — streaming text/data chunk
- `data: {"type": "metadata", "agent": "portfolio_health", "entities": {...}, "safety_verdict": "pass"}` — classification metadata
- `data: {"type": "result", "data": {...}}` — final structured agent output
- `data: {"type": "error", "code": "safety_blocked", "message": "..."}` — safety block or pipeline error
- `data: [DONE]` — stream termination sentinel

**Example request:**
```json
POST /chat
{
  "query": "how is my portfolio doing?",
  "user_id": "usr_001",
  "session_id": "sess_abc123"
}
```

**Example SSE response:**
```
data: {"type": "metadata", "agent": "portfolio_health", "entities": {}, "safety_verdict": "pass"}

data: {"type": "result", "data": {"concentration_risk": {"top_position_pct": 28.4, "flag": "moderate"}, ...}}

data: [DONE]
```

---

### `src/safety.py` — `check(query: str) -> SafetyVerdict`

**Description:** Synchronous rule-based filter.

**Input:** `query: str`

**Output:** `SafetyVerdict`
| Field | Type | Description |
|---|---|---|
| `blocked` | `bool` | Whether query was blocked |
| `category` | `str \| None` | One of the 6 harm categories, or None |
| `message` | `str \| None` | Professional refusal message (distinct per category), or None |

---

### `src/classifier.py` — `classify(query: str, prior_turns: list[str], llm) -> ClassificationResult`

**Description:** Single LLM call that classifies intent and extracts entities.

**Input:**
| Field | Type | Description |
|---|---|---|
| `query` | `str` | Current user turn |
| `prior_turns` | `list[str]` | Prior user turns in session (for context carryover) |
| `llm` | injectable | LLM client (injected for testability / mocking) |

**Output:** `ClassificationResult`
| Field | Type | Description |
|---|---|---|
| `agent` | `str` | One of the 10 taxonomy agent strings |
| `entities` | `dict` | Extracted entities per vocabulary |
| `safety_verdict` | `str` | Informational: `"pass"` or `"flag"` |

---

### `src/agents/portfolio_health.py` — `run(user: dict, llm) -> PortfolioHealthResult`

**Description:** Fetches live prices for user's positions, computes metrics, returns structured health assessment.

**Input:**
| Field | Type | Description |
|---|---|---|
| `user` | `dict` | Full user profile (positions, risk_profile, preferred_benchmark, base_currency) |
| `llm` | injectable | LLM client for generating observations text |

**Output:** `PortfolioHealthResult`
| Field | Type | Description |
|---|---|---|
| `concentration_risk.top_position_pct` | `float` | Largest single position as % of total value |
| `concentration_risk.top_3_positions_pct` | `float` | Top 3 positions as % |
| `concentration_risk.flag` | `str` | `"low"`, `"moderate"`, or `"high"` |
| `performance.total_return_pct` | `float` | Total return vs. avg cost |
| `performance.annualized_return_pct` | `float \| None` | Annualized return if purchase dates available |
| `benchmark_comparison.benchmark` | `str` | User's preferred benchmark name |
| `benchmark_comparison.portfolio_return_pct` | `float` | Portfolio total return |
| `benchmark_comparison.benchmark_return_pct` | `float` | Benchmark return over same period |
| `benchmark_comparison.alpha_pct` | `float` | Portfolio return minus benchmark return |
| `observations` | `list[Observation]` | 1–3 plain-language observations with `severity` and `text` |
| `disclaimer` | `str` | Must contain "not investment advice" |

---

## 6. Data Models / Schemas

### User Profile (from fixtures)
| Field | Type | Required | Description |
|---|---|---|---|
| `user_id` | `str` | Yes | e.g. `"usr_001"` |
| `name` | `str` | Yes | Display name |
| `age` | `int` | Yes | User age |
| `country` | `str` | Yes | ISO country code |
| `base_currency` | `str` | Yes | ISO 4217 (e.g. `"USD"`) |
| `kyc.status` | `str` | Yes | `"verified"` or `"pending"` |
| `risk_profile` | `str` | Yes | `"aggressive"`, `"moderate"`, `"conservative"` |
| `positions` | `list[Position]` | Yes | May be empty (`[]`) |
| `preferences.preferred_benchmark` | `str` | No | e.g. `"S&P 500"`, `"QQQ"` |

### Position
| Field | Type | Required | Description |
|---|---|---|---|
| `ticker` | `str` | Yes | e.g. `"AAPL"`, `"ASML.AS"` |
| `exchange` | `str` | Yes | e.g. `"NASDAQ"`, `"NYSE"` |
| `quantity` | `int` | Yes | Number of shares held |
| `avg_cost` | `float` | Yes | Average cost per share in `currency` |
| `currency` | `str` | Yes | ISO 4217 |
| `purchased_at` | `str` | Yes | ISO date `"YYYY-MM-DD"` |

### Observation (in PortfolioHealthResult)
| Field | Type | Required | Description |
|---|---|---|---|
| `severity` | `str` | Yes | `"info"`, `"warning"`, or `"critical"` |
| `text` | `str` | Yes | Plain-language observation for a novice investor |

### ClassificationResult
| Field | Type | Required | Description |
|---|---|---|---|
| `agent` | `str` | Yes | One of the 10 taxonomy strings |
| `entities` | `dict` | Yes | Extracted entities; may be `{}` |
| `safety_verdict` | `str` | Yes | `"pass"` or `"flag"` (informational only) |

### SafetyVerdict
| Field | Type | Required | Description |
|---|---|---|---|
| `blocked` | `bool` | Yes | True if query is blocked |
| `category` | `str \| None` | No | Harm category if blocked |
| `message` | `str \| None` | No | Professional refusal message if blocked |

---

## 7. Constraints

### Hard rules from ASSIGNMENT.md
- All code in `src/`, all tests in `tests/`
- Python 3.11+
- Streaming via SSE only — no JSON fallback response path
- Safety guard: no LLM, no network, pure local, <10ms
- One LLM call per classification — not multiple
- Tests must run without `OPENAI_API_KEY` in CI
- No hardcoded market data (prices, benchmarks, sector classifications)
- No secrets in the repo — `.env` is gitignored
- Incremental git commits required — a single-dump commit is disqualifying
- Defence video ≤ 10 minutes — submissions over 10 minutes are auto-rejected
- Do not delete `ASSIGNMENT.md`, `fixtures/`, `pytest.ini`, `requirements.txt`, `.env.example`, `.github/`

### Tech stack constraints
- Language: Python 3.11+
- Web: FastAPI + uvicorn
- SSE: `sse-starlette` (or custom)
- LLM: OpenAI SDK (`openai>=1.30.0`) — structured outputs mode
- Validation: Pydantic v2
- Testing: pytest + pytest-asyncio + pytest-mock
- Market data: `yfinance` or MCP (not hardcoded)

### Not allowed
- Multiple LLM calls in the classifier (must be exactly one)
- JSON-only response path (SSE is the only mode)
- Hardcoded stock prices, sector data, or benchmark values
- Committing `.env` or any file containing secrets
- Skipping the safety guard when the classifier also returns a safety flag (guard is the only authority)

---

## 8. Edge Cases & Error Handling

| Scenario | Expected Behavior | Error Code / Exit |
|---|---|---|
| Empty query `""` | Safety guard passes, classifier returns `general_query` with empty entities | No error; stream a clarifying response |
| Query is gibberish (`"abcdefg"`) | Classifier routes to `general_query` | No crash |
| `user_004` empty portfolio (`positions: []`) | Portfolio Health returns BUILD-oriented response with disclaimer | No crash, no 500 |
| `usr_006` multi-currency positions | Portfolio Health converts all positions to `base_currency` before computing metrics | No crash; results in base currency |
| OpenAI API timeout during classification | Return structured fallback `ClassificationResult` with `agent="general_query"` and log the error | SSE error event or fallback response |
| OpenAI API returns malformed JSON | Pydantic parse failure → fallback classification; no 500 | Log + fallback |
| Missing `OPENAI_API_KEY` at runtime | App starts; first LLM call raises `AuthenticationError` → structured SSE error | `{"type": "error", "code": "llm_unavailable"}` |
| `yfinance` returns no data for a ticker | Skip that position's market price; note in observations | No crash; partial result with warning observation |
| Request exceeds pipeline timeout | Cancel and stream timeout error event | `{"type": "error", "code": "timeout"}` |
| Safety guard throws unexpected exception | Catch, log, return `blocked=False` to avoid false-blocking [ASSUMED] | Log at ERROR level |
| Classifier `agent` not in taxonomy | Fallback to `general_query` | Log warning |
| Rate limit from OpenAI | Catch `RateLimitError`; return structured error; optionally retry once with backoff | SSE error event |
| Inputs exceeding LLM token limit | Truncate prior conversation turns (oldest first) before passing to classifier | No crash; truncation logged |

---

## 9. Acceptance Criteria

- [ ] `pytest tests/ -v` passes with zero failures in CI (no `OPENAI_API_KEY` set)
- [ ] `pytest tests/test_safety_pairs.py -v` — safety guard recall ≥ 95% on `should_block=true` queries
- [ ] `pytest tests/test_safety_pairs.py -v` — safety guard pass-through ≥ 90% on `should_block=false` queries
- [ ] `pytest tests/test_safety_pairs.py -v` — at least 4 distinct block messages across categories
- [ ] `pytest tests/test_classifier_routing.py -v` — routing accuracy ≥ 85% on `intent_classification.json`
- [ ] `pytest tests/test_portfolio_health_skeleton.py -v` — `usr_004` (empty) does not crash, response includes `disclaimer`
- [ ] `pytest tests/test_portfolio_health_skeleton.py -v` — `usr_003` concentration `flag` is `"high"` or `"warning"`
- [ ] `pytest tests/test_portfolio_health_skeleton.py -v` — `usr_001` response includes `disclaimer` containing "not investment advice"
- [ ] All stub agents (non-portfolio_health) return structured "not implemented" payloads — no 500s
- [ ] SSE stream for any query terminates with `[DONE]`
- [ ] Safety guard completes in <10ms for any input
- [ ] Autograding scores: Safety (25pts) + Classifier (30pts) + Portfolio Health (25pts) + Full suite (20pts) = 100pts

**Exact pytest commands:**
```bash
pytest tests/ -v
pytest tests/test_safety_pairs.py -v
pytest tests/test_classifier_routing.py -v
pytest tests/test_portfolio_health_skeleton.py -v
```

---

## 10. Test Plan

### Unit Tests — what needs coverage

| Module | What to test |
|---|---|
| `src/safety.py` | Each of the 6 block categories; each educational pass-through; empty string; gibberish; very long input |
| `src/classifier.py` | Routing accuracy against `intent_classification.json` gold set (≥85%); entity extraction; follow-up carryover; LLM failure fallback |
| `src/agents/portfolio_health.py` | Empty portfolio (usr_004); concentrated portfolio (usr_003); multi-currency (usr_006); disclaimer present; concentration flag logic |
| `src/router.py` | Each of the 10 agent strings routes to the right handler; unknown agent string falls back gracefully |
| Entity matcher (`tests/test_classifier_routing.py`) | Ticker normalization; ±5% numeric tolerance; vocabulary token exact match; subset match semantics |

### Integration Tests — end-to-end scenarios

| Scenario | Description |
|---|---|
| Full pipeline — blocked query | Safety blocks → SSE error event emitted; classifier never called |
| Full pipeline — portfolio health | Safe query → classifier → portfolio_health agent → SSE result stream |
| Full pipeline — stub agent | Safe query → classifier → market_research stub → SSE not-implemented payload |
| Follow-up resolution | Two-turn session; second turn resolves entity from first turn |
| Topic switch | Multi-turn session; context does NOT incorrectly carry to unrelated new topic |
| LLM failure | Mock LLM raises exception; pipeline returns structured SSE error, not 500 |

### How to run:
```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
pytest tests/test_safety_pairs.py -v        # safety guard only (25 pts)
pytest tests/test_classifier_routing.py -v  # classifier only (30 pts)
pytest tests/test_portfolio_health_skeleton.py -v  # portfolio health only (25 pts)
```

---

## 11. Incremental Git Commit Strategy

### Planned Commit Phases

| Phase | What gets committed | Example commit message |
|---|---|---|
| 1 | `.gitignore`, `.env.example`, `requirements.txt`, `pytest.ini`, scaffold | `chore: initialize project scaffold and environment` |
| 2 | `src/safety.py` + `SafetyVerdict` model | `feat(safety): implement rule-based safety guard for 6 harm categories` |
| 3 | `tests/test_safety_pairs.py` wired up (skip removed) | `test(safety): wire safety guard tests against gold fixture` |
| 4 | `src/classifier.py` + `ClassificationResult` model | `feat(classifier): implement intent classifier with single LLM call` |
| 5 | `tests/test_classifier_routing.py` wired up | `test(classifier): wire routing accuracy test against gold fixture` |
| 6 | `src/session.py` + follow-up context carryover | `feat(session): add in-memory session store for conversation context` |
| 7 | `src/agents/portfolio_health.py` (market data fetch + metrics) | `feat(portfolio-health): implement concentration, performance, and benchmark metrics` |
| 8 | `src/agents/portfolio_health.py` (observations + empty portfolio handling) | `feat(portfolio-health): add LLM observations generation and empty portfolio BUILD path` |
| 9 | `tests/test_portfolio_health_skeleton.py` wired up | `test(portfolio-health): wire agent tests for empty, concentrated, and standard portfolios` |
| 10 | `src/router.py` + stub agents | `feat(router): implement agent dispatcher with structured stubs for unimplemented agents` |
| 11 | `src/main.py` FastAPI app + SSE streaming | `feat(api): implement FastAPI SSE endpoint wiring full pipeline` |
| 12 | Performance validation + README | `docs: add setup instructions, env vars, decisions, and performance measurements` |

### Rules I will follow:
- [ ] Commit after every logical unit (function, module, test, fix)
- [ ] Never commit with messages like "final", "done", "wip", "update"
- [ ] Commit tests alongside or immediately after the feature they test
- [ ] Never commit secrets or .env files
- [ ] `.gitignore` is in the very first commit

### Suggested first 10 commits for this project:
1. `chore: initialize project scaffold and gitignore` — repo skeleton, no source yet
2. `feat(safety): add SafetyVerdict model and category enum`
3. `feat(safety): implement keyword/pattern matching for all 6 harm categories`
4. `test(safety): activate safety gold-set tests with recall/passthrough assertions`
5. `feat(classifier): add ClassificationResult model with 10-agent taxonomy`
6. `feat(classifier): implement single-call LLM classifier with structured output`
7. `feat(classifier): add follow-up context resolution using prior_turns`
8. `test(classifier): activate routing accuracy and entity extraction tests`
9. `feat(session): implement in-memory session store keyed by session_id`
10. `feat(portfolio-health): fetch live prices and compute concentration + performance metrics`

---

## 12. Environment Setup & Running the Project

```bash
# Clone and enter repo
git clone https://github.com/deepd9137/Valura-ai.git
cd Valura-ai

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate          # macOS/Linux
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY and OPENAI_MODEL

# Run the server
uvicorn src.main:app --reload --port 8000

# Run tests (no OPENAI_API_KEY needed — LLM is mocked)
pytest tests/ -v
```

### Required Environment Variables

| Variable | Description | Required | Example |
|---|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | Yes (runtime) | `sk-...` |
| `OPENAI_MODEL` | Model ID to use | No | `gpt-4o-mini` |
| `APP_ENV` | Runtime environment | No | `development` |
| `DATABASE_URL` | Postgres URL for session persistence | No | `postgresql://user:pass@host/db` |
| `PGVECTOR_DATABASE_URL` | Postgres+pgvector for embedding pre-classifier | No | — |
| `REDIS_URL` | Redis for dedupe cache | No | `redis://localhost:6379` |

---

## 13. File & Folder Structure

```
valura-ai/
├── .env.example                  # Documented env var template
├── .gitignore                    # Excludes .env, __pycache__, venv
├── ASSIGNMENT.md                 # Original assignment — do not delete
├── CLAUDE.md                     # Claude Code guidance file
├── SPEC.md                       # This file
├── README.md                     # Setup, decisions, video link (overwrite placeholder)
├── pytest.ini                    # pytest config: asyncio_mode=auto, testpaths=tests
├── requirements.txt              # Pinned dependencies
├── .github/
│   ├── workflows/pytest.yml      # CI: runs pytest tests/ -v on every push, no API key
│   └── classroom/autograding.json# Autograder: 25+30+25+20 points breakdown
├── fixtures/
│   ├── README.md                 # Matching rules for entity normalization
│   ├── users/                    # 5 user profiles (usr_001, 003, 004, 006, 008)
│   ├── conversations/            # 3 multi-turn test cases for follow-up/topic-switch
│   └── test_queries/
│       ├── intent_classification.json  # ~60 gold classification queries
│       └── safety_pairs.json           # ~45 gold safety queries
├── src/
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, SSE endpoint, pipeline orchestration
│   ├── safety.py                 # Synchronous safety guard, SafetyVerdict model
│   ├── classifier.py             # LLM intent classifier, ClassificationResult model
│   ├── router.py                 # Dispatches ClassificationResult.agent to agent fn
│   ├── session.py                # In-memory session store (session_id → prior_turns)
│   └── agents/
│       ├── __init__.py
│       ├── portfolio_health.py   # Fully implemented: live data, metrics, observations
│       └── stubs.py              # Structured not-implemented responses for 9 other agents
└── tests/
    ├── __init__.py
    ├── conftest.py               # Fixtures: load_user, gold queries, mock_llm
    ├── test_safety_pairs.py      # Safety recall/passthrough against gold set (25 pts)
    ├── test_classifier_routing.py # Routing accuracy + entity matcher (30 pts)
    └── test_portfolio_health_skeleton.py  # Portfolio Health edge cases (25 pts)
```

---

## 14. Defence Video Plan (≤ 10 minutes)

| Timestamp | What to show and say |
|---|---|
| 0:00–0:45 | Open the README. Read the one-paragraph mission statement aloud. State: "I built the spine — safety, classifier, router, portfolio health, SSE streaming." |
| 0:45–2:00 | **Architecture walkthrough**: draw or show the ASCII pipeline diagram. Trace one request from `POST /chat` → safety guard → classifier → portfolio health agent → SSE stream. |
| 2:00–3:30 | **Live demo**: fire a real query against the running server (`curl` or Postman). Show SSE chunks arriving in real time. Show a safety block (e.g. insider trading query). |
| 3:30–5:00 | **Safety guard**: show `src/safety.py`. Explain why no LLM — latency + reliability. Show that educational queries pass through. Show 6 distinct block messages. |
| 5:00–6:30 | **Classifier**: show `src/classifier.py`. Explain structured output schema. Show how `prior_turns` enables follow-up resolution (example: "what about AMD?" after NVDA). |
| 6:30–8:00 | **Portfolio Health agent**: show `src/agents/portfolio_health.py`. Highlight: live price fetch via yfinance, concentration calculation, `usr_004` empty portfolio BUILD path, disclaimer field. |
| 8:00–9:00 | **Non-obvious decision**: explain one key tradeoff (e.g. "I chose in-memory session store because X" or "I use keyword-pattern matching for safety because Y"). |
| 9:00–10:00 | **What I'd do differently with another week**: e.g. "Add an embedding-based pre-classifier to skip the LLM for high-confidence simple queries, saving ~$0.01/query and 300ms." |

---

## 15. Submission Checklist

- [ ] `pytest tests/ -v` passes locally with mocked LLM
- [ ] `pytest tests/ -v` passes in GitHub Actions CI (no `OPENAI_API_KEY`)
- [ ] Safety guard: ≥95% harmful recall, ≥90% educational pass-through
- [ ] Classifier: ≥85% routing accuracy on `intent_classification.json`
- [ ] `usr_004` (empty portfolio) does not crash; returns BUILD-oriented response
- [ ] `usr_003` concentration flag is `"high"` or `"warning"`
- [ ] All responses include disclaimer containing "not investment advice"
- [ ] All 9 non-portfolio-health agents return structured stubs (no crashes, no 500s)
- [ ] SSE is the only response mode — no JSON fallback path
- [ ] No hardcoded market data anywhere in `src/`
- [ ] No secrets or `.env` committed to git
- [ ] `OPENAI_API_KEY` and all other required variables documented in `.env.example` and README
- [ ] Incremental git history (≥10 commits, meaningful messages, no single-dump)
- [ ] `README.md` overwritten with: setup instructions, env var table, library decisions, video link
- [ ] Defence video ≤ 10 minutes, unlisted on YouTube (or equivalent)
- [ ] Video URL is in `README.md` and publicly accessible
- [ ] `ASSIGNMENT.md`, `fixtures/`, `pytest.ini`, `requirements.txt`, `.env.example`, `.github/` are untouched
- [ ] Performance measurements documented in README (first-token latency, end-to-end latency, cost per query)

---

## 16. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Safety guard over-blocks educational queries (recall/passthrough tradeoff) | High | High — fails ≥90% passthrough threshold | Use intent signals (e.g. "what is", "explain", "how does") to distinguish educational from harmful; document the tradeoff |
| Classifier routing accuracy below 85% on hidden eval set | Medium | High — 30 pts at risk | Do not overfit to the 60 gold queries; write prompts that generalize across the vocabulary; test follow-up cases |
| `yfinance` rate limits or returns stale/missing data | Medium | Medium — portfolio health crashes or returns wrong metrics | Wrap in try/except; skip missing tickers with an observation; cache prices within the request |
| OpenAI structured output schema mismatch causes parse failure | Medium | High — classifier crashes, pipeline fails | Always validate LLM output with Pydantic; define fallback `ClassificationResult` |
| Single-dump git commit history | Low (preventable) | High — disqualifying per assignment rules | Commit after every logical unit; enforce via commit message discipline |
| Defence video exceeds 10 minutes | Low (preventable) | High — auto-rejected | Rehearse; 10 minutes is tight; cut the live demo if running long |
| Multi-currency portfolio (usr_006) crashes Portfolio Health agent | Medium | Medium — 25 pts at risk | Convert all positions to `base_currency` using live FX rates before any aggregation |
| LLM costs exceed $0.05/query during development | Low | Low — `gpt-4o-mini` is cheap | Use `gpt-4o-mini` throughout dev; switch to `gpt-4.1` only for final evaluation run |

---

## 17. Open Questions & Assumptions

| Question | Assumed Resolution |
|---|---|
| Exact deadline (assignment says "3 days from acceptance") | [ASSUMED] 3 calendar days from the date the GitHub Classroom assignment was accepted |
| Session memory persistence choice | [ASSUMED] In-memory `dict` keyed by `session_id`; documented in README as the chosen tradeoff |
| How is `user_context` (portfolio) passed to the HTTP endpoint? | [ASSUMED] Client sends `user_id`; server loads from fixtures directory (or a DB if implemented). Alternatively, client sends the full user dict |
| What timeout to enforce on the pipeline? | [ASSUMED] 10 seconds total; documented in README |
| What constitutes "concentration risk: high"? | [ASSUMED] Top single position >40% of total portfolio value → `"high"`; 25–40% → `"moderate"`; <25% → `"low"` |
| `portfolio_query` agent appears in `follow_up_session.json` but not in the taxonomy | [ASSUMED] This is an artifact of the fixture; route `"portfolio_query"` to `portfolio_health` in the router |
| How many prior turns to pass to the classifier? | [ASSUMED] Last 5 user turns to stay within token budget |
| What benchmark to use for usr_006 (multi-currency, Singapore-based)? | [ASSUMED] `MSCI World` as the default international benchmark unless `preferred_benchmark` is set |
| Is the `/chat` endpoint authenticated? | [ASSUMED] No auth for this assignment; would add API key header in production |
| Should the classifier's `safety_verdict` field affect routing? | Explicitly stated in ASSIGNMENT.md: it is informational only — does not re-block |
