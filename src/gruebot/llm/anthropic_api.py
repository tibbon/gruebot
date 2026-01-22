"""Anthropic API backend for LLM interface."""

from collections.abc import AsyncIterator

import anthropic

from gruebot.llm.prompts import (
    get_summarization_prompt,
    get_system_prompt,
    parse_response,
)
from gruebot.llm.protocol import ConversationTurn, LLMResponse


class AnthropicAPIBackend:
    """LLM backend using the Anthropic API directly.

    This backend uses the anthropic Python SDK to communicate
    with Claude models.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 1024,
        temperature: float = 0.7,
        api_key: str | None = None,
    ) -> None:
        """Initialize the Anthropic API backend.

        Args:
            model: Model name to use.
            max_tokens: Maximum tokens in response.
            temperature: Sampling temperature.
            api_key: API key (defaults to ANTHROPIC_API_KEY env var).
        """
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Initialize the async client
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def send(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Send messages and get a response.

        Args:
            messages: Conversation history.
            system_prompt: Optional system prompt override.

        Returns:
            LLMResponse with extracted command.
        """
        # Build the system prompt
        if system_prompt is None:
            system_prompt = get_system_prompt()

        # Convert messages to Anthropic format
        api_messages = self._convert_messages(messages)

        # Make the API call
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=api_messages,
        )

        # Extract text from response
        raw_text = self._extract_text(response)

        # Parse the response
        parsed = parse_response(raw_text)

        return LLMResponse(
            raw_text=parsed.raw_text,
            command=parsed.command,
            reasoning=parsed.reasoning,
            is_meta=parsed.is_meta,
        )

    async def send_streaming(
        self,
        messages: list[ConversationTurn],
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream response text.

        Args:
            messages: Conversation history.
            system_prompt: Optional system prompt override.

        Yields:
            Text chunks as they arrive.
        """
        if system_prompt is None:
            system_prompt = get_system_prompt()

        api_messages = self._convert_messages(messages)

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=system_prompt,
            messages=api_messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text

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
            max_tokens: Maximum tokens for summary.

        Returns:
            Summary text.
        """
        # Build history text
        history_text = self._format_history_for_summary(history)

        # Create summarization prompt
        system_prompt = get_summarization_prompt(previous_summary)

        # Single user message with history to summarize
        messages: list[anthropic.types.MessageParam] = [
            {
                "role": "user",
                "content": f"Please summarize this game session:\n\n{history_text}",
            }
        ]

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.3,  # Lower temperature for summaries
            system=system_prompt,
            messages=messages,
        )

        return self._extract_text(response)

    def _convert_messages(
        self, messages: list[ConversationTurn]
    ) -> list[anthropic.types.MessageParam]:
        """Convert conversation turns to Anthropic message format.

        Args:
            messages: Conversation turns.

        Returns:
            List of Anthropic message dicts.
        """
        api_messages: list[anthropic.types.MessageParam] = []

        for turn in messages:
            # Skip system messages - they're handled separately
            if turn.role == "system":
                # Prepend to first user message or add as user context
                continue

            api_messages.append(
                {
                    "role": turn.role,
                    "content": turn.content,
                }
            )

        # Ensure we have at least one message
        if not api_messages:
            api_messages.append({"role": "user", "content": "Begin the game."})

        # Ensure conversation starts with user message
        if api_messages[0]["role"] != "user":
            api_messages.insert(0, {"role": "user", "content": "Continue playing."})

        # Ensure alternating roles (Anthropic requirement)
        cleaned_messages: list[anthropic.types.MessageParam] = []
        for msg in api_messages:
            if cleaned_messages and cleaned_messages[-1]["role"] == msg["role"]:
                # Combine consecutive same-role messages
                prev_content = cleaned_messages[-1]["content"]
                if isinstance(prev_content, str) and isinstance(msg["content"], str):
                    cleaned_messages[-1] = {
                        "role": msg["role"],
                        "content": f"{prev_content}\n\n{msg['content']}",
                    }
            else:
                cleaned_messages.append(msg)

        return cleaned_messages

    def _extract_text(self, response: anthropic.types.Message) -> str:
        """Extract text content from API response.

        Args:
            response: Anthropic API response.

        Returns:
            Extracted text content.
        """
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "\n".join(text_parts)

    def _format_history_for_summary(self, history: list[ConversationTurn]) -> str:
        """Format conversation history for summarization.

        Args:
            history: Conversation turns.

        Returns:
            Formatted history text.
        """
        lines = []
        for turn in history:
            if turn.role == "user":
                lines.append(f"GAME: {turn.content}")
            elif turn.role == "assistant":
                lines.append(f"PLAYER: {turn.content}")
            else:
                lines.append(f"[{turn.role.upper()}]: {turn.content}")
        return "\n\n".join(lines)
