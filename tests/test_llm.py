"""Tests for LLM interfaces."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gruebot.llm.anthropic_api import AnthropicAPIBackend
from gruebot.llm.claude_cli import (
    ClaudeCLIBackend,
    ClaudeCLIContextLimitError,
    ClaudeCLIError,
)
from gruebot.llm.prompts import (
    format_game_output,
    get_summarization_prompt,
    get_system_prompt,
    parse_response,
)
from gruebot.llm.protocol import ConversationTurn


class TestPrompts:
    """Tests for prompt generation."""

    def test_get_system_prompt_default(self) -> None:
        """Test default system prompt generation."""
        prompt = get_system_prompt()

        assert "interactive fiction" in prompt.lower()
        assert "COMMAND:" in prompt

    def test_get_system_prompt_with_game(self) -> None:
        """Test system prompt with game title."""
        prompt = get_system_prompt(game_title="Zork I", turn_count=5)

        assert "Zork I" in prompt
        assert "Turn: 5" in prompt

    def test_get_system_prompt_with_context(self) -> None:
        """Test system prompt with additional context."""
        prompt = get_system_prompt(additional_context="You have a brass lantern.")

        assert "brass lantern" in prompt

    def test_get_summarization_prompt(self) -> None:
        """Test summarization prompt generation."""
        prompt = get_summarization_prompt()

        assert "summariz" in prompt.lower()
        assert "locations" in prompt.lower()

    def test_get_summarization_prompt_with_previous(self) -> None:
        """Test summarization prompt with previous summary."""
        prompt = get_summarization_prompt(previous_summary="Player is in the kitchen.")

        assert "kitchen" in prompt


class TestParseResponse:
    """Tests for response parsing."""

    def test_parse_with_command_prefix(self) -> None:
        """Test parsing response with COMMAND: prefix."""
        text = """I see a door to the north. Let me try going that way.

COMMAND: go north"""

        result = parse_response(text)

        assert result.command == "go north"
        assert result.reasoning == "I see a door to the north. Let me try going that way."
        assert result.is_meta is False

    def test_parse_command_case_insensitive(self) -> None:
        """Test that COMMAND prefix is case insensitive."""
        text = "command: look around"
        result = parse_response(text)

        assert result.command == "look around"

    def test_parse_meta_command(self) -> None:
        """Test parsing meta commands (save/restore/quit)."""
        text = "I should save my progress.\n\nCOMMAND: save"
        result = parse_response(text)

        assert result.command == "save"
        assert result.is_meta is True

    def test_parse_fallback_last_line(self) -> None:
        """Test fallback parsing from last line."""
        text = "I should examine the table.\nexamine table"
        result = parse_response(text)

        assert result.command == "examine table"

    def test_parse_no_command(self) -> None:
        """Test parsing when no command found."""
        text = "I'm not sure what to do next. The room is confusing."
        result = parse_response(text)

        assert result.command is None
        assert result.reasoning == text

    def test_parse_empty_response(self) -> None:
        """Test parsing empty response."""
        result = parse_response("")

        assert result.command is None
        assert result.reasoning is None

    def test_parse_multiline_reasoning(self) -> None:
        """Test parsing with multiline reasoning."""
        text = """Looking around the room, I notice several things:
1. A brass lantern on the table
2. A small key in the corner
3. A door leading north

I should take the lantern first.

COMMAND: take lantern"""

        result = parse_response(text)

        assert result.command == "take lantern"
        assert "brass lantern" in result.reasoning
        assert "small key" in result.reasoning


class TestFormatGameOutput:
    """Tests for game output formatting."""

    def test_format_basic(self) -> None:
        """Test basic output formatting."""
        output = format_game_output("You are in a room.")

        assert output == "You are in a room."

    def test_format_with_location(self) -> None:
        """Test formatting with location."""
        output = format_game_output("A dark room.", location="Cellar")

        assert "[Location: Cellar]" in output
        assert "A dark room." in output

    def test_format_with_turn(self) -> None:
        """Test formatting with turn number."""
        output = format_game_output("Text", turn_number=10)

        assert "[Turn 10]" in output

    def test_format_with_all(self) -> None:
        """Test formatting with all parameters."""
        output = format_game_output(
            "Game text here.",
            location="Kitchen",
            turn_number=5,
        )

        assert "[Turn 5]" in output
        assert "[Location: Kitchen]" in output
        assert "Game text here." in output


class TestAnthropicAPIBackend:
    """Tests for Anthropic API backend."""

    def test_init_default(self) -> None:
        """Test default initialization."""
        backend = AnthropicAPIBackend()

        assert backend.model == "claude-sonnet-4-20250514"
        assert backend.max_tokens == 1024
        assert backend.temperature == 0.7

    def test_init_custom(self) -> None:
        """Test custom initialization."""
        backend = AnthropicAPIBackend(
            model="claude-3-opus",
            max_tokens=2048,
            temperature=0.5,
        )

        assert backend.model == "claude-3-opus"
        assert backend.max_tokens == 2048
        assert backend.temperature == 0.5

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """Test successful send."""
        backend = AnthropicAPIBackend()

        # Mock the API client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="I'll go north.\n\nCOMMAND: north")]

        backend._client.messages.create = AsyncMock(return_value=mock_response)

        messages = [ConversationTurn(role="user", content="You are in a room.")]
        response = await backend.send(messages)

        assert response.command == "north"
        assert backend._client.messages.create.called

    @pytest.mark.asyncio
    async def test_convert_messages_empty(self) -> None:
        """Test message conversion with empty list."""
        backend = AnthropicAPIBackend()
        result = backend._convert_messages([])

        assert len(result) == 1
        assert result[0]["role"] == "user"

    @pytest.mark.asyncio
    async def test_convert_messages_alternating(self) -> None:
        """Test message conversion ensures alternating roles."""
        backend = AnthropicAPIBackend()

        messages = [
            ConversationTurn(role="user", content="First"),
            ConversationTurn(role="user", content="Second"),
            ConversationTurn(role="assistant", content="Response"),
        ]

        result = backend._convert_messages(messages)

        # Check that consecutive user messages are combined
        assert result[0]["role"] == "user"
        assert "First" in str(result[0]["content"])
        assert "Second" in str(result[0]["content"])

    @pytest.mark.asyncio
    async def test_summarize(self) -> None:
        """Test summarization."""
        backend = AnthropicAPIBackend()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(type="text", text="Summary: Player explored the house.")]

        backend._client.messages.create = AsyncMock(return_value=mock_response)

        history = [
            ConversationTurn(role="user", content="You enter the house."),
            ConversationTurn(role="assistant", content="COMMAND: look"),
        ]

        summary = await backend.summarize(history)

        assert "Summary" in summary
        backend._client.messages.create.assert_called_once()


class TestClaudeCLIBackend:
    """Tests for Claude CLI backend."""

    def test_init_finds_claude(self) -> None:
        """Test that init finds claude or raises."""
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            backend = ClaudeCLIBackend()
            assert backend.claude_path == "/usr/local/bin/claude"

    def test_init_claude_not_found(self) -> None:
        """Test error when claude not found."""
        with (
            patch("shutil.which", return_value=None),
            pytest.raises(ClaudeCLIError, match="not found"),
        ):
            ClaudeCLIBackend()

    def test_init_custom_path(self) -> None:
        """Test custom claude path."""
        backend = ClaudeCLIBackend(claude_path="/custom/claude")
        assert backend.claude_path == "/custom/claude"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        """Test successful send via CLI."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            backend = ClaudeCLIBackend()

        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"Looking around.\n\nCOMMAND: look", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = [ConversationTurn(role="user", content="Game text")]
            response = await backend.send(messages)

        assert response.command == "look"

    @pytest.mark.asyncio
    async def test_send_cli_error(self) -> None:
        """Test CLI error handling."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            backend = ClaudeCLIBackend()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error message"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = [ConversationTurn(role="user", content="Text")]
            with pytest.raises(ClaudeCLIError):
                await backend.send(messages)

    @pytest.mark.asyncio
    async def test_send_context_limit_error(self) -> None:
        """Test context limit error detection."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            backend = ClaudeCLIBackend()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: context limit exceeded"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = [ConversationTurn(role="user", content="Text")]
            with pytest.raises(ClaudeCLIContextLimitError) as exc_info:
                await backend.send(messages)
            assert "context limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_send_rate_limit_error(self) -> None:
        """Test rate limit error detection."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            backend = ClaudeCLIBackend()

        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"Error: rate limit exceeded"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            messages = [ConversationTurn(role="user", content="Text")]
            with pytest.raises(ClaudeCLIError) as exc_info:
                await backend.send(messages)
            assert "rate limit" in str(exc_info.value).lower()

    def test_build_prompt(self) -> None:
        """Test prompt building."""
        with patch("shutil.which", return_value="/usr/bin/claude"):
            backend = ClaudeCLIBackend()

        messages = [
            ConversationTurn(role="user", content="Game output here"),
            ConversationTurn(role="assistant", content="COMMAND: north"),
        ]

        prompt = backend._build_prompt(messages)

        # System prompt is now passed separately to --system-prompt flag
        assert "Game output here" in prompt
        assert "COMMAND: north" in prompt
        assert "Please provide your next command" in prompt
