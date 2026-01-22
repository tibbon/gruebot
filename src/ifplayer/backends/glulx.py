"""Glulx backend using glulxe interpreter with remglk JSON I/O."""

import json
import re
from pathlib import Path
from typing import Any

from ifplayer.backends.base import (
    InterpreterCommunicationError,
    InterpreterProcess,
)
from ifplayer.backends.protocol import GameInfo, GameResponse, GameState


class GlulxBackend:
    """Glulx interpreter backend using glulxe with remglk.

    remglk provides a JSON-based I/O protocol for Glk applications,
    making it easier to programmatically control Glulx games.
    """

    # Patterns for detecting game state
    _GAME_OVER_PATTERNS = [
        r"\*\*\*\s*(?:You have died|The End|GAME OVER)\s*\*\*\*",
        r"(?:Would you like to|Do you want to)\s+(?:RESTART|RESTORE|QUIT)",
    ]

    def __init__(
        self,
        glulxe_path: str = "glulxe",
        save_directory: Path | None = None,
        screen_width: int = 80,
        screen_height: int = 50,
    ) -> None:
        """Initialize the Glulx backend.

        Args:
            glulxe_path: Path to glulxe executable (built with remglk).
            save_directory: Directory for save files.
            screen_width: Virtual screen width for the interpreter.
            screen_height: Virtual screen height for the interpreter.
        """
        self.glulxe_path = glulxe_path
        self.save_directory = save_directory or Path("./saves")
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._process: InterpreterProcess | None = None
        self._game_info: GameInfo | None = None
        self._current_location: str | None = None
        self._gen: int = 0  # Generation counter for remglk protocol
        self._input_window: int | None = None  # Window ID expecting input
        self._windows: dict[int, dict[str, Any]] = {}  # Cached window info

    def start(self, game_path: str) -> GameResponse:
        """Start a Glulx game.

        Args:
            game_path: Path to the game file (.ulx, .gblorb, .glb).

        Returns:
            GameResponse with the game's introduction.

        Raises:
            InterpreterStartError: If glulxe fails to start.
            FileNotFoundError: If the game file doesn't exist.
        """
        game_path_obj = Path(game_path)
        if not game_path_obj.exists():
            raise FileNotFoundError(f"Game file not found: {game_path}")

        # Ensure save directory exists
        self.save_directory.mkdir(parents=True, exist_ok=True)

        # Start glulxe with fixed metrics (skip init handshake)
        # -fm: fixed metrics mode
        # -width: screen width
        # -height: screen height
        self._process = InterpreterProcess.start(
            cmd=[
                self.glulxe_path,
                "-fm",
                "-width",
                str(self.screen_width),
                "-height",
                str(self.screen_height),
                str(game_path_obj),
            ],
            cwd=str(self.save_directory),
        )

        # Read initial game output
        update = self._read_update()

        # Extract text from the update
        intro_text = self._extract_text(update)

        # Extract game info from intro
        self._game_info = GameInfo(
            title=self._extract_title(intro_text),
            author=self._extract_author(intro_text),
            format="glulx",
            file_path=str(game_path_obj.absolute()),
        )

        # Try to extract initial location from grid window
        self._current_location = self._extract_location_from_update(update)

        return GameResponse(
            text=intro_text,
            location=self._current_location,
            state=self._detect_game_state_from_update(update, intro_text),
            raw_output=update,
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

        if self._input_window is None:
            raise RuntimeError("Game is not waiting for input")

        # Send line input as JSON
        input_msg = {
            "type": "line",
            "gen": self._gen,
            "window": self._input_window,
            "value": command,
        }
        self._send_json(input_msg)

        # Read the response
        update = self._read_update()

        # Extract text from the update
        response_text = self._extract_text(update)

        # Update location from grid window
        new_location = self._extract_location_from_update(update)
        if new_location:
            self._current_location = new_location

        # Determine game state
        state = self._detect_game_state_from_update(update, response_text)

        return GameResponse(
            text=response_text,
            location=self._current_location,
            state=state,
            raw_output=update,
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

        if self._input_window is None:
            return False

        # Send save command
        input_msg = {
            "type": "line",
            "gen": self._gen,
            "window": self._input_window,
            "value": "save",
        }
        self._send_json(input_msg)

        # Read prompt for filename (will be a fileref_prompt specialinput)
        update = self._read_update()

        # Check if we got a file prompt
        if "specialinput" in update and update.get("specialinput", {}).get("type") == "fileref_prompt":
            # Provide the save filename
            save_file = str(self.save_directory / f"{slot}.glksave")
            fileref_msg = {
                "type": "specialresponse",
                "gen": self._gen,
                "response": "fileref_prompt",
                "value": save_file,
            }
            self._send_json(fileref_msg)

            # Read confirmation
            update = self._read_update()
            response_text = self._extract_text(update)
            return "saved" in response_text.lower() or "ok" in response_text.lower()

        # Some games might handle save differently
        response_text = self._extract_text(update)
        return "saved" in response_text.lower()

    def restore(self, slot: str = "default") -> GameResponse:
        """Restore a saved game state.

        Args:
            slot: Name of the save slot.

        Returns:
            GameResponse after restoring.
        """
        if self._process is None or not self._process.is_alive:
            raise RuntimeError("No game is currently running")

        if self._input_window is None:
            raise RuntimeError("Game is not waiting for input")

        save_file = self.save_directory / f"{slot}.glksave"

        if not save_file.exists():
            return GameResponse(
                text=f"Save file not found: {slot}",
                state=GameState.ERROR,
            )

        # Send restore command
        input_msg = {
            "type": "line",
            "gen": self._gen,
            "window": self._input_window,
            "value": "restore",
        }
        self._send_json(input_msg)

        # Read prompt for filename
        update = self._read_update()

        # Check if we got a file prompt
        if "specialinput" in update and update.get("specialinput", {}).get("type") == "fileref_prompt":
            # Provide the save filename
            fileref_msg = {
                "type": "specialresponse",
                "gen": self._gen,
                "response": "fileref_prompt",
                "value": str(save_file),
            }
            self._send_json(fileref_msg)

            # Read response after restore
            update = self._read_update()

        response_text = self._extract_text(update)

        # Update location
        self._current_location = self._extract_location_from_update(update)

        return GameResponse(
            text=response_text,
            location=self._current_location,
            state=self._detect_game_state_from_update(update, response_text),
            raw_output=update,
        )

    def quit(self) -> None:
        """Quit the game and clean up."""
        if self._process is not None:
            if self._process.is_alive and self._input_window is not None:
                try:
                    input_msg = {
                        "type": "line",
                        "gen": self._gen,
                        "window": self._input_window,
                        "value": "quit",
                    }
                    self._send_json(input_msg)

                    # Try to read and confirm quit if needed
                    try:
                        update = self._read_update()
                        if "input" in update:
                            # Game might ask for confirmation
                            confirm_msg = {
                                "type": "line",
                                "gen": self._gen,
                                "window": self._input_window,
                                "value": "yes",
                            }
                            self._send_json(confirm_msg)
                    except InterpreterCommunicationError:
                        pass  # Game may have already exited
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

    def _send_json(self, msg: dict[str, Any]) -> None:
        """Send a JSON message to the interpreter.

        Args:
            msg: JSON-serializable message.
        """
        if self._process is None:
            raise InterpreterCommunicationError("No interpreter process")

        json_str = json.dumps(msg)
        # remglk expects each message followed by a blank line
        self._process.write(json_str + "\n\n")

    def _read_update(self) -> dict[str, Any]:
        """Read a JSON update from the interpreter.

        Returns:
            Parsed JSON update.

        Raises:
            InterpreterCommunicationError: If reading or parsing fails.
        """
        if self._process is None:
            raise InterpreterCommunicationError("No interpreter process")

        # Read until we get a complete JSON object (ends with blank line)
        lines: list[str] = []
        while True:
            line = self._process.readline()
            if not line:
                break
            if line.strip() == "":
                if lines:  # Got content, now got blank line = end of message
                    break
                continue  # Skip leading blank lines
            lines.append(line)

        if not lines:
            raise InterpreterCommunicationError("No output from interpreter")

        json_str = "".join(lines)

        try:
            update = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise InterpreterCommunicationError(f"Failed to parse JSON: {e}") from e

        # Update generation counter and input window
        if "gen" in update:
            self._gen = update["gen"]

        # Cache window info (windows array only sent when they change)
        for window in update.get("windows", []):
            window_id = window.get("id")
            if window_id is not None:
                self._windows[window_id] = window

        # Find window expecting input
        self._input_window = None
        for input_req in update.get("input", []):
            if input_req.get("type") == "line":
                self._input_window = input_req["id"]
                break

        # update is already a dict from json.loads
        result: dict[str, Any] = update
        return result

    def _extract_text(self, update: dict[str, Any]) -> str:
        """Extract readable text from a remglk update.

        Args:
            update: Parsed JSON update.

        Returns:
            Extracted text content.
        """
        text_parts = []

        # Process content for each window
        for content in update.get("content", []):
            window_id = content.get("id")
            window_info = self._find_window(update, window_id)

            if window_info and window_info.get("type") == "buffer":
                # Buffer window - story text
                for item in content.get("text", []):
                    if isinstance(item, dict):
                        if "content" in item:
                            # Text with styling
                            for segment in item["content"]:
                                if isinstance(segment, str):
                                    text_parts.append(segment)
                                elif isinstance(segment, dict):
                                    text_parts.append(segment.get("text", ""))
                        elif "text" in item:
                            text_parts.append(item["text"])
                    elif isinstance(item, str):
                        text_parts.append(item)
                # Add newline after each text item
                if content.get("text"):
                    text_parts.append("\n")

            elif window_info and window_info.get("type") == "grid":
                # Grid window - status bar (skip for main text)
                pass

        # Clean up the text
        text = "".join(text_parts)
        text = self._clean_text(text)
        return text

    def _find_window(self, update: dict[str, Any], window_id: int | None) -> dict[str, Any] | None:
        """Find window info by ID.

        Uses cached window info since remglk only sends windows array
        when windows change. Falls back to checking the update directly.

        Args:
            update: Parsed JSON update.
            window_id: Window ID to find.

        Returns:
            Window info dict or None.
        """
        if window_id is None:
            return None

        # Check cache first
        if window_id in self._windows:
            return self._windows[window_id]

        # Fallback: check the current update (for first call or tests)
        for window in update.get("windows", []):
            if window.get("id") == window_id:
                result: dict[str, Any] = window
                return result

        return None

    def _extract_location_from_update(self, update: dict[str, Any]) -> str | None:
        """Extract location from grid window (status bar).

        Args:
            update: Parsed JSON update.

        Returns:
            Location name if found.
        """
        for content in update.get("content", []):
            window_id = content.get("id")
            window_info = self._find_window(update, window_id)

            if window_info and window_info.get("type") == "grid":
                # Grid windows often contain the status bar with location
                lines = content.get("lines", [])
                if lines:
                    first_line = lines[0]
                    line_content = first_line.get("content", [])
                    text_parts = []
                    for item in line_content:
                        if isinstance(item, str):
                            text_parts.append(item)
                        elif isinstance(item, dict):
                            text_parts.append(item.get("text", ""))
                    location_text = "".join(text_parts).strip()
                    # Often format is "Location Name    Score: 0  Turns: 1"
                    # Extract just the location part
                    if location_text:
                        # Split at multiple spaces or common separators
                        parts = re.split(r"\s{2,}|Score:|Turns:|Moves:", location_text)
                        if parts:
                            return parts[0].strip()
        return None

    def _detect_game_state_from_update(
        self, update: dict[str, Any], text: str
    ) -> GameState:
        """Detect game state from update and text.

        Args:
            update: Parsed JSON update.
            text: Extracted text content.

        Returns:
            Detected GameState.
        """
        # Check for explicit exit
        if update.get("exit"):
            return GameState.GAME_OVER

        # Check for no input requested (game might be over)
        if not update.get("input"):
            return GameState.GAME_OVER

        # Check text for game over patterns
        for pattern in self._GAME_OVER_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return GameState.GAME_OVER

        return GameState.WAITING_INPUT

    def _clean_text(self, text: str) -> str:
        """Clean up extracted text.

        Args:
            text: Raw extracted text.

        Returns:
            Cleaned text.
        """
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

        text = "\n".join(cleaned_lines)

        # Strip leading/trailing whitespace
        return text.strip()

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
                return line
        return None

    def _extract_author(self, intro_text: str) -> str | None:
        """Extract author from introduction text.

        Args:
            intro_text: Game introduction text.

        Returns:
            Author if found, None otherwise.
        """
        patterns = [
            r"(?:by|written by|author[:\s]+)\s*([A-Z][a-zA-Z \.]+)",
            r"(?:Copyright|©|\(c\))\s*\d*\s*(?:by\s+)?([A-Z][a-zA-Z \.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, intro_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
