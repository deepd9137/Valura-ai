# System Architecture & Implementation Plan
> Total phases: 11 (Phase 0 → Phase 10)
> Branch strategy: one branch per phase, merged into `main` on completion
> Generated: 2026-05-04
> Repo: `Valura-ai` (https://github.com/deepd9137/Valura-ai.git)

---

## PART 1: SYSTEM ARCHITECTURE

### 1.1 Architecture Style

**Pattern:** Synchronous **request → safety → single-LLM-classifier → routed-agent → SSE stream** pipeline. This is a layered guard-then-route pattern: a deterministic pre-filter (safety guard), one structured LLM call (classifier), and a dispatch table to one of 10 agent handlers (only `portfolio_health` is real; the other 9 are structured stubs). Streaming happens at the very last hop — the bytes that the agent emits are pushed straight onto an SSE stream.

**Why this fits the problem:**
- ASSIGNMENT.md says "single LLM call per classification" and "safety guard runs first" — this maps 1:1 onto a fixed three-stage pipeline. There is no need for multi-agent collaboration, retrieval-augmented generation, planner/executor split, or an agent loop.
- The latency budget (p95 first-token < 2s, end-to-end < 6s) makes sequential stages with a single LLM hop the only viable layout. Adding a planner LLM or a tool-calling loop would blow the budget.
- The 10-agent taxonomy is finite and known up-front, so a static dispatch table is correct here. A dynamic agent registry would be over-engineered.

**Key trade-offs:**
| Decision | Trade-off |
|---|---|
| Safety guard is rule-based (no LLM) | Will over-block some edge cases vs. the 90% educational pass-through threshold — accepted because it must complete in <10ms and never fail |
| One LLM call for classification | Cannot use chain-of-thought self-correction; relies on a single structured-output schema being correct |
| In-memory session store | Sessions evaporate on restart — acceptable per ASSIGNMENT.md, defended in README |
| `yfinance` over MCP | Free, unauthenticated, deterministic; MCP is a P2 stretch |
| SSE only, no JSON fallback | Required by spec — even error responses are SSE events |

---

### 1.2 Component Map

#### `SafetyGuard`
- **Responsibility:** Block harmful queries before any LLM is called; produce a distinct refusal message per harm category.
- **Inputs:** `query: str`
- **Outputs:** `SafetyVerdict(blocked: bool, category: str | None, message: str | None)`
- **Dependencies:** none — pure local computation
- **External services:** none
- **File location:** `src/safety.py`

#### `SafetyPatterns`
- **Responsibility:** The keyword/regex pattern library, one ruleset per harm category, plus an educational-allowlist that overrides on phrases like "what is", "explain", "how does the SEC".
- **Inputs:** none (loaded as module constants)
- **Outputs:** category → list[Pattern], category → refusal message
- **Dependencies:** none
- **File location:** `src/safety_patterns.py` (split from `safety.py` for testability)

#### `IntentClassifier`
- **Responsibility:** Single LLM call to classify a user query into one of 10 agents and extract entities, with awareness of prior turns.
- **Inputs:** `query: str`, `prior_turns: list[str]`, `llm: AsyncOpenAI` (injectable)
- **Outputs:** `ClassificationResult(agent, entities, safety_verdict)`
- **Dependencies:** `Schemas` (Pydantic models), `SessionStore` (read-only via the caller)
- **External services:** OpenAI Chat Completions (structured outputs / `response_format=json_schema`)
- **File location:** `src/classifier.py`

#### `ClassifierPrompt`
- **Responsibility:** Build the system prompt that encodes the 10-agent taxonomy, the entity vocabulary, and the follow-up resolution rules. Kept out of `classifier.py` so prompts can be tuned without touching the LLM-call path.
- **Inputs:** `prior_turns: list[str]`
- **Outputs:** `str` — full system prompt
- **Dependencies:** none
- **File location:** `src/classifier_prompt.py`

#### `SessionStore`
- **Responsibility:** Per-session list of prior user turns, capped at last N=5 to bound classifier prompt size.
- **Inputs:** `session_id: str`, `turn: str` (append) or just `session_id` (read)
- **Outputs:** `list[str]`
- **Dependencies:** none
- **External services:** none (in-memory `dict[str, deque[str]]`)
- **File location:** `src/session.py`

#### `Router`
- **Responsibility:** Dispatch a `ClassificationResult.agent` string to its handler. Maps unknown agent strings (e.g. `portfolio_query` from fixture) to the correct agent.
- **Inputs:** `ClassificationResult`, `user: dict`, `llm`
- **Outputs:** async generator of dict events to be SSE-encoded
- **Dependencies:** `PortfolioHealthAgent`, `StubAgents`
- **External services:** none
- **File location:** `src/router.py`

#### `PortfolioHealthAgent`
- **Responsibility:** Compute concentration risk, performance, benchmark comparison, and 1–3 plain-language observations for a user's holdings, plus mandatory disclaimer.
- **Inputs:** `user: dict`, `llm`
- **Outputs:** `PortfolioHealthResult` (Pydantic model serialized to dict)
- **Dependencies:** `MarketData`, `PortfolioMath`, `Observations` (LLM-generated text)
- **External services:** `yfinance` for prices, OpenAI for observation phrasing
- **File location:** `src/agents/portfolio_health.py`

#### `PortfolioMath`
- **Responsibility:** Pure functions for concentration %, total return, annualized return, alpha. No I/O, fully unit-testable without mocks.
- **Inputs:** positions list, current prices, FX rates, benchmark return
- **Outputs:** primitives (floats, dicts)
- **Dependencies:** none
- **File location:** `src/agents/portfolio_math.py`

#### `MarketData`
- **Responsibility:** Fetch live prices, FX rates, and benchmark returns. Wrap `yfinance` with try/except and a per-request cache.
- **Inputs:** ticker symbols, currencies
- **Outputs:** `dict[ticker → price_usd]`, `dict[currency → fx_rate_to_usd]`, benchmark return %
- **Dependencies:** none
- **External services:** `yfinance`
- **File location:** `src/market_data.py`

#### `StubAgents`
- **Responsibility:** Return a structured "not implemented" payload (intent, entities, message) for the 9 non-portfolio-health agents.
- **Inputs:** `ClassificationResult`
- **Outputs:** `dict` payload
- **Dependencies:** none
- **File location:** `src/agents/stubs.py`

#### `HTTPApp`
- **Responsibility:** FastAPI app exposing `POST /chat` (SSE) and `GET /healthz`. Orchestrates the pipeline and converts events to SSE frames.
- **Inputs:** HTTP request
- **Outputs:** SSE response stream
- **Dependencies:** `SafetyGuard`, `IntentClassifier`, `Router`, `SessionStore`
- **External services:** OpenAI (transitively)
- **File location:** `src/main.py`

#### `Schemas`
- **Responsibility:** Centralized Pydantic models — `SafetyVerdict`, `ClassificationResult`, `Observation`, `PortfolioHealthResult`, request/response bodies for `/chat`.
- **File location:** `src/schemas.py`

#### `Settings`
- **Responsibility:** Load env vars (`OPENAI_API_KEY`, `OPENAI_MODEL`, `APP_ENV`, timeout) once via `python-dotenv` + Pydantic.
- **File location:** `src/settings.py`

---

### 1.3 System Data Flow

A `POST /chat` request flows through the following stages. Steps marked **(stream)** push an SSE frame to the client; the connection stays open until `[DONE]`.

1. Client opens `POST /chat` with `{query, user_id, session_id?}`.
2. `HTTPApp` validates the request body via `ChatRequest` Pydantic model.
3. `HTTPApp` loads the user profile by `user_id` (currently from `fixtures/users/`; future: DB).
4. `HTTPApp` reads `prior_turns` from `SessionStore` for `session_id` (empty list if none).
5. `SafetyGuard.check(query)` runs synchronously. **(<10ms)**
   - If `blocked`: emit one `error` SSE event with category-specific message, then `[DONE]`. Pipeline ends.
6. `IntentClassifier.classify(query, prior_turns, llm)` runs (one LLM call). **(stream metadata once result returns)**
   - On LLM exception or schema parse failure: fall back to `agent="general_query"`, `entities={}`, `safety_verdict="pass"`, log error.
7. `HTTPApp` emits a `metadata` SSE event with `agent`, `entities`, `safety_verdict`.
8. `Router.dispatch(result, user, llm)` selects the agent function:
   - `portfolio_health` (and aliases like `portfolio_query`) → `PortfolioHealthAgent.run(user, llm)`
   - any other agent string → `StubAgents.run(result)`
9. The agent yields one or more event dicts. For `PortfolioHealthAgent`:
   - `MarketData` fetches prices and FX in parallel.
   - `PortfolioMath` computes concentration, performance, alpha.
   - `Observations` calls LLM (optional second LLM call — **only inside the agent, not the classifier**) to phrase 1–3 observations. If observations LLM fails, fall back to deterministic templated observations.
10. `HTTPApp` emits the agent's `result` event as SSE. **(stream)**
11. `SessionStore.append(session_id, query)` records the turn for future follow-ups.
12. `HTTPApp` emits `[DONE]` and closes the stream.

```
[Client]
   │  POST /chat {query, user_id, session_id}
   ▼
[HTTPApp / src/main.py]
   │  validate request, load user, read prior_turns
   ▼
[SafetyGuard / src/safety.py] ──── blocked? ───→ emit SSE error → [DONE]
   │  pass
   ▼
[IntentClassifier / src/classifier.py] ──── LLM call ────→ [OpenAI API]
   │  ClassificationResult                              ↓
   │                                       on failure: fallback to general_query
   │  emit SSE metadata event
   ▼
[Router / src/router.py]
   │
   ├─ if agent == "portfolio_health" or alias ─→ [PortfolioHealthAgent]
   │                                                  │
   │                                                  ├─→ [MarketData] ──→ [yfinance]
   │                                                  │       (prices, FX, benchmark)
   │                                                  ├─→ [PortfolioMath] (pure funcs)
   │                                                  └─→ [LLM observations] ──→ [OpenAI API]
   │                                                  ↓
   │                                          PortfolioHealthResult
   │
   └─ else ──→ [StubAgents] → structured not-implemented payload
   │
   ▼
[HTTPApp]
   │  emit SSE result event
   │  SessionStore.append(session_id, query)
   │  emit [DONE]
   ▼
[Client] (stream closed)
```

---

### 1.4 External Dependencies & Integrations

| Service / Library | Purpose | How it's used | Fallback if unavailable |
|---|---|---|---|
| **OpenAI API** | Intent classification + observation phrasing | `AsyncOpenAI.chat.completions.create(response_format={"type": "json_schema", ...})` | Classifier: deterministic fallback `general_query`. Observations: deterministic templates from `PortfolioMath` outputs |
| **`openai>=1.30.0`** | Python SDK for OpenAI | Imported in `classifier.py` and `agents/portfolio_health.py` | n/a (hard dep) |
| **`fastapi`** | Web framework | App + `/chat` endpoint + DI | n/a (hard dep) |
| **`sse-starlette`** | SSE response wrapper | `EventSourceResponse(generator)` in `main.py` | Could roll own; not blocking |
| **`pydantic` v2** | Validation + structured output schemas | All schemas in `src/schemas.py`; LLM `response_format` fed from `ClassificationResult.model_json_schema()` | n/a (hard dep) |
| **`yfinance`** | Live market data | `yf.Ticker(symbol).fast_info["last_price"]`, history for benchmark returns | Skip the missing ticker, emit a warning observation, continue |
| **`python-dotenv`** | Load `.env` | Called once in `settings.py` | OS env vars work without it |
| **`pytest` / `pytest-asyncio` / `pytest-mock`** | Test framework | All tests under `tests/` | n/a |
| **`httpx`** | Test client (FastAPI `TestClient` uses it) | Integration tests | n/a |

---

### 1.5 Data Flow & State Management

**Persisted vs in-memory:**
| Data | Lifetime | Storage |
|---|---|---|
| User profiles | Static, repo files | `fixtures/users/*.json` (loaded on demand) |
| Session prior turns | Process lifetime | In-memory `dict[session_id, deque[str](maxlen=5)]` |
| Market prices | Per-request | `dict` cache local to the agent call |
| Safety patterns | Process lifetime | Compiled regex constants in `safety_patterns.py` |
| LLM responses | None (no caching unless P2 dedupe stretch is built) | — |

**Data formats at boundaries:**
| Boundary | Format |
|---|---|
| HTTP request body | JSON → `ChatRequest` Pydantic model |
| Safety guard | `str` → `SafetyVerdict` Pydantic model |
| Classifier ↔ OpenAI | JSON Schema (auto-derived from `ClassificationResult.model_json_schema()`) |
| Router → Agent | `ClassificationResult` + `user: dict` |
| Agent → SSE | `dict` → JSON-encoded SSE `data:` frame |
| Session store | `str` (raw user turn) |

**Where validation happens:**
- HTTP boundary: FastAPI auto-validates request body against `ChatRequest`.
- LLM output: Pydantic `model_validate_json` on the LLM's content; failures trigger fallback.
- Agent output: Pydantic `model_validate` before emitting SSE result event.

**State passing:** All state flows by argument. No globals beyond `SessionStore` (a singleton initialized in `main.py`) and the safety pattern constants.

---

### 1.6 Error Propagation Map

| Failure | Caught at | Logged at | Surfaced to caller as | Retried? |
|---|---|---|---|---|
| Pydantic request validation fails | FastAPI auto | INFO | HTTP 422 (FastAPI default) — *not* SSE because the connection isn't established yet | No |
| Safety guard raises (should never happen) | `HTTPApp` outer try | ERROR | SSE `error` event with `code: "internal_error"`, then `[DONE]` | No |
| Safety guard blocks query | `SafetyGuard.check` (returns verdict, not exception) | INFO | SSE `error` event with `code: "safety_blocked"`, category-specific message | No |
| OpenAI `RateLimitError` | `IntentClassifier.classify` | WARN | Fallback to `general_query` classification, still streams a metadata event + general stub result | One retry with exponential backoff (1s) — then fallback |
| OpenAI `APITimeoutError` | `IntentClassifier.classify` | WARN | Same fallback as above | One retry — then fallback |
| OpenAI returns malformed JSON | `IntentClassifier.classify` | WARN | Fallback to `general_query` | No |
| Classifier returns agent not in taxonomy | `Router` | WARN | Route to `general_query` stub | No |
| `yfinance` returns no data for a ticker | `MarketData` | WARN | Skip the position; agent emits observation `"Could not fetch live price for X"` | One retry — then skip |
| Agent raises unexpected exception | `Router` outer try | ERROR | SSE `error` event with `code: "agent_error"`, then `[DONE]` | No |
| Pipeline exceeds `REQUEST_TIMEOUT_SECONDS` (10s) | `HTTPApp` `asyncio.wait_for` | ERROR | SSE `error` with `code: "timeout"`, then `[DONE]` | No |
| LLM observations call fails (in agent) | `PortfolioHealthAgent` | WARN | Use deterministic templated observations; result still emitted | No |

**Fail-fast vs continue:** The pipeline is fail-soft for everything except request validation. A single LLM failure must never crash the response.

---

### 1.7 Project File & Folder Structure (Final State)

```
Valura-ai/
├── .env.example                                # documented env var template
├── .gitignore                                  # excludes .env, __pycache__, venv
├── ASSIGNMENT.md                               # original assignment (do not delete)
├── CLAUDE.md                                   # Claude Code guidance
├── SPEC.md                                     # full spec (Phase 0 doc)
├── ARCHITECTURE.md                             # this file (Phase 0 doc)
├── README.md                                   # setup, decisions, video link (rewritten in Phase 10)
├── pytest.ini                                  # pytest config (untouched scaffold)
├── requirements.txt                            # pinned deps (extended in Phase 0)
├── .github/
│   ├── workflows/pytest.yml                    # CI runs pytest on push (untouched)
│   └── classroom/autograding.json              # 25+30+25+20 = 100 pts (untouched)
├── fixtures/                                   # untouched scaffold — all gold data lives here
│   ├── README.md
│   ├── users/                                  # 5 user profiles
│   ├── conversations/                          # 3 follow-up/topic-switch test cases
│   └── test_queries/
│       ├── intent_classification.json          # ~60 gold classification queries
│       └── safety_pairs.json                   # ~45 gold safety queries
├── src/
│   ├── __init__.py
│   ├── main.py                                 # FastAPI app, /chat SSE endpoint, pipeline orchestration
│   ├── settings.py                             # env config via dotenv + Pydantic Settings
│   ├── schemas.py                              # all Pydantic models (request, response, agent outputs)
│   ├── safety.py                               # SafetyGuard.check() — synchronous rule-based filter
│   ├── safety_patterns.py                      # regex patterns + refusal messages per harm category
│   ├── classifier.py                           # IntentClassifier.classify() — single LLM call + fallback
│   ├── classifier_prompt.py                    # system prompt builder for the classifier
│   ├── session.py                              # in-memory SessionStore, deque(maxlen=5) per session
│   ├── router.py                               # Router.dispatch() — agent string → handler
│   ├── market_data.py                          # MarketData wrapper around yfinance with cache + retries
│   └── agents/
│       ├── __init__.py
│       ├── portfolio_health.py                 # full implementation: fetch + compute + observe + disclaim
│       ├── portfolio_math.py                   # pure functions: concentration, return, alpha
│       └── stubs.py                            # structured "not implemented" responses for 9 agents
└── tests/
    ├── __init__.py                             # untouched scaffold
    ├── conftest.py                             # untouched scaffold (load_user, gold queries, mock_llm)
    ├── test_safety_pairs.py                    # SCAFFOLD — wired up in Phase 1
    ├── test_classifier_routing.py              # SCAFFOLD — wired up in Phase 3
    ├── test_portfolio_health_skeleton.py       # SCAFFOLD — wired up in Phase 6
    ├── test_session.py                         # NEW — Phase 4
    ├── test_portfolio_math.py                  # NEW — Phase 5/6 (pure unit tests, no mocks)
    ├── test_router.py                          # NEW — Phase 7
    ├── test_classifier_followup.py             # NEW — Phase 4 (multi-turn cases from fixtures/conversations)
    └── test_chat_endpoint.py                   # NEW — Phase 8 (FastAPI TestClient SSE integration)
```

---

## PART 2: PHASED IMPLEMENTATION PLAN

### Phasing Rules (followed exactly)
- Phase 0 sets up project skeleton, dependencies, gitignore, branch hygiene — nothing else.
- Each phase depends only on earlier phases; nothing forward-references later code.
- Each phase produces a green `pytest` run before merge.
- Each phase = its own `phase/<kebab-name>` branch, merged into `main` on completion.
- Phase 10 is the final "submission-ready" cleanup phase.

---

### Phase 0: Project Setup & Skeleton
**Branch:** `phase/0-setup`
**Goal:** Repo has the dependency tree, .gitignore, empty package skeletons, settings loader, and a smoke `pytest` run that confirms the harness wires up.
**Depends on:** none
**Estimated time:** 1.5 hours

#### What gets built:
- `.gitignore` — exclude `.env`, `__pycache__/`, `venv/`, `.pytest_cache/`, `*.pyc`, `.coverage`
- `requirements.txt` — extend scaffold with `yfinance`, `pydantic-settings`
- `src/__init__.py` (already exists, leave empty)
- `src/agents/__init__.py` — new empty package
- `src/settings.py` — `Settings` class loading `OPENAI_API_KEY`, `OPENAI_MODEL`, `APP_ENV`, `REQUEST_TIMEOUT_SECONDS` (default 10)
- `src/schemas.py` — empty placeholder file with module docstring (filled in Phase 2)
- Place `SPEC.md` and `ARCHITECTURE.md` in the project root (currently in `.claude/specs/`)

#### Implementation steps:
1. Create branch: `git checkout -b phase/0-setup`
2. Verify/extend `.gitignore` (already exists from scaffold — confirm coverage)
3. Append `yfinance>=0.2.40` and `pydantic-settings>=2.2.0` to `requirements.txt`
4. Create `src/agents/__init__.py`
5. Create `src/settings.py` with `Settings(BaseSettings)`
6. Create empty `src/schemas.py` (just the module docstring)
7. Run `pytest tests/ -v` — all skeleton tests should still pass (they are `@pytest.mark.skip`)
8. Copy `SPEC.md` from `.claude/specs/SPEC.md` to repo root if not already there [it is]; copy `ARCHITECTURE.md` to root.

#### Commits to make in this phase:
1. `chore(setup): extend .gitignore and requirements with yfinance + pydantic-settings`
2. `chore(setup): scaffold src/agents package and src/schemas placeholder`
3. `feat(settings): add Settings loader for env vars with Pydantic`
4. `docs(setup): place SPEC.md and ARCHITECTURE.md at repo root`

#### Tests to write / pass:
- No new tests in this phase. Existing skeleton tests must still load (pytest collection succeeds).

#### Definition of Done:
- [ ] `pip install -r requirements.txt` succeeds in a fresh venv
- [ ] `pytest tests/ -v` runs without import errors (skeleton tests are `skipped`, not `errored`)
- [ ] `python -c "from src.settings import Settings; Settings()"` runs without missing-var errors when no API key is set [ASSUMED — `OPENAI_API_KEY` made optional with empty default]
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-0): setup complete, skeleton compiles"
git checkout main
git merge phase/0-setup
git push origin main
git tag phase-0-complete
git checkout -b phase/1-safety-guard
```

---

### Phase 1: Safety Guard
**Branch:** `phase/1-safety-guard`
**Goal:** A pure-Python rule-based safety guard that achieves ≥95% recall and ≥90% pass-through against `fixtures/test_queries/safety_pairs.json`, with 6 distinct refusal messages.
**Depends on:** Phase 0
**Estimated time:** 3 hours

#### What gets built:
- `src/safety_patterns.py` — 6 categories' worth of regex patterns + the educational allowlist
- `src/safety.py` — `check(query: str) -> SafetyVerdict`
- `src/schemas.py` (extended) — `SafetyVerdict` Pydantic model
- `tests/test_safety_pairs.py` — remove `@pytest.mark.skip` and wire up the import

#### Implementation steps:
1. Add `SafetyVerdict` to `src/schemas.py` (`blocked: bool`, `category: str | None`, `message: str | None`)
2. Build `src/safety_patterns.py`: per-category regex lists for `insider_trading`, `market_manipulation`, `money_laundering`, `guaranteed_returns`, `reckless_advice`, `sanctions_evasion` + a `fraud` catch-all
3. Build the educational allowlist (`what is`, `explain`, `how does the SEC`, `what are the penalties`, `is X illegal`, etc.) that *overrides* a category match
4. Build refusal messages — 6 distinct, professional, references the right regulatory framing per category
5. Build `check(query)`: lowercase query → check allowlist → if educational, return pass → else iterate categories, return first hit
6. Wire up `tests/test_safety_pairs.py` (remove skips, import `from src.safety import check`)
7. Iterate on patterns until both thresholds are met against the gold fixture
8. Confirm safety guard runs in <10ms (microbenchmark with `timeit`)

#### Commits to make in this phase:
1. `feat(schemas): add SafetyVerdict Pydantic model`
2. `feat(safety): add regex pattern library for 6 harm categories`
3. `feat(safety): add educational allowlist override`
4. `feat(safety): implement check() with category dispatch and 6 distinct messages`
5. `test(safety): activate gold-set tests; safety_pairs.json passing thresholds`
6. `perf(safety): confirm <10ms p99 with microbenchmark`

#### Tests to write / pass:
- `tests/test_safety_pairs.py::test_safety_recall_and_passthrough` — ≥95% block recall, ≥90% educational pass-through
- `tests/test_safety_pairs.py::test_safety_guard_returns_distinct_categories` — ≥4 distinct messages

#### Definition of Done:
- [ ] `pytest tests/test_safety_pairs.py -v` — both tests pass
- [ ] No `@pytest.mark.skip` decorators left in `test_safety_pairs.py`
- [ ] Each category has a distinct refusal message
- [ ] Microbenchmark confirms `check()` returns in <10ms for the longest fixture query
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-1): safety guard complete and passing thresholds"
git checkout main
git merge phase/1-safety-guard
git push origin main
git tag phase-1-complete
git checkout -b phase/2-schemas
```

---

### Phase 2: Shared Pydantic Schemas
**Branch:** `phase/2-schemas`
**Goal:** All shared data contracts (`ChatRequest`, `ClassificationResult`, `Observation`, `PortfolioHealthResult`, etc.) defined and unit-tested before any consumer is built.
**Depends on:** Phase 1
**Estimated time:** 2 hours

#### What gets built:
- `src/schemas.py` (full) — `ChatRequest`, `ChatResponseEvent`, `ClassificationResult`, `Entity` (TypedDict / dict alias), `Observation`, `ConcentrationRisk`, `Performance`, `BenchmarkComparison`, `PortfolioHealthResult`, `StubAgentResult`
- `tests/test_schemas.py` — round-trip JSON serialization tests for each model + the LLM-output JSON Schema export test

#### Implementation steps:
1. Define `ClassificationResult` with `agent: Literal[...10 agent strings...]`, `entities: dict[str, Any]`, `safety_verdict: Literal["pass", "flag"]`
2. Confirm `ClassificationResult.model_json_schema()` produces a structured-output-compatible schema (no `$ref` issues, `additionalProperties: false`, `required: [...]`)
3. Define `PortfolioHealthResult` with nested `concentration_risk`, `performance`, `benchmark_comparison`, `observations: list[Observation]`, `disclaimer: str`
4. Define `ChatRequest(query: str, user_id: str, session_id: str | None = None)` and `ChatResponseEvent(type: Literal[...], ...)`.
5. Add `tests/test_schemas.py` — for each model: build a valid instance, serialize, deserialize, assert equality
6. Add a test that asserts `ClassificationResult.agent` literal contains all 10 taxonomy strings + the alias `portfolio_query` is *not* in the literal (it's resolved at the router, not classifier)

#### Commits to make in this phase:
1. `feat(schemas): add ClassificationResult with 10-agent literal and entities dict`
2. `feat(schemas): add PortfolioHealthResult, Observation, and nested risk/performance models`
3. `feat(schemas): add ChatRequest and ChatResponseEvent for HTTP boundary`
4. `test(schemas): add round-trip serialization tests for all models`

#### Tests to write / pass:
- `tests/test_schemas.py::test_classification_result_round_trip`
- `tests/test_schemas.py::test_portfolio_health_result_round_trip`
- `tests/test_schemas.py::test_chat_request_validates_required_fields`
- `tests/test_schemas.py::test_classification_result_json_schema_is_strict`

#### Definition of Done:
- [ ] `pytest tests/test_schemas.py -v` — all pass
- [ ] `ClassificationResult.model_json_schema()` validates as strict JSON Schema for OpenAI structured outputs
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-2): schemas complete, all round-trip tests passing"
git checkout main
git merge phase/2-schemas
git push origin main
git tag phase-2-complete
git checkout -b phase/3-classifier
```

---

### Phase 3: Intent Classifier (Single-Turn)
**Branch:** `phase/3-classifier`
**Goal:** Single-turn classification ≥85% routing accuracy on `intent_classification.json` with a deterministic fallback on LLM failure. Follow-up handling is Phase 4.
**Depends on:** Phase 2
**Estimated time:** 4 hours

#### What gets built:
- `src/classifier_prompt.py` — `build_system_prompt(prior_turns: list[str]) -> str`
- `src/classifier.py` — `async classify(query, prior_turns, llm) -> ClassificationResult`
- `tests/test_classifier_routing.py` — wire up the existing skeleton; build a `mock_llm` that returns canned responses per query keyword
- `tests/test_classifier_fallback.py` — new file; ensures LLM exception falls back to `general_query`

#### Implementation steps:
1. Build the classifier system prompt: encodes the agent taxonomy descriptions verbatim from `intent_classification.json`, the entity vocabulary, ticker-suffix rules, and the multi-intent rule ("primary intent wins")
2. Implement `classify()` using `openai.AsyncOpenAI.chat.completions.create` with `response_format={"type": "json_schema", "json_schema": {"name": "ClassificationResult", "strict": True, "schema": ClassificationResult.model_json_schema()}}`
3. Wrap the call with one-shot retry on `RateLimitError`/`APITimeoutError` then fallback on any other exception
4. Validate output with `ClassificationResult.model_validate_json(content)` — fallback on failure
5. Map `agent` strings not in the literal taxonomy (e.g. an LLM hallucination) to `general_query`
6. Wire `tests/test_classifier_routing.py`: build a `mock_llm` fixture that, given a query keyword, returns a canned JSON string matching `ClassificationResult`. Strategy: a small dispatch table keyed on substrings of the gold queries
7. Run gold set; tune prompt until `accuracy ≥ 0.85`

#### Commits to make in this phase:
1. `feat(classifier): build classifier system prompt with taxonomy and entity vocabulary`
2. `feat(classifier): implement classify() with structured output and Pydantic validation`
3. `feat(classifier): add LLM error fallback and one-shot retry on rate limit/timeout`
4. `test(classifier): wire routing accuracy test against gold set; passing ≥85%`
5. `test(classifier): add LLM-failure fallback test`

#### Tests to write / pass:
- `tests/test_classifier_routing.py::test_classifier_routing_accuracy` — ≥85% accuracy
- `tests/test_classifier_routing.py::test_classifier_entity_extraction` — soft (reports rate, doesn't fail)
- `tests/test_classifier_fallback.py::test_classifier_falls_back_on_llm_exception`
- `tests/test_classifier_fallback.py::test_classifier_falls_back_on_malformed_json`

#### Definition of Done:
- [ ] `pytest tests/test_classifier_routing.py tests/test_classifier_fallback.py -v` — all pass
- [ ] Routing accuracy ≥85% (printed in test output for evidence)
- [ ] LLM failure never raises an exception out of `classify()`
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-3): single-turn classifier passing 85% routing threshold"
git checkout main
git merge phase/3-classifier
git push origin main
git tag phase-3-complete
git checkout -b phase/4-session-followup
```

---

### Phase 4: Session Store & Follow-up Resolution
**Branch:** `phase/4-session-followup`
**Goal:** Multi-turn classification works for the cases in `fixtures/conversations/`. Pronoun and entity carryover ("what about AMD?") is resolved correctly.
**Depends on:** Phase 3
**Estimated time:** 3 hours

#### What gets built:
- `src/session.py` — `SessionStore` with `dict[str, deque[str]]`, `append`, `get`, capped at last 5 turns
- `src/classifier_prompt.py` (extended) — prompt section that injects `prior_turns` with explicit "treat the most recent prior turn as context for resolving pronouns and dropped entities"
- `tests/test_session.py` — unit tests for the store
- `tests/test_classifier_followup.py` — runs the 3 conversation files end-to-end through `classify()` with a richer mock_llm

#### Implementation steps:
1. Build `SessionStore` (in-memory; `maxlen=5`)
2. Extend the classifier prompt with the prior-turns block and the carryover rules from `fixtures/conversations/follow_up_session.json` (e.g. ambiguous "compare them" should resolve to the union of recent tickers)
3. Add a `prior_turns` parameter to the canned `mock_llm` so it can return the expected agent for follow-up cases
4. Map fixture `agent: "portfolio_query"` → treat as alias of `portfolio_health` at the **router** level (Phase 7), but the classifier may also legitimately output `portfolio_health` directly here
5. Iterate on prompt until all 3 conversation fixtures pass

#### Commits to make in this phase:
1. `feat(session): in-memory SessionStore with deque(maxlen=5) per session_id`
2. `feat(classifier): inject prior_turns into prompt with carryover rules`
3. `test(session): unit tests for append/get/cap behavior`
4. `test(classifier): follow-up resolution against fixtures/conversations/*.json`

#### Tests to write / pass:
- `tests/test_session.py::test_session_store_caps_at_five_turns`
- `tests/test_session.py::test_session_store_isolated_per_session_id`
- `tests/test_classifier_followup.py::test_followup_session_carries_ticker`
- `tests/test_classifier_followup.py::test_multi_intent_session_topic_switch`
- `tests/test_classifier_followup.py::test_ambiguous_session_handles_typos`

#### Definition of Done:
- [ ] All 3 conversation fixtures pass (each test case in `test_cases[]` is a sub-assertion)
- [ ] SessionStore unit tests pass
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-4): session store and follow-up resolution complete"
git checkout main
git merge phase/4-session-followup
git push origin main
git tag phase-4-complete
git checkout -b phase/5-market-data
```

---

### Phase 5: Market Data Layer
**Branch:** `phase/5-market-data`
**Goal:** A reliable `yfinance` wrapper that fetches prices, FX rates, and benchmark returns with retries, caching, and graceful skipping of missing tickers.
**Depends on:** Phase 2
**Estimated time:** 2.5 hours

#### What gets built:
- `src/market_data.py` — `MarketData` class with `get_prices(tickers)`, `get_fx_rates(currencies, base)`, `get_benchmark_return(symbol, period)`
- `src/agents/portfolio_math.py` — pure functions for concentration %, total return, annualized return, alpha
- `tests/test_market_data.py` — mock-based tests (no real network) using `pytest-mock` to patch `yfinance.Ticker`
- `tests/test_portfolio_math.py` — pure unit tests, no mocks

#### Implementation steps:
1. Build `MarketData.get_prices(tickers: list[str]) -> dict[str, float]`. Use `yf.Tickers(...)` for batched fetch; on missing ticker, omit from the dict (don't raise)
2. Build `get_fx_rates(currencies: list[str], base: str) -> dict[str, float]` using `yf.Ticker("EURUSD=X")`-style symbols
3. Build `get_benchmark_return(symbol: str, period: str = "1y") -> float` using `yf.Ticker(symbol).history(period=period)`
4. Add a per-instance dict cache so that repeated lookups inside one request don't refetch
5. Wrap each fetch in try/except; log warnings; never raise
6. Build `portfolio_math.py`: `concentration(positions, prices, fx) -> ConcentrationRisk`, `performance(positions, prices, fx) -> Performance`, `alpha(portfolio_return, benchmark_return) -> float`
7. Write pure unit tests for `portfolio_math` covering: empty positions, single concentrated position, multi-currency, missing prices

#### Commits to make in this phase:
1. `feat(market-data): yfinance wrapper for prices with batched fetch and graceful missing-ticker handling`
2. `feat(market-data): FX rate and benchmark return helpers`
3. `feat(portfolio-math): pure functions for concentration, performance, alpha`
4. `test(market-data): mocked yfinance integration tests`
5. `test(portfolio-math): pure unit tests for math (no mocks)`

#### Tests to write / pass:
- `tests/test_market_data.py::test_get_prices_skips_missing_ticker`
- `tests/test_market_data.py::test_get_prices_caches_within_request`
- `tests/test_portfolio_math.py::test_concentration_empty_returns_zeros`
- `tests/test_portfolio_math.py::test_concentration_single_position_is_100_pct`
- `tests/test_portfolio_math.py::test_concentration_flag_thresholds`  # >40 = high, 25–40 = moderate, <25 = low
- `tests/test_portfolio_math.py::test_performance_total_return_with_fx`

#### Definition of Done:
- [ ] `pytest tests/test_market_data.py tests/test_portfolio_math.py -v` — all pass
- [ ] No real `yfinance` network calls in tests (CI must work offline)
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-5): market data layer and portfolio math complete"
git checkout main
git merge phase/5-market-data
git push origin main
git tag phase-5-complete
git checkout -b phase/6-portfolio-health
```

---

### Phase 6: Portfolio Health Agent
**Branch:** `phase/6-portfolio-health`
**Goal:** `src.agents.portfolio_health.run(user, llm)` produces a complete `PortfolioHealthResult` for all 5 user fixtures (including empty `usr_004` and concentrated `usr_003`), with disclaimer.
**Depends on:** Phase 5
**Estimated time:** 4 hours

#### What gets built:
- `src/agents/portfolio_health.py` — `async run(user: dict, llm) -> dict`
- `tests/test_portfolio_health_skeleton.py` — wire up the 3 existing skeleton tests
- `tests/test_portfolio_health.py` — extended tests for all 5 users + multi-currency case

#### Implementation steps:
1. Implement `run(user, llm)`:
   - If `positions` is empty: return BUILD-oriented result with empty metrics, observation pointing to risk profile, full disclaimer
   - Otherwise: fetch prices via `MarketData`, fetch FX rates if multi-currency, compute metrics via `portfolio_math`
2. Determine benchmark from `user["preferences"]["preferred_benchmark"]` (default `"S&P 500"` for US, `"MSCI World"` for non-US users [ASSUMED])
3. Compute alpha against benchmark
4. Generate 1–3 observations: try LLM call for natural phrasing using the metrics as context; on failure, fall back to deterministic templated observations ("Top position X represents N% of portfolio")
5. Always include `disclaimer: "This is not investment advice..."` (constant string)
6. Wire skeleton tests; add full coverage

#### Commits to make in this phase:
1. `feat(portfolio-health): implement run() with empty/normal/multi-currency branches`
2. `feat(portfolio-health): LLM-generated observations with deterministic fallback`
3. `feat(portfolio-health): benchmark selection by user country and preference`
4. `test(portfolio-health): activate skeleton tests for usr_001/003/004`
5. `test(portfolio-health): extended coverage for usr_006 multi-currency and usr_008 retiree`

#### Tests to write / pass:
- `tests/test_portfolio_health_skeleton.py::test_portfolio_health_does_not_crash_on_empty_portfolio`
- `tests/test_portfolio_health_skeleton.py::test_portfolio_health_flags_concentration`
- `tests/test_portfolio_health_skeleton.py::test_portfolio_health_includes_disclaimer`
- `tests/test_portfolio_health.py::test_usr_006_multi_currency_aggregates_to_base`
- `tests/test_portfolio_health.py::test_disclaimer_contains_not_investment_advice`
- `tests/test_portfolio_health.py::test_observations_fallback_when_llm_fails`

#### Definition of Done:
- [ ] All `tests/test_portfolio_health*.py` tests pass
- [ ] `usr_004` empty case returns a result, not a crash, with a BUILD-oriented observation
- [ ] `usr_003` concentration `flag` is `"high"`
- [ ] `usr_006` does not crash on multi-currency
- [ ] All responses include a `disclaimer` containing "not investment advice"
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-6): portfolio health agent complete; all 5 user fixtures pass"
git checkout main
git merge phase/6-portfolio-health
git push origin main
git tag phase-6-complete
git checkout -b phase/7-router-stubs
```

---

### Phase 7: Router & Stub Agents
**Branch:** `phase/7-router-stubs`
**Goal:** Every classifier output (including unknown agents like `portfolio_query` and hallucinations) is dispatched without crashing; the 9 non-portfolio-health agents return structured stubs.
**Depends on:** Phase 6
**Estimated time:** 1.5 hours

#### What gets built:
- `src/agents/stubs.py` — `def run(result: ClassificationResult) -> dict` returning structured not-implemented payload
- `src/router.py` — `async dispatch(result, user, llm)` async generator
- `tests/test_router.py` — tests every taxonomy string + alias + unknown string

#### Implementation steps:
1. Build `stubs.run()`: returns `{"intent": result.agent, "entities": result.entities, "agent_would_have_handled": result.agent, "message": "Agent not implemented in this build", "disclaimer": "..."}`
2. Build `router.dispatch()`: routing table maps each of the 10 taxonomy strings + the alias `portfolio_query` → handler; default branch routes unknown strings to the `general_query` stub
3. Test each route returns the right handler's output without raising

#### Commits to make in this phase:
1. `feat(stubs): structured not-implemented response for non-portfolio agents`
2. `feat(router): dispatch table for 10 agents + portfolio_query alias`
3. `test(router): coverage for every taxonomy string and unknown fallback`

#### Tests to write / pass:
- `tests/test_router.py::test_router_dispatches_portfolio_health`
- `tests/test_router.py::test_router_dispatches_market_research_to_stub`
- `tests/test_router.py::test_router_handles_portfolio_query_alias`
- `tests/test_router.py::test_router_falls_back_for_unknown_agent`
- `tests/test_router.py::test_stub_includes_intent_and_entities`

#### Definition of Done:
- [ ] `pytest tests/test_router.py -v` — all pass
- [ ] No agent string causes a crash
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-7): router and stubs complete"
git checkout main
git merge phase/7-router-stubs
git push origin main
git tag phase-7-complete
git checkout -b phase/8-http-sse
```

---

### Phase 8: HTTP Layer & SSE Streaming
**Branch:** `phase/8-http-sse`
**Goal:** `POST /chat` runs the full pipeline end-to-end and streams SSE events to the client; errors stream as SSE error events; pipeline timeout enforced.
**Depends on:** Phase 7
**Estimated time:** 3 hours

#### What gets built:
- `src/main.py` — FastAPI app, `POST /chat`, `GET /healthz`
- `tests/test_chat_endpoint.py` — integration tests using FastAPI's `TestClient` (which is sync) plus httpx's async client for SSE
- A small user-loader helper (could live in `main.py` or `src/users.py`) that reads from `fixtures/users/`

#### Implementation steps:
1. Build `main.py`: load `Settings`, instantiate `SessionStore`, define request handler
2. The handler:
   - Validate `ChatRequest`
   - Load user from fixtures (or accept `user_context` in the body as override)
   - Read prior turns from `SessionStore`
   - Wrap everything in `asyncio.wait_for(..., timeout=Settings().REQUEST_TIMEOUT_SECONDS)`
   - Call safety guard → emit error event if blocked → close
   - Call classifier → emit metadata event
   - Call router → consume async generator → emit each event as SSE
   - Append turn to session
   - Emit `[DONE]`
3. SSE format: use `sse_starlette.EventSourceResponse(generator)` with each yield being `{"data": json.dumps({...})}`
4. Add `GET /healthz` returning `{"ok": true}`
5. Integration tests:
   - Mock `IntentClassifier.classify` and `PortfolioHealthAgent.run` (or pass a mock `llm`)
   - Assert SSE frames contain expected events in order
   - Test the safety-blocked path
   - Test the pipeline-timeout path (mock classifier to sleep > timeout)

#### Commits to make in this phase:
1. `feat(api): FastAPI app skeleton with Settings and SessionStore singleton`
2. `feat(api): /chat endpoint orchestrating safety → classifier → router → SSE`
3. `feat(api): pipeline timeout via asyncio.wait_for with structured error event`
4. `feat(api): /healthz endpoint`
5. `test(api): integration tests for happy path, safety block, and timeout`

#### Tests to write / pass:
- `tests/test_chat_endpoint.py::test_chat_safe_query_streams_metadata_then_result`
- `tests/test_chat_endpoint.py::test_chat_blocked_query_streams_error_event`
- `tests/test_chat_endpoint.py::test_chat_timeout_streams_timeout_error`
- `tests/test_chat_endpoint.py::test_chat_session_history_persists_across_turns`
- `tests/test_chat_endpoint.py::test_healthz_returns_ok`

#### Definition of Done:
- [ ] `pytest tests/test_chat_endpoint.py -v` — all pass
- [ ] `uvicorn src.main:app` starts without errors locally
- [ ] `curl -N -X POST http://localhost:8000/chat -d '{"query":"how is my portfolio?","user_id":"usr_001"}' -H "Content-Type: application/json"` streams SSE frames in real time (manual smoke test, documented in README)
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-8): HTTP layer and SSE streaming complete"
git checkout main
git merge phase/8-http-sse
git push origin main
git tag phase-8-complete
git checkout -b phase/9-perf-hardening
```

---

### Phase 9: Performance Validation & Hardening
**Branch:** `phase/9-perf-hardening`
**Goal:** Measured first-token latency < 2s, end-to-end < 6s, cost-per-query < $0.05; pre-existing hidden eval risks mitigated by improving prompt edge-cases.
**Depends on:** Phase 8
**Estimated time:** 2 hours

#### What gets built:
- `scripts/measure_latency.py` — runs N=20 sample queries, prints p50/p95 first-token and end-to-end timings
- `scripts/measure_cost.py` — calls classifier 50 times with `OPENAI_MODEL=gpt-4.1`, sums token usage × pricing, prints $/query
- README sections (filled in Phase 10): "Performance Measurements"
- Prompt tweaks if hidden-set risk uncovered: edge-case queries like single-ticker-no-verb, gibberish, multi-intent

#### Implementation steps:
1. Write `scripts/measure_latency.py` — use `httpx.AsyncClient` against locally running server with mocked OpenAI for deterministic timing of code path
2. Write `scripts/measure_cost.py` — actually call OpenAI (requires real API key) with `gpt-4.1` for a sample of 50 gold queries, log `usage.prompt_tokens` + `usage.completion_tokens`, multiply by current pricing
3. Run measurements; capture numbers
4. Re-run gold-set tests with `gpt-4.1` (manual run with API key, not in CI) to confirm routing accuracy holds
5. Add prompt patches if any class of queries fails > expected on the hidden-set heuristic (check: edge cases in `intent_classification.json` like `"AAPL"` alone, `"abcdefg"`, multi-intent queries)
6. Confirm safety guard <10ms still holds with `tests/test_safety_pairs.py::test_safety_guard_latency` [NEW]

#### Commits to make in this phase:
1. `chore(scripts): add latency measurement script`
2. `chore(scripts): add cost-per-query measurement script`
3. `perf(classifier): tune prompt for edge-case queries (single ticker, gibberish, multi-intent)`
4. `test(safety): add explicit <10ms latency assertion`

#### Tests to write / pass:
- `tests/test_safety_pairs.py::test_safety_guard_latency_under_10ms` (uses `time.perf_counter`)
- All previous tests still pass

#### Definition of Done:
- [ ] Measured p95 first-token < 2s (recorded in README)
- [ ] Measured p95 end-to-end < 6s (recorded in README)
- [ ] Measured cost-per-query at `gpt-4.1` < $0.05 (recorded in README)
- [ ] Safety guard p99 < 10ms (asserted in test)
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-9): performance validated, all NFR targets met"
git checkout main
git merge phase/9-perf-hardening
git push origin main
git tag phase-9-complete
git checkout -b phase/10-submission-ready
```

---

### Phase 10: Submission-Ready
**Branch:** `phase/10-submission-ready`
**Goal:** README is the single source of truth; defence video is recorded and linked; final `pytest tests/ -v` runs green; nothing left in a half-written state.
**Depends on:** Phase 9
**Estimated time:** 2 hours

#### What gets built:
- `README.md` — completely rewritten: setup, env vars table, library decisions, performance numbers, defence video URL, `curl` example
- Final review of `.gitignore`, `requirements.txt`, no dead code, no `print` statements

#### Implementation steps:
1. Rewrite `README.md` — kill the placeholder, add: project description (one paragraph), setup, environment table, run instructions, test instructions, performance measurements, library justifications, decision log (in-memory session + rule-based safety + yfinance), video URL placeholder
2. Run `pytest tests/ -v` clean
3. Run a final `grep -r "TODO\|FIXME\|XXX" src/ tests/` and resolve each
4. Run `python -m py_compile src/**/*.py` (or equivalent) to confirm no syntax errors anywhere
5. Record defence video (≤10 min) following the SPEC.md video plan
6. Upload as unlisted YouTube; paste URL into README
7. Final commit

#### Commits to make in this phase:
1. `docs(readme): rewrite with setup, env, decisions, performance, video URL`
2. `chore: final cleanup — remove TODOs, dead code, prints`
3. `docs(readme): paste defence video URL`

#### Tests to write / pass:
- The full suite: `pytest tests/ -v` — zero failures, zero errors

#### Definition of Done:
- [ ] `pytest tests/ -v` — fully green
- [ ] CI on GitHub Actions — green on latest push
- [ ] README has setup, env table, performance numbers, library justifications, decision log, video URL
- [ ] Defence video ≤ 10 minutes, unlisted, accessible
- [ ] Git log shows ≥30 commits across all phases
- [ ] No `.env` or secrets committed
- [ ] Submission form filled (if applicable)
- [ ] Branch merged to `main`

#### Git commands at end of phase:
```bash
git add .
git commit -m "chore(phase-10): submission ready — README polished, video linked, all tests green"
git checkout main
git merge phase/10-submission-ready
git push origin main
git tag submission
```

---

## PART 3: MASTER TIMELINE

### 3.1 Phase Schedule

Assuming the assignment was accepted on **2026-05-04** with a **3-day deadline → 2026-05-07 23:59**, total estimated focused work ≈ **24.5 hours**, spread across 3 days at ~8 hrs/day with buffer.

| Phase | Branch | Est. Hours | Start | End | Status |
|-------|--------|------------|-------|-----|--------|
| 0 | `phase/0-setup` | 1.5h | Day 1 09:00 | Day 1 10:30 | ⬜ Not started |
| 1 | `phase/1-safety-guard` | 3.0h | Day 1 10:30 | Day 1 13:30 | ⬜ Not started |
| 2 | `phase/2-schemas` | 2.0h | Day 1 14:30 | Day 1 16:30 | ⬜ Not started |
| 3 | `phase/3-classifier` | 4.0h | Day 1 16:30 | Day 1 20:30 | ⬜ Not started |
| 4 | `phase/4-session-followup` | 3.0h | Day 2 09:00 | Day 2 12:00 | ⬜ Not started |
| 5 | `phase/5-market-data` | 2.5h | Day 2 13:00 | Day 2 15:30 | ⬜ Not started |
| 6 | `phase/6-portfolio-health` | 4.0h | Day 2 15:30 | Day 2 19:30 | ⬜ Not started |
| 7 | `phase/7-router-stubs` | 1.5h | Day 3 09:00 | Day 3 10:30 | ⬜ Not started |
| 8 | `phase/8-http-sse` | 3.0h | Day 3 10:30 | Day 3 13:30 | ⬜ Not started |
| 9 | `phase/9-perf-hardening` | 2.0h | Day 3 14:30 | Day 3 16:30 | ⬜ Not started |
| 10 | `phase/10-submission-ready` | 2.0h | Day 3 16:30 | Day 3 18:30 | ⬜ Not started |
| **Buffer** | — | **3.0h** | Day 3 18:30 | Day 3 21:30 | reserved for slippage |

Status icons: ⬜ Not started · 🔄 In progress · ✅ Complete · 🚨 Blocked

### 3.2 Critical Path

The 5 items below, if delayed, push the deadline. Each has a mitigation.

1. **Phase 1 — Safety guard hits both thresholds (≥95% recall, ≥90% pass-through).**
   *Why critical:* 25 autograding points. The dual threshold is hard — over-block kills pass-through; under-block kills recall.
   *Mitigation:* Build the educational allowlist *first*; it's the lever that prevents over-blocking. If thresholds aren't met after 2h of tuning, bias toward recall (≥95%) and accept passing the test with a documented tradeoff in README.

2. **Phase 3 — Classifier ≥85% routing accuracy on the gold set, generalizes to hidden set.**
   *Why critical:* 30 autograding points; the mock_llm strategy is non-trivial (must respond appropriately for every gold query).
   *Mitigation:* The mock_llm should pattern-match on the actual gold queries (deterministic). Test against `gpt-4o-mini` once locally to confirm prompt generalizes. Don't memorize the gold set — write a generic prompt.

3. **Phase 6 — Portfolio Health passes all 5 user fixtures (especially `usr_004` and `usr_006`).**
   *Why critical:* 25 autograding points; multi-currency and empty-portfolio are real failure modes that the assignment explicitly calls out.
   *Mitigation:* Implement the empty-portfolio path *first* (returns BUILD message, no math). Then the normal path. Add multi-currency last with FX fetch.

4. **Phase 8 — `/chat` endpoint streams SSE correctly with the timeout enforced.**
   *Why critical:* SSE is required by spec; a JSON-only response is disqualifying. Timeout failure causes test flakes.
   *Mitigation:* Use `sse_starlette.EventSourceResponse` with a generator that yields properly-shaped dicts; do not roll your own. Test SSE parsing with `httpx.AsyncClient.stream()` in tests.

5. **Phase 10 — Defence video recorded ≤ 10 minutes.**
   *Why critical:* >10 min = auto-rejection; can't be fixed after submission.
   *Mitigation:* Rehearse once before recording. Have the demo script ready (`curl` command preloaded). If running long, cut the live demo in favor of the architecture walkthrough.

### 3.3 Time Buffers

- **Built-in buffer:** 3 hours reserved on Day 3 (18:30–21:30) for slippage.
- **What gets cut first if behind schedule (P2 features):** All P2 items per SPEC.md — dedupe cache, embedding pre-classifier, per-tenant model selection, rate limiting, MCP integration. None of these affect autograding.
- **Minimum viable submission (must exist to not be disqualified):**
  - Phases 0, 1, 2, 3, 6, 7, 8 — the spine without follow-up handling, performance scripts, or polish
  - Tests for safety, classifier, portfolio health passing
  - Working `/chat` SSE endpoint
  - Bare-minimum README with setup + env vars + a recorded video
  - Incremental git history (≥10 commits)

If on Day 3 morning you're still in Phase 4, **skip directly to Phase 6** and merge follow-up handling into Phase 4 + 6 as a single combined effort. Phase 9 is the second-most cuttable phase (performance numbers can be estimated rather than measured if absolutely necessary, with the tradeoff documented in README).

---

## PART 4: GIT BRANCH STRATEGY (COMPLETE)

### Branch Map

```
main
├── phase/0-setup                  ← merged first
├── phase/1-safety-guard           ← merged second
├── phase/2-schemas
├── phase/3-classifier
├── phase/4-session-followup
├── phase/5-market-data
├── phase/6-portfolio-health
├── phase/7-router-stubs
├── phase/8-http-sse
├── phase/9-perf-hardening
└── phase/10-submission-ready      ← final merge before submit
```

### Full Git Workflow

```bash
# Once at the start
git checkout main
git pull origin main

# Starting each phase
git checkout -b phase/<phase-name>

# During a phase — commit often, after each logical unit
git add <specific files>
git commit -m "<type>(<scope>): <imperative description>"

# Finishing a phase
git checkout main
git pull origin main
git merge phase/<phase-name> --no-ff -m "merge phase/<phase-name>: <one-line summary>"
git push origin main
git tag phase-<N>-complete
git push origin --tags

# Move to the next phase
git checkout -b phase/<next-phase-name>
```

### Commit Message Reference

| Prefix | Meaning |
|---|---|
| `feat(scope):` | New capability added |
| `fix(scope):` | Bug fixed |
| `test(scope):` | Tests added or updated |
| `docs(scope):` | Documentation updated |
| `refactor(scope):` | Code restructured, no behavior change |
| `chore(scope):` | Setup, config, dependencies |
| `perf(scope):` | Performance improvement |

Scopes used in this project: `setup`, `safety`, `schemas`, `classifier`, `session`, `market-data`, `portfolio-math`, `portfolio-health`, `router`, `stubs`, `api`, `readme`, `phase-N`.

### What NEVER goes in git

- `.env` files (secrets) — covered by `.gitignore`
- `__pycache__/`, `*.pyc` — covered by `.gitignore`
- Any file containing `OPENAI_API_KEY`, `sk-...`, or other credentials
- Any large binary, model, or downloaded data file (e.g. cached `yfinance` parquet) — add to `.gitignore` immediately if such a file appears
- `venv/`, `.venv/` — covered by `.gitignore`

---

## PART 5: PRE-SUBMISSION CHECKLIST

### Code Quality
- [ ] `pytest tests/ -v` — zero failures, zero errors
- [ ] `pytest tests/test_safety_pairs.py -v` — recall ≥95%, pass-through ≥90%
- [ ] `pytest tests/test_classifier_routing.py -v` — accuracy ≥85%
- [ ] `pytest tests/test_portfolio_health_skeleton.py -v` — all 3 cases pass
- [ ] No hardcoded secrets anywhere in codebase (`grep -r "sk-" src/ tests/` returns nothing)
- [ ] All environment variables documented in `.env.example` and README
- [ ] Type hints on all public functions in `src/`
- [ ] No dead code, no `print()` statements, no commented-out blocks
- [ ] `grep -r "TODO\|FIXME" src/ tests/` resolved or filed in README

### Git History
- [ ] At least 30 commits across 11 phases
- [ ] No commit messages like `final`, `done`, `wip`, `asdf`, `update`, `stuff`
- [ ] All phase branches merged into `main` via `--no-ff`
- [ ] All phase tags pushed (`phase-0-complete` through `phase-10-complete`, plus `submission`)
- [ ] `git log --oneline` tells a clear story: setup → safety → schemas → classifier → session → market data → portfolio health → router → http → perf → polish

### Documentation
- [ ] `README.md` has: project description, setup steps, env var table, run instructions, test instructions, library justifications, performance measurements, decision log, defence video URL
- [ ] `SPEC.md` exists at repo root
- [ ] `ARCHITECTURE.md` exists at repo root (this file)
- [ ] `CLAUDE.md` exists at repo root for future Claude Code sessions

### Submission
- [ ] Defence video recorded and ≤ 10 minutes
- [ ] Video URL is publicly accessible (unlisted YouTube is fine; private is not)
- [ ] Video URL is in README.md
- [ ] Final push to `main` on GitHub
- [ ] CI on GitHub Actions passes on latest commit
- [ ] Submission form (if any) submitted before deadline

---

## SUMMARY

- **Total phases:** 11 (Phase 0 → Phase 10)
- **Total estimated focused hours:** 24.5h + 3h buffer = 27.5h (fits within 3-day deadline at ~9h/day)
- **Critical path items:** (1) safety guard dual threshold, (2) classifier 85% accuracy, (3) portfolio health on `usr_004`/`usr_006`, (4) SSE streaming with timeout, (5) defence video ≤10min
- **Autograding scoring map:** Safety 25 (Phase 1) + Classifier 30 (Phase 3+4) + Portfolio Health 25 (Phase 6) + Full suite 20 (all phases) = 100 pts
- **Inferences flagged [ASSUMED]:** 3-day deadline window, MSCI World as default benchmark for non-US users, `OPENAI_API_KEY` made optional in `Settings` for tests, exception-safety fallback returns `blocked=False`

**First git command to run right now:**
```bash
git checkout -b phase/0-setup
```
