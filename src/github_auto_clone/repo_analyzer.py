"""Repository analyzer - clones and analyzes repository structure and code."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import git

from github_auto_clone.config import Settings, get_settings
from github_auto_clone.models import FileInfo, RepoInfo
from github_auto_clone.utils import (
    count_lines,
    detect_language,
    is_config_file,
    is_doc_file,
    is_test_file,
    read_file_safe,
    should_skip_dir,
)

logger = logging.getLogger(__name__)


class RepoAnalyzer:
    """Analyzes repository structure and code."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.settings.ensure_dirs()

    def clone_repo(self, repo: RepoInfo, shallow: bool = True) -> Path:
        """Clone a repository to the local clone directory."""
        clone_path = self.settings.clone_dir / repo.owner / repo.name
        if clone_path.exists():
            logger.info(f"Repository already cloned at {clone_path}")
            # Pull latest changes
            try:
                r = git.Repo(clone_path)
                r.remotes.origin.pull()
                logger.info("Pulled latest changes")
            except Exception as e:
                logger.warning(f"Could not pull latest changes: {e}")
            return clone_path

        clone_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cloning {repo.clone_url} to {clone_path}")

        clone_kwargs: dict[str, object] = {}
        if shallow:
            clone_kwargs["depth"] = 1

        git.Repo.clone_from(repo.clone_url, str(clone_path), **clone_kwargs)
        logger.info(f"Successfully cloned {repo.full_name}")
        return clone_path

    def remove_clone(self, repo: RepoInfo) -> None:
        """Remove a cloned repository."""
        clone_path = self.settings.clone_dir / repo.owner / repo.name
        if clone_path.exists():
            shutil.rmtree(clone_path)
            logger.info(f"Removed clone at {clone_path}")

    def scan_files(self, repo_path: Path) -> list[FileInfo]:
        """Scan all files in a repository and collect metadata."""
        files: list[FileInfo] = []
        count = 0

        for file_path in repo_path.rglob("*"):
            if count >= self.settings.max_files_to_analyze:
                logger.warning(
                    f"Reached max file limit ({self.settings.max_files_to_analyze})"
                )
                break

            # Skip directories in the skip list
            parts = file_path.relative_to(repo_path).parts
            if any(should_skip_dir(p) for p in parts):
                continue

            if not file_path.is_file():
                continue

            relative = str(file_path.relative_to(repo_path))
            language = detect_language(file_path)

            try:
                size = file_path.stat().st_size
            except OSError:
                continue

            files.append(
                FileInfo(
                    path=str(file_path),
                    relative_path=relative,
                    language=language,
                    size_bytes=size,
                    line_count=count_lines(file_path),
                    is_test=is_test_file(relative),
                    is_config=is_config_file(relative),
                    is_documentation=is_doc_file(relative),
                )
            )
            count += 1

        return files

    def read_source_files(
        self,
        repo_path: Path,
        files: list[FileInfo],
        include_tests: bool = False,
        include_docs: bool = False,
    ) -> dict[str, str]:
        """Read source files and return a mapping of path to content."""
        contents: dict[str, str] = {}

        for f in files:
            if f.is_test and not include_tests:
                continue
            if f.is_documentation and not include_docs:
                continue
            if f.is_config:
                # Always include config files as they define dependencies
                pass

            if f.size_bytes > self.settings.max_file_size_kb * 1024:
                continue

            content = read_file_safe(Path(f.path), self.settings.max_file_size_kb)
            if content is not None:
                contents[f.relative_path] = content

        return contents

    def get_readme(self, repo_path: Path) -> str | None:
        """Read the README file from a repository."""
        readme_names = [
            "README.md",
            "README.rst",
            "README.txt",
            "README",
            "readme.md",
            "Readme.md",
        ]
        for name in readme_names:
            readme_path = repo_path / name
            if readme_path.exists():
                return read_file_safe(readme_path, max_size_kb=200)
        return None

    def get_dependency_files(self, repo_path: Path) -> dict[str, str]:
        """Read dependency/config files from a repository."""
        dep_files: dict[str, str] = {}
        dep_file_names = [
            "package.json",
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "requirements.txt",
            "Pipfile",
            "Cargo.toml",
            "go.mod",
            "go.sum",
            "pom.xml",
            "build.gradle",
            "Gemfile",
            "composer.json",
        ]
        for name in dep_file_names:
            file_path = repo_path / name
            if file_path.exists():
                content = read_file_safe(file_path)
                if content:
                    dep_files[name] = content
        return dep_files

    def get_project_structure(self, repo_path: Path, max_depth: int = 3) -> str:
        """Generate a tree-like project structure string."""
        lines: list[str] = []
        self._build_tree(repo_path, repo_path, lines, max_depth=max_depth)
        return "\n".join(lines)

    def _build_tree(
        self,
        root: Path,
        current: Path,
        lines: list[str],
        prefix: str = "",
        max_depth: int = 3,
        current_depth: int = 0,
    ) -> None:
        """Recursively build a tree structure."""
        if current_depth > max_depth:
            return

        try:
            entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            return

        # Filter out skip directories
        entries = [
            e for e in entries if not (e.is_dir() and should_skip_dir(e.name))
        ]

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._build_tree(
                    root,
                    entry,
                    lines,
                    prefix + extension,
                    max_depth,
                    current_depth + 1,
                )
