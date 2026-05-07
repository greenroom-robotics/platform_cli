import click
import tempfile

from glob import glob
import os
from typing import List, Optional, Dict, Iterable, Any
from enum import Enum
from pathlib import Path
import xml.etree.ElementTree as ET
import json
import shutil
from dataclasses import dataclass

from platform_cli.groups.base import PlatformCliGroup
from platform_cli.helpers import echo, call


class ReleaseMode(Enum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


@dataclass
class ModuleInfo:
    platform_module_path: Path
    platform_module_name: str


@dataclass
class PackageInfo:
    package_path: Path
    package_name: str
    package_version: str
    module_info: Optional[ModuleInfo]


def check_parents_for_file(filename: str, path: Optional[Path] = None) -> Path:
    """Checks each parent directory for a file"""
    current_path = path if path else Path.cwd()

    while current_path.exists():
        file_path = current_path / filename
        if file_path.exists():
            return file_path.parent

        if current_path == current_path.parent:
            break
        else:
            current_path = current_path.parent

    raise Exception(f"Could not find {filename} in any parent directory")


def get_module_info(path: Optional[Path] = None) -> Optional[ModuleInfo]:
    """
    Returns the module info for the directory (or CWD).
    """

    try:
        platform_module_path = check_parents_for_file(".git", path)
        platform_module_name = platform_module_path.name

        return ModuleInfo(
            platform_module_path=platform_module_path,
            platform_module_name=platform_module_name,
        )
    except Exception:
        return None


def get_package_info(
    package_path: Optional[Path] = None, obtain_module_info: bool = True
) -> PackageInfo:
    """
    Returns the package info for the directory (or CWD if no path provided).
    This assumes the cwd is a package. It will find out the name of the platform module.

    File structure should be something like:
    platform_module/packages/package_name

    eg)
    platform_notifications/packages/notification_msgs
    """
    package_path = package_path if package_path else Path.cwd()

    return PackageInfo(
        package_path=package_path,
        package_name=get_package_name_from_package_xml(package_path / "package.xml"),
        package_version=get_package_version_from_package_xml(package_path / "package.xml"),
        module_info=get_module_info(package_path) if obtain_module_info else None,
    )


def get_releaserc(
    changelog: bool,
    github_release: bool = True,
    package: Optional[str] = None,
    package_dir: Optional[str] = None,
    ros_distro: Optional[str] = None,
    recipes_repo: str = "greenroom-robotics/ros-kilted-recipes",
    branches: Optional[List[str]] = None,
):
    """
    Returns the releaserc with the plugins configured for the conda flow.

    `publishCmd` opens a PR on the recipes repo upserting the package's pin.
    Build + channel publish happen on the recipes repo's CI; nothing is
    built or attached to the source repo's GH release.
    """
    publish_args = f"--recipes-repo={recipes_repo}"
    if package_dir:
        publish_args += f" --package-dir={package_dir}"
    if package:
        publish_args += f" --package={package}"
    if ros_distro:
        publish_args += f" --ros-distro={ros_distro}"

    releaserc = {
        "branches": branches or ["main", "master", {"name": "alpha", "prerelease": True}],
        "plugins": [],
    }

    def add_plugin(plugin_name: str, plugin_config: Dict[str, Any]):
        releaserc["plugins"].append([plugin_name, plugin_config])  # type: ignore

    add_plugin("@semantic-release/commit-analyzer", {"preset": "conventionalcommits"})
    add_plugin("@semantic-release/release-notes-generator", {"preset": "conventionalcommits"})
    add_plugin("@semantic-release/changelog", {})
    add_plugin(
        "@semantic-release/exec",
        {
            "publishCmd": (
                "platform release conda-publish "
                f"--version=${{nextRelease.version}} {publish_args}"
            ),
        },
    )
    if github_release:
        add_plugin(
            "@semantic-release/github",
            {"assets": [], "successComment": False},
        )
    if changelog:
        add_plugin(
            "@semantic-release/git",
            {"assets": ["CHANGELOG.md", "**/package.xml"]},
        )

    return releaserc


def get_package_name_from_package_xml(package_xml: Path) -> str:
    """
    Returns the package name from the package.xml
    """
    if not package_xml.exists():
        raise Exception(f"Could not find package.xml at {package_xml}")

    tree = ET.parse(package_xml)
    root = tree.getroot()
    return root.find("name").text  # type: ignore


def get_package_version_from_package_xml(package_xml: Path) -> str:
    """
    Returns the package version from the package.xml
    """
    tree = ET.parse(package_xml)
    root = tree.getroot()
    return root.find("version").text  # type: ignore


def find_packages(path: Optional[Path] = None, module_info: bool = True) -> Dict[str, PackageInfo]:
    """
    Finds all the packages in the given path
    """

    path = path if path else Path.cwd()

    # Path.glob does not seem to traverse into symlink directories
    package_xmls = [Path(p) for p in glob(f"{path}/**/package.xml", recursive=True)]

    packages = {}
    for package_xml in package_xmls:
        if package_xml.parent.parent.name == "share":
            # this package is inside an install directory, so ignore it
            continue
        package = get_package_info(package_xml.parent, module_info)
        packages[package.package_name] = package

    return packages


class Release(PlatformCliGroup):
    def _write_root_package_json(self, src: Path, packages: Iterable[PackageInfo]):
        """Writes the root package.json file"""
        dest = Path.cwd() / "package.json"
        with open(src) as f:
            package_json = json.load(f)

            # If there is a package.xml in the root directory, use that as the package name
            package_name = next(
                (
                    package_info.package_name
                    for package_info in packages
                    if package_info.package_path == Path.cwd()
                ),
                "platform_module",
            )
            package_json["name"] = package_name

            # The workspaces are the parent directories of the package.jsons
            package_json["workspaces"] = [
                str(package_info.package_path) for package_info in packages
            ]
            with open(dest, "w") as f:
                json.dump(package_json, f, indent=4)

    def _write_package_json(self, dest: Path, package_name: str):
        package_json = {
            "name": package_name,
            "version": "0.0.0",
            "license": "UNLICENSED",
        }
        echo(f"Writing {dest}", "blue")
        with open(dest, "w") as f:
            json.dump(package_json, f, indent=4)

    def _get_release_mode(self) -> ReleaseMode:
        """Returns the release mode for the current working directory"""
        package_xml_path = Path.cwd() / "package.xml"
        if package_xml_path.exists():
            return ReleaseMode.SINGLE
        return ReleaseMode.MULTI

    def _write_root_yarn_lock(self, src: Path):
        dest = Path.cwd() / "yarn.lock"
        shutil.copyfile(src, dest)

    def _get_package_name_from_package_xml(self, package_xml_path: Path) -> str:
        """Reads the name from a package.xml"""
        package_xml = ET.parse(package_xml_path)
        root = package_xml.getroot()
        package_name: str = root.find("name").text  # type: ignore
        return package_name

    def _write_package_jsons_for_each_package(self, packages: Iterable[PackageInfo]):
        """
        This will generate a fake package.json next to any package.xml.
        This is done as a hack so semantic-release can be used to release the package.
        """
        for package_info in packages:
            package_json_path = package_info.package_path / "package.json"
            if not package_json_path.exists():
                self._write_package_json(package_json_path, package_info.package_name)

    def create(self, cli: click.Group):
        @cli.group(help="CLI handlers associated releasing a platform module")
        def release():
            pass

        @release.command(name="setup")
        @click.option(
            "--package",
            type=str,
            help="The package to release. If not set, all packages in the 'package_dir' will be released.",
            default="",
        )
        @click.option(
            "--package-dir",
            type=str,
            help="The directory to release packages from. If not set, the root of the repo will be used",
            default="./",
        )
        def setup(package: str, package_dir: str):  # type: ignore
            """Copies the package.json and yarn.lock into the root of the project and installs the deps"""
            echo("Setting up release...", "blue")
            echo(
                "Copying package.json and yarn.lock to root and installing deps...",
                "blue",
            )
            asset_dir = Path(__file__).parent.parent / "assets"

            packages = find_packages(Path.cwd() / package_dir)

            # Make sure the package exists if it was specified
            if package and package not in packages:
                raise click.ClickException(f"Package {package} not found in workspace")

            # If a package is specified, only build that package
            if package:
                packages = {package: packages[package]}

            self._write_root_yarn_lock(asset_dir / "yarn.lock")
            self._write_package_jsons_for_each_package(packages.values())
            self._write_root_package_json(asset_dir / "package.json", packages.values())

            call("yarn install --frozen-lockfile")

        @release.command(name="create")
        @click.option(
            "--changelog",
            type=bool,
            help="Should we publish a CHANGELOG.md back to git",
            default=True,
        )
        @click.option(
            "--github-release",
            type=bool,
            help="Should we create a github release?",
            default=True,
        )
        @click.option(
            "--package",
            type=str,
            help="The package to release. If not set, all packages in the 'package_dir' will be released.",
            default="",
        )
        @click.option(
            "--package-dir",
            type=str,
            help="The directory to release packages from. If not set, the root of the repo will be used",
            default="./",
        )
        @click.option(
            "--ros-distro",
            type=str,
            help="The ROS2 distro to build for. eg) kilted",
            default="kilted",
        )
        @click.option(
            "--recipes-repo",
            type=str,
            help="The conda recipes repo to PR against",
            default="greenroom-robotics/ros-kilted-recipes",
        )
        @click.option(
            "--skip-tag",
            type=bool,
            help="Should semantic-release NOT tag the release",
            default=False,
        )
        @click.option(
            "--branches",
            type=str,
            help="The branches to release on. Defaults to: main,master,alpha",
        )
        @click.argument(
            "args",
            nargs=-1,
        )
        def create(changelog: bool, github_release: bool, package: str, package_dir: str, ros_distro: str, recipes_repo: str, skip_tag: bool, branches: str, args: List[str]):  # type: ignore
            """Creates a release of the platform module package. See .releaserc for more info"""
            args_str = " ".join(args)
            branches_split = branches.split(",") if branches else None
            if skip_tag:
                args_str += " --skip-tag"

            packages = find_packages(Path.cwd() / package_dir)

            # Make sure the package exists if it was specified
            if package and package not in packages:
                raise click.ClickException(f"Package {package} not found in workspace")

            # Create a releaserc for each package
            for package_name, package_info in packages.items():
                # If package is specified, only build that package, otherwise build all packages
                package_to_build = package_name if package else None
                releaserc = get_releaserc(
                    changelog=changelog,
                    github_release=github_release and not skip_tag,
                    package=package_to_build,
                    package_dir=package_dir,
                    ros_distro=ros_distro,
                    recipes_repo=recipes_repo,
                    branches=branches_split,
                )
                with open(package_info.package_path / ".releaserc", "w+") as f:
                    f.write(json.dumps(releaserc, indent=4))

            # Run the correct release script in the package.json based off the release mode
            release_mode = self._get_release_mode()

            if release_mode == ReleaseMode.SINGLE:
                args_str += " --tag-format='${version}'"
                echo(
                    "Release mode: SINGLE, running semantic-release for root package",
                    "blue",
                )
                call(f"yarn semantic-release {args_str}")
            else:
                args_str += " --tag-format='${name}@${version}'"
                echo(
                    "Release mode: MULTI, running multi-semantic-release for root package",
                    "blue",
                )
                call(f"yarn multi-semantic-release {args_str}")

        @release.command(name="conda-publish")
        @click.option(
            "--version",
            type=str,
            required=True,
            help="Release version (without leading 'v').",
        )
        @click.option(
            "--recipes-repo",
            type=str,
            default="greenroom-robotics/ros-kilted-recipes",
            show_default=True,
        )
        @click.option(
            "--package-dir",
            type=str,
            default="./",
            show_default=True,
        )
        @click.option(
            "--package",
            type=str,
            default="",
            help="Single package; default = all under package-dir.",
        )
        @click.option(
            "--ros-distro",
            type=str,
            default="kilted",
            show_default=True,
        )
        def conda_publish(  # type: ignore
            version: str,
            recipes_repo: str,
            package_dir: str,
            package: str,
            ros_distro: str,
        ):
            """Open/update a PR on the recipes repo upserting this release's pin(s)."""
            from platform_cli.groups.conda_channel import (
                clone_recipes_repo,
                get_source_repo_short_name,
                get_source_repo_url,
                open_or_update_pr,
                upsert_recipe_entry,
            )

            src_url = get_source_repo_url()
            src_short = get_source_repo_short_name()
            tag = f"v{version}"

            if package:
                targets = [package]
            else:
                targets = sorted(find_packages(Path.cwd() / package_dir).keys())

            if not targets:
                raise click.ClickException(f"No packages found under {package_dir}")

            with tempfile.TemporaryDirectory() as tmp:
                recipes_root = Path(tmp) / "recipes"
                clone_recipes_repo(recipes_repo, recipes_root)

                branch = f"release/{src_short}-v{version}"
                call(f"git checkout -b {branch}", cwd=recipes_root)

                # vinca prepends the `ros-<distro>-` prefix when generating
                # recipes, so the key here is the bare package name (matches
                # `<name>` in package.xml).
                recipes_yaml = recipes_root / "rosdistro_additional_recipes.yaml"
                for pkg in targets:
                    upsert_recipe_entry(recipes_yaml, pkg, src_url, tag, version)

                call("git add rosdistro_additional_recipes.yaml", cwd=recipes_root)
                call(
                    "git -c user.name=greenroom-bot "
                    "-c user.email=greenroom-bot@users.noreply.github.com "
                    f'commit -m "release: {src_short} {tag}"',
                    cwd=recipes_root,
                )

                open_or_update_pr(
                    repo=recipes_repo,
                    branch=branch,
                    title=f"release: {src_short} {tag}",
                    cwd=recipes_root,
                )
