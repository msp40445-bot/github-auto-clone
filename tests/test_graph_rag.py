"""Tests for the Graph RAG system."""

from github_auto_clone.graph_rag import FeatureGraphRAG
from github_auto_clone.models import Feature


def _make_features() -> list[Feature]:
    """Create test features."""
    return [
        Feature(
            name="auth",
            description="Authentication system",
            category="auth",
            files=["auth/login.py", "auth/models.py", "shared/utils.py"],
            internal_dependencies=[],
            external_packages=["bcrypt", "jwt"],
        ),
        Feature(
            name="api",
            description="REST API endpoints",
            category="api",
            files=["api/routes.py", "api/middleware.py", "shared/utils.py"],
            internal_dependencies=["auth"],
            external_packages=["fastapi", "pydantic"],
        ),
        Feature(
            name="database",
            description="Database layer",
            category="database",
            files=["db/models.py", "db/session.py"],
            internal_dependencies=[],
            external_packages=["sqlalchemy"],
        ),
        Feature(
            name="cache",
            description="Caching layer",
            category="performance",
            files=["cache/redis.py"],
            internal_dependencies=["database"],
            external_packages=["redis"],
        ),
    ]


def test_build_graph() -> None:
    rag = FeatureGraphRAG()
    features = _make_features()
    graph = rag.build_graph(features)

    assert graph.metadata["total_features"] == 4
    assert graph.metadata["total_relationships"] > 0


def test_get_dependencies() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    deps = rag.get_dependencies("api")
    assert "auth" in deps

    deps_cache = rag.get_dependencies("cache")
    assert "database" in deps_cache


def test_get_extraction_order() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    order = rag.get_extraction_order(["api", "cache"])
    # Dependencies should come before dependents
    auth_idx = order.index("auth") if "auth" in order else -1
    api_idx = order.index("api") if "api" in order else -1
    if auth_idx >= 0 and api_idx >= 0:
        assert auth_idx < api_idx


def test_find_independent_features() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    independent = rag.find_independent_features()
    assert "auth" in independent
    assert "database" in independent
    assert "api" not in independent


def test_feature_importance() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    importance = rag.get_feature_importance()
    assert len(importance) == 4
    assert all(0 <= v <= 1 for v in importance.values())


def test_feature_clusters() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    clusters = rag.get_feature_clusters()
    assert len(clusters) >= 1
    # All features should be in some cluster
    all_in_clusters = set()
    for cluster in clusters:
        all_in_clusters.update(cluster)
    assert len(all_in_clusters) == 4


def test_suggest_features() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    suggestions = rag.suggest_features(
        selected=["api"],
        available=["auth", "database", "cache"],
    )
    # auth should be suggested since api depends on it
    assert "auth" in suggestions


def test_get_related_features() -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    # auth and api share "shared/utils.py"
    related = rag.get_related_features("auth")
    related_names = [name for name, _ in related]
    assert "api" in related_names


def test_export_graph(tmp_path) -> None:
    rag = FeatureGraphRAG()
    rag.build_graph(_make_features())

    output = tmp_path / "graph.json"
    rag.export_graph(output)

    assert output.exists()
    import json
    data = json.loads(output.read_text())
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) == 4
