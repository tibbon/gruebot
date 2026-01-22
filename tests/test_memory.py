"""Tests for memory and context management."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gruebot.llm.protocol import ConversationTurn
from gruebot.memory.context import ContextManager, GameContext
from gruebot.memory.summarizer import (
    SummarizationConfig,
    Summarizer,
    create_summary_message,
)


class TestGameContext:
    """Tests for GameContext dataclass."""

    def test_default_values(self) -> None:
        """Test default context values."""
        context = GameContext()

        assert context.summary is None
        assert context.recent_turns == []
        assert context.current_location is None
        assert context.inventory == []
        assert context.objectives == []
        assert context.turn_count == 0


class TestContextManager:
    """Tests for ContextManager."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        manager = ContextManager()

        assert manager.max_recent_turns == 20
        assert manager.summarize_threshold == 15
        assert manager.llm is None
        assert manager.context.turn_count == 0

    def test_init_custom(self) -> None:
        """Test custom initialization."""
        mock_llm = MagicMock()
        manager = ContextManager(
            max_recent_turns=30,
            summarize_threshold=20,
            llm=mock_llm,
        )

        assert manager.max_recent_turns == 30
        assert manager.summarize_threshold == 20
        assert manager.llm is mock_llm

    def test_add_turn(self) -> None:
        """Test adding a conversation turn."""
        manager = ContextManager()

        manager.add_turn("user", "Game output")

        assert len(manager.context.recent_turns) == 1
        assert manager.context.recent_turns[0].role == "user"
        assert manager.context.recent_turns[0].content == "Game output"
        assert manager.context.turn_count == 1

    def test_add_turn_invalid_role(self) -> None:
        """Test adding turn with invalid role."""
        manager = ContextManager()

        with pytest.raises(ValueError, match="Invalid role"):
            manager.add_turn("invalid", "Content")

    def test_add_game_output(self) -> None:
        """Test adding game output."""
        manager = ContextManager()

        manager.add_game_output("You are in a room.", location="Kitchen")

        assert len(manager.context.recent_turns) == 1
        assert manager.context.current_location == "Kitchen"

    def test_add_player_response(self) -> None:
        """Test adding player response."""
        manager = ContextManager()

        manager.add_player_response("Let me look around.\n\nCOMMAND: look")

        assert len(manager.context.recent_turns) == 1
        assert manager.context.recent_turns[0].role == "assistant"

    def test_add_system_note(self) -> None:
        """Test adding system note."""
        manager = ContextManager()

        manager.add_system_note("You appear to be stuck.")

        assert len(manager.context.recent_turns) == 1
        assert manager.context.recent_turns[0].role == "system"

    def test_should_summarize(self) -> None:
        """Test summarization trigger."""
        manager = ContextManager(summarize_threshold=3)

        assert manager.should_summarize() is False

        manager.add_turn("user", "Turn 1")
        manager.add_turn("assistant", "Response 1")
        assert manager.should_summarize() is False

        manager.add_turn("user", "Turn 2")
        assert manager.should_summarize() is True

    @pytest.mark.asyncio
    async def test_maybe_summarize_no_llm(self) -> None:
        """Test summarization without LLM."""
        manager = ContextManager(
            max_recent_turns=10,
            summarize_threshold=3,
        )

        # Add enough turns to trigger summarization
        for i in range(5):
            manager.add_turn("user", f"Turn {i}")

        result = await manager.maybe_summarize()

        # Without LLM, just trims history
        assert result is False

    @pytest.mark.asyncio
    async def test_maybe_summarize_with_llm(self) -> None:
        """Test summarization with LLM."""
        mock_llm = MagicMock()
        mock_llm.summarize = AsyncMock(return_value="Game summary here")

        manager = ContextManager(
            max_recent_turns=10,
            summarize_threshold=8,  # Trigger at 8 turns
            llm=mock_llm,
        )

        # Add enough turns to trigger summarization and have some to summarize
        # With summarize_threshold=8, max_recent_turns=10:
        # keep_count = max(5, 10 - 8//2) = max(5, 6) = 6
        # So we need more than 6 turns for to_summarize to be non-empty
        for i in range(10):
            manager.add_turn("user", f"Turn {i}")

        result = await manager.maybe_summarize()

        assert result is True
        assert manager.context.summary == "Game summary here"
        mock_llm.summarize.assert_called_once()

    def test_build_messages_empty(self) -> None:
        """Test building messages with empty context."""
        manager = ContextManager()

        messages = manager.build_messages()

        assert messages == []

    def test_build_messages_with_summary(self) -> None:
        """Test building messages with summary."""
        manager = ContextManager()
        manager.context.summary = "Previous events summary"
        manager.add_turn("user", "Current turn")

        messages = manager.build_messages()

        assert len(messages) == 2
        assert messages[0].role == "system"
        assert "Previous events summary" in messages[0].content
        assert messages[1].content == "Current turn"

    def test_build_messages_with_state(self) -> None:
        """Test building messages with state context."""
        manager = ContextManager()
        manager.context.current_location = "Library"
        manager.context.inventory = ["lantern", "key"]
        manager.context.objectives = ["Find the book"]
        manager.add_turn("user", "Game output")

        messages = manager.build_messages()

        assert len(messages) == 2
        state_msg = messages[0]
        assert "Library" in state_msg.content
        assert "lantern" in state_msg.content
        assert "Find the book" in state_msg.content

    def test_get_full_history(self) -> None:
        """Test getting full history."""
        manager = ContextManager()
        manager.add_turn("user", "Turn 1")
        manager.add_turn("assistant", "Response 1")

        history = manager.get_full_history()

        assert len(history) == 2
        # Should be a copy
        history.append(ConversationTurn(role="user", content="Extra"))
        assert len(manager._full_history) == 2

    def test_update_location(self) -> None:
        """Test location update."""
        manager = ContextManager()

        manager.update_location("Basement")

        assert manager.context.current_location == "Basement"

    def test_update_inventory(self) -> None:
        """Test inventory update."""
        manager = ContextManager()

        manager.update_inventory(["sword", "shield"])

        assert manager.context.inventory == ["sword", "shield"]

    def test_add_objective(self) -> None:
        """Test adding objective."""
        manager = ContextManager()

        manager.add_objective("Find treasure")
        manager.add_objective("Find treasure")  # Duplicate should be ignored

        assert manager.context.objectives == ["Find treasure"]

    def test_complete_objective(self) -> None:
        """Test completing objective."""
        manager = ContextManager()
        manager.add_objective("Find key")

        manager.complete_objective("Find key")

        assert manager.context.objectives == []

    def test_reset(self) -> None:
        """Test context reset."""
        manager = ContextManager()
        manager.add_turn("user", "Turn 1")
        manager.context.summary = "Summary"
        manager.context.current_location = "Room"

        manager.reset()

        assert manager.context.turn_count == 0
        assert manager.context.summary is None
        assert manager.context.current_location is None
        assert len(manager._full_history) == 0


class TestSummarizationConfig:
    """Tests for SummarizationConfig."""

    def test_defaults(self) -> None:
        """Test default config values."""
        config = SummarizationConfig()

        assert config.turn_threshold == 15
        assert config.token_threshold == 8000
        assert config.keep_recent == 5
        assert config.max_summary_tokens == 1000


class TestSummarizer:
    """Tests for Summarizer."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        summarizer = Summarizer()

        assert summarizer.config.turn_threshold == 15

    def test_init_custom_config(self) -> None:
        """Test custom config."""
        config = SummarizationConfig(turn_threshold=10)
        summarizer = Summarizer(config=config)

        assert summarizer.config.turn_threshold == 10

    def test_should_summarize_turns(self) -> None:
        """Test turn-based summarization trigger."""
        summarizer = Summarizer(SummarizationConfig(turn_threshold=3))

        turns = [
            ConversationTurn(role="user", content="Short"),
            ConversationTurn(role="assistant", content="Reply"),
        ]
        assert summarizer.should_summarize(turns) is False

        turns.append(ConversationTurn(role="user", content="Third"))
        assert summarizer.should_summarize(turns) is True

    def test_should_summarize_tokens(self) -> None:
        """Test token-based summarization trigger."""
        summarizer = Summarizer(
            SummarizationConfig(
                turn_threshold=100,  # High turn threshold
                token_threshold=100,  # Low token threshold
            )
        )

        # Short content - shouldn't trigger
        short_turns = [ConversationTurn(role="user", content="Hi")]
        assert summarizer.should_summarize(short_turns) is False

        # Long content - should trigger
        long_turns = [ConversationTurn(role="user", content="x" * 500)]
        assert summarizer.should_summarize(long_turns) is True

    def test_estimate_tokens(self) -> None:
        """Test token estimation."""
        summarizer = Summarizer()

        # ~4 chars per token
        assert summarizer.estimate_tokens("a" * 40) == 10
        assert summarizer.estimate_tokens("") == 0

    def test_split_for_summarization(self) -> None:
        """Test splitting turns."""
        summarizer = Summarizer(SummarizationConfig(keep_recent=2))

        turns = [ConversationTurn(role="user", content=f"Turn {i}") for i in range(5)]

        to_summarize, to_keep = summarizer.split_for_summarization(turns)

        assert len(to_summarize) == 3
        assert len(to_keep) == 2
        assert to_keep[0].content == "Turn 3"
        assert to_keep[1].content == "Turn 4"

    def test_split_short_history(self) -> None:
        """Test splitting with short history."""
        summarizer = Summarizer(SummarizationConfig(keep_recent=5))

        turns = [ConversationTurn(role="user", content="Only one")]

        to_summarize, to_keep = summarizer.split_for_summarization(turns)

        assert len(to_summarize) == 0
        assert len(to_keep) == 1

    @pytest.mark.asyncio
    async def test_summarize(self) -> None:
        """Test generating summary."""
        mock_llm = MagicMock()
        mock_llm.summarize = AsyncMock(return_value="Summary of events")

        summarizer = Summarizer()
        history = [
            ConversationTurn(role="user", content="Game start"),
            ConversationTurn(role="assistant", content="COMMAND: look"),
        ]

        summary = await summarizer.summarize(mock_llm, history)

        assert summary == "Summary of events"
        mock_llm.summarize.assert_called_once()

    def test_format_history(self) -> None:
        """Test history formatting."""
        summarizer = Summarizer()

        history = [
            ConversationTurn(role="user", content="Game output"),
            ConversationTurn(role="assistant", content="Player action"),
            ConversationTurn(role="system", content="Note"),
        ]

        formatted = summarizer._format_history(history)

        assert "GAME: Game output" in formatted
        assert "PLAYER: Player action" in formatted
        assert "[SYSTEM]: Note" in formatted


class TestCreateSummaryMessage:
    """Tests for create_summary_message."""

    def test_creates_system_message(self) -> None:
        """Test creating summary message."""
        msg = create_summary_message("This is a summary")

        assert msg.role == "system"
        assert "This is a summary" in msg.content
        assert "summary" in msg.content.lower()
