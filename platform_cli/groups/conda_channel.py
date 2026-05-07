"""Helpers for opening release PRs against the conda-recipes repo."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List

import click
from ruamel.yaml import YAML

from platform_cli.helpers import call, echo, stdout_call

DEFAULT_RECIPES_REPO = "greenroom-robotics/ros-kilted-recipes"
DEFAULT_BASE_BRANCH = "main"

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=4, offset=2)


def get_recipes_repo_url(repo: str) -> str:
    """HTTPS with API_TOKEN_GITHUB if available, else SSH."""
    token = os.environ.get("API_TOKEN_GITHUB") or os.environ.get("GITHUB_TOKEN")
    if token:
        return f"https://x-access-token:{token}@github.com/{repo}.git"
    return f"git@github.com:{repo}.git"


def clone_recipes_repo(repo: str, dest: Path, base_branch: str = DEFAULT_BASE_BRANCH) -> None:
    url = get_recipes_repo_url(repo)
    call(f"git clone --depth=1 --branch={base_branch} {url} {dest}")


def upsert_recipe_entry(
    recipes_yaml: Path,
    package_name: str,
    source_repo_url: str,
    tag: str,
    version: str,
) -> None:
    """Idempotently upsert one entry; preserves comments and ordering."""
    if recipes_yaml.exists():
        with recipes_yaml.open() as f:
            data = _yaml.load(f) or {}
    else:
        data = {}
    if not isinstance(data, dict):
        raise click.ClickException(
            f"Expected mapping in {recipes_yaml}, got {type(data).__name__}"
        )
    data[package_name] = {
        "url": source_repo_url,
        "tag": tag,
        "version": version,
    }
    with recipes_yaml.open("w") as f:
        _yaml.dump(data, f)


def get_source_repo_url() -> str:
    """Return the source repo's https url, normalising from ssh if needed."""
    raw = stdout_call("git config --get remote.origin.url").strip()
    m = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", raw)
    if m:
        return f"https://github.com/{m.group(1)}.git"
    return raw if raw.endswith(".git") else f"{raw}.git"


def get_source_repo_short_name() -> str:
    url = get_source_repo_url()
    m = re.search(r"/([^/]+?)(?:\.git)?$", url)
    if not m:
        raise click.ClickException(f"Could not parse repo name from {url}")
    return m.group(1)


def open_or_update_pr(
    repo: str,
    branch: str,
    title: str,
    cwd: Path,
    label: str = "automerge",
    base: str = DEFAULT_BASE_BRANCH,
) -> None:
    """Push branch and open PR; if PR already exists for this branch, no-op."""
    call(f"git push --force-with-lease origin {branch}", cwd=cwd)

    existing = stdout_call(
        f"gh pr list --repo {repo} --head {branch} --json number --jq '.[0].number'",
        abort=False,
    ).strip()

    if existing:
        echo(f"PR already exists for {branch} (#{existing}); branch updated.", "blue")
        return

    subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            repo,
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            "Automated by `platform release conda-publish`.",
            "--label",
            label,
        ],
        check=True,
    )
