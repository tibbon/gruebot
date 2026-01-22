# Gruebot - LLM-powered interactive fiction player
#
# Build: docker build -t gruebot .
# Run:   docker run -it -v /path/to/games:/games gruebot play /games/zork1.z5

FROM python:3.12-slim

# Install build dependencies and frotz
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    frotz \
    && rm -rf /var/lib/apt/lists/*

# Build glulxe with remglk
WORKDIR /tmp/build
RUN git clone --depth 1 https://github.com/erkyrath/remglk.git \
    && git clone --depth 1 https://github.com/erkyrath/glulxe.git \
    && cd remglk && make \
    && cd ../glulxe \
    && make GLKINCLUDEDIR=../remglk GLKLIBDIR=../remglk GLKMAKEFILE=Make.remglk \
    && cp glulxe /usr/local/bin/ \
    && cd / && rm -rf /tmp/build

# Create app directory
WORKDIR /app

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install gruebot
RUN pip install --no-cache-dir -e .

# Create directories for games, saves, and transcripts
RUN mkdir -p /games /saves /transcripts

# Set working directory for runtime
WORKDIR /transcripts

# Default command shows help
ENTRYPOINT ["gruebot"]
CMD ["--help"]
