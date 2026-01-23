# Gruebot

[![CI](https://github.com/tibbon/gruebot/actions/workflows/ci.yml/badge.svg)](https://github.com/tibbon/gruebot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> *"It is pitch black. You are likely to be eaten by a grue."*

A testing framework and automation tool for interactive fiction games. Run smoke tests, execute walkthroughs with assertions, or let an LLM play your game autonomously.

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Testing Commands](#testing-commands)
- [GitHub Action](#github-action)
- [LLM Play Mode](#llm-play-mode)
- [Development](#development)
- [Why "Gruebot"?](#why-gruebot)

## Features

**Testing & CI/CD:**
- Smoke tests to verify games load and respond
- Walkthrough tests with scripted commands
- Assertion system for validating game state
- Reusable GitHub Action for IF projects
- No API key required for basic testing

**Game Format Support:**
- Z-Machine via dfrotz (Infocom, Inform 6/7: .z3, .z5, .z8)
- Glulx via glulxe+remglk (modern Inform 7: .ulx, .gblorb)
- MUD servers via telnet

**LLM Integration (Optional):**
- Let Claude play your game autonomously
- Generate transcripts for review
- Configurable models (Sonnet, Opus)
- Useful for difficulty testing and regression checks

## Quick Start

**Test your game (no API key needed):**

```bash
# Install
pip install -e ".[dev]"

# Smoke test - verify game loads
gruebot test mygame.z8 --smoke

# Walkthrough test - run scripted commands
gruebot test mygame.z8 --walkthrough tests/walkthrough.txt
```

**Let Claude play (requires API key):**

```bash
export ANTHROPIC_API_KEY=your-key-here
gruebot test mygame.z8 --ai --max-turns 100 --transcript playthrough.md
```

## Installation

### Requirements

- Python 3.11 or higher
- Game interpreter: dfrotz (Z-Machine) or glulxe (Glulx)
- `ANTHROPIC_API_KEY` (only for LLM features)

### Install Gruebot

```bash
pip install -e ".[dev]"
```

### Install Game Interpreters

```bash
# Z-Machine (macOS)
brew install frotz

# Z-Machine (Linux)
apt install frotz
```

For Glulx games, glulxe must be built with remglk:

```bash
git clone https://github.com/erkyrath/remglk.git
git clone https://github.com/erkyrath/glulxe.git

cd remglk && make
cd ../glulxe
make GLKINCLUDEDIR=../remglk GLKLIBDIR=../remglk GLKMAKEFILE=Make.remglk
sudo cp glulxe /usr/local/bin/
```

## Testing Commands

### Smoke Test

Verify a game loads and responds to basic input:

```bash
gruebot test game.z5 --smoke
```

### Walkthrough Test

Run a sequence of commands and check assertions:

```bash
gruebot test game.z5 --walkthrough walkthrough.txt
```

**Walkthrough file format:**

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

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | Game failed to start |
| 2 | Assertion failed |
| 3 | Game error during playthrough |
| 4 | Invalid input (bad walkthrough file) |
| 5 | Walkthrough execution error |

## GitHub Action

Add automated testing to your IF project:

```yaml
name: Test IF Game

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Smoke test
        uses: tibbon/gruebot@v1
        with:
          game: ./mygame.z8
          mode: smoke

      - name: Walkthrough test
        uses: tibbon/gruebot@v1
        with:
          game: ./mygame.z8
          mode: walkthrough
          walkthrough: ./tests/walkthrough.txt
          expect-location: "Victory Room"
```

### Action Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `game` | Yes | - | Path to game file (.z5, .z8, .ulx, .gblorb) |
| `mode` | No | `smoke` | Test mode: `smoke`, `walkthrough`, or `ai` |
| `walkthrough` | For walkthrough | - | Path to walkthrough file |
| `max-turns` | No | `50` | Maximum turns for AI mode |
| `expect-location` | No | - | Assert final location contains text |
| `expect-text` | No | - | Assert final output contains text |
| `transcript` | No | - | Save transcript to this path |
| `model` | No | - | Model for AI mode |
| `anthropic-api-key` | For AI mode | - | Anthropic API key |
| `verbose` | No | `false` | Show detailed output |

### AI Playthrough in CI

Let Claude play your game to test difficulty or generate transcripts:

```yaml
  ai-test:
    runs-on: ubuntu-latest
    if: github.event_name == 'push'  # Save API costs
    steps:
      - uses: actions/checkout@v4

      - name: Claude playthrough
        uses: tibbon/gruebot@v1
        with:
          game: ./mygame.z8
          mode: ai
          max-turns: '100'
          expect-location: "Treasure Room"
          transcript: ./playthrough.md
          anthropic-api-key: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Upload transcript
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: claude-playthrough
          path: ./playthrough.md
```

### Docker Alternative

```bash
docker run --rm \
  -v $(pwd):/workspace -w /workspace \
  ghcr.io/tibbon/gruebot:latest \
  test ./mygame.z8 --walkthrough ./tests/walkthrough.txt
```

## LLM Play Mode

Beyond testing, Gruebot can run interactive sessions where Claude plays your game in real-time.

```bash
# Watch Claude play
gruebot play game.z5

# Use a specific model
gruebot play game.z5 --model claude-opus-4-20250514

# Connect to a MUD
gruebot mud mud.example.com:4000
```

### Configuration

**Config file (`config.yaml`):**

```yaml
llm:
  model: claude-opus-4-20250514
  max_tokens: 1024
  temperature: 0.7
```

```bash
gruebot play game.z5 --config config.yaml
```

**Environment variable:**

```bash
export GRUEBOT_LLM__MODEL=claude-opus-4-20250514
```

## Development

```bash
pip install -e ".[dev]"

# Linting
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/

# Tests
pytest tests/ -v
```

## Why "Gruebot"?

The [grue](https://zork.fandom.com/wiki/Grue) is the iconic monster from Zork that lurks in dark places, waiting to devour adventurers who wander without a light source. Gruebot helps you navigate through the darkness of untested code paths - whether through automated walkthroughs or by letting an LLM explore your game and report what it finds.

## License

MIT
