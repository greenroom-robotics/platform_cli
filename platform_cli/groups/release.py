import click
import shutil
import platform

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
    public: bool = False,
    arch: List[Architecture] = [],
    package: Optional[str] = None,
    package_dir: Optional[str] = None,
    ros_distro: Optional[str] = None,
    skip_build: bool = False,
    branches: Optional[List[str]] = None,
    secrets: str = "{}",
):
    """
    Returns the releaserc with the plugins configured according to the arguments
    """
    prepare_cmd_args = "--version=${nextRelease.version}"
    if package_dir:
        prepare_cmd_args += f" --package-dir={package_dir}"
    for a in arch:
        prepare_cmd_args += f" --arch={a.value}"
    if package:
        prepare_cmd_args += f" --package={package}"
    if ros_distro:
        prepare_cmd_args += f" --ros-distro={ros_distro}"
    if secrets != "{}":
        prepare_cmd_args += f" --secrets='{secrets}'"

    releaserc = {
        "branches": branches or ["main", "master", {"name": "alpha", "prerelease": True}],
        "plugins": [],
    }

    def add_plugin(plugin_name: str, plugin_config: Dict[str, Any]):
        releaserc["plugins"].append([plugin_name, plugin_config])  # type: ignore

    add_plugin("@semantic-release/commit-analyzer", {"preset": "conventionalcommits"})
    add_plugin("@semantic-release/release-notes-generator", {"preset": "conventionalcommits"})
    add_plugin("@semantic-release/changelog", {})
    if not skip_build:
        # Build legs (one per arch) build + publish the .deb. They run
        # concurrently and must NOT commit/push anything: a push here advances
        # the remote branch, leaving the central release job's checkout behind
        # remote ("a new version won't be published"). So no git plugin below.
        add_plugin(
            "@semantic-release/exec",
            {
                "prepareCmd": f"platform release deb-prepare {prepare_cmd_args}",
                "publishCmd": f"platform release deb-publish --public {public}",
            },
        )
    else:
        # Release job: no docker build here, so bump pixi.toml to the released
        # version directly. @semantic-release/git (below) commits it at the
        # tagged commit. This is the only place that writes back to the branch.
        bump_cmd_args = "--version=${nextRelease.version}"
        if package_dir:
            bump_cmd_args += f" --package-dir={package_dir}"
        if package:
            bump_cmd_args += f" --package={package}"
        add_plugin(
            "@semantic-release/exec",
            {"prepareCmd": f"platform release set-pixi-version {bump_cmd_args}"},
        )
    if github_release:
        add_plugin(
            "@semantic-release/github",
            {"assets": [{"path": "**/*.deb"}, {"path": "**/*.ddeb"}], "successComment": False},
        )
    # Commit the release artifacts ONLY from the release job (skip_build). Build
    # legs never push, or they desync the release job (see above). The release
    # job commits the bumped pixi.toml, plus CHANGELOG.md when requested.
    if skip_build:
        git_assets = ["pixi.toml"]
        if changelog:
            git_assets.append("CHANGELOG.md")
        add_plugin("@semantic-release/git", {"assets": git_assets})
    elif changelog:
        add_plugin("@semantic-release/git", {"assets": ["CHANGELOG.md"]})

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


def set_pixi_version(pixi_toml: Path, version: str) -> None:
    """Write `version` into the [package] table of a pixi.toml, preserving
    comments and formatting. No-op-safe; raises if there is no [package] table.
    """
    import tomlkit

    doc = tomlkit.parse(pixi_toml.read_text())
    pkg = doc.get("package")
    if pkg is None:
        raise Exception(f"{pixi_toml} has no [package] table")
    pkg["version"] = version
    pixi_toml.write_text(tomlkit.dumps(doc))


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

            self._write_docker_ignore()
            self._write_root_yarn_lock(asset_dir / "yarn.lock")
            self._write_package_jsons_for_each_package(packages.values())
            self._write_root_package_json(asset_dir / "package.json", packages.values())

            release_mode = self._get_release_mode()
            module_info = get_module_info()

            if not module_info:
                raise Exception("Could not find module info")

            # If a Dockerfile does not exist in the module root, create it
            docker_file_exists = (module_info.platform_module_path / "Dockerfile").exists()
            echo(f"Dockerfile exists: {docker_file_exists}", "blue")
            if not docker_file_exists:
                echo("Creating Dockerfile...", "blue")
                self._write_docker_file(asset_dir, module_info.platform_module_path, release_mode)

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
            "--public",
            type=bool,
            help="Should this package be published to the public PPA",
            default=False,
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
            "--arch",
            type=click.Choice(Architecture),  # type: ignore
            help="The architecture to build for. OS will be linux. eg) amd64, arm64",
            default=[Architecture.amd64, Architecture.arm64],
            multiple=True,
        )
        @click.option(
            "--ros-distro",
            type=str,
            help="The ROS2 distro to build for. eg) kilted",
            default="kilted",
        )
        @click.option(
            "--skip-tag",
            type=bool,
            help="Should semantic-release NOT tag the release",
            default=False,
        )
        @click.option(
            "--skip-build",
            type=bool,
            help="Should platform NOT build the packages",
            default=False,
        )
        @click.option(
            "--branches",
            type=str,
            help="The branches to release on. Defaults to: main,master,alpha",
        )
        @click.option(
            "--secrets",
            type=str,
            help='JSON string of secrets to pass to docker build (e.g. \'{"API_TOKEN_GITHUB": "./.secrets/github_token"}\')',
            default="{}",
        )
        @click.argument(
            "args",
            nargs=-1,
        )
        def create(changelog: bool, github_release: bool, public: bool, package: str, package_dir: str, arch: List[Architecture], ros_distro: str, skip_tag: bool, skip_build: bool, branches: str, secrets: str, args: List[str]):  # type: ignore
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
                # If package is specified, only build that package, otherwise build all packages (None)
                # This prevents us from building the docker image multiple times
                package_to_build = package_name if package else None
                releaserc = get_releaserc(
                    changelog,
                    github_release and not skip_tag,
                    public,
                    arch,
                    package_to_build,
                    package_dir,
                    ros_distro,
                    skip_build,
                    branches_split,
                    secrets,
                )
                with open(package_info.package_path / ".releaserc", "w+") as f:
                    f.write(json.dumps(releaserc, indent=4))

            # Run the correct release script in the package.json based off the release mode
            release_mode = self._get_release_mode()

            if release_mode == ReleaseMode.SINGLE:
                if len(arch) == 1:
                    args_str += " --tag-format='${version}'"
                echo(
                    "Release mode: SINGLE, running semantic-release for root package",
                    "blue",
                )
                call(f"yarn semantic-release {args_str}")
            else:
                if len(arch) == 1:
                    args_str += " --tag-format='${name}@${version}'"

                echo(
                    "Release mode: MULTI, running multi-semantic-release for root package",
                    "blue",
                )
                call(f"yarn multi-semantic-release {args_str}")

        @release.command(name="set-pixi-version")
        @click.option(
            "--version",
            type=str,
            help="The version to write into the package's pixi.toml [package] table",
            required=True,
        )
        @click.option(
            "--package",
            type=str,
            help="Which package's pixi.toml to bump. If not specified, the package in the current directory is used",
            default="",
        )
        @click.option(
            "--package-dir",
            type=str,
            help="The directory to release packages from. If not set, the root of the repo will be used",
            default="./",
        )
        def set_pixi_version_cmd(version: str, package: str, package_dir: str):  # type: ignore
            """Bumps a package's pixi.toml version so the release commit carries it.

            Runs in the central release job (no docker build); @semantic-release/git
            then commits the bumped pixi.toml at the tagged commit.
            """
            # Resolve the package the same way deb-prepare does.
            if package:
                package_info = find_packages()[package]
            else:
                package_info = get_package_info()

            pixi_toml = package_info.package_path / "pixi.toml"
            if pixi_toml.exists():
                set_pixi_version(pixi_toml, version)
                echo(f"Bumped {pixi_toml} to {version}", "green")
            else:
                echo(f"No pixi.toml at {pixi_toml}; nothing to bump", "yellow")

        @release.command(name="deb-prepare")
        @click.option(
            "--version",
            type=str,
            help="The version number to assign to the debian",
            required=False,
            default="",
        )
        @click.option(
            "--arch",
            type=click.Choice(Architecture),  # type: ignore
            help="The architecture to build for. OS will be linux. eg) amd64, arm64",
            default=[Architecture.amd64, Architecture.arm64],
            multiple=True,
        )
        @click.option(
            "--package",
            type=str,
            help="Which package should we build. If not specified, all packages will be built",
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
            "--secrets",
            type=str,
            help='JSON string of secrets to pass to docker build (e.g. \'{"API_TOKEN_GITHUB": "./.secrets/github_token"}\')',
            default="{}",
        )
        def deb_prepare(version: str, arch: List[Architecture], package: str, package_dir: str, ros_distro: str, secrets: str):  # type: ignore
            """Prepares the release by building the debian package inside a docker container"""
            docker_platforms = [f"linux/{a.value}" for a in arch]
            echo(
                f"Preparing to build .deb for {[a.value for a in arch]}", "blue", group_start=True
            )

            if "API_TOKEN_GITHUB" not in os.environ:
                raise Exception("API_TOKEN_GITHUB must be set")

            # Resolve path of package
            if package:
                packages = find_packages()
                package_info = packages[package]
            else:
                package_info = get_package_info()

            if not package_info.module_info:
                raise Exception("Module info is required to build debs")

            # Determine if we need to use QEMU for cross-platform emulation
            needs_qemu = should_build_with_qemu(arch)

            docker_image_name = self._get_docker_image_name(
                package_info.module_info.platform_module_name, use_registry=needs_qemu
            )

            # Setup cross-platform emulation if needed
            if needs_qemu:
                self._setup_qemu()
                self._setup_local_registry()
                self._setup_buildx_environment()

            echo(group_end=True)

            buildx_secrets = self._parse_secrets_for_buildx(secrets)

            # Build docker image with appropriate strategy
            image_manifests = self._build_docker_image_with_buildx(
                package_info,
                docker_image_name,
                buildx_secrets,
                package_dir,
                ros_distro,
                package,
                docker_platforms=docker_platforms if needs_qemu else None,
                use_registry=needs_qemu,
            )

            # Build .deb files for all architectures
            self._build_all_architecture_debs(
                arch, version, package_info, docker_image_name, image_manifests
            )

        @release.command(name="deb-publish")
        @click.option(
            "--public",
            type=bool,
            help="Should this package be published to the public PPA",
            default=False,
        )
        def deb_publish(public: bool):  # type: ignore
            """Publishes the deb to the apt repo"""
            try:
                echo("Publishing .deb to apt repo...")
                apt_clone(public)

                debs_folder = Path.cwd() / DEBS_DIRECTORY

                apt_add(debs_folder)
                apt_push()
            except Exception as e:
                echo("Failed to publish .deb", "red", level=LogLevels.ERROR)
                raise e
