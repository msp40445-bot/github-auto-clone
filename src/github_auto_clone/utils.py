"""Shared utilities for GitHub Auto Clone."""

from __future__ import annotations

import re
from pathlib import Path

# File extensions to language mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".cpp": "C++",
    ".cc": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".r": "R",
    ".jl": "Julia",
    ".lua": "Lua",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".less": "LESS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hs": "Haskell",
    ".ml": "OCaml",
    ".clj": "Clojure",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".rst": "reStructuredText",
}

CONFIG_FILES = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "Makefile",
    "CMakeLists.txt",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "tsconfig.json",
    "webpack.config.js",
    "vite.config.ts",
    "vite.config.js",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "Gemfile",
    "composer.json",
}

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "target",
    "vendor",
    ".tox",
    "eggs",
    ".eggs",
    "htmlcov",
    "coverage",
}

TEST_PATTERNS = [
    r"test[_s]?/",
    r"spec[_s]?/",
    r"__tests__/",
    r"test_.*\.py$",
    r".*_test\.py$",
    r".*\.test\.(js|ts|tsx|jsx)$",
    r".*\.spec\.(js|ts|tsx|jsx)$",
]

DOC_PATTERNS = [
    r"docs?/",
    r"documentation/",
    r"README",
    r"CHANGELOG",
    r"CONTRIBUTING",
    r"LICENSE",
    r".*\.md$",
    r".*\.rst$",
]


def detect_language(file_path: str | Path) -> str | None:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return EXTENSION_MAP.get(ext)


def is_test_file(file_path: str) -> bool:
    """Check if a file is a test file."""
    return any(re.search(pattern, file_path) for pattern in TEST_PATTERNS)


def is_doc_file(file_path: str) -> bool:
    """Check if a file is a documentation file."""
    return any(re.search(pattern, file_path) for pattern in DOC_PATTERNS)


def is_config_file(file_path: str) -> bool:
    """Check if a file is a configuration file."""
    return Path(file_path).name in CONFIG_FILES


def should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    return dir_name in SKIP_DIRS


def count_lines(file_path: Path) -> int:
    """Count the number of lines in a file."""
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except (OSError, UnicodeDecodeError):
        return 0


def read_file_safe(file_path: Path, max_size_kb: int = 500) -> str | None:
    """Read a file safely, returning None if it's too large or binary."""
    try:
        if file_path.stat().st_size > max_size_kb * 1024:
            return None
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        # Check for binary content
        if "\x00" in content[:1024]:
            return None
        return content
    except (OSError, UnicodeDecodeError):
        return None


def sanitize_name(name: str) -> str:
    """Sanitize a name for use as a directory/file name."""
    sanitized = re.sub(r"[^\w\-.]", "_", name)
    sanitized = re.sub(r"_+", "_", sanitized)
    return sanitized.strip("_").lower()


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to a maximum length."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_size(size_bytes: int) -> str:
    """Format a file size in bytes to a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def extract_imports_python(content: str) -> list[str]:
    """Extract import statements from Python code."""
    imports: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("import "):
            parts = line.replace("import ", "").split(",")
            for part in parts:
                mod = part.strip().split(" as ")[0].split(".")[0]
                if mod:
                    imports.append(mod)
        elif line.startswith("from "):
            match = re.match(r"from\s+([\w.]+)\s+import", line)
            if match:
                imports.append(match.group(1).split(".")[0])
    return list(set(imports))


def extract_imports_js(content: str) -> list[str]:
    """Extract import/require statements from JavaScript/TypeScript code."""
    imports: list[str] = []
    # ES6 imports
    for match in re.finditer(r'import\s+.*?from\s+["\']([^"\']+)["\']', content):
        pkg = match.group(1)
        if not pkg.startswith("."):
            imports.append(pkg.split("/")[0] if pkg.startswith("@") else pkg.split("/")[0])
    # CommonJS require
    for match in re.finditer(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)', content):
        pkg = match.group(1)
        if not pkg.startswith("."):
            imports.append(pkg.split("/")[0] if pkg.startswith("@") else pkg.split("/")[0])
    return list(set(imports))
