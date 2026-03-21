"""CLI interface for GitHub Auto Clone."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from github_auto_clone.ai_engine import AIEngine
from github_auto_clone.config import get_settings
from github_auto_clone.feature_extractor import FeatureExtractor
from github_auto_clone.github_client import GitHubClient
from github_auto_clone.graph_rag import FeatureGraphRAG
from github_auto_clone.models import AISearchQuery, Feature, RepoInfo, SearchQuery
from github_auto_clone.packager import Packager

app = typer.Typer(
    name="ghclone",
    help="AI-powered GitHub feature extraction and packaging tool.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        handlers=[logging.StreamHandler()],
    )


def _display_repos(repos: list[RepoInfo]) -> None:
    """Display repositories in a rich table."""
    table = Table(title="GitHub Repositories", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Repository", style="cyan bold", min_width=25)
    table.add_column("Description", min_width=30)
    table.add_column("Stars", justify="right", style="yellow")
    table.add_column("Language", style="green")
    table.add_column("Updated", style="dim")

    for i, repo in enumerate(repos, 1):
        desc = repo.description or "[dim]No description[/dim]"
        if len(desc) > 80:
            desc = desc[:77] + "..."
        updated = repo.last_updated[:10] if repo.last_updated else "N/A"
        table.add_row(
            str(i),
            f"[link={repo.url}]{repo.full_name}[/link]",
            desc,
            f"⭐ {repo.stars:,}",
            repo.language or "N/A",
            updated,
        )

    console.print(table)


def _display_features(features: list[Feature]) -> None:
    """Display extracted features in a rich tree."""
    tree = Tree("📦 [bold]Extracted Features[/bold]")

    for feature in features:
        complexity_color = {
            "low": "green",
            "medium": "yellow",
            "high": "red",
        }.get(feature.estimated_complexity, "white")

        branch = tree.add(
            f"[bold cyan]{feature.name}[/bold cyan] "
            f"[{complexity_color}]({feature.estimated_complexity})[/{complexity_color}] "
            f"[dim]- {feature.category}[/dim]"
        )
        branch.add(f"[dim]{feature.description}[/dim]")

        if feature.files:
            files_branch = branch.add(f"📁 Files ({len(feature.files)})")
            for f in feature.files[:10]:
                files_branch.add(f"[dim]{f}[/dim]")
            if len(feature.files) > 10:
                files_branch.add(f"[dim]... and {len(feature.files) - 10} more[/dim]")

        if feature.entry_points:
            ep_branch = branch.add("🔌 Entry Points")
            for ep in feature.entry_points:
                ep_branch.add(f"[green]{ep}[/green]")

        if feature.external_packages:
            deps_branch = branch.add("📚 Dependencies")
            for dep in feature.external_packages:
                deps_branch.add(f"[yellow]{dep}[/yellow]")

        if feature.integration_notes:
            branch.add(f"💡 [italic]{feature.integration_notes}[/italic]")

    console.print(tree)


def _parse_repo_arg(repo_arg: str) -> tuple[str, str]:
    """Parse a repo argument like 'owner/name' or full URL."""
    repo_arg = repo_arg.strip().rstrip("/")

    # Handle full GitHub URLs
    if "github.com" in repo_arg:
        parts = repo_arg.split("github.com/")[-1].split("/")
        if len(parts) >= 2:
            return parts[0], parts[1].replace(".git", "")

    # Handle owner/name format
    if "/" in repo_arg:
        parts = repo_arg.split("/")
        return parts[0], parts[1]

    raise typer.BadParameter(
        f"Invalid repository format: {repo_arg}. Use 'owner/name' or a GitHub URL."
    )


# ─── Commands ────────────────────────────────────────────────────────────────


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query for GitHub repositories"),
    language: str | None = typer.Option(None, "--lang", "-l", help="Filter by language"),
    min_stars: int = typer.Option(0, "--stars", "-s", help="Minimum number of stars"),
    sort: str = typer.Option("stars", "--sort", help="Sort by: stars, forks, updated"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
    ai: bool = typer.Option(False, "--ai", help="Use AI to optimize search"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Search for GitHub repositories."""
    setup_logging(verbose)
    settings = get_settings()

    with GitHubClient(settings) as client:
        if ai and settings.has_openai_key:
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]AI is crafting optimal search queries..."),
                console=console,
            ) as progress:
                progress.add_task("", total=None)
                engine = AIEngine(settings)
                ai_query = AISearchQuery(natural_query=query, max_results=limit)
                queries = engine.generate_search_queries(ai_query)

            all_repos: list[RepoInfo] = []
            for sq in queries:
                console.print(f"[dim]Searching: {sq.query}[/dim]")
                repos = client.search_repos(sq)
                all_repos.extend(repos)

            # Deduplicate by full_name
            seen: set[str] = set()
            unique_repos: list[RepoInfo] = []
            for repo in all_repos:
                if repo.full_name not in seen:
                    seen.add(repo.full_name)
                    unique_repos.append(repo)

            # AI ranking
            if unique_repos and settings.has_openai_key:
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]AI is ranking results by relevance..."),
                    console=console,
                ) as progress:
                    progress.add_task("", total=None)
                    ranked = engine.rank_repos(unique_repos[:20], query)
                    unique_repos = [r for r, _ in ranked]

            _display_repos(unique_repos[:limit])
        else:
            search_query = SearchQuery(
                query=query,
                language=language,
                min_stars=min_stars,
                sort=sort,
                per_page=limit,
            )
            repos = client.search_repos(search_query)
            _display_repos(repos)


@app.command()
def list_repos(
    user: str = typer.Argument(..., help="GitHub username to list repos for"),
    sort: str = typer.Option("updated", "--sort", help="Sort by: updated, created, full_name"),
    limit: int = typer.Option(30, "--limit", "-n", help="Number of results"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List all repositories for a GitHub user."""
    setup_logging(verbose)
    settings = get_settings()

    with GitHubClient(settings) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold blue]Fetching repos for {user}..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            repos = client.list_user_repos(user, sort=sort, per_page=limit)

    _display_repos(repos)

    # Show summary
    if repos:
        languages = {}
        for r in repos:
            lang = r.language or "Unknown"
            languages[lang] = languages.get(lang, 0) + 1

        summary = Table(title="Summary", show_header=False)
        summary.add_column("Metric", style="bold")
        summary.add_column("Value")
        summary.add_row("Total repos", str(len(repos)))
        summary.add_row("Total stars", f"⭐ {sum(r.stars for r in repos):,}")
        top_langs = sorted(languages.items(), key=lambda x: -x[1])[:5]
        summary.add_row(
            "Languages",
            ", ".join(f"{k} ({v})" for k, v in top_langs),
        )
        console.print(summary)


@app.command()
def analyze(
    repo_arg: str = typer.Argument(..., help="Repository (owner/name or URL)"),
    summarize: bool = typer.Option(True, "--summarize/--no-summarize", help="AI summarize"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Analyze a repository and extract its features."""
    setup_logging(verbose)
    settings = get_settings()
    owner, name = _parse_repo_arg(repo_arg)

    with GitHubClient(settings) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Fetching repository info..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            repo = client.get_repo(owner, name)
            readme_content = client.get_repo_readme(owner, name)

    # Display repo info
    console.print(Panel(
        f"[bold]{repo.full_name}[/bold]\n"
        f"{repo.description or 'No description'}\n\n"
        f"⭐ {repo.stars:,} stars | 🍴 {repo.forks:,} forks | "
        f"📝 {repo.language or 'Unknown'} | 📋 {repo.license or 'No license'}",
        title="Repository Info",
    ))

    # AI Summary
    if summarize and settings.has_openai_key and readme_content:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]AI is analyzing the repository..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            engine = AIEngine(settings)
            summary = engine.summarize_readme(readme_content, repo)

        console.print(Panel(
            f"[bold]Summary:[/bold] {summary.short_description}\n\n"
            f"[bold]Quality Score:[/bold] {summary.quality_score}/10 | "
            f"[bold]Complexity:[/bold] {summary.complexity}\n\n"
            f"[bold]Key Features:[/bold]\n" +
            "\n".join(f"  • {f}" for f in summary.key_features) +
            f"\n\n[bold]Tech Stack:[/bold] {', '.join(summary.tech_stack)}" +
            "\n\n[bold]Use Cases:[/bold]\n" +
            "\n".join(f"  • {u}" for u in summary.use_cases),
            title="AI Analysis",
            border_style="green",
        ))

    # Extract features
    if settings.has_openai_key:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Extracting features from codebase..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            extractor = FeatureExtractor(settings=settings)
            features, repo_path = extractor.analyze_repo(repo)

        _display_features(features)

        # Build feature graph
        graph_rag = FeatureGraphRAG()
        feature_graph = graph_rag.build_graph(features)

        # Display graph insights
        meta = feature_graph.metadata
        console.print(Panel(
            f"[bold]Features:[/bold] {meta.get('total_features', 0)}\n"
            f"[bold]Relationships:[/bold] {meta.get('total_relationships', 0)}\n"
            f"[bold]Independent Features:[/bold] {meta.get('independent_features', 0)}\n"
            f"[bold]Feature Clusters:[/bold] {meta.get('clusters', 0)}\n"
            f"[bold]Categories:[/bold] {json.dumps(meta.get('categories', {}), indent=2)}",
            title="Feature Graph Analysis",
            border_style="blue",
        ))

        # Show importance ranking
        importance = graph_rag.get_feature_importance()
        if importance:
            imp_table = Table(title="Feature Importance (PageRank)")
            imp_table.add_column("Feature", style="cyan")
            imp_table.add_column("Score", justify="right", style="yellow")
            for name_val, score in sorted(importance.items(), key=lambda x: -x[1]):
                imp_table.add_row(name_val, f"{score:.4f}")
            console.print(imp_table)
    else:
        console.print("[yellow]Set OPENAI_API_KEY for AI-powered feature extraction[/yellow]")


@app.command()
def extract(
    repo_arg: str = typer.Argument(..., help="Repository (owner/name or URL)"),
    features: str | None = typer.Option(
        None, "--features", "-f", help="Comma-separated feature names to extract (empty = all)"
    ),
    output: str = typer.Option("./extracted_features", "--output", "-o", help="Output directory"),
    no_rewrite: bool = typer.Option(False, "--no-rewrite", help="Don't rewrite imports"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Extract and package features from a repository into an importable folder."""
    setup_logging(verbose)
    settings = get_settings()

    if not settings.has_openai_key:
        console.print("[red]OPENAI_API_KEY is required for feature extraction[/red]")
        raise typer.Exit(1)

    owner, name = _parse_repo_arg(repo_arg)

    with GitHubClient(settings) as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Fetching repository..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            repo = client.get_repo(owner, name)

    feature_names = [f.strip() for f in features.split(",")] if features else []

    # Extract features
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Analyzing and extracting features..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        extractor = FeatureExtractor(settings=settings)
        extracted_features, extracted_files = extractor.extract_specific_features(
            repo, feature_names
        )

    if not extracted_files:
        console.print(
            "[red]No files were extracted. "
            "Try running 'analyze' first to see available features.[/red]"
        )
        raise typer.Exit(1)

    _display_features(extracted_features)

    # Build graph and get optimal order
    graph_rag = FeatureGraphRAG()
    graph_rag.build_graph(extracted_features)

    names = [f.name for f in extracted_features]
    order = graph_rag.get_extraction_order(names)
    console.print(f"\n[bold]Extraction order:[/bold] {' → '.join(order)}")

    # Package
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Packaging features..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        packager = Packager(settings=settings)
        output_path = Path(output)
        package_dir = packager.package_features(
            extracted_features,
            extracted_files,
            repo,
            output_dir=output_path,
            rewrite_imports=not no_rewrite,
        )

        # Export graph
        graph_rag.export_graph(package_dir / "feature_graph.json")

    console.print(Panel(
        f"[bold green]Features packaged successfully![/bold green]\n\n"
        f"📂 Output: [cyan]{package_dir}[/cyan]\n"
        f"📦 Features: {len(extracted_features)}\n"
        f"📄 Files: {len(extracted_files)}\n\n"
        f"[bold]Next steps:[/bold]\n"
        f"1. Review the files in [cyan]{package_dir}/src[/cyan]\n"
        f"2. Read [cyan]{package_dir}/INTEGRATION.md[/cyan] for integration guide\n"
        f"3. Read [cyan]{package_dir}/SAFETY.md[/cyan] for security notes\n"
        f"4. Install dependencies from [cyan]{package_dir}/requirements.txt[/cyan]",
        title="Package Complete",
        border_style="green",
    ))


@app.command()
def ai_search(
    query: str = typer.Argument(..., help="Natural language description of what you need"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    auto_analyze: bool = typer.Option(False, "--analyze", "-a", help="Auto-analyze top result"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Use AI to find the best GitHub repositories for your needs."""
    setup_logging(verbose)
    settings = get_settings()

    if not settings.has_openai_key:
        console.print("[red]OPENAI_API_KEY is required for AI search[/red]")
        raise typer.Exit(1)

    engine = AIEngine(settings)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]AI is understanding your requirements..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        ai_query = AISearchQuery(natural_query=query, max_results=limit)
        search_queries = engine.generate_search_queries(ai_query)

    console.print(f"[dim]Generated {len(search_queries)} search strategies[/dim]")

    all_repos: list[RepoInfo] = []
    with GitHubClient(settings) as client:
        for sq in search_queries:
            console.print(f"  [dim]→ Searching: {sq.query}[/dim]")
            repos = client.search_repos(sq)
            all_repos.extend(repos)

    # Deduplicate
    seen: set[str] = set()
    unique: list[RepoInfo] = []
    for repo in all_repos:
        if repo.full_name not in seen:
            seen.add(repo.full_name)
            unique.append(repo)

    if not unique:
        console.print("[yellow]No repositories found. Try a different query.[/yellow]")
        raise typer.Exit(0)

    # AI ranking
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]AI is ranking results..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        ranked = engine.rank_repos(unique[:20], query)

    # Display ranked results
    table = Table(title="AI-Ranked Results", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Repository", style="cyan bold")
    table.add_column("Description")
    table.add_column("Score", justify="right", style="green bold")
    table.add_column("Stars", justify="right", style="yellow")

    for i, (repo, score) in enumerate(ranked[:limit], 1):
        desc = repo.description or "[dim]No description[/dim]"
        if len(desc) > 60:
            desc = desc[:57] + "..."
        table.add_row(
            str(i),
            f"[link={repo.url}]{repo.full_name}[/link]",
            desc,
            f"{score:.1f}/10",
            f"⭐ {repo.stars:,}",
        )

    console.print(table)

    # Auto-analyze top result
    if auto_analyze and ranked:
        top_repo = ranked[0][0]
        console.print(f"\n[bold]Auto-analyzing top result: {top_repo.full_name}[/bold]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]Extracting features..."),
            console=console,
        ) as progress:
            progress.add_task("", total=None)
            extractor = FeatureExtractor(settings=settings)
            features, _ = extractor.analyze_repo(top_repo)

        _display_features(features)


@app.command()
def graph(
    repo_arg: str = typer.Argument(..., help="Repository (owner/name or URL)"),
    output: str = typer.Option("./feature_graph.json", "--output", "-o", help="Output file"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Build and visualize a feature dependency graph for a repository."""
    setup_logging(verbose)
    settings = get_settings()

    if not settings.has_openai_key:
        console.print("[red]OPENAI_API_KEY is required[/red]")
        raise typer.Exit(1)

    owner, name = _parse_repo_arg(repo_arg)

    with GitHubClient(settings) as client:
        repo = client.get_repo(owner, name)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Analyzing repository features..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        extractor = FeatureExtractor(settings=settings)
        features, _ = extractor.analyze_repo(repo)

    graph_rag = FeatureGraphRAG()
    graph_rag.build_graph(features)

    # Display graph
    tree = Tree("🔗 [bold]Feature Dependency Graph[/bold]")
    clusters = graph_rag.get_feature_clusters()

    for i, cluster in enumerate(clusters, 1):
        cluster_branch = tree.add(f"[bold]Cluster {i}[/bold] ({len(cluster)} features)")
        for feat_name in cluster:
            deps = graph_rag.get_dependencies(feat_name, recursive=False)
            related = graph_rag.get_related_features(feat_name)

            feat_label = f"[cyan]{feat_name}[/cyan]"
            if deps:
                feat_label += f" → depends on: [yellow]{', '.join(deps)}[/yellow]"
            feat_branch = cluster_branch.add(feat_label)

            if related:
                for rel_name, weight in related[:3]:
                    feat_branch.add(f"[dim]~ related to {rel_name} (weight: {weight:.1f})[/dim]")

    console.print(tree)

    # Export
    output_path = Path(output)
    graph_rag.export_graph(output_path)
    console.print(f"\n[green]Graph exported to {output_path}[/green]")

    # Suggestions
    independent = graph_rag.find_independent_features()
    if independent:
        console.print("\n[bold]Standalone features (no dependencies):[/bold]")
        for name_val in independent:
            console.print(f"  [green]✓[/green] {name_val}")


@app.command()
def quickstart(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Interactive quickstart - describe what you need and get features packaged automatically."""
    setup_logging(verbose)
    settings = get_settings()

    console.print(Panel(
        "[bold]Welcome to GitHub Auto Clone![/bold]\n\n"
        "Describe the feature you need, and I'll find the best implementation\n"
        "from GitHub, extract it, and package it for you to import.\n\n"
        "[dim]Example: 'I need a browser automation agent for my enterprise AI app'[/dim]",
        title="🚀 Quickstart",
        border_style="cyan",
    ))

    if not settings.has_openai_key:
        console.print("[red]OPENAI_API_KEY is required for quickstart mode[/red]")
        console.print("[dim]Set it with: export OPENAI_API_KEY=your-key[/dim]")
        raise typer.Exit(1)

    # Get user's need
    query = typer.prompt("\n🔍 What feature do you need?")

    engine = AIEngine(settings)

    # AI search
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Finding the best repositories..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        ai_query = AISearchQuery(natural_query=query, max_results=10)
        search_queries = engine.generate_search_queries(ai_query)

    all_repos: list[RepoInfo] = []
    with GitHubClient(settings) as client:
        for sq in search_queries:
            repos = client.search_repos(sq)
            all_repos.extend(repos)

    # Deduplicate and rank
    seen: set[str] = set()
    unique: list[RepoInfo] = []
    for repo in all_repos:
        if repo.full_name not in seen:
            seen.add(repo.full_name)
            unique.append(repo)

    if not unique:
        console.print("[red]No repositories found. Try a different description.[/red]")
        raise typer.Exit(0)

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]AI is evaluating repositories..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        ranked = engine.rank_repos(unique[:15], query)

    # Show top 5
    table = Table(title="Top Repositories")
    table.add_column("#", width=4)
    table.add_column("Repository", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Stars", style="yellow")

    for i, (repo, score) in enumerate(ranked[:5], 1):
        table.add_row(str(i), repo.full_name, f"{score:.1f}", f"⭐ {repo.stars:,}")
    console.print(table)

    # Ask which to use
    choice = typer.prompt("\nWhich repo? (number or 'all' for top result)", default="1")
    idx = 0 if choice == "all" else int(choice) - 1
    selected_repo = ranked[idx][0]

    console.print(f"\n[bold]Analyzing {selected_repo.full_name}...[/bold]")

    # Extract features
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Extracting all features..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        extractor = FeatureExtractor(settings=settings)
        features, extracted_files = extractor.extract_specific_features(selected_repo, [])

    _display_features(features)

    # Ask which features to package
    console.print("\n[bold]Which features do you want to package?[/bold]")
    console.print("[dim]Enter feature numbers (comma-separated) or 'all'[/dim]")

    for i, f in enumerate(features, 1):
        console.print(f"  {i}. {f.name} - {f.description[:60]}")

    feat_choice = typer.prompt("\nFeatures", default="all")
    if feat_choice.lower() == "all":
        selected_features = features
    else:
        indices = [int(x.strip()) - 1 for x in feat_choice.split(",")]
        selected_features = [features[i] for i in indices if 0 <= i < len(features)]

    # Package
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Packaging features..."),
        console=console,
    ) as progress:
        progress.add_task("", total=None)
        packager = Packager(settings=settings)
        package_dir = packager.package_features(
            selected_features, extracted_files, selected_repo
        )

    console.print(Panel(
        f"[bold green]Done! Your features are ready.[/bold green]\n\n"
        f"📂 Package: [cyan]{package_dir}[/cyan]\n"
        f"📦 Features: {len(selected_features)}\n"
        f"📄 Files: {len(extracted_files)}\n\n"
        f"[bold]To integrate:[/bold]\n"
        f"1. Copy [cyan]{package_dir}/src[/cyan] into your project\n"
        f"2. Install deps from [cyan]{package_dir}/requirements.txt[/cyan]\n"
        f"3. Follow [cyan]{package_dir}/INTEGRATION.md[/cyan]",
        title="🎉 Package Complete",
        border_style="green",
    ))


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
) -> None:
    """GitHub Auto Clone - AI-powered feature extraction and packaging."""
    if version:
        from github_auto_clone import __version__
        rprint(f"ghclone v{__version__}")
        raise typer.Exit()


if __name__ == "__main__":
    app()
