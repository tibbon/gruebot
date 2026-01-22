# IF Player

LLM-powered interactive fiction player. Claude acts as the player of text adventure games.

## Features

- Z-Machine support via dfrotz (Infocom games, Inform 6/7 Z-code)
- Glulx support via glulxe+remglk (modern Inform 7 games)
- Switchable LLM backends (Anthropic API or Claude CLI)
- Full context management with periodic summarization
- Dual transcript logging (JSON for replay, Markdown for reading)

## Installation

```bash
pip install -e ".[dev]"
```

## External Dependencies

### Z-Machine (dfrotz)

- macOS: `brew install frotz`
- Linux: `apt install frotz`

### Glulx (glulxe with remglk)

glulxe must be built with remglk for JSON I/O support:

```bash
# Clone repositories
git clone https://github.com/erkyrath/remglk.git
git clone https://github.com/erkyrath/glulxe.git

# Build remglk
cd remglk
make

# Build glulxe with remglk
cd ../glulxe
make GLKINCLUDEDIR=../remglk GLKLIBDIR=../remglk GLKMAKEFILE=Make.remglk

# Install (copy to PATH)
sudo cp glulxe /usr/local/bin/
```

Alternatively on macOS with Homebrew:
```bash
# If a formula exists
brew install glulxe --with-remglk
```

## Usage

```bash
# Play a Z-Machine game
ifplayer play path/to/game.z5

# With configuration
ifplayer play path/to/game.z8 --config config.yaml --llm anthropic_api
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/

# Run tests
pytest tests/ -v
```

## License

MIT
