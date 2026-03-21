"""Feature packager - bundles extracted features into clean, importable folders."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from github_auto_clone.ai_engine import AIEngine
from github_auto_clone.config import Settings, get_settings
from github_auto_clone.models import Feature, PackageManifest, RepoInfo

logger = logging.getLogger(__name__)


class Packager:
    """Packages extracted features into clean, importable folder structures."""

    def __init__(
        self,
        ai_engine: AIEngine | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.ai = ai_engine or AIEngine(self.settings)

    def package_features(
        self,
        features: list[Feature],
        extracted_files: dict[str, str],
        repo: RepoInfo,
        output_dir: Path | None = None,
        rewrite_imports: bool = True,
    ) -> Path:
        """Package extracted features into a clean folder.

        Returns the path to the created package directory.
        """
        output = output_dir or self.settings.output_dir
        package_name = self._make_package_name(repo, features)
        package_dir = output / package_name
        package_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Packaging {len(features)} features to {package_dir}")

        # Create source directory
        src_dir = package_dir / "src"
        src_dir.mkdir(exist_ok=True)

        # Write extracted files
        written_files: list[str] = []
        for file_path, content in extracted_files.items():
            if rewrite_imports and self.settings.has_openai_key:
                content = self._rewrite_file_imports(content, repo, file_path)

            dest_path = src_dir / file_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(content, encoding="utf-8")
            written_files.append(f"src/{file_path}")
            logger.debug(f"Wrote {dest_path}")

        # Generate __init__.py files for Python packages
        if repo.language and repo.language.lower() == "python":
            self._generate_init_files(src_dir)

        # Generate manifest
        manifest = self._create_manifest(features, repo, written_files)
        manifest_path = package_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(), indent=2),
            encoding="utf-8",
        )

        # Generate README
        readme = self._generate_readme(features, repo, manifest)
        (package_dir / "README.md").write_text(readme, encoding="utf-8")

        # Generate integration guide
        if self.settings.has_openai_key:
            guide = self.ai.generate_integration_guide(features, repo)
            (package_dir / "INTEGRATION.md").write_text(guide, encoding="utf-8")

            # Generate safety notes
            safety = self.ai.generate_safety_notes(features, extracted_files)
            if safety:
                safety_content = "# Safety & Security Notes\n\n"
                for i, note in enumerate(safety, 1):
                    safety_content += f"{i}. {note}\n"
                (package_dir / "SAFETY.md").write_text(safety_content, encoding="utf-8")
                manifest.safety_notes = safety

        # Generate dependency file
        self._generate_dependency_file(features, repo, package_dir)

        logger.info(f"Package created at {package_dir}")
        return package_dir

    def _make_package_name(self, repo: RepoInfo, features: list[Feature]) -> str:
        """Create a clean package directory name."""
        base = re.sub(r"[^\w\-]", "_", f"{repo.owner}_{repo.name}")
        if len(features) == 1:
            base += f"_{features[0].name}"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        return f"{base}_{timestamp}".lower()

    def _rewrite_file_imports(self, content: str, repo: RepoInfo, file_path: str) -> str:
        """Rewrite imports in a file to work in the new package structure."""
        lang = repo.language or ""
        if lang.lower() == "python":
            return self._rewrite_python_imports(content, repo.name)
        elif lang.lower() in ("javascript", "typescript"):
            return self._rewrite_js_imports(content)
        return content

    def _rewrite_python_imports(self, content: str, repo_name: str) -> str:
        """Rewrite Python imports to be relative."""
        lines = content.splitlines()
        new_lines: list[str] = []

        for line in lines:
            # Convert absolute imports from the repo to relative
            if re.match(rf"from\s+{re.escape(repo_name)}", line):
                line = re.sub(
                    rf"from\s+{re.escape(repo_name)}\.?",
                    "from .",
                    line,
                )
            elif re.match(rf"import\s+{re.escape(repo_name)}", line):
                line = re.sub(
                    rf"import\s+{re.escape(repo_name)}\.?",
                    "from . import ",
                    line,
                )
            new_lines.append(line)

        return "\n".join(new_lines)

    def _rewrite_js_imports(self, content: str) -> str:
        """Rewrite JavaScript/TypeScript imports to be relative."""
        # Convert @/ alias imports to relative
        content = re.sub(
            r"""(from\s+['"])@/""",
            r"\1./",
            content,
        )
        return content

    def _generate_init_files(self, src_dir: Path) -> None:
        """Generate __init__.py files for Python package directories."""
        for dir_path in src_dir.rglob("*"):
            if dir_path.is_dir():
                init_file = dir_path / "__init__.py"
                if not init_file.exists():
                    # Check if there are .py files in this directory
                    py_files = list(dir_path.glob("*.py"))
                    if py_files:
                        init_file.write_text(
                            '"""Auto-generated init file."""\n',
                            encoding="utf-8",
                        )

        # Also create init at src root if needed
        init_root = src_dir / "__init__.py"
        if not init_root.exists():
            init_root.write_text('"""Extracted features package."""\n', encoding="utf-8")

    def _create_manifest(
        self,
        features: list[Feature],
        repo: RepoInfo,
        files: list[str],
    ) -> PackageManifest:
        """Create a package manifest."""
        all_deps: dict[str, str] = {}
        for feature in features:
            for pkg in feature.external_packages:
                all_deps[pkg] = "*"

        return PackageManifest(
            name=f"{repo.owner}/{repo.name}",
            description=f"Extracted features from {repo.full_name}",
            source_repo=repo.url,
            features=[f.name for f in features],
            files=files,
            external_dependencies=all_deps,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _generate_readme(
        self,
        features: list[Feature],
        repo: RepoInfo,
        manifest: PackageManifest,
    ) -> str:
        """Generate a README for the packaged features."""
        lines = [
            f"# {repo.name} - Extracted Features",
            "",
            f"> Extracted from [{repo.full_name}]({repo.url})",
            "",
            "## Features",
            "",
        ]

        for feature in features:
            lines.append(f"### {feature.name}")
            lines.append(f"**Category:** {feature.category}")
            lines.append(f"**Complexity:** {feature.estimated_complexity}")
            lines.append(f"\n{feature.description}\n")

            if feature.entry_points:
                lines.append("**Entry Points:**")
                for ep in feature.entry_points:
                    lines.append(f"- `{ep}`")
                lines.append("")

            if feature.external_packages:
                lines.append("**Dependencies:**")
                for dep in feature.external_packages:
                    lines.append(f"- `{dep}`")
                lines.append("")

            if feature.integration_notes:
                lines.append(f"**Integration:** {feature.integration_notes}")
                lines.append("")

        lines.extend([
            "## Dependencies",
            "",
            "Install the following packages:",
            "",
            "```",
        ])

        for pkg, version in manifest.external_dependencies.items():
            lines.append(f"{pkg}")

        lines.extend([
            "```",
            "",
            "## Files",
            "",
        ])

        for f in manifest.files:
            lines.append(f"- `{f}`")

        lines.extend([
            "",
            "---",
            f"Generated on {manifest.created_at}",
        ])

        return "\n".join(lines)

    def _generate_dependency_file(
        self,
        features: list[Feature],
        repo: RepoInfo,
        package_dir: Path,
    ) -> None:
        """Generate appropriate dependency file for the package."""
        all_deps: set[str] = set()
        for feature in features:
            all_deps.update(feature.external_packages)

        lang = (repo.language or "").lower()

        if lang == "python":
            req_path = package_dir / "requirements.txt"
            req_path.write_text(
                "\n".join(sorted(all_deps)) + "\n",
                encoding="utf-8",
            )
        elif lang in ("javascript", "typescript"):
            pkg_json = {
                "name": f"@extracted/{repo.name}",
                "version": "1.0.0",
                "description": f"Extracted features from {repo.full_name}",
                "dependencies": {dep: "*" for dep in sorted(all_deps)},
            }
            (package_dir / "package.json").write_text(
                json.dumps(pkg_json, indent=2) + "\n",
                encoding="utf-8",
            )
        elif lang == "rust":
            cargo = "[package]\n"
            cargo += f'name = "extracted-{repo.name}"\n'
            cargo += 'version = "1.0.0"\n\n'
            cargo += "[dependencies]\n"
            for dep in sorted(all_deps):
                cargo += f'{dep} = "*"\n'
            (package_dir / "Cargo.toml").write_text(cargo, encoding="utf-8")
        elif lang == "go":
            (package_dir / "go_dependencies.txt").write_text(
                "\n".join(sorted(all_deps)) + "\n",
                encoding="utf-8",
            )
