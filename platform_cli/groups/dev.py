from __future__ import annotations

import json
import os
import shutil
import subprocess
from importlib.metadata import distribution
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import click
import yaml

from platform_cli.groups.base import PlatformCliGroup


PRODUCTS: Dict[str, Any] = {
    "lookout": {
        "cli_package": "lookout-cli",
        "compose_dir": "tools/lookout_cli/lookout_cli/docker",
        "marker_path": "tools/lookout_cli",
        "default_service": "lookout_core",
        "services": {
            "lookout_core": {
                "ros_overlay": "/opt/greenroom/lookout_core",
                "command_env": "LOOKOUT_CORE_COMMAND",
                "workdir": "/home/ros/lookout_core",
            },
            "lookout_greenstream": {
                "ros_overlay": "/opt/greenroom/lookout_greenstream",
                "command_env": "LOOKOUT_GREENSTREAM_COMMAND",
                "workdir": "/home/ros/lookout_greenstream",
            },
        },
    },
    "gama": {
        "cli_package": "gama-cli",
        # The gama vessel CLI looks for the overlay at <gama_cli>/docker/docker-compose.local-dev.yaml
        # (one level above the per-variant `vessel/` dir), so we write it there.
        "compose_dir": "libs/gama_cli/gama_cli/docker",
        "marker_path": "libs/gama_cli",
        "default_service": "gama_vessel",
        "services": {
            "gama_vessel": {
                "ros_overlay": "/opt/greenroom/gama_vessel",
                "command_env": "GAMA_VESSEL_COMMAND",
                "workdir": "/home/ros/gama_vessel",
            },
        },
    },
    "missim": {
        "cli_package": "missim-cli",
        "compose_dir": "tools/missim_cli/missim_cli/docker",
        "marker_path": "tools/missim_cli",
        "default_service": "missim_core",
        "services": {
            "missim_core": {
                "ros_overlay": "/opt/greenroom/missim_core",
                "command_env": None,
                "default_command": "ros2 launch missim_bringup missim.launch.py",
                "workdir": "/home/ros/missim_core",
            },
        },
    },
}

PRODUCT_NAMES = list(PRODUCTS.keys())
PRODUCT_ALIASES = {"l": "lookout", "g": "gama", "m": "missim"}


class ProductType(click.ParamType):
    name = "product"

    def convert(self, value, param, ctx):
        resolved = PRODUCT_ALIASES.get(value, value)
        if resolved not in PRODUCTS:
            valid = ", ".join(f"{n} ({a})" for a, n in PRODUCT_ALIASES.items())
            self.fail(f"'{value}' is not a valid product. Valid: {valid}", param, ctx)
        return resolved


OVERLAY_FILENAME = "docker-compose.local-dev.yaml"
CONTAINER_MOUNT_BASE = "/home/ros/local_dev"
CONTAINER_BUILD_BASE = "/home/ros/.local-dev/build"
CONTAINER_TOKEN_PATH = "/home/ros/.local-dev/api-token-github"
SECRETS_TOKEN_RELATIVE = ".secrets/API_TOKEN_GITHUB"
CONTAINER_PLATFORM_CLI_SRC = "/home/ros/.local-dev/platform_cli_src"

SKIP_DIRS = {
    "node_modules",
    ".cache",
    ".local",
    "__pycache__",
    "venv",
    ".venv",
    ".npm",
    ".cargo",
    "build",
    "install",
    "log",
}
MAX_DEPTH = 5


# ---------------------------------------------------------------------------
# Product repo discovery
# ---------------------------------------------------------------------------


def _find_via_importlib(product_name: str) -> Optional[Path]:
    """If the product CLI is editable-installed, resolve its repo root."""
    product_config = PRODUCTS[product_name]
    try:
        dist = distribution(product_config["cli_package"])
        direct_url_text = dist.read_text("direct_url.json")
        if not direct_url_text:
            return None
        direct_url = json.loads(direct_url_text)
        if not direct_url.get("dir_info", {}).get("editable"):
            return None
        cli_path = Path(urlparse(direct_url["url"]).path)
        marker = product_config["marker_path"]
        candidate = cli_path
        for _ in range(10):
            if (candidate / marker).exists():
                return candidate
            if candidate.parent == candidate:
                break
            candidate = candidate.parent
        return None
    except Exception:
        return None


def _find_via_fd(product_name: str) -> Optional[Path]:
    """Use fd/fdfind to search ~ for the product directory."""
    product_config = PRODUCTS[product_name]
    fd_bin = shutil.which("fdfind") or shutil.which("fd")
    if not fd_bin:
        return None
    try:
        result = subprocess.run(
            [
                fd_bin,
                "--type",
                "d",
                "--max-depth",
                str(MAX_DEPTH),
                "--no-ignore",
                "--glob",
                product_name,
                str(Path.home()),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        for line in result.stdout.strip().splitlines():
            candidate = Path(line)
            if (candidate / product_config["marker_path"]).exists():
                return candidate
        return None
    except Exception:
        return None


def _find_via_scandir(
    product_name: str,
    search_root: Optional[Path] = None,
    max_depth: int = MAX_DEPTH,
) -> Optional[Path]:
    """Recursively search for the product directory using os.scandir."""
    product_config = PRODUCTS[product_name]
    root = search_root or Path.home()

    def _search(directory: Path, depth: int) -> Optional[Path]:
        if depth > max_depth:
            return None
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if entry.name.startswith(".") or entry.name in SKIP_DIRS:
                        continue
                    if entry.name == product_name:
                        candidate = Path(entry.path)
                        if (candidate / product_config["marker_path"]).exists():
                            return candidate
                    found = _search(Path(entry.path), depth + 1)
                    if found:
                        return found
        except PermissionError:
            pass
        return None

    return _search(root, 0)


def find_product_repo(product_name: str, product_repo: Optional[str] = None) -> Path:
    """Find the product repository on disk. Raises click.ClickException on failure."""
    product_config = PRODUCTS[product_name]

    if product_repo:
        repo_path = Path(product_repo).resolve()
        if not (repo_path / product_config["marker_path"]).exists():
            raise click.ClickException(
                f"Directory {repo_path} does not appear to be a {product_name} repo "
                f"(missing {product_config['marker_path']})"
            )
        return repo_path

    for finder in (_find_via_importlib, _find_via_fd, _find_via_scandir):
        result = finder(product_name)
        if result:
            return result

    raise click.ClickException(
        f"Could not find {product_name} repository. "
        f"Please pass --product-repo /path/to/{product_name}"
    )


# ---------------------------------------------------------------------------
# Overlay read/write
# ---------------------------------------------------------------------------


def read_overlay(overlay_path: Path) -> dict:
    """Read the overlay YAML. Returns empty structure if missing."""
    if not overlay_path.exists():
        return {"services": {}}
    with open(overlay_path) as f:
        data = yaml.safe_load(f)
    if not data:
        return {"services": {}}
    data.setdefault("services", {})
    return data


def write_overlay(overlay_path: Path, data: dict) -> None:
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    with open(overlay_path, "w") as f:
        f.write("# Auto-generated by platform dev mount - do not edit manually\n")
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Overlay mutation
# ---------------------------------------------------------------------------


def _format_mounts_env(mounts: List[Tuple[str, List[str]]]) -> str:
    """Encode mounts as space-separated '<container_path>:<pkg1>,<pkg2>' entries."""
    return " ".join(f"{cp}:{','.join(pkgs)}" for cp, pkgs in mounts)


def _parse_mounts_env(raw: str) -> List[Tuple[str, List[str]]]:
    """Inverse of _format_mounts_env. Empty string → empty list."""
    if not raw.strip():
        return []
    out: List[Tuple[str, List[str]]] = []
    for entry in raw.split():
        cp, _, pkg_csv = entry.partition(":")
        pkgs = [p for p in pkg_csv.split(",") if p]
        out.append((cp, pkgs))
    return out


def _build_service_command(service_config: dict) -> str:
    """Compose command: bootstrap host platform_cli, then `platform dev _run`.

    `$$` escapes docker-compose's variable interpolation so the literal `$VAR`
    reaches the container shell (which expands it against the container env).

    The `pip install` step ensures the container picks up the host's current
    platform_cli (bind-mounted at CONTAINER_PLATFORM_CLI_SRC) — otherwise a
    pre-built image may lack newer subcommands like `platform dev _run`.
    """
    if service_config.get("command_env"):
        inner = f'bash -c "$${service_config["command_env"]}"'
    else:
        inner = service_config["default_command"]
    bootstrap = (
        f"[ -d {CONTAINER_PLATFORM_CLI_SRC} ] && "
        f"pip install --user --quiet --no-deps --force-reinstall "
        f"{CONTAINER_PLATFORM_CLI_SRC} >/dev/null 2>&1 ||:"
    )
    return f"bash -l -c '{bootstrap} ; platform dev _run -- {inner}'"


def _find_host_platform_cli_repo() -> Optional[Path]:
    """Locate the host platform_cli repo (the dir containing setup.cfg).

    Used to bind-mount the host's current platform_cli source into the
    container so `platform dev _run` (and any in-flight dev.py changes) are
    available even in pre-built images.
    """
    # This file lives at <repo>/platform_cli/groups/dev.py. Walk up 2 levels.
    here = Path(__file__).resolve().parents[2]
    if (here / "setup.cfg").exists() and (here / "platform_cli").is_dir():
        return here
    return None


def _service_mounts(service_data: dict) -> List[Tuple[str, List[str]]]:
    env = service_data.get("environment", {}) or {}
    return _parse_mounts_env(env.get("PLATFORM_DEV_MOUNTS", ""))


def add_mount_to_overlay(
    overlay: dict,
    service_name: str,
    service_config: dict,
    host_path: Path,
    packages: List[str],
    token_host_path: Optional[Path] = None,
) -> None:
    """Add or update a mount entry in the overlay dict (mutates in place).

    If `token_host_path` is provided and exists, bind-mounts it into the container
    read-only so `_run` can inject `API_TOKEN_GITHUB` into install-deps.
    """
    container_path = f"{CONTAINER_MOUNT_BASE}/{host_path.name}"

    services = overlay.setdefault("services", {})
    svc = services.setdefault(service_name, {})

    # Preserve existing host:container mappings so a new mount doesn't clobber old ones.
    existing_host_by_cp: Dict[str, str] = {}
    for vol in svc.get("volumes", []) or []:
        if not isinstance(vol, str) or ":" not in vol:
            continue
        h, c = vol.split(":", 1)
        c = c.rsplit(":", 1)[0] if c.endswith(":ro") or c.endswith(":rw") else c
        if c.startswith(CONTAINER_MOUNT_BASE + "/"):
            existing_host_by_cp[c] = h

    mounts = _service_mounts(svc)
    for i, (cp, _) in enumerate(mounts):
        if cp == container_path:
            mounts[i] = (container_path, list(packages))
            break
    else:
        mounts.append((container_path, list(packages)))

    existing_host_by_cp[container_path] = str(host_path)
    volumes = [f"{existing_host_by_cp[cp]}:{cp}" for cp, _ in mounts]
    if token_host_path and token_host_path.exists():
        volumes.append(f"{token_host_path}:{CONTAINER_TOKEN_PATH}:ro")
    platform_cli_host = _find_host_platform_cli_repo()
    if platform_cli_host is not None:
        volumes.append(f"{platform_cli_host}:{CONTAINER_PLATFORM_CLI_SRC}:ro")

    svc["environment"] = {
        "PLATFORM_DEV_MOUNTS": _format_mounts_env(mounts),
        "PLATFORM_DEV_SOURCE": f"{service_config['ros_overlay']}/setup.bash",
        "PLATFORM_DEV_WORKDIR": service_config["workdir"],
    }
    svc["volumes"] = volumes
    svc["command"] = _build_service_command(service_config)


# ---------------------------------------------------------------------------
# `platform dev _run` — container-side entrypoint
# ---------------------------------------------------------------------------


def _run_local_dev(passthrough: List[str]) -> None:
    """Install deps + build each mounted repo, source overlay, cd workdir, exec passthrough."""
    raw_mounts = os.environ.get("PLATFORM_DEV_MOUNTS", "")
    source_path = os.environ.get("PLATFORM_DEV_SOURCE", "")
    workdir = os.environ.get("PLATFORM_DEV_WORKDIR", "")

    if not passthrough:
        raise click.ClickException("platform dev _run requires a passthrough command after `--`")
    if not source_path or not workdir:
        raise click.ClickException(
            "PLATFORM_DEV_SOURCE and PLATFORM_DEV_WORKDIR must be set by the overlay"
        )

    # Build a subprocess env that injects API_TOKEN_GITHUB (read from the
    # bind-mounted secret file) only for the children — never exported to the
    # parent process, so it isn't visible via `env` in the service shell later.
    deps_env = dict(os.environ)
    token_path = Path(CONTAINER_TOKEN_PATH)
    if token_path.exists():
        token = token_path.read_text().strip()
        if token:
            deps_env["API_TOKEN_GITHUB"] = token

    for container_path, packages in _parse_mounts_env(raw_mounts):
        base = Path(container_path).name
        build_base = f"{CONTAINER_BUILD_BASE}/{base}"

        click.echo(click.style(f"[platform dev] installing deps for {container_path}", fg="cyan"))
        subprocess.run(
            ["platform", "pkg", "install-deps", "--no-apt-update"],
            cwd=container_path,
            env=deps_env,
            check=True,
        )

        pkg_args: List[str] = []
        for p in packages:
            pkg_args += ["--package", p]
        label = ",".join(packages) if packages else "all packages"
        click.echo(click.style(f"[platform dev] building {label} in {container_path}", fg="cyan"))
        subprocess.run(
            ["platform", "ros", "build", *pkg_args, "--", "--build-base", build_base],
            cwd=container_path,
            check=True,
        )

    # Chain: source overlay → cd workdir → spawn a fresh login shell to run the command.
    # Running the passthrough under a new `bash -l -c` (rather than exec'ing it directly)
    # means /etc/profile and ~/.profile re-run from scratch, rebuilding AMENT_PREFIX_PATH
    # and friends against the now-current state of /opt/greenroom/<module>. Without this,
    # packages symlinked in by colcon during the build step are missed by setup.bash
    # because their local_setup.bash sourcing happens in the already-partially-initialized
    # outer shell.
    joined = " ".join(_shquote(arg) for arg in passthrough)
    shell_cmd = (
        f"source {_shquote(source_path)} && "
        f"cd {_shquote(workdir)} && "
        f"exec bash -l -c {_shquote(joined)}"
    )
    os.execvp("bash", ["bash", "-l", "-c", shell_cmd])


def _shquote(s: str) -> str:
    """Minimal shell quoting (single-quote wrap, escape embedded single quotes)."""
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


class Dev(PlatformCliGroup):
    def create(self, cli: click.Group):
        @cli.group(help="Tools for local package development against product containers")
        def dev():
            pass

        @dev.command(name="mount")
        @click.argument("product", type=ProductType())
        @click.option(
            "--service",
            default=None,
            type=str,
            help="Target container service name (defaults to the product's primary service)",
        )
        @click.argument("packages", nargs=-1)
        @click.option(
            "--repo",
            default=".",
            type=click.Path(exists=True, file_okay=False),
            help="Path to local repo to mount (default: cwd)",
        )
        @click.option(
            "--product-repo",
            default=None,
            type=str,
            help="Explicit path to the product repository",
        )
        def mount(
            product: str,
            service: Optional[str],
            packages: Tuple[str, ...],
            repo: str,
            product_repo: Optional[str],
        ):
            """Mount a local repo into a product container for development."""
            product_config = PRODUCTS[product]
            if service is None:
                service = product_config["default_service"]
            valid_services = list(product_config["services"].keys())
            if service not in valid_services:
                raise click.ClickException(
                    f"Invalid service '{service}' for {product}. "
                    f"Valid services: {', '.join(valid_services)}"
                )

            repo_path = Path(repo).resolve()
            product_repo_path = find_product_repo(product, product_repo)
            overlay_path = product_repo_path / product_config["compose_dir"] / OVERLAY_FILENAME

            overlay = read_overlay(overlay_path)
            add_mount_to_overlay(
                overlay,
                service_name=service,
                service_config=product_config["services"][service],
                host_path=repo_path,
                packages=list(packages),
                token_host_path=product_repo_path / SECRETS_TOKEN_RELATIVE,
            )
            write_overlay(overlay_path, overlay)

            click.echo(click.style(f"[+] Mounted {repo_path.name} into {service}", fg="green"))
            for pkg in packages:
                click.echo(f"  - {pkg}")
            click.echo(
                click.style(
                    f"\nOverlay: {overlay_path}\n"
                    f"Run '{product} down && {product} up' to apply.",
                    fg="yellow",
                )
            )

        @dev.command(name="unmount")
        @click.argument("product", type=ProductType())
        @click.option(
            "--product-repo",
            default=None,
            type=str,
            help="Explicit path to the product repository",
        )
        def unmount(product: str, product_repo: Optional[str]):
            """Remove all local dev mounts for a product."""
            product_config = PRODUCTS[product]
            product_repo_path = find_product_repo(product, product_repo)
            overlay_path = product_repo_path / product_config["compose_dir"] / OVERLAY_FILENAME

            if not overlay_path.exists():
                click.echo(
                    click.style(f"No local dev mounts configured for {product}.", fg="yellow")
                )
                return

            overlay_path.unlink()
            click.echo(click.style(f"[+] Removed local dev mounts for {product}.", fg="green"))
            click.echo(
                click.style(
                    f"Run '{product} down && {product} up' to apply.",
                    fg="yellow",
                )
            )

        @dev.command(name="status")
        @click.argument("product", type=ProductType())
        @click.option(
            "--product-repo",
            default=None,
            type=str,
            help="Explicit path to the product repository",
        )
        def status(product: str, product_repo: Optional[str]):
            """Show current local dev mounts for a product."""
            product_config = PRODUCTS[product]
            product_repo_path = find_product_repo(product, product_repo)
            overlay_path = product_repo_path / product_config["compose_dir"] / OVERLAY_FILENAME

            overlay = read_overlay(overlay_path)
            services = overlay.get("services", {})
            if not services:
                click.echo(
                    click.style(f"No local dev mounts configured for {product}.", fg="yellow")
                )
                return

            for svc_name, svc_data in services.items():
                mounts = _service_mounts(svc_data)
                volumes = svc_data.get("volumes", []) or []
                host_by_container = {}
                for vol in volumes:
                    if ":" in vol:
                        host, container = vol.split(":", 1)
                        host_by_container[container] = host
                click.echo(click.style(f"{svc_name}:", fg="green", bold=True))
                for container_path, pkgs in mounts:
                    host = host_by_container.get(container_path, container_path)
                    click.echo(f"  {host} -> {', '.join(pkgs) if pkgs else '(all packages)'}")

        @dev.command(name="_run", hidden=True, context_settings={"ignore_unknown_options": True})
        @click.argument("passthrough", nargs=-1, type=click.UNPROCESSED)
        def _run(passthrough: Tuple[str, ...]):
            """Internal: container-side entrypoint. Builds mounts, sources overlay, execs cmd."""
            _run_local_dev(list(passthrough))
