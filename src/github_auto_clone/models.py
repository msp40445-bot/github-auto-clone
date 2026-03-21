"""Data models for GitHub Auto Clone."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class Language(str, Enum):
    """Programming languages."""

    PYTHON = "Python"
    JAVASCRIPT = "JavaScript"
    TYPESCRIPT = "TypeScript"
    RUST = "Rust"
    GO = "Go"
    JAVA = "Java"
    CPP = "C++"
    C = "C"
    CSHARP = "C#"
    RUBY = "Ruby"
    PHP = "PHP"
    SWIFT = "Swift"
    KOTLIN = "Kotlin"
    SCALA = "Scala"
    OTHER = "Other"


class RepoInfo(BaseModel):
    """Information about a GitHub repository."""

    full_name: str
    name: str
    owner: str
    description: str | None = None
    url: str
    clone_url: str
    stars: int = 0
    forks: int = 0
    language: str | None = None
    topics: list[str] = Field(default_factory=list)
    default_branch: str = "main"
    last_updated: str | None = None
    license: str | None = None
    is_fork: bool = False
    open_issues: int = 0
    size_kb: int = 0

    @property
    def display_name(self) -> str:
        return f"{self.owner}/{self.name}"


class RepoSummary(BaseModel):
    """AI-generated summary of a repository."""

    repo: RepoInfo
    short_description: str = ""
    key_features: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    use_cases: list[str] = Field(default_factory=list)
    complexity: str = "medium"  # low, medium, high
    quality_score: float = 0.0  # 0-10


class FileInfo(BaseModel):
    """Information about a file in a repository."""

    path: str
    relative_path: str
    language: str | None = None
    size_bytes: int = 0
    line_count: int = 0
    is_test: bool = False
    is_config: bool = False
    is_documentation: bool = False


class Feature(BaseModel):
    """A discrete feature extracted from a repository."""

    name: str
    description: str
    category: str = "general"
    files: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    internal_dependencies: list[str] = Field(default_factory=list)
    external_packages: list[str] = Field(default_factory=list)
    estimated_complexity: str = "medium"
    code_snippets: dict[str, str] = Field(default_factory=dict)
    integration_notes: str = ""


class FeatureGraph(BaseModel):
    """Graph representation of features and their relationships."""

    features: list[Feature] = Field(default_factory=list)
    edges: list[FeatureEdge] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeatureEdge(BaseModel):
    """An edge in the feature dependency graph."""

    source: str  # feature name
    target: str  # feature name
    relationship: str = "depends_on"  # depends_on, related_to, extends
    weight: float = 1.0


class PackageManifest(BaseModel):
    """Manifest for a packaged feature bundle."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    source_repo: str = ""
    features: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    external_dependencies: dict[str, str] = Field(default_factory=dict)
    integration_guide: str = ""
    created_at: str = ""
    safety_notes: list[str] = Field(default_factory=list)


class SearchQuery(BaseModel):
    """A search query for GitHub repos."""

    query: str
    language: str | None = None
    min_stars: int = 0
    sort: str = "stars"  # stars, forks, updated, best-match
    order: str = "desc"
    per_page: int = 10
    page: int = 1
    topics: list[str] = Field(default_factory=list)


class AISearchQuery(BaseModel):
    """An AI-powered natural language search query."""

    natural_query: str
    context: str = ""
    max_results: int = 10


class ExtractionConfig(BaseModel):
    """Configuration for feature extraction."""

    repo_path: Path
    output_dir: Path = Path("./extracted_features")
    features_to_extract: list[str] = Field(default_factory=list)
    include_tests: bool = False
    include_docs: bool = True
    rewrite_imports: bool = True
    generate_integration_guide: bool = True
    max_file_size_kb: int = 500
