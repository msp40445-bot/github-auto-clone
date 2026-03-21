"""Graph RAG system - builds and queries a knowledge graph of features and their relationships."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from github_auto_clone.models import Feature, FeatureEdge, FeatureGraph

logger = logging.getLogger(__name__)


class FeatureGraphRAG:
    """Graph-based retrieval augmented generation for feature analysis.

    Builds a directed graph of features and their dependencies to enable
    intelligent querying, dependency resolution, and feature recommendation.
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._feature_data: dict[str, Feature] = {}

    def build_graph(self, features: list[Feature]) -> FeatureGraph:
        """Build a feature dependency graph from extracted features."""
        self.graph.clear()
        self._feature_data.clear()

        # Add nodes
        for feature in features:
            self.graph.add_node(
                feature.name,
                description=feature.description,
                category=feature.category,
                complexity=feature.estimated_complexity,
                file_count=len(feature.files),
                packages=feature.external_packages,
            )
            self._feature_data[feature.name] = feature

        # Add edges from internal dependencies
        edges: list[FeatureEdge] = []
        for feature in features:
            for dep in feature.internal_dependencies:
                if dep in self._feature_data:
                    self.graph.add_edge(
                        feature.name,
                        dep,
                        relationship="depends_on",
                        weight=1.0,
                    )
                    edges.append(
                        FeatureEdge(
                            source=feature.name,
                            target=dep,
                            relationship="depends_on",
                        )
                    )

        # Detect related features (shared files or packages)
        feature_names = list(self._feature_data.keys())
        for i, name_a in enumerate(feature_names):
            fa = self._feature_data[name_a]
            for name_b in feature_names[i + 1 :]:
                fb = self._feature_data[name_b]

                shared_files = set(fa.files) & set(fb.files)
                shared_packages = set(fa.external_packages) & set(fb.external_packages)

                if shared_files or len(shared_packages) > 2:
                    weight = len(shared_files) * 2 + len(shared_packages)
                    if not self.graph.has_edge(name_a, name_b):
                        self.graph.add_edge(
                            name_a,
                            name_b,
                            relationship="related_to",
                            weight=float(weight),
                        )
                        edges.append(
                            FeatureEdge(
                                source=name_a,
                                target=name_b,
                                relationship="related_to",
                                weight=float(weight),
                            )
                        )

        # Compute metadata
        metadata = self._compute_graph_metadata()

        return FeatureGraph(features=features, edges=edges, metadata=metadata)

    def get_extraction_order(self, feature_names: list[str]) -> list[str]:
        """Get the optimal order to extract features respecting dependencies.

        Uses topological sort to determine the correct extraction order.
        """
        # Build subgraph with only requested features and their dependencies
        all_needed = set(feature_names)
        for name in feature_names:
            all_needed.update(self._get_all_dependencies(name))

        # Build a dependency-only subgraph (exclude "related_to" edges)
        dep_graph = nx.DiGraph()
        dep_graph.add_nodes_from(all_needed)
        for u, v, data in self.graph.edges(data=True):
            if u in all_needed and v in all_needed:
                if data.get("relationship") == "depends_on":
                    dep_graph.add_edge(u, v)

        try:
            ordered = list(nx.topological_sort(dep_graph))
            # Reverse because topological sort gives dependents first
            ordered.reverse()
            return ordered
        except nx.NetworkXUnfeasible:
            logger.warning("Circular dependency detected, returning unordered list")
            return list(all_needed)

    def get_dependencies(self, feature_name: str, recursive: bool = True) -> list[str]:
        """Get all dependencies for a feature."""
        if recursive:
            return self._get_all_dependencies(feature_name)
        return [
            target
            for _, target, data in self.graph.out_edges(feature_name, data=True)
            if data.get("relationship") == "depends_on"
        ]

    def get_related_features(self, feature_name: str) -> list[tuple[str, float]]:
        """Get features related to the given feature, sorted by relevance."""
        related: list[tuple[str, float]] = []

        for neighbor in self.graph.neighbors(feature_name):
            edge_data = self.graph.get_edge_data(feature_name, neighbor)
            if edge_data and edge_data.get("relationship") == "related_to":
                related.append((neighbor, edge_data.get("weight", 1.0)))

        # Also check reverse edges
        for predecessor in self.graph.predecessors(feature_name):
            edge_data = self.graph.get_edge_data(predecessor, feature_name)
            if edge_data and edge_data.get("relationship") == "related_to":
                if predecessor not in [r[0] for r in related]:
                    related.append((predecessor, edge_data.get("weight", 1.0)))

        related.sort(key=lambda x: x[1], reverse=True)
        return related

    def suggest_features(self, selected: list[str], available: list[str]) -> list[str]:
        """Suggest additional features based on what's already selected."""
        suggestions: set[str] = set()

        for name in selected:
            # Add dependencies
            deps = self.get_dependencies(name)
            suggestions.update(deps)

            # Add strongly related features
            related = self.get_related_features(name)
            for related_name, weight in related:
                if weight > 2.0:
                    suggestions.add(related_name)

        # Remove already selected features
        suggestions -= set(selected)
        # Only include available features
        suggestions &= set(available)

        return sorted(suggestions)

    def get_feature_importance(self) -> dict[str, float]:
        """Calculate importance scores for each feature using PageRank."""
        if not self.graph.nodes:
            return {}

        try:
            scores = nx.pagerank(self.graph)
            return {name: round(score, 4) for name, score in scores.items()}
        except (nx.NetworkXError, ImportError, ModuleNotFoundError):
            # Fallback: use degree centrality if pagerank fails (e.g. missing scipy)
            centrality = nx.degree_centrality(self.graph)
            return {name: round(score, 4) for name, score in centrality.items()}

    def find_independent_features(self) -> list[str]:
        """Find features that have no dependencies and can be extracted standalone."""
        independent: list[str] = []
        for node in self.graph.nodes:
            deps = [
                target
                for _, target, data in self.graph.out_edges(node, data=True)
                if data.get("relationship") == "depends_on"
            ]
            if not deps:
                independent.append(node)
        return independent

    def get_feature_clusters(self) -> list[list[str]]:
        """Find clusters of closely related features."""
        undirected = self.graph.to_undirected()
        components = list(nx.connected_components(undirected))
        return [sorted(comp) for comp in components]

    def export_graph(self, output_path: Path) -> None:
        """Export the graph to a JSON file for visualization."""
        nodes = []
        for node, data in self.graph.nodes(data=True):
            nodes.append({
                "id": node,
                "label": node,
                **{k: v for k, v in data.items() if isinstance(v, (str, int, float, list))},
            })

        edges = []
        for source, target, data in self.graph.edges(data=True):
            edges.append({
                "source": source,
                "target": target,
                "relationship": data.get("relationship", "unknown"),
                "weight": data.get("weight", 1.0),
            })

        graph_data = {
            "nodes": nodes,
            "edges": edges,
            "metadata": self._compute_graph_metadata(),
        }

        output_path.write_text(json.dumps(graph_data, indent=2), encoding="utf-8")
        logger.info(f"Graph exported to {output_path}")

    def _get_all_dependencies(self, feature_name: str) -> list[str]:
        """Recursively get all dependencies for a feature."""
        if feature_name not in self.graph:
            return []

        visited: set[str] = set()
        stack = [feature_name]

        while stack:
            current = stack.pop()
            for _, target, data in self.graph.out_edges(current, data=True):
                if data.get("relationship") == "depends_on" and target not in visited:
                    visited.add(target)
                    stack.append(target)

        return sorted(visited)

    def _compute_graph_metadata(self) -> dict[str, Any]:
        """Compute metadata about the feature graph."""
        if not self.graph.nodes:
            return {"total_features": 0}

        categories: dict[str, int] = {}
        for _, data in self.graph.nodes(data=True):
            cat = data.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_features": self.graph.number_of_nodes(),
            "total_relationships": self.graph.number_of_edges(),
            "categories": categories,
            "independent_features": len(self.find_independent_features()),
            "clusters": len(self.get_feature_clusters()),
            "has_cycles": not nx.is_directed_acyclic_graph(self.graph),
        }
