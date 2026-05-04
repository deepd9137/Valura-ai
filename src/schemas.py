"""
Shared Pydantic models for Valura AI.

All request/response boundaries, agent outputs, and inter-component
contracts are defined here.
"""
from typing import Optional

from pydantic import BaseModel


class SafetyVerdict(BaseModel):
    blocked: bool
    category: Optional[str] = None
    message: Optional[str] = None
