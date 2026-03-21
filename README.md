# GitHub Auto Clone

**AI-powered GitHub feature extraction and packaging tool.**

Search any GitHub repository, analyze its codebase with AI, extract discrete features, and package them into clean, importable folders you can drop into any project.

Uses **Ollama** for free, local AI inference — no API keys needed, runs on macOS with ~1-3GB RAM.

## The Vision

Imagine you're building an enterprise AI agent but need a browser automation module. Instead of building from scratch, you:

1. **Search** GitHub for the world's best browser automation implementations
2. **Analyze** the top repos — AI identifies every feature, dependency, and integration point
3. **Extract** just the features you need (browser control, page parsing, session management)
4. **Package** everything into a single folder with rewritten imports, dependency lists, integration guides, and safety notes
5. **Import** the folder into your project and integrate the rich functionality

That's it. You go from "I need feature X" to "feature X is in my project" in minutes.

## Installation

### 1. Install Ollama (free local AI)

```bash
# macOS
brew install ollama

# Or download from https://ollama.com

# Start the Ollama server
ollama serve

# Pull the default model (~1.5GB, good for code analysis)
ollama pull qwen2.5:1.5b
```

### 2. Install GitHub Auto Clone

```bash
pip install -e .
```

Or with dev dependencies:

```bash
pip install -e ".[dev]"
```

## Configuration

```bash
# Optional but recommended for higher GitHub API rate limits
export GITHUB_TOKEN="your-github-token"

# Optional: use a different Ollama model
export OLLAMA_MODEL="qwen2.5:1.5b"  # default, ~1.5GB
# Other options: phi3:mini (~2.3GB), llama3.2:1b (~1.3GB)

# Optional: custom Ollama host
export OLLAMA_HOST="http://localhost:11434"  # default
```

## Usage

### Web UI (recommended)

```bash
# Start the web interface
ghclone-web

# Open http://localhost:5000 in your browser
```

The web UI has 5 sections:

- **AI Chat** — Chat with AI about what you need, get search suggestions
- **Search Repos** — Search GitHub with optional AI-powered ranking
- **List Repos** — Browse all repos for any GitHub user
- **Analyze & Extract** — Deep-analyze any repo, see all features, extract them
- **Manual Input** — Input any repo URL (public/private) and extract features to a target directory

### CLI — Quick Start

```bash
ghclone quickstart
```

Describe what you need in plain English, and the tool will find, analyze, extract, and package it for you.

### CLI — Search for Repositories

```bash
# Basic search
ghclone search "browser automation python"

# AI-powered search (understands natural language)
ghclone search "I need a production-ready WebSocket server with authentication" --ai

# Filter by language and stars
ghclone search "graph database" --lang Python --stars 1000
```

### CLI — List User Repositories

```bash
ghclone list-repos torvalds
ghclone list-repos openai --sort stars
```

### CLI — Analyze a Repository

```bash
# Analyze and extract features
ghclone analyze langchain-ai/langchain

# Analyze from URL
ghclone analyze https://github.com/fastapi/fastapi
```

This will:
- Fetch repository metadata
- AI-summarize the README
- Clone and scan the codebase
- Extract all discrete features with AI
- Build a feature dependency graph
- Show feature importance rankings

### CLI — Extract & Package Features

```bash
# Extract ALL features
ghclone extract langchain-ai/langchain -o ./my_features

# Extract specific features
ghclone extract fastapi/fastapi -f "routing,dependency-injection,middleware"

# Keep original imports (no rewriting)
ghclone extract owner/repo --no-rewrite
```

The output package includes:
- `src/` — All extracted source files with rewritten imports
- `README.md` — Feature documentation
- `INTEGRATION.md` — Step-by-step integration guide
- `SAFETY.md` — Security and safety notes
- `manifest.json` — Package metadata
- `requirements.txt` — Python dependencies (or `package.json` for JS/TS)
- `feature_graph.json` — Feature relationship data

### CLI — AI-Powered Search

```bash
# Natural language search
ghclone ai-search "production-ready GraphRAG implementation with vector database support"

# Auto-analyze the top result
ghclone ai-search "enterprise browser agent" --analyze
```

### CLI — Feature Dependency Graph

```bash
# Build and visualize the feature graph
ghclone graph fastapi/fastapi

# Export to JSON
ghclone graph owner/repo -o graph.json
```

## Safety & Rate Limiting

GitHub Auto Clone includes built-in safety measures:

- **Request throttling** — Polite delays between API calls (configurable)
- **Per-minute rate limiting** — Stays within GitHub's rate limits
- **Automatic backoff** — Waits and retries when rate limited
- **No spam behavior** — Single-threaded, sequential requests
- **Token-aware** — Uses authenticated rate limits when token is set

## How It Works

### 1. Search & Discovery
The GitHub API client searches repositories with built-in rate limiting. The AI engine (Ollama) converts natural language queries into optimal search strategies and ranks results.

### 2. Repository Analysis
Repos are cloned locally and scanned. The analyzer identifies all source files, their languages, and categorizes them (source, test, config, docs).

### 3. AI Feature Extraction
The local AI reads through the codebase and identifies discrete, extractable features. For each feature it determines:
- Entry points (functions, classes)
- File dependencies
- External package dependencies
- Inter-feature dependencies
- Integration complexity

### 4. Graph RAG
A directed graph of features is built using NetworkX. This enables:
- **Dependency resolution** — correct extraction order
- **Feature clustering** — related features grouped together
- **Importance ranking** — PageRank-based feature scoring
- **Smart suggestions** — "you selected X, you probably also need Y"

### 5. Packaging
Selected features are packaged into a clean folder:
- Imports are rewritten to work standalone
- `__init__.py` files are generated for Python packages
- Dependency files are created
- AI generates integration guides and safety audits

## Architecture

```
src/github_auto_clone/
├── cli.py              # Typer CLI with rich terminal UI
├── web.py              # Flask web frontend
├── templates/          # HTML templates for web UI
├── config.py           # Pydantic settings from env vars
├── models.py           # Data models (RepoInfo, Feature, etc.)
├── github_client.py    # GitHub API client with rate limiting
├── ai_engine.py        # Ollama-powered analysis engine (local, free)
├── repo_analyzer.py    # Repository cloning and file scanning
├── feature_extractor.py # Feature identification and extraction
├── packager.py         # Feature packaging into importable folders
├── graph_rag.py        # Feature dependency graph (NetworkX)
└── utils.py            # Shared utilities
```

## Tech Stack

- **Python 3.10+** — Modern Python with type hints
- **Ollama** — Free, local AI inference (no API keys needed)
- **Flask** — Web frontend for browser-based usage
- **Typer** — CLI framework
- **Rich** — Beautiful terminal UI
- **httpx** — HTTP client for GitHub API
- **GitPython** — Git operations
- **NetworkX** — Graph algorithms
- **Pydantic** — Data validation

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## License

MIT
