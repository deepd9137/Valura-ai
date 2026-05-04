"""
Safety guard — synchronous, no LLM, no network, <10ms per query.

Pipeline position: runs FIRST before the classifier. If blocked=True,
the classifier never runs and a category-specific SSE error is returned.
"""
from src.safety_patterns import (
    REFUSAL_MESSAGES,
    _EDUCATIONAL_PATTERNS,
    _HARM_PATTERNS,
)
from src.schemas import SafetyVerdict


def check(query: str) -> SafetyVerdict:
    """
    Return a SafetyVerdict for the given query.

    Algorithm:
      1. Normalize to lowercase.
      2. Check educational allowlist — if any pattern matches, pass through.
      3. Iterate harm patterns — return first match as a block verdict.
      4. Default: pass.
    """
    normalized = query.lower().strip()

    # Step 1: educational allowlist override
    for pattern in _EDUCATIONAL_PATTERNS:
        if pattern.search(normalized):
            return SafetyVerdict(blocked=False)

    # Step 2: harmful pattern matching
    for pattern, category in _HARM_PATTERNS:
        if pattern.search(normalized):
            return SafetyVerdict(
                blocked=True,
                category=category,
                message=REFUSAL_MESSAGES[category],
            )

    return SafetyVerdict(blocked=False)
