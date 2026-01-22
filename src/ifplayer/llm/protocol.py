"""Protocol definitions for LLM interfaces."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class ConversationTurn:
    """A single turn in the conversation."""

    role: Literal["user", "assistant", "system"]
    content: str


@dataclass
class LLMResponse:
    """Response from the LLM."""

    raw_text: str
    command: str | None = None
    reasoning: str | None = None
    is_meta: bool = False  # True if LLM wants to save/restore/quit


class LLMInterface(Protocol):
    """Protocol for LLM backends.

    Implementations must provide methods to send messages and receive
    responses, with optional streaming support.
    """

    async def send(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send conversation messages and get a response.

        Args:
            messages: List of conversation turns.
            system_prompt: Optional system prompt to prepend.

        Returns:
            LLMResponse with the extracted command and reasoning.
        """
        ...

    async def send_streaming(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream response text from the LLM.

        Args:
            messages: List of conversation turns.
            system_prompt: Optional system prompt to prepend.

        Yields:
            Text chunks as they arrive.
        """
        ...

    async def summarize(
        self,
        history: list[ConversationTurn],
        previous_summary: str | None = None,
        max_tokens: int = 500,
    ) -> str:
        """Generate a summary of game history.

        Args:
            history: Conversation turns to summarize.
            previous_summary: Previous summary to incorporate.
            max_tokens: Maximum tokens for the summary.

        Returns:
            Summary text.
        """
        ...
