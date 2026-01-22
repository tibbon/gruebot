# Gruebot

> *"It is pitch black. You are likely to be eaten by a grue."*

LLM-powered interactive fiction player. Claude acts as the player of text adventure games, providing the light to navigate through the darkness.

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
gruebot play path/to/game.z5

# Play a Glulx game
gruebot play path/to/game.ulx

# Connect to a MUD server
gruebot mud mud.example.com:4000

# With configuration
gruebot play path/to/game.z8 --config config.yaml --llm claude_cli

# Show supported formats
gruebot formats
```

## Model Configuration

Gruebot defaults to Claude Sonnet. You can switch models in several ways:

### CLI Option (recommended)

```bash
# Use Opus for more capable gameplay
gruebot play game.z5 --model claude-opus-4-20250514

# Use Sonnet (default)
gruebot play game.z5 --model claude-sonnet-4-20250514
```

### Config File

Create a `config.yaml`:

```yaml
llm:
  model: claude-opus-4-20250514
  max_tokens: 1024
  temperature: 0.7
```

Then run with:

```bash
gruebot play game.z5 --config config.yaml
```

### Environment Variable

```bash
export IFPLAYER__LLM__MODEL=claude-opus-4-20250514
gruebot play game.z5
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

## Why "Gruebot"?

The [grue](https://zork.fandom.com/wiki/Grue) is the iconic monster from Zork that lurks in dark places, waiting to devour adventurers who venture without a light source. Gruebot is the light - an LLM companion that illuminates the path through text adventures, preventing you from stumbling in the dark.

## License

MIT
