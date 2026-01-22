"""MUD backend using telnet connection."""

import asyncio
import re
from dataclasses import dataclass

from gruebot.backends.protocol import GameInfo, GameResponse, GameState


class MUDConnectionError(Exception):
    """Error connecting to MUD server."""


class MUDTimeoutError(Exception):
    """Timeout waiting for MUD response."""


@dataclass
class MUDConfig:
    """Configuration for MUD connection."""

    host: str
    port: int = 23
    encoding: str = "utf-8"
    # Timeout for reading responses (seconds)
    read_timeout: float = 5.0
    # Time to wait for more output after initial response
    settle_time: float = 0.5
    # Patterns that indicate the MUD is waiting for input
    prompt_patterns: list[str] | None = None

    def __post_init__(self) -> None:
        if self.prompt_patterns is None:
            # Common MUD prompt patterns
            self.prompt_patterns = [
                r"^>",  # Simple prompt
                r"^\[.*\]>",  # [Room] >
                r"^HP:.*>",  # HP: 100 >
                r"^\d+h, \d+m",  # 100h, 50m (DikuMUD style)
                r"^What is your name\?",  # Login prompt
                r"^Password:",  # Password prompt
                r"^Enter your character",  # Character selection
            ]


class MUDBackend:
    """MUD backend using telnet connection.

    Connects to MUD servers via telnet and handles the
    real-time, streaming nature of MUD output.
    """

    def __init__(self, config: MUDConfig) -> None:
        """Initialize the MUD backend.

        Args:
            config: MUD connection configuration.
        """
        self.config = config
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._game_info: GameInfo | None = None
        self._current_location: str | None = None
        self._buffer: str = ""
        self._connected: bool = False

    async def connect(self) -> GameResponse:
        """Connect to the MUD server.

        Returns:
            GameResponse with the initial connection text.

        Raises:
            MUDConnectionError: If connection fails.
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.config.host, self.config.port),
                timeout=10.0,
            )
            self._connected = True

            # Read initial welcome/login text
            initial_text = await self._read_until_prompt()

            self._game_info = GameInfo(
                title=f"MUD: {self.config.host}:{self.config.port}",
                author=None,
                format="mud",
                file_path=f"telnet://{self.config.host}:{self.config.port}",
            )

            return GameResponse(
                text=initial_text,
                location=self._current_location,
                state=GameState.WAITING_INPUT,
            )

        except TimeoutError as e:
            raise MUDConnectionError(
                f"Timeout connecting to {self.config.host}:{self.config.port}"
            ) from e
        except OSError as e:
            raise MUDConnectionError(
                f"Failed to connect to {self.config.host}:{self.config.port}: {e}"
            ) from e

    def start(self, game_path: str) -> GameResponse:
        """Start connection to MUD (sync wrapper).

        Args:
            game_path: MUD address in format "host:port" or just "host".

        Returns:
            GameResponse with initial text.
        """
        # Parse host:port from game_path
        if ":" in game_path:
            host, port_str = game_path.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                host = game_path
                port = self.config.port
        else:
            host = game_path
            port = self.config.port

        self.config.host = host
        self.config.port = port

        # Run async connect
        return asyncio.get_event_loop().run_until_complete(self.connect())

    def send_command(self, command: str) -> GameResponse:
        """Send a command to the MUD.

        Args:
            command: The command to send.

        Returns:
            GameResponse with the MUD's output.
        """
        return asyncio.get_event_loop().run_until_complete(self.send_command_async(command))

    async def send_command_async(self, command: str) -> GameResponse:
        """Send a command to the MUD (async).

        Args:
            command: The command to send.

        Returns:
            GameResponse with the MUD's output.

        Raises:
            RuntimeError: If not connected.
            MUDTimeoutError: If response times out.
        """
        if not self._connected or self._writer is None:
            raise RuntimeError("Not connected to MUD")

        # Send the command
        self._writer.write((command + "\r\n").encode(self.config.encoding))
        await self._writer.drain()

        # Read the response
        response_text = await self._read_until_prompt()

        # Strip the echoed command if present
        response_text = self._strip_command_echo(response_text, command)

        # Try to extract location from response
        new_location = self._extract_location(response_text)
        if new_location:
            self._current_location = new_location

        return GameResponse(
            text=response_text,
            location=self._current_location,
            state=self._detect_game_state(response_text),
        )

    async def _read_until_prompt(self) -> str:
        """Read from MUD until a prompt is detected or timeout.

        Returns:
            The text received.

        Raises:
            MUDTimeoutError: If read times out with no prompt.
        """
        if self._reader is None:
            return ""

        collected: list[str] = []
        last_receive_time = asyncio.get_event_loop().time()

        while True:
            try:
                # Try to read with a short timeout
                data = await asyncio.wait_for(
                    self._reader.read(4096),
                    timeout=self.config.settle_time,
                )

                if not data:
                    # Connection closed
                    self._connected = False
                    break

                text = data.decode(self.config.encoding, errors="replace")
                # Handle telnet IAC sequences by stripping them
                text = self._strip_telnet_sequences(text)
                collected.append(text)
                last_receive_time = asyncio.get_event_loop().time()

                # Check if we've hit a prompt
                full_text = "".join(collected)
                if self._is_at_prompt(full_text):
                    break

            except TimeoutError:
                # No data received within settle_time
                current_time = asyncio.get_event_loop().time()
                elapsed = current_time - last_receive_time

                if collected:
                    # We have some text, check if it looks complete
                    full_text = "".join(collected)
                    if self._is_at_prompt(full_text) or elapsed > self.config.settle_time:
                        break

                if elapsed > self.config.read_timeout:
                    if collected:
                        break
                    raise MUDTimeoutError("Timeout waiting for MUD response") from None

        return self._clean_text("".join(collected))

    def _strip_telnet_sequences(self, text: str) -> str:
        """Strip telnet IAC sequences from text.

        Args:
            text: Text potentially containing telnet sequences.

        Returns:
            Cleaned text.
        """
        # IAC = 0xFF, followed by command byte and possibly option byte
        # Simple approach: remove sequences starting with \xff
        result = []
        i = 0
        while i < len(text):
            if text[i] == "\xff" and i + 1 < len(text):
                cmd = ord(text[i + 1])
                if cmd >= 251 and cmd <= 254:  # WILL/WONT/DO/DONT
                    i += 3  # Skip IAC + cmd + option
                elif cmd == 250:  # SB (subnegotiation)
                    # Skip until IAC SE (255, 240)
                    end = text.find("\xff\xf0", i)
                    if end != -1:
                        i = end + 2
                    else:
                        i += 2
                else:
                    i += 2  # Skip IAC + cmd
            else:
                result.append(text[i])
                i += 1
        return "".join(result)

    def _is_at_prompt(self, text: str) -> bool:
        """Check if text ends with a prompt pattern.

        Args:
            text: Text to check.

        Returns:
            True if text appears to end at a prompt.
        """
        if not text:
            return False

        # Check last few lines for prompt patterns
        lines = text.strip().split("\n")
        last_lines = "\n".join(lines[-3:]) if len(lines) > 3 else text

        for pattern in self.config.prompt_patterns or []:
            if re.search(pattern, last_lines, re.MULTILINE | re.IGNORECASE):
                return True

        return False

    def _clean_text(self, text: str) -> str:
        """Clean up MUD output text.

        Args:
            text: Raw MUD output.

        Returns:
            Cleaned text.
        """
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove ANSI color codes
        ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")
        text = ansi_pattern.sub("", text)

        # Remove other ANSI sequences
        text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)

        # Remove excessive blank lines
        lines = text.split("\n")
        cleaned_lines = []
        prev_blank = False
        for line in lines:
            is_blank = not line.strip()
            if not (is_blank and prev_blank):
                cleaned_lines.append(line)
            prev_blank = is_blank

        return "\n".join(cleaned_lines).strip()

    def _strip_command_echo(self, text: str, command: str) -> str:
        """Strip echoed command from response.

        Args:
            text: Response text.
            command: Command that was sent.

        Returns:
            Text with echo stripped.
        """
        lines = text.split("\n")
        if lines and lines[0].strip().lower() == command.lower():
            return "\n".join(lines[1:]).strip()
        return text

    def _extract_location(self, text: str) -> str | None:
        """Extract location from MUD output.

        Args:
            text: MUD response text.

        Returns:
            Location name if found.
        """
        lines = text.strip().split("\n")

        # Look for room name patterns (often first line, possibly colored)
        for line in lines[:3]:
            line = line.strip()
            # Skip empty lines and obvious non-room-names
            if not line or len(line) > 60:
                continue
            # Skip lines that look like descriptions
            if "." in line or "," in line:
                continue
            # Potential room name
            if line and line[0].isupper():
                return line

        return None

    def _detect_game_state(self, text: str) -> GameState:
        """Detect game state from response.

        Args:
            text: MUD response text.

        Returns:
            Detected GameState.
        """
        lower_text = text.lower()

        # Check for disconnect/quit messages
        if any(
            phrase in lower_text
            for phrase in ["connection closed", "goodbye", "disconnected", "come back soon"]
        ):
            return GameState.GAME_OVER

        return GameState.WAITING_INPUT

    def save(self, slot: str = "default") -> bool:  # noqa: ARG002
        """Save is not typically supported for MUDs.

        Args:
            slot: Ignored for MUDs.

        Returns:
            False (MUDs don't support save in the traditional sense).
        """
        # Most MUDs auto-save or have their own save commands
        return False

    def restore(self, slot: str = "default") -> GameResponse:  # noqa: ARG002
        """Restore is not supported for MUDs.

        Args:
            slot: Ignored.

        Returns:
            Error response.
        """
        return GameResponse(
            text="MUDs do not support restore. Your character state is saved on the server.",
            state=GameState.ERROR,
        )

    def quit(self) -> None:
        """Disconnect from the MUD."""
        if self._writer is not None:
            try:
                self._writer.write(b"quit\r\n")
                asyncio.get_event_loop().run_until_complete(self._writer.drain())
            except Exception:
                pass
            self._writer.close()

        self._connected = False
        self._reader = None
        self._writer = None

    @property
    def is_running(self) -> bool:
        """Check if connected to MUD."""
        return self._connected

    @property
    def game_info(self) -> GameInfo | None:
        """Get MUD connection info."""
        return self._game_info
