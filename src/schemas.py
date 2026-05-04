"""
Shared Pydantic models for Valura AI.

All request/response boundaries, agent outputs, and inter-component
contracts are defined here.
"""
from __future__ import annotations

from pydantic import BaseModel


class SafetyVerdict(BaseModel):
    blocked: bool
    category: str | None = None
    message: str | None = None
