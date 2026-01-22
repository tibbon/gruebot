"""Shared types for the testing module."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TestState:
    """Current state during test execution."""

    current_location: str | None = None
    last_output: str = ""
    full_transcript: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    score: int | None = None
    turns: int = 0
    game_over: bool = False
    error: str | None = None
