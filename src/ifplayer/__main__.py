"""Entry point for ifplayer CLI."""

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ifplayer import __version__
from ifplayer.backends.glulx import GlulxBackend
from ifplayer.backends.protocol import GameResponse
from ifplayer.backends.zmachine import ZMachineBackend
from ifplayer.config import load_config
from ifplayer.llm.anthropic_api import AnthropicAPIBackend
from ifplayer.llm.claude_cli import ClaudeCLIBackend
from ifplayer.llm.protocol import LLMResponse
from ifplayer.logging.transcript import TranscriptLogger, create_transcript_paths
from ifplayer.main import GameSession

app = typer.Typer(
    name="ifplayer",
    help="LLM-powered interactive fiction player",
)
console = Console()

# Z-Machine file extensions
ZMACHINE_EXTENSIONS = {".z1", ".z2", ".z3", ".z4", ".z5", ".z6", ".z7", ".z8", ".zblorb"}

# Glulx file extensions
GLULX_EXTENSIONS = {".ulx", ".gblorb", ".glb", ".blb"}


def detect_game_format(game_path: Path) -> str:
    """Detect game format from file extension.

    Args:
        game_path: Path to the game file.

    Returns:
        "zmachine" or "glulx"

    Raises:
        typer.BadParameter: If format cannot be detected.
    """
    ext = game_path.suffix.lower()

    if ext in ZMACHINE_EXTENSIONS:
        return "zmachine"
    elif ext in GLULX_EXTENSIONS:
        return "glulx"
    else:
        raise typer.BadParameter(
            f"Unknown game format for extension '{ext}'. "
            f"Supported Z-Machine: {sorted(ZMACHINE_EXTENSIONS)}, "
            f"Glulx: {sorted(GLULX_EXTENSIONS)}"
        )


def create_game_backend(
    game_format: str,
    config_path: str | None,
    dfrotz_path: str | None,
    glulxe_path: str | None,
) -> ZMachineBackend | GlulxBackend:
    """Create the appropriate game backend.

    Args:
        game_format: "zmachine" or "glulx"
        config_path: Optional config file path
        dfrotz_path: Optional dfrotz path override
        glulxe_path: Optional glulxe path override

    Returns:
        Game backend instance.
    """
    config = load_config(Path(config_path) if config_path else None)

    if game_format == "zmachine":
        return ZMachineBackend(
            dfrotz_path=dfrotz_path or config.game.dfrotz_path,
            save_directory=config.game.save_directory,
        )
    else:
        return GlulxBackend(
            glulxe_path=glulxe_path or config.game.glulxe_path,
            save_directory=config.game.save_directory,
        )


def create_llm_backend(
    backend_type: str,
    config_path: str | None,
) -> AnthropicAPIBackend | ClaudeCLIBackend:
    """Create the LLM backend.

    Args:
        backend_type: "anthropic_api" or "claude_cli"
        config_path: Optional config file path

    Returns:
        LLM backend instance.
    """
    config = load_config(Path(config_path) if config_path else None)

    if backend_type == "anthropic_api":
        return AnthropicAPIBackend(
            model=config.llm.model,
            max_tokens=config.llm.max_tokens,
            temperature=config.llm.temperature,
        )
    else:
        return ClaudeCLIBackend()


@app.command()
def play(
    game_path: Annotated[
        Path,
        typer.Argument(
            help="Path to the game file (.z5, .z8, .ulx, .gblorb, etc.)",
            exists=True,
            dir_okay=False,
        ),
    ],
    config: Annotated[
        str | None,
        typer.Option("--config", "-c", help="Path to config YAML file"),
    ] = None,
    llm_backend: Annotated[
        str,
        typer.Option(
            "--llm",
            "-l",
            help="LLM backend: anthropic_api or claude_cli",
        ),
    ] = "anthropic_api",
    game_backend: Annotated[
        str,
        typer.Option(
            "--backend",
            "-b",
            help="Game backend: auto, zmachine, or glulx",
        ),
    ] = "auto",
    max_turns: Annotated[
        int | None,
        typer.Option("--max-turns", "-m", help="Maximum turns before stopping"),
    ] = None,
    transcript_dir: Annotated[
        Path | None,
        typer.Option("--transcript-dir", "-t", help="Directory for transcripts"),
    ] = None,
    no_transcript: Annotated[
        bool,
        typer.Option("--no-transcript", help="Disable transcript logging"),
    ] = False,
    dfrotz_path: Annotated[
        str | None,
        typer.Option("--dfrotz", help="Path to dfrotz executable"),
    ] = None,
    glulxe_path: Annotated[
        str | None,
        typer.Option("--glulxe", help="Path to glulxe executable"),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Show detailed output"),
    ] = False,
) -> None:
    """Play an interactive fiction game with an LLM as the player."""
    # Determine game format
    game_format = (
        detect_game_format(game_path) if game_backend == "auto" else game_backend
    )

    console.print(f"[bold blue]IF Player[/bold blue] - {game_path.name}")
    console.print(f"  Backend: {game_format}, LLM: {llm_backend}")
    if max_turns:
        console.print(f"  Max turns: {max_turns}")
    console.print()

    # Create backends
    try:
        backend = create_game_backend(game_format, config, dfrotz_path, glulxe_path)
    except Exception as e:
        console.print(f"[red]Error creating game backend:[/red] {e}")
        raise typer.Exit(1) from None

    try:
        llm = create_llm_backend(llm_backend, config)
    except Exception as e:
        console.print(f"[red]Error creating LLM backend:[/red] {e}")
        raise typer.Exit(1) from None

    # Load config for session settings
    app_config = load_config(Path(config) if config else None, game_path)

    # Set up transcript logging
    transcript_logger: TranscriptLogger | None = None
    if not no_transcript:
        t_dir = transcript_dir or app_config.logging.transcript_dir
        t_dir.mkdir(parents=True, exist_ok=True)

        json_path, md_path = create_transcript_paths(t_dir, game_path.stem)
        transcript_logger = TranscriptLogger(
            json_path=json_path if app_config.logging.enable_json else None,
            markdown_path=md_path if app_config.logging.enable_markdown else None,
            game_title=game_path.stem,
        )
        console.print(f"  Transcript: {md_path}")
        console.print()

    # Create game session
    session = GameSession(backend, llm, app_config)  # type: ignore[arg-type]

    # Callbacks for output
    def on_game_output(response: GameResponse) -> None:
        if verbose:
            panel = Panel(
                response.text,
                title=f"[green]Game[/green] - {response.location or 'Unknown'}",
                border_style="green",
            )
            console.print(panel)
        else:
            # Compact output
            if response.location:
                console.print(f"[dim]Location:[/dim] [cyan]{response.location}[/cyan]")
            # Truncate long output
            text = response.text
            if len(text) > 500:
                text = text[:500] + "..."
            console.print(text)
            console.print()

        # Log to transcript
        if transcript_logger:
            transcript_logger.log_game_output(response.text, response.location)

    def on_llm_response(response: LLMResponse) -> None:
        if verbose:
            text = Text()
            if response.reasoning:
                text.append(response.reasoning + "\n\n", style="italic")
            if response.command:
                text.append("Command: ", style="bold")
                text.append(response.command, style="yellow bold")
            panel = Panel(text, title="[blue]Claude[/blue]", border_style="blue")
            console.print(panel)
        else:
            # Compact output
            if response.command:
                console.print(f"[yellow]> {response.command}[/yellow]")
            console.print()

        # Log to transcript
        if transcript_logger:
            transcript_logger.log_llm_response(
                response.raw_text,
                command=response.command,
                reasoning=response.reasoning,
            )

    # Run the game
    console.print("[bold]Starting game...[/bold]")
    console.print("─" * 40)

    try:
        result = asyncio.run(
            session.run(
                game_path,
                max_turns=max_turns,
                on_game_output=on_game_output,
                on_llm_response=on_llm_response,
            )
        )

        # Show result
        console.print("─" * 40)
        console.print(f"[bold]Game ended:[/bold] {result.outcome}")
        console.print(f"  Turns: {result.turns}")
        if result.final_location:
            console.print(f"  Final location: {result.final_location}")
        if result.error:
            console.print(f"  [red]Error: {result.error}[/red]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    finally:
        if transcript_logger:
            transcript_logger.finalize()
            console.print("\n[dim]Transcript saved[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"[bold]ifplayer[/bold] {__version__}")


@app.command()
def formats() -> None:
    """Show supported game formats."""
    console.print("[bold]Supported Game Formats[/bold]")
    console.print()
    console.print("[cyan]Z-Machine[/cyan] (via dfrotz):")
    console.print(f"  {', '.join(sorted(ZMACHINE_EXTENSIONS))}")
    console.print()
    console.print("[cyan]Glulx[/cyan] (via glulxe+remglk):")
    console.print(f"  {', '.join(sorted(GLULX_EXTENSIONS))}")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
