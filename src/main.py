"""
Valura AI — FastAPI HTTP layer.

Single endpoint: POST /chat
Pipeline: safety guard → classifier → router → agent → SSE stream

Timeout: 10 seconds total (REQUEST_TIMEOUT_SECONDS in .env).
Chosen because: classifier LLM call ≈ 1–2s, yfinance batch ≈ 2–4s,
leaving headroom while staying well inside a human-perceptible wait.

SSE frame shape:
    data: {"type": "metadata", "agent": "...", "entities": {...}, "safety_verdict": "..."}
    data: {"type": "result",   "data": {...}}
    data: [DONE]

On any error:
    data: {"type": "error", "code": "...", "message": "..."}
    data: [DONE]
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from src.classifier import classify
from src.router import route
from src.safety import check
from src.schemas import ChatRequest
from src.session import SessionStore
from src.settings import Settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Valura AI", version="1.0.0")

_settings = Settings()
_sessions = SessionStore()

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "users"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_user(user_id: str) -> Optional[Dict[str, Any]]:
    for path in _FIXTURES_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        if user.get("user_id") == user_id:
            return user
    return None


def _event(type_: str, **kwargs: Any) -> str:
    payload: Dict[str, Any] = {"type": type_}
    payload.update({k: v for k, v in kwargs.items() if v is not None})
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(request: ChatRequest) -> EventSourceResponse:
    """
    Main pipeline endpoint. Streams SSE events for every stage.

    Request body: {"query": str, "user_id": str, "session_id": str | null}
    """
    async def generate() -> AsyncIterator[Dict[str, str]]:
        try:
            # 1. Load user profile
            user = _load_user(request.user_id)
            if user is None:
                yield {"data": _event("error", code="user_not_found",
                                      message=f"No profile found for user_id '{request.user_id}'")}
                yield {"data": "[DONE]"}
                return

            # 2. Safety guard — synchronous, <10ms, runs before any LLM call
            safety = check(request.query)
            if safety.blocked:
                yield {"data": _event("error", code="safety_blocked",
                                      message=safety.message)}
                yield {"data": "[DONE]"}
                return

            # 3. Resolve prior session turns
            prior_turns = _sessions.get(request.session_id) if request.session_id else []

            # 4. Classify intent (LLM call, subject to overall timeout)
            try:
                classification = await asyncio.wait_for(
                    classify(request.query, prior_turns=prior_turns),
                    timeout=_settings.request_timeout_seconds,
                )
            except asyncio.TimeoutError:
                yield {"data": _event("error", code="timeout",
                                      message="Classification timed out. Please try again.")}
                yield {"data": "[DONE]"}
                return

            # 5. Emit metadata immediately so the client sees routing decision fast
            yield {"data": _event(
                "metadata",
                agent=classification.agent,
                entities=classification.entities,
                safety_verdict=classification.safety_verdict,
            )}

            # 6. Store this turn in session memory
            if request.session_id:
                _sessions.append(request.session_id, request.query)

            # 7. Dispatch to agent (blocking I/O run in thread pool)
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(route, classification, user),
                    timeout=_settings.request_timeout_seconds,
                )
            except asyncio.TimeoutError:
                yield {"data": _event("error", code="timeout",
                                      message="Agent timed out. Please try again.")}
                yield {"data": "[DONE]"}
                return

            # 8. Stream result
            yield {"data": _event("result", data=result)}
            yield {"data": "[DONE]"}

        except Exception as exc:
            logger.error("Unhandled pipeline error: %s", exc, exc_info=True)
            yield {"data": _event("error", code="internal_error",
                                  message="An unexpected error occurred. Please try again.")}
            yield {"data": "[DONE]"}

    return EventSourceResponse(generate())


# ---------------------------------------------------------------------------
# Health check (useful for CI / deployment probes)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}
