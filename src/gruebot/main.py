"""Main game session orchestration."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from gruebot.backends.protocol import GameBackend, GameResponse, GameState
from gruebot.config import Config
from gruebot.llm.prompts import format_game_output, get_system_prompt
from gruebot.llm.protocol import LLMInterface, LLMResponse
from gruebot.memory.context import ContextManager

# Type aliases for callbacks
OutputCallback = Callable[[GameResponse], None]
ResponseCallback = Callable[[LLMResponse], None]


@dataclass
class GameResult:
    """Result of a game session."""

    outcome: str  # "game_over", "max_turns", "stopped", "error"
    turns: int
    final_location: str | None = None
    error: str | None = None


@dataclass
class StuckDetector:
    """Detects when the LLM is stuck repeating actions."""

    threshold: int = 5
    _recent_outputs: deque[str] = field(default_factory=lambda: deque(maxlen=5))
    _recent_commands: deque[str] = field(default_factory=lambda: deque(maxlen=5))

    def check(self, response: GameResponse, command: str | None = None) -> bool:
        """Check if we're in a stuck state.

        Args:
            response: Game response.
            command: Command that was sent.

        Returns:
            True if stuck state detected.
        """
        # Track recent outputs (first 200 chars for comparison)
        self._recent_outputs.append(response.text[:200])

        # Track recent commands
        if command:
            self._recent_commands.append(command.lower())

        # Check for repeated outputs
        if len(self._recent_outputs) >= self.threshold:
            unique_outputs = len(set(self._recent_outputs))
            if unique_outputs <= 2:
                return True

        # Check for repeated commands
        if len(self._recent_commands) >= self.threshold:
            unique_commands = len(set(self._recent_commands))
            if unique_commands <= 2:
                return True

        return False

    def reset(self) -> None:
        """Reset stuck detection after intervention."""
        self._recent_outputs.clear()
        self._recent_commands.clear()


class GameSessionError(Exception):
    """Error during game session."""


class GameSession:
    """Main game session orchestrator.

    Ties together the game backend, LLM interface, and context
    manager to run an interactive fiction session.
    """

    def __init__(
        self,
        backend: GameBackend,
        llm: LLMInterface,
        config: Config,
    ) -> None:
        """Initialize the game session.

        Args:
            backend: Game interpreter backend.
            llm: LLM interface for generating commands.
            config: Application configuration.
        """
        self.backend = backend
        self.llm = llm
        self.config = config
        self.context = ContextManager(
            max_recent_turns=config.memory.max_recent_turns,
            summarize_threshold=config.memory.summarize_threshold,
            llm=llm,
        )
        self._stuck_detector = StuckDetector(threshold=config.stuck_threshold)
        self._turn_count = 0
        self._max_turns: int | None = None
        self._running = False

    async def run(
        self,
        game_path: Path,
        max_turns: int | None = None,
        on_game_output: OutputCallback | None = None,
        on_llm_response: ResponseCallback | None = None,
    ) -> GameResult:
        """Run the main game loop.

        Args:
            game_path: Path to the game file.
            max_turns: Optional maximum number of turns.
            on_game_output: Callback for game output.
            on_llm_response: Callback for LLM responses.

        Returns:
            GameResult with session outcome.
        """
        self._max_turns = max_turns
        self._running = True
        self._turn_count = 0

        try:
            # Start the game
            intro = self.backend.start(str(game_path))
            self._handle_game_output(intro, on_game_output)

            # Main game loop
            while self._should_continue():
                try:
                    # Check for summarization
                    await self.context.maybe_summarize()

                    # Get LLM response
                    response = await self._get_llm_response()
                    self._handle_llm_response(response, on_llm_response)

                    # Handle meta commands
                    if response.is_meta:
                        meta_result = self._handle_meta_command(response)
                        if meta_result == "quit":
                            break

                    # Send command to game
                    if response.command:
                        game_response = self.backend.send_command(response.command)
                        self._handle_game_output(game_response, on_game_output)

                        # Check for stuck state
                        if self._stuck_detector.check(game_response, response.command):
                            await self._handle_stuck_state()

                        # Check for game over
                        if game_response.state == GameState.GAME_OVER:
                            return GameResult(
                                outcome="game_over",
                                turns=self._turn_count,
                                final_location=self.context.context.current_location,
                            )
                    else:
                        # No command extracted
                        self.context.add_system_note(
                            "No command was extracted from your response. "
                            "Please provide a game command."
                        )

                    self._turn_count += 1

                except GameSessionError as e:
                    # Try to recover
                    recovered = await self._handle_error(e)
                    if not recovered:
                        return GameResult(
                            outcome="error",
                            turns=self._turn_count,
                            error=str(e),
                        )

            return GameResult(
                outcome="max_turns"
                if self._turn_count >= (max_turns or float("inf"))
                else "stopped",
                turns=self._turn_count,
                final_location=self.context.context.current_location,
            )

        finally:
            self._running = False
            self.backend.quit()

    def stop(self) -> None:
        """Signal the game loop to stop."""
        self._running = False

    def _should_continue(self) -> bool:
        """Check if the game loop should continue."""
        if not self._running:
            return False
        if not self.backend.is_running:
            return False
        return not (self._max_turns and self._turn_count >= self._max_turns)

    async def _get_llm_response(self) -> LLMResponse:
        """Get the next command from the LLM.

        Returns:
            LLM response with command.
        """
        messages = self.context.build_messages()
        system_prompt = get_system_prompt(
            game_title=self.backend.game_info.title if self.backend.game_info else None,
            turn_count=self._turn_count,
        )

        return await self.llm.send(messages, system_prompt=system_prompt)

    def _handle_game_output(
        self,
        response: GameResponse,
        callback: OutputCallback | None = None,
    ) -> None:
        """Handle game output.

        Args:
            response: Game response.
            callback: Optional output callback.
        """
        formatted = format_game_output(
            response.text,
            location=response.location,
            turn_number=self._turn_count,
        )
        self.context.add_game_output(formatted, location=response.location)

        if callback:
            callback(response)

    def _handle_llm_response(
        self,
        response: LLMResponse,
        callback: ResponseCallback | None = None,
    ) -> None:
        """Handle LLM response.

        Args:
            response: LLM response.
            callback: Optional response callback.
        """
        self.context.add_player_response(response.raw_text)

        if callback:
            callback(response)

    def _handle_meta_command(self, response: LLMResponse) -> str | None:
        """Handle meta commands (save, restore, quit).

        Args:
            response: LLM response with meta command.

        Returns:
            "quit" if should quit, None otherwise.
        """
        if not response.command:
            return None

        cmd = response.command.lower().split()[0]

        if cmd == "save":
            if self.backend.save():
                self.context.add_system_note("Game saved successfully.")
            else:
                self.context.add_system_note("Failed to save game.")

        elif cmd == "restore":
            restore_response = self.backend.restore()
            self.context.add_game_output(restore_response.text)

        elif cmd in ("quit", "restart"):
            return "quit"

        return None

    async def _handle_stuck_state(self) -> None:
        """Handle when LLM appears stuck."""
        self.context.add_system_note(
            "You appear to be stuck in a loop. Try a completely different approach:\n"
            "- Examine objects you haven't looked at closely\n"
            "- Go in a direction you haven't tried\n"
            "- Check your inventory\n"
            "- Think about what puzzle you're trying to solve"
        )
        self._stuck_detector.reset()

    async def _handle_error(self, error: Exception) -> bool:
        """Try to recover from an error.

        Args:
            error: The error that occurred.

        Returns:
            True if recovery was successful.
        """
        self.context.add_system_note(f"An error occurred: {error}")

        # Try to restore from last save
        try:
            restore_response = self.backend.restore()
            self.context.add_game_output(
                f"Recovered from error by restoring save.\n{restore_response.text}"
            )
            return True
        except Exception:
            return False


async def run_game(
    game_path: Path,
    backend: GameBackend,
    llm: LLMInterface,
    config: Config,
    max_turns: int | None = None,
) -> GameResult:
    """Convenience function to run a game session.

    Args:
        game_path: Path to the game file.
        backend: Game interpreter backend.
        llm: LLM interface.
        config: Application configuration.
        max_turns: Optional maximum turns.

    Returns:
        GameResult with session outcome.
    """
    session = GameSession(backend, llm, config)
    return await session.run(game_path, max_turns=max_turns)
