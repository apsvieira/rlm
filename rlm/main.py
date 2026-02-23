"""CLI entrypoint for the RLM."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import click

from rlm.agent import RLMConfig, rlm_call
from rlm.workspace import Workspace


@click.command()
@click.option("--context", "context_path", type=click.Path(exists=True), help="Path to context file")
@click.option("--context-text", "context_text", type=str, help="Inline context string")
@click.option("--goal", required=True, type=str, help="The task/question to accomplish")
@click.option("--model", default="claude-sonnet-4-6", help="Model to use")
@click.option("--max-depth", default=3, type=int, help="Maximum recursion depth")
@click.option(
    "--workspace",
    "workspace_path",
    type=click.Path(),
    default=None,
    help="Workspace directory (default: rlm_workspace/<timestamp>)",
)
def cli(
    context_path: str | None,
    context_text: str | None,
    goal: str,
    model: str,
    max_depth: int,
    workspace_path: str | None,
):
    """RLM — Recursive Language Model agent."""
    if not context_path and not context_text:
        # Try reading from stdin
        if not sys.stdin.isatty():
            context_text = sys.stdin.read()
        else:
            raise click.UsageError("Provide --context, --context-text, or pipe input via stdin.")

    if workspace_path is None:
        workspace_path = f"rlm_workspace/{int(time.time())}"

    workspace = Workspace(root=Path(workspace_path))
    config = RLMConfig(goal=goal, model=model, max_depth=max_depth)

    workspace.write_run_manifest(
        goal=goal, model=model, max_depth=max_depth, status="running",
    )

    result = asyncio.run(
        rlm_call(
            workspace=workspace,
            config=config,
            depth=0,
            call_index=0,
            context=context_text,
            context_path=Path(context_path) if context_path else None,
        )
    )

    workspace.update_run_manifest(
        status="completed",
        total_cost_usd=result.total_cost_usd,
        total_calls=result.total_calls,
    )

    click.echo(f"\n{'='*60}")
    click.echo("RLM Complete")
    click.echo(f"Workspace: {result.workspace_root}")
    click.echo(f"Total API calls: {result.total_calls}")
    click.echo(f"Total cost: ${result.total_cost_usd:.4f}")
    if result.output_files:
        click.echo(f"\nOutput files ({len(result.output_files)}):")
        for f in result.output_files:
            size = f.stat().st_size if f.exists() else 0
            if size >= 1024:
                size_str = f"({size / 1024:.1f}KB)"
            else:
                size_str = f"({size}B)"
            click.echo(f"  {f}  {size_str}")
    click.echo(f"{'='*60}\n")
    click.echo(result.answer)


if __name__ == "__main__":
    cli()
