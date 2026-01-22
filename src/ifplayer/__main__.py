"""Entry point for ifplayer CLI."""

import typer

app = typer.Typer(
    name="ifplayer",
    help="LLM-powered interactive fiction player",
)


@app.command()
def play(
    game_path: str = typer.Argument(..., help="Path to the game file"),
    config: str | None = typer.Option(None, "--config", "-c", help="Path to config file"),
    llm_backend: str = typer.Option(
        "anthropic_api", "--llm", "-l", help="LLM backend (anthropic_api or claude_cli)"
    ),
) -> None:
    """Play an interactive fiction game with an LLM as the player."""
    # TODO: Implement game playing logic
    _ = config  # Will be used when implemented
    typer.echo(f"Would play {game_path} with {llm_backend}")
    typer.echo("Not yet implemented")


@app.command()
def version() -> None:
    """Show version information."""
    from ifplayer import __version__

    typer.echo(f"ifplayer {__version__}")


def main() -> None:
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
