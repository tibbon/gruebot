# Gruebot

> *"It is pitch black. You are likely to be eaten by a grue."*

LLM-powered interactive fiction player. Claude acts as the player of text adventure games, providing the light to navigate through the darkness.

## Features

- Z-Machine support via dfrotz (Infocom games, Inform 6/7 Z-code)
- Glulx support via glulxe+remglk (modern Inform 7 games)
- MUD support via telnet
- Switchable LLM backends (Anthropic API or Claude CLI)
- Full context management with periodic summarization
- Dual transcript logging (JSON for replay, Markdown for reading)
- **CI/CD testing** - Test IF games with walkthroughs and assertions (no API key required)

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

## Testing IF Games (CI/CD)

Gruebot includes a `test` command for automated testing of interactive fiction games. This is useful for IF authors who want to test their games in CI/CD pipelines - **no API key required**.

### Smoke Test

Verify a game loads and responds to input:

```bash
gruebot test game.z5 --smoke
```

### Walkthrough Test

Run a sequence of commands from a file:

```bash
gruebot test game.z5 --walkthrough walkthrough.txt
```

### Walkthrough File Format

```text
# Comments start with #
look
north
take lamp

# Assertions check game state
@expect-location "Kitchen"
@expect-contains "brass lantern"
@expect-not-contains "grue"
@expect-inventory "lamp"
@expect-score-gte 10
@expect-turns-lte 50

south
@expect-location "Living Room"
```

### CLI Assertions

Add assertions via command line:

```bash
gruebot test game.z5 -w walkthrough.txt \
  --expect-location "Treasure Room" \
  --expect-text "gold"
```

### AI Play Mode

Let Claude play your game and check assertions (requires `ANTHROPIC_API_KEY`):

```bash
# Let Claude play for 100 turns, check final location
gruebot test game.z5 --ai --max-turns 100 --expect-location "Treasure Room"

# Save transcript for later analysis (by another LLM, reviewer, etc.)
gruebot test game.z5 --ai --max-turns 50 --transcript playthrough.md

# Use a specific model
gruebot test game.z5 --ai -M claude-opus-4-20250514 --max-turns 100
```

This is useful for:
- Regression testing: ensure game is completable
- Difficulty testing: see how far Claude gets in N turns
- Generating transcripts for human/LLM review

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | Game failed to start |
| 2 | Assertion failed |
| 3 | Game error during playthrough |
| 4 | Invalid input (bad walkthrough file) |
| 5 | Walkthrough execution error |

### GitHub Actions Example

Test your IF game on every push:

```yaml
name: Test IF Game

on: [push, pull_request]

jobs:
  # Walkthrough test (no API key needed)
  walkthrough-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Test with walkthrough
        run: |
          docker run --rm \
            -v ${{ github.workspace }}:/games \
            ghcr.io/tibbon/gruebot:latest \
            test /games/mygame.z8 --walkthrough /games/test-walkthrough.txt

  # AI playthrough test (requires ANTHROPIC_API_KEY secret)
  ai-test:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'  # Only on push, not PRs (to save API costs)
    steps:
      - uses: actions/checkout@v4

      - name: Let Claude play
        run: |
          docker run --rm \
            -e ANTHROPIC_API_KEY=${{ secrets.ANTHROPIC_API_KEY }} \
            -v ${{ github.workspace }}:/games \
            ghcr.io/tibbon/gruebot:latest \
            test /games/mygame.z8 --ai --max-turns 50 \
            --transcript /games/playthrough.md \
            --expect-location "Victory"

      - name: Upload transcript
        uses: actions/upload-artifact@v4
        with:
          name: playthrough-transcript
          path: playthrough.md
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
