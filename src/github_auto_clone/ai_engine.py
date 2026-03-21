"""AI engine for intelligent code analysis, feature extraction, and summarization.

Uses Ollama for local, free AI inference. Runs on macOS with ~1-3GB RAM.
Default model: qwen2.5:1.5b (fast, small, good at code analysis).
"""

from __future__ import annotations

import json
import logging
from typing import Any

import ollama
from tenacity import retry, stop_after_attempt, wait_exponential

from github_auto_clone.config import Settings, get_settings
from github_auto_clone.models import AISearchQuery, Feature, RepoInfo, RepoSummary, SearchQuery

logger = logging.getLogger(__name__)


class AIEngine:
    """AI-powered analysis engine using Ollama (local, free)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: ollama.Client | None = None

    @property
    def client(self) -> ollama.Client:
        if self._client is None:
            self._client = ollama.Client(host=self.settings.ollama_host)
        return self._client

    def ensure_model(self) -> bool:
        """Check if the model is available and pull it if not."""
        try:
            models = self.client.list()
            model_names = [
                m.model for m in models.models
            ]
            target = self.settings.ollama_model
            if not any(target in name for name in model_names):
                logger.info(f"Pulling model {target}... (first time only)")
                self.client.pull(target)
            return True
        except Exception as e:
            logger.error(f"Ollama not available: {e}")
            return False

    def is_available(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            self.client.list()
            return True
        except Exception:
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=15))
    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.3) -> str:
        """Make a chat completion request via Ollama."""
        response = self.client.chat(
            model=self.settings.ollama_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            options={"temperature": temperature},
        )
        return response.message.content or ""

    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """Make a chat completion request and parse JSON response."""
        json_suffix = (
            "\n\nYou MUST respond with valid JSON only."
            " No markdown, no explanation, no extra text."
        )
        full_system = system_prompt + json_suffix
        raw = self._chat(full_system, user_prompt, temperature=0.1)
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)
        # Try to find JSON in the response
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from mixed content
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
            raise

    def generate_search_queries(self, ai_query: AISearchQuery) -> list[SearchQuery]:
        """Convert a natural language query into structured GitHub search queries."""
        system_prompt = """You are a GitHub search expert. Convert natural language descriptions
into optimal GitHub search queries. Generate multiple search queries to cover different angles.

Return JSON with this structure:
{
  "queries": [
    {
      "query": "search terms",
      "language": "Python or null",
      "min_stars": 100,
      "sort": "stars",
      "topics": ["topic1"]
    }
  ]
}"""
        user_prompt = f"""Find GitHub repositories for: {ai_query.natural_query}

Additional context: {ai_query.context}
Max results per query: {ai_query.max_results}"""

        data = self._chat_json(system_prompt, user_prompt)
        queries: list[SearchQuery] = []
        for q in data.get("queries", []):
            queries.append(
                SearchQuery(
                    query=q.get("query", ai_query.natural_query),
                    language=q.get("language"),
                    min_stars=q.get("min_stars", 0),
                    sort=q.get("sort", "stars"),
                    topics=q.get("topics", []),
                    per_page=min(ai_query.max_results, 10),
                )
            )
        return queries or [SearchQuery(query=ai_query.natural_query)]

    def summarize_readme(self, readme_content: str, repo: RepoInfo) -> RepoSummary:
        """Generate an AI summary of a repository from its README."""
        system_prompt = """You are a technical analyst. Analyze the README and repository info
to produce a structured summary.

Return JSON:
{
  "short_description": "one-line description",
  "key_features": ["feature 1", "feature 2"],
  "tech_stack": ["Python", "FastAPI"],
  "use_cases": ["use case 1"],
  "complexity": "low|medium|high",
  "quality_score": 7.5
}"""
        user_prompt = f"""Repository: {repo.full_name}
Stars: {repo.stars} | Forks: {repo.forks} | Language: {repo.language}
Description: {repo.description or 'N/A'}

README content (truncated to 8000 chars):
{readme_content[:8000]}"""

        data = self._chat_json(system_prompt, user_prompt)
        return RepoSummary(
            repo=repo,
            short_description=data.get("short_description", repo.description or ""),
            key_features=data.get("key_features", []),
            tech_stack=data.get("tech_stack", []),
            use_cases=data.get("use_cases", []),
            complexity=data.get("complexity", "medium"),
            quality_score=data.get("quality_score", 0.0),
        )

    def extract_features_from_code(
        self,
        file_contents: dict[str, str],
        repo: RepoInfo,
        readme: str | None = None,
    ) -> list[Feature]:
        """Analyze code files and extract discrete features."""
        system_prompt = """You are a senior software architect. Analyze the codebase and identify
ALL discrete features. A feature is a self-contained piece of functionality that could be
extracted and reused in another project.

For each feature, identify:
- Name and description
- Category (auth, api, database, ui, utils, networking, ai, data-processing, etc.)
- Which files implement it
- Entry points (main functions/classes)
- Internal dependencies (other features it depends on)
- External packages it requires
- How complex it is to extract
- Integration notes

Return JSON:
{
  "features": [
    {
      "name": "feature-name",
      "description": "what it does",
      "category": "category",
      "files": ["path/to/file.py"],
      "entry_points": ["ClassName", "function_name"],
      "internal_dependencies": ["other-feature-name"],
      "external_packages": ["package-name"],
      "estimated_complexity": "low|medium|high",
      "integration_notes": "how to integrate this"
    }
  ]
}"""
        # Build a concise code summary
        code_summary_parts: list[str] = []
        total_chars = 0
        max_chars = 50000  # Stay well within context limits

        # Prioritize non-test, non-config files
        sorted_files = sorted(
            file_contents.items(),
            key=lambda x: (
                "test" in x[0].lower(),
                "config" in x[0].lower(),
                len(x[1]),
            ),
        )

        for path, content in sorted_files:
            if total_chars > max_chars:
                break
            truncated = content[:3000]
            entry = f"--- FILE: {path} ---\n{truncated}"
            code_summary_parts.append(entry)
            total_chars += len(entry)

        code_summary = "\n\n".join(code_summary_parts)

        user_prompt = f"""Repository: {repo.full_name}
Language: {repo.language}
Description: {repo.description or 'N/A'}

README Summary:
{(readme or 'No README available')[:2000]}

Codebase ({len(file_contents)} files analyzed):

{code_summary}"""

        data = self._chat_json(system_prompt, user_prompt)
        features: list[Feature] = []
        for f in data.get("features", []):
            features.append(
                Feature(
                    name=f.get("name", "unknown"),
                    description=f.get("description", ""),
                    category=f.get("category", "general"),
                    files=f.get("files", []),
                    entry_points=f.get("entry_points", []),
                    internal_dependencies=f.get("internal_dependencies", []),
                    external_packages=f.get("external_packages", []),
                    estimated_complexity=f.get("estimated_complexity", "medium"),
                    integration_notes=f.get("integration_notes", ""),
                )
            )
        return features

    def generate_integration_guide(
        self,
        features: list[Feature],
        repo: RepoInfo,
        target_structure: str = "",
    ) -> str:
        """Generate a detailed integration guide for extracted features."""
        system_prompt = """You are a technical writer creating integration guides.
Write a clear, actionable guide for integrating extracted features into a new project.
Include code examples, dependency installation, and step-by-step instructions.
Use markdown formatting."""

        features_desc = "\n".join(
            f"- **{f.name}**: {f.description} (deps: {', '.join(f.external_packages)})"
            for f in features
        )

        user_prompt = f"""Source repository: {repo.full_name}
Language: {repo.language}

Features to integrate:
{features_desc}

Target project structure: {target_structure or 'Generic project'}

Write a comprehensive integration guide."""

        return self._chat(system_prompt, user_prompt)

    def generate_safety_notes(
        self,
        features: list[Feature],
        file_contents: dict[str, str],
    ) -> list[str]:
        """Generate safety and security notes for extracted features."""
        system_prompt = """You are a security analyst. Review the extracted features and code
for potential safety concerns. Identify:
- Security vulnerabilities
- License compliance issues
- Dependency risks
- API key / secret exposure risks
- Data privacy concerns

Return JSON:
{
  "safety_notes": ["note 1", "note 2"]
}"""
        # Provide a summary of the code for analysis
        code_snippet = ""
        for path, content in list(file_contents.items())[:10]:
            code_snippet += f"\n--- {path} ---\n{content[:1000]}\n"

        features_desc = "\n".join(f"- {f.name}: {f.description}" for f in features)
        user_prompt = f"""Features:
{features_desc}

Code samples:
{code_snippet[:10000]}"""

        data = self._chat_json(system_prompt, user_prompt)
        return data.get("safety_notes", [])

    def rewrite_imports(
        self,
        code: str,
        old_base_module: str,
        new_base_module: str,
        language: str = "Python",
    ) -> str:
        """Use AI to intelligently rewrite import paths in code."""
        system_prompt = f"""You are a code refactoring tool. Rewrite import statements in
{language} code to change the base module path. Only modify import/require statements,
do not change any other code. Return ONLY the modified code, nothing else."""

        user_prompt = f"""Rewrite imports from '{old_base_module}' to '{new_base_module}'.

Original code:
```
{code}
```"""

        return self._chat(system_prompt, user_prompt, temperature=0.0)

    def rank_repos(
        self,
        repos: list[RepoInfo],
        query: str,
    ) -> list[tuple[RepoInfo, float]]:
        """AI-rank repositories by relevance to a query."""
        system_prompt = """You are a technical evaluator. Rank these repositories by how well
they match the user's needs. Consider: relevance, quality (stars/forks), maintenance,
documentation quality.

Return JSON:
{
  "rankings": [
    {"index": 0, "score": 9.5, "reason": "why it's ranked here"}
  ]
}"""
        repos_desc = "\n".join(
            f"[{i}] {r.full_name} - {r.description or 'No description'} "
            f"(stars: {r.stars}, lang: {r.language})"
            for i, r in enumerate(repos)
        )

        user_prompt = f"""User needs: {query}

Repositories to rank:
{repos_desc}"""

        data = self._chat_json(system_prompt, user_prompt)
        ranked: list[tuple[RepoInfo, float]] = []
        for entry in data.get("rankings", []):
            idx = entry.get("index", 0)
            score = entry.get("score", 0.0)
            if 0 <= idx < len(repos):
                ranked.append((repos[idx], score))
        # Sort by score descending
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked
