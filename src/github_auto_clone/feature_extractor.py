"""Feature extraction engine - identifies and extracts discrete features from repositories."""

from __future__ import annotations

import logging
from pathlib import Path

from github_auto_clone.ai_engine import AIEngine
from github_auto_clone.config import Settings, get_settings
from github_auto_clone.models import ExtractionConfig, Feature, RepoInfo
from github_auto_clone.repo_analyzer import RepoAnalyzer
from github_auto_clone.utils import extract_imports_js, extract_imports_python

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Extracts discrete features from a repository."""

    def __init__(
        self,
        ai_engine: AIEngine | None = None,
        analyzer: RepoAnalyzer | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ai = ai_engine or AIEngine(self.settings)
        self.analyzer = analyzer or RepoAnalyzer(self.settings)

    def analyze_repo(self, repo: RepoInfo) -> tuple[list[Feature], Path]:
        """Clone and analyze a repository to extract features.

        Returns a tuple of (features, repo_path).
        """
        # Clone the repo
        repo_path = self.analyzer.clone_repo(repo)

        # Get README
        readme = self.analyzer.get_readme(repo_path)

        # Scan and read files
        files = self.analyzer.scan_files(repo_path)
        logger.info(f"Found {len(files)} files in {repo.full_name}")

        source_files = self.analyzer.read_source_files(repo_path, files)
        logger.info(f"Read {len(source_files)} source files")

        # Use AI to extract features
        features = self.ai.extract_features_from_code(source_files, repo, readme)
        logger.info(f"Extracted {len(features)} features")

        # Enrich features with additional analysis
        features = self._enrich_features(features, source_files, repo)

        return features, repo_path

    def extract_specific_features(
        self,
        repo: RepoInfo,
        feature_names: list[str],
        config: ExtractionConfig | None = None,
    ) -> tuple[list[Feature], dict[str, str]]:
        """Extract specific features by name from a repository.

        Returns a tuple of (features, extracted_files).
        """
        features, repo_path = self.analyze_repo(repo)

        # Filter to requested features
        selected: list[Feature] = []
        for feature in features:
            if feature.name in feature_names or not feature_names:
                selected.append(feature)

        if not selected:
            logger.warning(f"No matching features found. Available: {[f.name for f in features]}")
            return features, {}

        # Collect all files needed for selected features
        needed_files: set[str] = set()
        for feature in selected:
            needed_files.update(feature.files)

            # Also include files from internal dependencies
            for dep_name in feature.internal_dependencies:
                for f in features:
                    if f.name == dep_name:
                        needed_files.update(f.files)

        # Read the needed files
        extracted: dict[str, str] = {}
        for file_path in needed_files:
            full_path = repo_path / file_path
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    extracted[file_path] = content
                except OSError as e:
                    logger.warning(f"Could not read {file_path}: {e}")

        return selected, extracted

    def _enrich_features(
        self,
        features: list[Feature],
        source_files: dict[str, str],
        repo: RepoInfo,
    ) -> list[Feature]:
        """Enrich features with dependency analysis from actual code."""
        for feature in features:
            all_imports: set[str] = set()
            for file_path in feature.files:
                content = source_files.get(file_path, "")
                if not content:
                    continue

                lang = repo.language or ""
                if lang.lower() in ("python",):
                    all_imports.update(extract_imports_python(content))
                elif lang.lower() in ("javascript", "typescript"):
                    all_imports.update(extract_imports_js(content))

            # Update external packages if AI missed any
            existing_pkgs = set(feature.external_packages)
            for imp in all_imports:
                if imp not in existing_pkgs and not imp.startswith("_"):
                    feature.external_packages.append(imp)
            feature.external_packages = sorted(set(feature.external_packages))

            # Store code snippets for entry points
            for ep in feature.entry_points:
                for file_path in feature.files:
                    content = source_files.get(file_path, "")
                    if ep in content:
                        # Extract a relevant snippet around the entry point
                        lines = content.splitlines()
                        for i, line in enumerate(lines):
                            if ep in line:
                                start = max(0, i - 2)
                                end = min(len(lines), i + 20)
                                snippet = "\n".join(lines[start:end])
                                feature.code_snippets[ep] = snippet
                                break
                        break

        return features

    def list_features(self, repo: RepoInfo) -> list[Feature]:
        """List all features in a repository without extracting files."""
        features, _ = self.analyze_repo(repo)
        return features
