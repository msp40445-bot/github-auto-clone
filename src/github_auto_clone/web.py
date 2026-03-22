"""Flask web frontend for GitHub Auto Clone.

Run locally on macOS with: ghclone-web
Provides a browser UI for searching, analyzing, and extracting features.
"""

from __future__ import annotations

import logging
import os
import traceback
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from github_auto_clone.ai_engine import AIEngine
from github_auto_clone.config import Settings, get_settings
from github_auto_clone.feature_extractor import FeatureExtractor
from github_auto_clone.github_client import GitHubClient
from github_auto_clone.graph_rag import FeatureGraphRAG
from github_auto_clone.models import AISearchQuery, SearchQuery
from github_auto_clone.packager import Packager

logger = logging.getLogger(__name__)

# Flask app
template_dir = Path(__file__).parent / "templates"
app = Flask(__name__, template_folder=str(template_dir))
app.secret_key = os.urandom(24)


def _get_settings() -> Settings:
    return get_settings()


def _get_ai_engine(settings: Settings) -> AIEngine:
    engine = AIEngine(settings)
    return engine


# ── Routes ──────────────────────────────────────────────────


@app.route("/")
def index() -> str:
    """Main page."""
    settings = _get_settings()
    ai_available = False
    try:
        engine = _get_ai_engine(settings)
        ai_available = engine.is_available()
    except Exception:
        pass
    return render_template(
        "index.html",
        ai_available=ai_available,
        has_github_token=settings.has_github_token,
        ollama_model=settings.ollama_model,
    )


@app.route("/api/status")
def api_status() -> tuple[dict, int]:
    """Check system status."""
    settings = _get_settings()
    ai_available = False
    ai_model = settings.ollama_model
    try:
        engine = _get_ai_engine(settings)
        ai_available = engine.is_available()
    except Exception:
        pass
    return jsonify({
        "ai_available": ai_available,
        "ai_model": ai_model,
        "github_token": settings.has_github_token,
    }), 200


@app.route("/api/chat", methods=["POST"])
def api_chat() -> tuple[dict, int]:
    """Chat with the AI about what you need."""
    data = request.get_json() or {}
    message = data.get("message", "")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    settings = _get_settings()
    try:
        engine = _get_ai_engine(settings)
        if not engine.is_available():
            return jsonify({"error": "Ollama is not running. Start it with: ollama serve"}), 503

        response = engine._chat(
            "You are a helpful assistant for GitHub Auto Clone. "
            "Help users find GitHub repos, understand features, "
            "and extract code. Be concise and helpful. "
            "If the user describes a feature they need, suggest "
            "search terms they could use to find it on GitHub.",
            message,
        )
        return jsonify({"response": response}), 200
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/search", methods=["POST"])
def api_search() -> tuple[dict, int]:
    """Search GitHub repos."""
    data = request.get_json() or {}
    query = data.get("query", "")
    language = data.get("language")
    min_stars = data.get("min_stars", 0)
    use_ai = data.get("use_ai", False)
    limit = min(data.get("limit", 10), 30)

    if not query:
        return jsonify({"error": "No query provided"}), 400

    settings = _get_settings()

    try:
        with GitHubClient(settings) as client:
            if use_ai:
                engine = _get_ai_engine(settings)
                if not engine.is_available():
                    return jsonify({
                        "error": "Ollama not running. Using basic search.",
                    }), 503

                ai_query = AISearchQuery(
                    natural_query=query,
                    max_results=limit,
                )
                search_queries = engine.generate_search_queries(ai_query)

                all_repos = []
                for sq in search_queries:
                    repos = client.search_repos(sq)
                    all_repos.extend(repos)

                # Deduplicate
                seen: set[str] = set()
                unique = []
                for repo in all_repos:
                    if repo.full_name not in seen:
                        seen.add(repo.full_name)
                        unique.append(repo)

                # AI rank
                if unique:
                    ranked = engine.rank_repos(unique[:20], query)
                    results = [
                        {**r.model_dump(), "ai_score": s}
                        for r, s in ranked[:limit]
                    ]
                else:
                    results = []
            else:
                sq = SearchQuery(
                    query=query,
                    language=language,
                    min_stars=min_stars,
                    per_page=limit,
                )
                repos = client.search_repos(sq)
                results = [r.model_dump() for r in repos]

        return jsonify({"repos": results}), 200
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/list-repos", methods=["POST"])
def api_list_repos() -> tuple[dict, int]:
    """List repos for a GitHub user."""
    data = request.get_json() or {}
    username = data.get("username", "")
    if not username:
        return jsonify({"error": "No username provided"}), 400

    settings = _get_settings()
    try:
        with GitHubClient(settings) as client:
            repos = client.list_user_repos(
                username,
                sort=data.get("sort", "updated"),
                per_page=min(data.get("limit", 30), 100),
            )

        # Get README summaries if AI available
        results = []
        for repo in repos:
            repo_data = repo.model_dump()
            results.append(repo_data)

        return jsonify({"repos": results}), 200
    except Exception as e:
        logger.error(f"List repos error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze() -> tuple[dict, int]:
    """Analyze a repo and extract features."""
    data = request.get_json() or {}
    repo_url = data.get("repo", "")
    if not repo_url:
        return jsonify({"error": "No repo provided"}), 400

    settings = _get_settings()

    try:
        # Parse repo
        repo_url = repo_url.strip().rstrip("/")
        if "github.com" in repo_url:
            parts = repo_url.split("github.com/")[-1].split("/")
            owner, name = parts[0], parts[1].replace(".git", "")
        elif "/" in repo_url:
            owner, name = repo_url.split("/")[:2]
        else:
            return jsonify({"error": "Invalid repo format. Use owner/name or URL"}), 400

        with GitHubClient(settings) as client:
            repo = client.get_repo(owner, name)
            readme = client.get_repo_readme(owner, name)
            languages = client.get_repo_languages(owner, name)

        result: dict = {
            "repo": repo.model_dump(),
            "readme_preview": (readme or "")[:2000],
            "languages": languages,
            "features": [],
            "graph": None,
        }

        # AI analysis
        engine = _get_ai_engine(settings)
        if engine.is_available():
            # Summarize
            if readme:
                summary = engine.summarize_readme(readme, repo)
                result["summary"] = summary.model_dump()

            # Extract features
            extractor = FeatureExtractor(settings=settings)
            features, repo_path = extractor.analyze_repo(repo)
            result["features"] = [f.model_dump() for f in features]

            # Build graph
            graph_rag = FeatureGraphRAG()
            fg = graph_rag.build_graph(features)
            importance = graph_rag.get_feature_importance()
            clusters = graph_rag.get_feature_clusters()
            result["graph"] = {
                "metadata": fg.metadata,
                "importance": importance,
                "clusters": clusters,
            }

        return jsonify(result), 200
    except Exception as e:
        logger.error(f"Analyze error: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract", methods=["POST"])
def api_extract() -> tuple[dict, int]:
    """Extract and package features from a repo."""
    data = request.get_json() or {}
    repo_url = data.get("repo", "")
    feature_names = data.get("features", [])
    target_dir = data.get("target_dir", "")

    if not repo_url:
        return jsonify({"error": "No repo provided"}), 400

    settings = _get_settings()

    try:
        # Parse repo
        repo_url = repo_url.strip().rstrip("/")
        if "github.com" in repo_url:
            parts = repo_url.split("github.com/")[-1].split("/")
            owner, name = parts[0], parts[1].replace(".git", "")
        elif "/" in repo_url:
            owner, name = repo_url.split("/")[:2]
        else:
            return jsonify({"error": "Invalid repo format"}), 400

        with GitHubClient(settings) as client:
            repo = client.get_repo(owner, name)

        # Extract features
        extractor = FeatureExtractor(settings=settings)
        features, extracted_files = extractor.extract_specific_features(
            repo, feature_names
        )

        if not extracted_files:
            return jsonify({"error": "No files extracted"}), 400

        # Package
        packager = Packager(settings=settings)
        output_dir = Path(target_dir) if target_dir else settings.output_dir
        package_dir = packager.package_features(
            features, extracted_files, repo, output_dir=output_dir
        )

        # Build graph
        graph_rag = FeatureGraphRAG()
        graph_rag.build_graph(features)
        graph_rag.export_graph(package_dir / "feature_graph.json")

        return jsonify({
            "package_dir": str(package_dir),
            "features": [f.model_dump() for f in features],
            "files_count": len(extracted_files),
            "message": f"Packaged {len(features)} features to {package_dir}",
        }), 200
    except Exception as e:
        logger.error(f"Extract error: {traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/summarize-repo", methods=["POST"])
def api_summarize_repo() -> tuple[dict, int]:
    """Get AI summary of a single repo."""
    data = request.get_json() or {}
    repo_url = data.get("repo", "")
    if not repo_url:
        return jsonify({"error": "No repo provided"}), 400

    settings = _get_settings()
    try:
        repo_url = repo_url.strip().rstrip("/")
        if "github.com" in repo_url:
            parts = repo_url.split("github.com/")[-1].split("/")
            owner, name = parts[0], parts[1].replace(".git", "")
        elif "/" in repo_url:
            owner, name = repo_url.split("/")[:2]
        else:
            return jsonify({"error": "Invalid repo format"}), 400

        with GitHubClient(settings) as client:
            repo = client.get_repo(owner, name)
            readme = client.get_repo_readme(owner, name)

        if not readme:
            return jsonify({
                "repo": repo.model_dump(),
                "summary": "No README found",
            }), 200

        engine = _get_ai_engine(settings)
        if engine.is_available():
            summary = engine.summarize_readme(readme, repo)
            return jsonify({
                "repo": repo.model_dump(),
                "summary": summary.model_dump(),
            }), 200
        else:
            return jsonify({
                "repo": repo.model_dump(),
                "summary": readme[:500],
            }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def main() -> None:
    """Run the web server."""
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", "5000"))
    print("\n  GitHub Auto Clone Web UI")
    print(f"  http://localhost:{port}")
    print("  Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    main()
