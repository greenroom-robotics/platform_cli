import click
import shutil
import platform
import tempfile

from glob import glob
import os
from typing import List, Optional, Dict, Iterable, Any, Union
from enum import Enum
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from dataclasses import dataclass
from python_on_whales import docker
from python_on_whales.components.buildx.imagetools.models import Manifest

from platform_cli.groups.base import PlatformCliGroup
from platform_cli.helpers import echo, call, LogLevels

from platform_cli.groups.packaging import apt_clone, apt_push, apt_add

DEBS_DIRECTORY = "debs"
DOCKER_REGISTRY = "localhost:5000"


class ReleaseMode(Enum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"


class Architecture(str, Enum):
    amd64 = "amd64"
    arm64 = "arm64"


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


def get_current_system_architecture() -> Architecture:
    """
    Returns the current system architecture mapped to our Architecture enum.
    """
    machine = platform.machine()
    if machine in ("x86_64", "AMD64"):
        return Architecture.amd64
    elif machine in ("aarch64", "arm64"):
        return Architecture.arm64
    else:
        # Default to amd64 for unknown architectures
        return Architecture.amd64


def should_build_with_qemu(target_architectures: List[Architecture]) -> bool:
    """
    Determines if we need to use QEMU for cross-platform emulation.
    Returns True if we need QEMU (cross-platform or multiple architectures),
    False if we can build natively (single native architecture).
    Note: We still use buildx in both cases for secrets support.
    """
    if len(target_architectures) == 0:
        return False

    if len(target_architectures) > 1:
        return True

    current_arch = get_current_system_architecture()
    return target_architectures[0] != current_arch


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

    def _write_docker_file(self, asset_dir: Path, dest_dir: Path, release_mode: ReleaseMode):
        """
        Writes the dockerfile to the destination directory
        Select the "single" or "multi" dockerfile based on the release mode
        """
        dockerfile = (
            asset_dir / "Dockerfile.single"
            if release_mode == ReleaseMode.SINGLE
            else asset_dir / "Dockerfile.multi"
        )
        dest = dest_dir / "Dockerfile"
        shutil.copyfile(dockerfile, dest)

    def _write_package_json(self, dest: Path, package_name: str):
        package_json = {
            "name": package_name,
            "version": "0.0.0",
            "license": "UNLICENSED",
        }
        echo(f"Writing {dest}", "blue")
        with open(dest, "w") as f:
            json.dump(package_json, f, indent=4)

    def _write_docker_ignore(self):
        """Write a .dockerignore which ignores node_modules"""
        dest = Path.cwd() / ".dockerignore"
        # If the .dockerignore already exists, check to see if it already ignores node_modules
        if dest.exists():
            with open(dest) as f:
                if "node_modules" in f.read():
                    # It already ignores node_modules, so return
                    return
                # If it doesn't ignore node_modules, append it
                with open(dest, "a") as f:
                    f.write("node_modules")
                return
        # If there is no .dockerignore, create one
        with open(dest, "w") as f:
            f.write("node_modules")
            return

    def _get_release_mode(self) -> ReleaseMode:
        """Returns the release mode for the current working directory"""
        package_xml_path = Path.cwd() / "package.xml"
        if package_xml_path.exists():
            return ReleaseMode.SINGLE
        return ReleaseMode.MULTI

    def _get_docker_image_name(self, platform_module_name: str, use_registry: bool = False) -> str:
        """Returns the docker image name for a package"""
        # Note, uppercase is not allowed in docker image names
        image_name = f"{platform_module_name.lower()}:latest"
        if use_registry:
            return f"{DOCKER_REGISTRY}/{image_name}"
        else:
            return image_name

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

    def _get_docker_image_name_with_digest(
        self, image_name: str, image_manifests: Optional[Manifest], architecture: Architecture
    ) -> str:
        """Returns the digest for a docker image given an architecture"""
        if image_manifests is None or image_manifests.manifests is None:
            # If there are no manifests (native build), then there is only one image so we don't need the digest
            return image_name

        # Find the image for the platform and archicture
        image_for_docker_platform = next(
            manifest
            for manifest in image_manifests.manifests
            if manifest.platform and manifest.platform.architecture == architecture.value
        )

        return f"{image_name}@{image_for_docker_platform.digest}"

    def _build_deb_in_docker(
        self,
        version: str,
        package_info: PackageInfo,
        docker_image_name: str,
        architecture: Architecture,
        image_manifests: Optional[Manifest],
    ):
        """
        Runs the build command in a docker container
        The volume is mounted so we have access to the created deb file
        """
        echo(
            f"Building {package_info.package_name} .deb for {architecture.value}",
        )
        docker_image_name_with_digest = self._get_docker_image_name_with_digest(
            docker_image_name, image_manifests, architecture
        )

        docker_plaform = f"linux/{architecture.value}"

        if not package_info.module_info:
            raise Exception("Module info is required to build debs")

        package_relative_to_platform_module = package_info.package_path.relative_to(
            package_info.module_info.platform_module_path
        )
        host_debs_path = package_info.package_path / DEBS_DIRECTORY
        docker_working_dir = (
            Path("/home/ros/")
            / package_info.module_info.platform_module_name
            / package_relative_to_platform_module
        )
        docker_debs_path = docker_working_dir / DEBS_DIRECTORY

        # Make the .debs directory on the host, otherwise docker will make it with root permissions!
        host_debs_path.mkdir(exist_ok=True)
        # Make the .debs directory writable by all users
        os.chmod(host_debs_path, 0o777)

        docker.run(
            docker_image_name_with_digest,
            [
                "/bin/bash",
                "-l",
                "-c",
                f"platform pkg build --version {version} --output {DEBS_DIRECTORY} && platform pkg clean",
            ],
            workdir=docker_working_dir,
            volumes=[
                # We only mount the /debs directory for each package
                (host_debs_path, docker_debs_path)
            ],
            platform=docker_plaform,
            tty=True,
        )

    def _setup_qemu(self):
        """Install qemu binfmt support for other architectures"""
        echo("Setting up QEMU...")
        try:
            docker.run(
                "multiarch/qemu-user-static",
                ["--reset", "-p", "yes", "--credential", "yes"],
                privileged=True,
                remove=True,
            )
        except Exception as e:
            # docker on ZFS causes this to error and there is no known fix
            echo(f"QEMU already running: {e}", "yellow")
            pass

    def _setup_local_registry(self):
        """Start a local docker registry on port 5000"""
        echo("Setting up local docker registry...")
        try:
            docker.run(
                "registry:2",
                publish=[(5000, 5000)],
                detach=True,
                name="registry",
                remove=True,
            )
        except Exception as e:
            echo(f"Local registry already running: {e}", "yellow")

    def _setup_buildx_environment(self):
        """Configure buildx environment"""
        # Custom builder needed for local registry access (cross-platform builds)
        try:
            docker.buildx.create(
                name="platform",
                driver="docker-container",
                use=True,
                driver_options={"network": "host"},
            )
            echo("Created custom buildx builder for registry access", "blue")
        except Exception:
            echo("Custom buildx builder already exists", "yellow")
            echo(
                "Consider running `docker buildx rm platform` if you want to reset the build environment",
                "yellow",
            )
        docker.buildx.use("platform")

    def _parse_secrets_for_buildx(self, secrets: str) -> List[str]:
        """Parse secrets JSON and prepare buildx secrets format"""
        buildx_secrets = []
        try:
            secrets_dict = json.loads(secrets)
            for secret_id, secret_path in secrets_dict.items():
                buildx_secrets.append(f"id={secret_id},src={secret_path}")
        except json.JSONDecodeError:
            if secrets != "{}":
                echo(f"Warning: Invalid secrets JSON format: {secrets}", "yellow")

        return buildx_secrets

    def _build_docker_image_with_buildx(
        self,
        package_info: PackageInfo,
        docker_image_name: str,
        buildx_secrets: List[str],
        package_dir: str,
        ros_distro: str,
        package: str,
        docker_platforms: Optional[List[str]] = None,
        use_registry: bool = False,
    ) -> Optional[Manifest]:
        """Build docker image using buildx with unified logic for both native and multiplatform builds"""
        if not package_info.module_info:
            raise Exception("Module info is required to build docker images")

        # Dynamic echo message based on build type
        if docker_platforms:
            echo("Building docker container with buildx...", group_start=True)
        else:
            echo(
                f"Building docker container for native architecture ({get_current_system_architecture().value}) with buildx...",
                group_start=True,
            )

        # Prepare build argument
        build_kwargs = {
            "tags": [docker_image_name],
            "secrets": buildx_secrets,
            "build_args": {
                "API_TOKEN_GITHUB": os.environ["API_TOKEN_GITHUB"],
                "GPU": os.environ["GPU"],
                "PLATFORM_MODULE": package_info.module_info.platform_module_name,
                "PACKAGE_DIR": package_dir,
                "ROS_DISTRO": ros_distro,
                "PACKAGE_NAME": package,
            },
        }

        # Add platform-specific options
        if docker_platforms:
            build_kwargs["platforms"] = docker_platforms

        if use_registry:
            build_kwargs["output"] = {"type": "registry"}
        else:
            build_kwargs["load"] = True

        # Build the image - context path is first positional argument
        docker.buildx.build(package_info.module_info.platform_module_path, **build_kwargs)
        echo(group_end=True)

        # Return manifest for registry builds, None for local builds
        if use_registry:
            return docker.buildx.imagetools.inspect(docker_image_name)
        else:
            return None

    def _build_all_architecture_debs(
        self,
        arch: List[Architecture],
        version: str,
        package_info: PackageInfo,
        docker_image_name: str,
        image_manifests: Optional[Manifest],
    ):
        """Build .deb files for all target architectures"""
        for architecture in arch:
            echo(
                f"Building .deb for package {package_info.package_name} for {architecture.value}",
                "blue",
                group_start=True,
            )
            try:
                self._build_deb_in_docker(
                    version=version if version else package_info.package_version,
                    package_info=package_info,
                    docker_image_name=docker_image_name,
                    architecture=architecture,
                    image_manifests=image_manifests,
                )
            except Exception as e:
                echo(
                    f"Failed to build .deb for {architecture}",
                    "red",
                    level=LogLevels.ERROR,
                )
                raise e
            echo(group_end=True)

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

                recipes_yaml = recipes_root / "rosdistro_additional_recipes.yaml"
                for pkg in targets:
                    conda_name = f"ros-{ros_distro}-{pkg}"
                    upsert_recipe_entry(recipes_yaml, conda_name, src_url, tag, version)

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
