"""GitHub API client for searching and fetching repository information."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from github_auto_clone.config import Settings, get_settings
from github_auto_clone.models import RepoInfo, SearchQuery

logger = logging.getLogger(__name__)


class GitHubClient:
    """Client for interacting with the GitHub API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            headers: dict[str, str] = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if self.settings.has_github_token:
                headers["Authorization"] = f"Bearer {self.settings.github_token}"
            self._client = httpx.Client(
                base_url=self.settings.github_api_url,
                headers=headers,
                timeout=30.0,
            )
        return self._client

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GET request to the GitHub API with retry logic."""
        response = self.client.get(endpoint, params=params)
        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
            logger.warning(f"Rate limited. Remaining: {remaining}")
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        return response.json()

    def search_repos(self, query: SearchQuery) -> list[RepoInfo]:
        """Search for GitHub repositories."""
        q_parts = [query.query]
        if query.language:
            q_parts.append(f"language:{query.language}")
        if query.min_stars > 0:
            q_parts.append(f"stars:>={query.min_stars}")
        for topic in query.topics:
            q_parts.append(f"topic:{topic}")

        params = {
            "q": " ".join(q_parts),
            "sort": query.sort,
            "order": query.order,
            "per_page": query.per_page,
            "page": query.page,
        }

        data = self._get("/search/repositories", params=params)
        repos: list[RepoInfo] = []
        for item in data.get("items", []):
            repos.append(self._parse_repo(item))
        return repos

    def get_repo(self, owner: str, name: str) -> RepoInfo:
        """Get information about a specific repository."""
        data = self._get(f"/repos/{owner}/{name}")
        return self._parse_repo(data)

    def get_repo_readme(self, owner: str, name: str) -> str | None:
        """Fetch the README content of a repository."""
        try:
            response = self.client.get(
                f"/repos/{owner}/{name}/readme",
                headers={"Accept": "application/vnd.github.raw+json"},
            )
            if response.status_code == 200:
                return response.text
            return None
        except httpx.HTTPError:
            return None

    def get_repo_contents(
        self, owner: str, name: str, path: str = ""
    ) -> list[dict[str, Any]]:
        """Get the contents of a repository directory."""
        try:
            data = self._get(f"/repos/{owner}/{name}/contents/{path}")
            if isinstance(data, list):
                return data
            return [data]
        except httpx.HTTPError:
            return []

    def get_repo_languages(self, owner: str, name: str) -> dict[str, int]:
        """Get the languages used in a repository."""
        try:
            return self._get(f"/repos/{owner}/{name}/languages")
        except httpx.HTTPError:
            return {}

    def get_repo_topics(self, owner: str, name: str) -> list[str]:
        """Get the topics of a repository."""
        try:
            data = self._get(f"/repos/{owner}/{name}/topics")
            return data.get("names", [])
        except httpx.HTTPError:
            return []

    def list_user_repos(
        self,
        username: str,
        sort: str = "updated",
        per_page: int = 30,
    ) -> list[RepoInfo]:
        """List repositories for a user."""
        params = {"sort": sort, "per_page": per_page, "type": "all"}
        data = self._get(f"/users/{username}/repos", params=params)
        return [self._parse_repo(item) for item in data]

    def search_code(
        self,
        query: str,
        language: str | None = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for code across GitHub repositories."""
        q_parts = [query]
        if language:
            q_parts.append(f"language:{language}")
        params = {"q": " ".join(q_parts), "per_page": per_page}
        data = self._get("/search/code", params=params)
        return data.get("items", [])

    @staticmethod
    def _parse_repo(data: dict[str, Any]) -> RepoInfo:
        """Parse a GitHub API repo response into a RepoInfo model."""
        license_info = data.get("license")
        license_name = license_info.get("spdx_id", "Unknown") if license_info else None

        return RepoInfo(
            full_name=data.get("full_name", ""),
            name=data.get("name", ""),
            owner=data.get("owner", {}).get("login", ""),
            description=data.get("description"),
            url=data.get("html_url", ""),
            clone_url=data.get("clone_url", ""),
            stars=data.get("stargazers_count", 0),
            forks=data.get("forks_count", 0),
            language=data.get("language"),
            topics=data.get("topics", []),
            default_branch=data.get("default_branch", "main"),
            last_updated=data.get("updated_at"),
            license=license_name,
            is_fork=data.get("fork", False),
            open_issues=data.get("open_issues_count", 0),
            size_kb=data.get("size", 0),
        )
