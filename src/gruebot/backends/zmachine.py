"""Z-Machine backend using dfrotz interpreter."""

import re
from pathlib import Path

from gruebot.backends.base import (
    InterpreterCommunicationError,
    InterpreterProcess,
)
from gruebot.backends.protocol import GameInfo, GameResponse, GameState


class ZMachineBackend:
    """Z-Machine interpreter backend using dfrotz.

    dfrotz is the "dumb terminal" version of frotz, suitable for
    programmatic control via stdin/stdout.
    """

    # Patterns for detecting game state
    _GAME_OVER_PATTERNS = [
        r"\*\*\*\s*(?:You have died|The End|GAME OVER)\s*\*\*\*",
        r"(?:Would you like to|Do you want to)\s+(?:RESTART|RESTORE|QUIT)",
    ]

    def __init__(
        self,
        dfrotz_path: str = "dfrotz",
        save_directory: Path | None = None,
    ) -> None:
        """Initialize the Z-Machine backend.

        Args:
            dfrotz_path: Path to dfrotz executable.
            save_directory: Directory for save files.
        """
        self.dfrotz_path = dfrotz_path
        self.save_directory = save_directory or Path("./saves")
        self._process: InterpreterProcess | None = None
        self._game_info: GameInfo | None = None
        self._current_location: str | None = None

    def start(self, game_path: str) -> GameResponse:
        """Start a Z-Machine game.

        Args:
            game_path: Path to the game file (.z3, .z4, .z5, .z8, .zblorb).

        Returns:
            GameResponse with the game's introduction.

        Raises:
            InterpreterStartError: If dfrotz fails to start.
            FileNotFoundError: If the game file doesn't exist.
        """
        game_path_obj = Path(game_path)
        if not game_path_obj.exists():
            raise FileNotFoundError(f"Game file not found: {game_path}")

        # Ensure save directory exists
        self.save_directory.mkdir(parents=True, exist_ok=True)

        # Start dfrotz with the game
        # -p: Don't pause at end of page
        # -w 80: Set screen width
        self._process = InterpreterProcess.start(
            cmd=[self.dfrotz_path, "-p", "-w", "80", str(game_path_obj)],
            cwd=str(self.save_directory),
        )

        # Read initial game output
        intro_text = self._read_response()

        # Extract game info from intro
        self._game_info = GameInfo(
            title=self._extract_title(intro_text),
            author=self._extract_author(intro_text),
            format="zmachine",
            file_path=str(game_path_obj.absolute()),
        )

        # Try to extract initial location
        self._current_location = self._extract_location(intro_text)

        return GameResponse(
            text=intro_text,
            location=self._current_location,
            state=GameState.WAITING_INPUT,
        )

    def send_command(self, command: str) -> GameResponse:
        """Send a command to the game.

        Args:
            command: The command to send.

        Returns:
            GameResponse with the game's output.

        Raises:
            InterpreterCommunicationError: If communication fails.
            RuntimeError: If no game is running.
        """
        if self._process is None or not self._process.is_alive:
            raise RuntimeError("No game is currently running")

        # Send the command
        self._process.write_line(command)

        # Read the response
        response_text = self._read_response()

        # Strip echoed command from beginning of response
        response_text = self._strip_command_echo(response_text, command)

        # Update current location if changed
        new_location = self._extract_location(response_text)
        if new_location:
            self._current_location = new_location

        # Determine game state
        state = self._detect_game_state(response_text)

        return GameResponse(
            text=response_text,
            location=self._current_location,
            state=state,
        )

    def save(self, slot: str = "default") -> bool:
        """Save the current game state.

        Args:
            slot: Name for the save slot.

        Returns:
            True if save was successful.
        """
        if self._process is None or not self._process.is_alive:
            return False

        save_file = self.save_directory / f"{slot}.sav"

        # Send save command
        self._process.write_line("save")

        # dfrotz will prompt for filename - read and discard
        self._read_response()

        # Provide filename
        self._process.write_line(str(save_file))

        # Read confirmation
        confirmation = self._read_response()

        return "ok" in confirmation.lower() or "saved" in confirmation.lower()

    def restore(self, slot: str = "default") -> GameResponse:
        """Restore a saved game state.

        Args:
            slot: Name of the save slot.

        Returns:
            GameResponse after restoring.
        """
        if self._process is None or not self._process.is_alive:
            raise RuntimeError("No game is currently running")

        save_file = self.save_directory / f"{slot}.sav"

        if not save_file.exists():
            return GameResponse(
                text=f"Save file not found: {slot}",
                state=GameState.ERROR,
            )

        # Send restore command
        self._process.write_line("restore")

        # dfrotz will prompt for filename
        self._read_response()

        # Provide filename
        self._process.write_line(str(save_file))

        # Read response after restore
        response_text = self._read_response()

        # Update location
        self._current_location = self._extract_location(response_text)

        return GameResponse(
            text=response_text,
            location=self._current_location,
            state=GameState.WAITING_INPUT,
        )

    def quit(self) -> None:
        """Quit the game and clean up."""
        if self._process is not None:
            if self._process.is_alive:
                try:
                    self._process.write_line("quit")
                    self._process.write_line("y")  # Confirm quit
                except InterpreterCommunicationError:
                    pass  # Process may have already exited

            self._process.terminate()
            self._process = None

    @property
    def is_running(self) -> bool:
        """Check if a game is currently running."""
        return self._process is not None and self._process.is_alive

    @property
    def game_info(self) -> GameInfo | None:
        """Get information about the current game."""
        return self._game_info

    def _read_response(self) -> str:
        """Read game output until the next input prompt.

        Returns:
            The game's response text.
        """
        if self._process is None:
            return ""

        # Read until we see a prompt (usually '>')
        output = self._process.read_until_prompt(prompt_char=">")

        # Clean up the output
        return self._clean_output(output)

    def _clean_output(self, text: str) -> str:
        """Clean up dfrotz output.

        Removes extra whitespace and prompt characters.

        Args:
            text: Raw output from dfrotz.

        Returns:
            Cleaned output text.
        """
        # Remove trailing prompt and whitespace
        text = text.rstrip()
        if text.endswith(">"):
            text = text[:-1].rstrip()

        # Normalize line endings
        text = text.replace("\r\n", "\n")

        # Remove excessive blank lines
        lines = text.split("\n")
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if not (is_blank and prev_blank):
                cleaned_lines.append(line)
            prev_blank = is_blank

        return "\n".join(cleaned_lines)

    def _strip_command_echo(self, text: str, command: str) -> str:
        """Strip the echoed command from the beginning of text.

        IF games typically echo the player's command back. This removes
        that echo for cleaner output.

        Args:
            text: Response text that may contain echoed command.
            command: The command that was sent.

        Returns:
            Text with echoed command stripped.
        """
        # Check if text starts with the command (case-insensitive)
        if text.lower().startswith(command.lower()):
            text = text[len(command) :].lstrip()

        return text

    def _detect_game_state(self, text: str) -> GameState:
        """Detect the game state from response text.

        Args:
            text: Game response text.

        Returns:
            Detected GameState.
        """
        for pattern in self._GAME_OVER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GameState.GAME_OVER

        return GameState.WAITING_INPUT

    def _extract_location(self, text: str) -> str | None:
        """Extract the current location from game text.

        Many IF games display the location in a specific format,
        often on its own line or in the status bar area.

        Args:
            text: Game response text.

        Returns:
            Location name if found, None otherwise.
        """
        lines = text.strip().split("\n")

        # Look for a standalone location line (common in IF)
        # Usually a short line that looks like a room name
        for line in lines[:5]:  # Check first few lines
            line = line.strip()
            # Skip empty lines and obvious non-locations
            if not line or len(line) > 60:
                continue
            # Skip lines that look like descriptions (contain certain punctuation)
            if "." in line or "," in line or "!" in line or "?" in line:
                continue
            # Potential location - capitalized, not too long
            if line[0].isupper() and 3 <= len(line) <= 50:
                return line

        return None

    def _extract_title(self, intro_text: str) -> str | None:
        """Extract game title from introduction text.

        Args:
            intro_text: Game introduction text.

        Returns:
            Title if found, None otherwise.
        """
        lines = intro_text.strip().split("\n")
        for line in lines[:10]:
            line = line.strip()
            if line and len(line) > 3:
                # First substantial line is often the title
                return line
        return None

    def _extract_author(self, intro_text: str) -> str | None:
        """Extract author from introduction text.

        Args:
            intro_text: Game introduction text.

        Returns:
            Author if found, None otherwise.
        """
        # Look for common author patterns
        # Use [^\n] instead of . to avoid matching across lines
        patterns = [
            r"(?:by|written by|author[:\s]+)\s*([A-Z][a-zA-Z \.]+)",
            r"(?:Copyright|©|\(c\))\s*\d*\s*(?:by\s+)?([A-Z][a-zA-Z \.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, intro_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
