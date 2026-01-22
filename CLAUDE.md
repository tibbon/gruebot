# IF Player

LLM-powered interactive fiction player. Claude acts as the player of text adventure games.

## Project Structure

```
src/ifplayer/
├── backends/     # Game interpreters (dfrotz for Z-Machine, glulxe+remglk for Glulx)
├── llm/          # LLM interfaces (Anthropic API, Claude CLI)
├── memory/       # Context management and summarization
└── logging/      # Transcript logging (JSON + Markdown)
```

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/

# Run tests
pytest tests/ -v
```

## External Dependencies

- `dfrotz` - Z-Machine interpreter (`brew install frotz`)
- `glulxe` with remglk - Glulx interpreter (build from source)

## Architecture

- **GameBackend Protocol**: Abstract interface for game interpreters
- **LLMInterface Protocol**: Abstract interface for LLM backends
- **ContextManager**: Manages game history with summarization
- **GameSession**: Main orchestrator running the game loop
