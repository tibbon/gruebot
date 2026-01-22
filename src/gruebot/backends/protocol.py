"""Protocol definitions for game backends."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Protocol


class GameState(Enum):
    """Current state of the game."""

    RUNNING = auto()
    WAITING_INPUT = auto()
    GAME_OVER = auto()
    ERROR = auto()


@dataclass
class GameResponse:
    """Output from a game command."""

    text: str
    location: str | None = None
    state: GameState = GameState.WAITING_INPUT
    raw_output: dict[str, Any] | None = None


@dataclass
class GameInfo:
    """Metadata about the loaded game."""

    title: str | None
    author: str | None
    format: str  # "zmachine" or "glulx"
    file_path: str
    extra: dict[str, Any] = field(default_factory=dict)


class GameBackend(Protocol):
    """Protocol for game interpreter backends.

    Implementations must provide methods to start a game, send commands,
    and manage game state (save/restore/quit).
    """

    def start(self, game_path: str) -> GameResponse:
        """Start a game and return the intro text.

        Args:
            game_path: Path to the game file.

        Returns:
            GameResponse with the game's introduction text.
        """
        ...

    def send_command(self, command: str) -> GameResponse:
        """Send a command to the game and return the response.

        Args:
            command: The command to send (e.g., "go north", "take lamp").

        Returns:
            GameResponse with the game's output.
        """
        ...

    def save(self, slot: str = "default") -> bool:
        """Save the current game state.

        Args:
            slot: Name of the save slot.

        Returns:
            True if save was successful.
        """
        ...

    def restore(self, slot: str = "default") -> GameResponse:
        """Restore a saved game state.

        Args:
            slot: Name of the save slot to restore.

        Returns:
            GameResponse after restoring.
        """
        ...

    def quit(self) -> None:
        """Cleanly shut down the interpreter."""
        ...

    @property
    def is_running(self) -> bool:
        """Check if the interpreter process is alive."""
        ...

    @property
    def game_info(self) -> GameInfo | None:
        """Return metadata about the loaded game."""
        ...
