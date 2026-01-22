"""Context management for game sessions."""

from dataclasses import dataclass, field

from gruebot.llm.protocol import ConversationTurn, LLMInterface


@dataclass
class GameContext:
    """Full game context for LLM.

    Tracks the current state of the game session including
    conversation history, current location, and objectives.
    """

    summary: str | None = None
    recent_turns: list[ConversationTurn] = field(default_factory=list)
    current_location: str | None = None
    inventory: list[str] = field(default_factory=list)
    objectives: list[str] = field(default_factory=list)
    turn_count: int = 0


class ContextManager:
    """Manages game context and triggers summarization.

    The context manager maintains a sliding window of recent turns
    while periodically summarizing older turns to manage token usage.
    """

    def __init__(
        self,
        max_recent_turns: int = 20,
        summarize_threshold: int = 15,
        llm: LLMInterface | None = None,
    ) -> None:
        """Initialize the context manager.

        Args:
            max_recent_turns: Maximum turns to keep in recent window.
            summarize_threshold: Trigger summarization when this many turns.
            llm: LLM interface for generating summaries.
        """
        self.max_recent_turns = max_recent_turns
        self.summarize_threshold = summarize_threshold
        self.llm = llm
        self.context = GameContext()
        self._full_history: list[ConversationTurn] = []

    def add_turn(self, role: str, content: str) -> None:
        """Add a conversation turn.

        Args:
            role: The role (user, assistant, system).
            content: The turn content.
        """
        # Validate role
        if role not in ("user", "assistant", "system"):
            raise ValueError(f"Invalid role: {role}")

        turn = ConversationTurn(role=role, content=content)  # type: ignore[arg-type]
        self._full_history.append(turn)
        self.context.recent_turns.append(turn)
        self.context.turn_count += 1

    def add_game_output(self, text: str, location: str | None = None) -> None:
        """Add game output as a user turn.

        Args:
            text: Game output text.
            location: Current location if known.
        """
        if location:
            self.context.current_location = location

        self.add_turn("user", text)

    def add_player_response(self, text: str) -> None:
        """Add player (LLM) response as an assistant turn.

        Args:
            text: Full LLM response text.
        """
        self.add_turn("assistant", text)

    def add_system_note(self, note: str) -> None:
        """Add a system note.

        Args:
            note: System note content.
        """
        self.add_turn("system", note)

    def should_summarize(self) -> bool:
        """Check if summarization is needed.

        Returns:
            True if summarization should be triggered.
        """
        return len(self.context.recent_turns) >= self.summarize_threshold

    async def maybe_summarize(self) -> bool:
        """Check if summarization needed and perform if so.

        Returns:
            True if summarization was performed.
        """
        if not self.should_summarize():
            return False

        if self.llm is None:
            # No LLM available, just trim the history
            self._trim_history()
            return False

        await self._perform_summarization()
        return True

    async def _perform_summarization(self) -> None:
        """Compress older turns into summary."""
        if self.llm is None:
            return

        # Keep the most recent N turns
        keep_count = max(5, self.max_recent_turns - self.summarize_threshold // 2)
        to_summarize = self.context.recent_turns[:-keep_count]

        if not to_summarize:
            return

        # Generate summary including previous summary
        new_summary = await self.llm.summarize(
            history=to_summarize,
            previous_summary=self.context.summary,
        )

        self.context.summary = new_summary
        self.context.recent_turns = self.context.recent_turns[-keep_count:]

    def _trim_history(self) -> None:
        """Trim history without summarization."""
        if len(self.context.recent_turns) > self.max_recent_turns:
            # Simple trim: keep the most recent turns
            self.context.recent_turns = self.context.recent_turns[-self.max_recent_turns :]

    def build_messages(self) -> list[ConversationTurn]:
        """Build message list for LLM with summary + recent turns.

        Returns:
            List of conversation turns for LLM input.
        """
        messages: list[ConversationTurn] = []

        # Add summary as system context if available
        if self.context.summary:
            messages.append(
                ConversationTurn(
                    role="system",
                    content=f"Game history summary:\n{self.context.summary}",
                )
            )

        # Add current state context
        state_parts = []
        if self.context.current_location:
            state_parts.append(f"Current location: {self.context.current_location}")
        if self.context.inventory:
            state_parts.append(f"Inventory: {', '.join(self.context.inventory)}")
        if self.context.objectives:
            state_parts.append(f"Objectives: {', '.join(self.context.objectives)}")

        if state_parts:
            messages.append(
                ConversationTurn(
                    role="system",
                    content="\n".join(state_parts),
                )
            )

        # Add recent conversation turns
        messages.extend(self.context.recent_turns)

        return messages

    def get_full_history(self) -> list[ConversationTurn]:
        """Get the complete conversation history.

        Returns:
            Full history list (for logging/replay).
        """
        return self._full_history.copy()

    def update_location(self, location: str) -> None:
        """Update the current location.

        Args:
            location: New location name.
        """
        self.context.current_location = location

    def update_inventory(self, items: list[str]) -> None:
        """Update the inventory list.

        Args:
            items: New inventory items.
        """
        self.context.inventory = items.copy()

    def add_objective(self, objective: str) -> None:
        """Add a player objective.

        Args:
            objective: Objective description.
        """
        if objective not in self.context.objectives:
            self.context.objectives.append(objective)

    def complete_objective(self, objective: str) -> None:
        """Mark an objective as complete.

        Args:
            objective: Objective to remove.
        """
        if objective in self.context.objectives:
            self.context.objectives.remove(objective)

    def reset(self) -> None:
        """Reset the context for a new game."""
        self.context = GameContext()
        self._full_history.clear()
