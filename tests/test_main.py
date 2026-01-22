"""Tests for main game session."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ifplayer.backends.protocol import GameInfo, GameResponse, GameState
from ifplayer.config import Config
from ifplayer.llm.protocol import LLMResponse
from ifplayer.main import GameResult, GameSession, StuckDetector


class TestStuckDetector:
    """Tests for StuckDetector."""

    def test_init_defaults(self) -> None:
        """Test default initialization."""
        detector = StuckDetector()

        assert detector.threshold == 5

    def test_not_stuck_initially(self) -> None:
        """Test detector not stuck initially."""
        detector = StuckDetector(threshold=3)
        response = GameResponse(text="You are in a room.")

        result = detector.check(response, "look")

        assert result is False

    def test_stuck_repeated_outputs(self) -> None:
        """Test detection of repeated outputs."""
        detector = StuckDetector(threshold=3)

        # Same output three times
        for _ in range(3):
            response = GameResponse(text="You can't go that way.")
            result = detector.check(response)

        assert result is True

    def test_stuck_repeated_commands(self) -> None:
        """Test detection of repeated commands."""
        detector = StuckDetector(threshold=3)

        # Same command three times with different outputs
        for i in range(3):
            response = GameResponse(text=f"Output {i}")
            result = detector.check(response, "north")

        assert result is True

    def test_not_stuck_varied_actions(self) -> None:
        """Test not stuck with varied actions."""
        detector = StuckDetector(threshold=3)

        commands = ["north", "look", "take lamp", "south", "inventory"]
        for cmd in commands:
            response = GameResponse(text=f"Response to {cmd}")
            result = detector.check(response, cmd)

        assert result is False

    def test_reset(self) -> None:
        """Test reset clears history."""
        detector = StuckDetector(threshold=3)

        # Build up some history
        for _ in range(2):
            response = GameResponse(text="Same output")
            detector.check(response, "same")

        detector.reset()

        # Should not be stuck after reset
        response = GameResponse(text="Same output")
        result = detector.check(response, "same")

        assert result is False


class TestGameSession:
    """Tests for GameSession."""

    def create_mock_backend(self) -> MagicMock:
        """Create a mock game backend."""
        backend = MagicMock()
        backend.is_running = True
        backend.game_info = GameInfo(
            title="Test Game",
            author="Test Author",
            format="zmachine",
            file_path="/path/to/game.z5",
        )
        backend.start.return_value = GameResponse(
            text="Welcome to Test Game!",
            location="Start Room",
            state=GameState.WAITING_INPUT,
        )
        backend.send_command.return_value = GameResponse(
            text="You go north.",
            location="North Room",
            state=GameState.WAITING_INPUT,
        )
        return backend

    def create_mock_llm(self) -> MagicMock:
        """Create a mock LLM interface."""
        llm = MagicMock()
        llm.send = AsyncMock(
            return_value=LLMResponse(
                raw_text="Let me go north.\n\nCOMMAND: north",
                command="north",
                reasoning="Let me go north.",
                is_meta=False,
            )
        )
        llm.summarize = AsyncMock(return_value="Game summary")
        return llm

    def test_init(self) -> None:
        """Test session initialization."""
        backend = self.create_mock_backend()
        llm = self.create_mock_llm()
        config = Config()

        session = GameSession(backend, llm, config)

        assert session.backend is backend
        assert session.llm is llm
        assert session._turn_count == 0
        assert session._running is False

    @pytest.mark.asyncio
    async def test_run_max_turns(self) -> None:
        """Test running with max turns limit."""
        backend = self.create_mock_backend()
        llm = self.create_mock_llm()
        config = Config()

        session = GameSession(backend, llm, config)

        result = await session.run(Path("/fake/game.z5"), max_turns=3)

        assert result.outcome == "max_turns"
        assert result.turns == 3
        backend.start.assert_called_once()
        assert llm.send.call_count == 3
        backend.quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_game_over(self) -> None:
        """Test game over detection."""
        backend = self.create_mock_backend()
        backend.send_command.return_value = GameResponse(
            text="*** You have died ***",
            state=GameState.GAME_OVER,
        )

        llm = self.create_mock_llm()
        config = Config()

        session = GameSession(backend, llm, config)

        result = await session.run(Path("/fake/game.z5"), max_turns=10)

        assert result.outcome == "game_over"
        # Turn count is 0 because game over happens before turn increment
        assert result.turns == 0

    @pytest.mark.asyncio
    async def test_run_meta_quit(self) -> None:
        """Test quit meta command."""
        backend = self.create_mock_backend()
        llm = self.create_mock_llm()
        llm.send = AsyncMock(
            return_value=LLMResponse(
                raw_text="I should quit now.\n\nCOMMAND: quit",
                command="quit",
                is_meta=True,
            )
        )
        config = Config()

        session = GameSession(backend, llm, config)

        result = await session.run(Path("/fake/game.z5"), max_turns=10)

        assert result.outcome == "stopped"

    @pytest.mark.asyncio
    async def test_run_meta_save(self) -> None:
        """Test save meta command."""
        backend = self.create_mock_backend()
        backend.save.return_value = True

        call_count = 0

        async def mock_send(
            _messages: list,  # noqa: ARG001
            **_kwargs: object,  # noqa: ARG001
        ) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return LLMResponse(
                    raw_text="Save game\n\nCOMMAND: save",
                    command="save",
                    is_meta=True,
                )
            else:
                return LLMResponse(
                    raw_text="Now quit\n\nCOMMAND: quit",
                    command="quit",
                    is_meta=True,
                )

        llm = self.create_mock_llm()
        llm.send = mock_send
        config = Config()

        session = GameSession(backend, llm, config)

        await session.run(Path("/fake/game.z5"), max_turns=10)

        backend.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_no_command_extracted(self) -> None:
        """Test handling when no command is extracted."""
        backend = self.create_mock_backend()

        call_count = 0

        async def mock_send(
            _messages: list,  # noqa: ARG001
            **_kwargs: object,  # noqa: ARG001
        ) -> LLMResponse:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First response has no command
                return LLMResponse(
                    raw_text="I'm thinking about what to do...",
                    command=None,
                    is_meta=False,
                )
            else:
                # Second response quits
                return LLMResponse(
                    raw_text="COMMAND: quit",
                    command="quit",
                    is_meta=True,
                )

        llm = self.create_mock_llm()
        llm.send = mock_send
        config = Config()

        session = GameSession(backend, llm, config)

        await session.run(Path("/fake/game.z5"), max_turns=10)

        # Should have added system note about missing command
        assert session.context.context.turn_count >= 1

    @pytest.mark.asyncio
    async def test_run_callback(self) -> None:
        """Test output callbacks."""
        backend = self.create_mock_backend()
        llm = self.create_mock_llm()
        config = Config()

        outputs: list[GameResponse] = []
        responses: list[LLMResponse] = []

        def on_output(resp: GameResponse) -> None:
            outputs.append(resp)

        def on_response(resp: LLMResponse) -> None:
            responses.append(resp)

        session = GameSession(backend, llm, config)

        await session.run(
            Path("/fake/game.z5"),
            max_turns=2,
            on_game_output=on_output,
            on_llm_response=on_response,
        )

        # Should have intro + 2 command responses
        assert len(outputs) == 3
        assert len(responses) == 2

    def test_stop_sets_flag(self) -> None:
        """Test that stop() sets the running flag."""
        backend = self.create_mock_backend()
        llm = self.create_mock_llm()
        config = Config()

        session = GameSession(backend, llm, config)
        session._running = True

        session.stop()

        assert session._running is False


class TestGameResult:
    """Tests for GameResult."""

    def test_game_over_result(self) -> None:
        """Test game over result."""
        result = GameResult(
            outcome="game_over",
            turns=50,
            final_location="Throne Room",
        )

        assert result.outcome == "game_over"
        assert result.turns == 50
        assert result.final_location == "Throne Room"
        assert result.error is None

    def test_error_result(self) -> None:
        """Test error result."""
        result = GameResult(
            outcome="error",
            turns=10,
            error="Interpreter crashed",
        )

        assert result.outcome == "error"
        assert result.error == "Interpreter crashed"
