"""Tests for data models."""

from github_auto_clone.models import (
    ExtractionConfig,
    Feature,
    FeatureEdge,
    FeatureGraph,
    PackageManifest,
    RepoInfo,
    SearchQuery,
)


def test_repo_info_creation() -> None:
    repo = RepoInfo(
        full_name="owner/repo",
        name="repo",
        owner="owner",
        url="https://github.com/owner/repo",
        clone_url="https://github.com/owner/repo.git",
        stars=100,
    )
    assert repo.display_name == "owner/repo"
    assert repo.stars == 100


def test_feature_creation() -> None:
    feature = Feature(
        name="auth",
        description="Authentication module",
        category="auth",
        files=["auth.py", "models.py"],
        entry_points=["login", "register"],
        external_packages=["bcrypt", "jwt"],
    )
    assert feature.name == "auth"
    assert len(feature.files) == 2
    assert "bcrypt" in feature.external_packages


def test_search_query_defaults() -> None:
    query = SearchQuery(query="fastapi")
    assert query.sort == "stars"
    assert query.order == "desc"
    assert query.per_page == 10


def test_feature_graph() -> None:
    graph = FeatureGraph(
        features=[
            Feature(name="a", description="Feature A"),
            Feature(name="b", description="Feature B"),
        ],
        edges=[
            FeatureEdge(source="a", target="b", relationship="depends_on"),
        ],
    )
    assert len(graph.features) == 2
    assert len(graph.edges) == 1


def test_package_manifest() -> None:
    manifest = PackageManifest(
        name="test-package",
        features=["auth", "api"],
        external_dependencies={"bcrypt": ">=4.0"},
    )
    assert manifest.name == "test-package"
    assert "auth" in manifest.features


def test_extraction_config_defaults() -> None:
    config = ExtractionConfig(repo_path="/tmp/test")
    assert config.include_tests is False
    assert config.include_docs is True
    assert config.rewrite_imports is True
