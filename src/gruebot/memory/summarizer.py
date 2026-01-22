"""Summarization utilities for game history."""

from dataclasses import dataclass

from gruebot.llm.protocol import ConversationTurn, LLMInterface


@dataclass
class SummarizationConfig:
    """Configuration for summarization behavior."""

    # Trigger summarization when recent_turns exceeds this
    turn_threshold: int = 15

    # Alternative: trigger based on estimated token count
    token_threshold: int = 8000

    # After summarization, keep this many recent turns
    keep_recent: int = 5

    # Maximum summary length in tokens
    max_summary_tokens: int = 1000


class Summarizer:
    """Handles summarization of game history.

    Provides utilities for determining when to summarize
    and generating summaries from conversation history.
    """

    SUMMARIZE_PROMPT = """\
Summarize this interactive fiction game session.

Include in your summary:
- Key locations visited and their descriptions
- Important items found or used
- Puzzles encountered and their solutions (if solved)
- Current objectives or goals
- Any important NPCs or conversations

{previous_section}

Recent game history:
{history}

Provide a concise summary that preserves critical information for continuing the game.\
"""

    def __init__(self, config: SummarizationConfig | None = None) -> None:
        """Initialize the summarizer.

        Args:
            config: Summarization configuration.
        """
        self.config = config or SummarizationConfig()

    def should_summarize(
        self,
        recent_turns: list[ConversationTurn],
    ) -> bool:
        """Determine if summarization is needed.

        Args:
            recent_turns: Current recent turns.

        Returns:
            True if summarization should be triggered.
        """
        # Turn-based trigger
        if len(recent_turns) >= self.config.turn_threshold:
            return True

        # Token-based trigger (estimate 4 chars per token)
        total_chars = sum(len(t.content) for t in recent_turns)
        estimated_tokens = total_chars // 4
        return estimated_tokens >= self.config.token_threshold

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text.

        Uses a simple heuristic of ~4 characters per token.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        return len(text) // 4

    async def summarize(
        self,
        llm: LLMInterface,
        history: list[ConversationTurn],
        previous_summary: str | None = None,
    ) -> str:
        """Generate summary of game history.

        Args:
            llm: LLM interface for generating summary.
            history: Conversation turns to summarize.
            previous_summary: Previous summary to incorporate.

        Returns:
            Summary text.
        """
        history_text = self._format_history(history)

        previous_section = ""
        if previous_summary:
            previous_section = f"Previous summary (incorporate this):\n{previous_summary}\n"

        prompt = self.SUMMARIZE_PROMPT.format(
            previous_section=previous_section,
            history=history_text,
        )

        # Create a single user message with the summarization request
        messages = [ConversationTurn(role="user", content=prompt)]

        return await llm.summarize(
            history=messages,
            previous_summary=previous_summary,
            max_tokens=self.config.max_summary_tokens,
        )

    def split_for_summarization(
        self,
        recent_turns: list[ConversationTurn],
    ) -> tuple[list[ConversationTurn], list[ConversationTurn]]:
        """Split turns into parts to summarize and keep.

        Args:
            recent_turns: All recent turns.

        Returns:
            Tuple of (turns_to_summarize, turns_to_keep).
        """
        keep_count = self.config.keep_recent

        if len(recent_turns) <= keep_count:
            return [], recent_turns

        to_summarize = recent_turns[:-keep_count]
        to_keep = recent_turns[-keep_count:]

        return to_summarize, to_keep

    def _format_history(self, history: list[ConversationTurn]) -> str:
        """Format history for summarization prompt.

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


def create_summary_message(summary: str) -> ConversationTurn:
    """Create a system message containing a summary.

    Args:
        summary: The summary text.

    Returns:
        ConversationTurn with the summary.
    """
    return ConversationTurn(
        role="system",
        content=f"Previous game session summary:\n{summary}",
    )
