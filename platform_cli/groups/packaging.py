from pathlib import Path
from typing import List, Dict, Optional
import click
from psutil import cpu_count
import shutil
import os
import math

from platform_cli.groups.base import PlatformCliGroup
from platform_cli.helpers import call, stdout_call, echo

GR_APT_REPO_PRIVATE = "Greenroom-Robotics/packages"
GR_APT_REPO_PUBLIC = "Greenroom-Robotics/public_packages"
GR_APT_REPO_PATH = Path.home() / ".gr/gr-packages"


def get_ros_distro():
    return os.environ["ROS_DISTRO"]


def get_debs(p: Path, debug_files: bool = False) -> List[Path]:
    return list(p.glob("*.deb")) + (list(p.glob("*.ddeb")) if debug_files else [])


def find_packages_with_colcon(p: Path) -> Dict[str, Path]:
    """Use colcon to find all packages in a workspace"""

    # TODO: use colcon python API instead of shelling out
    lines = stdout_call("colcon --log-base=/dev/null list", cwd=p)
    packages = {}
    for line in lines.splitlines():
        # Line example:
        # can_idl_generator       can_idl_generator       (ros.ament_cmake)
        name, path, builder = line.split("\t")
        if "node_modules" in path:
            # Always ignore packages inside node_modules
            continue
        packages[name] = p / path

    return packages


def parse_version(version: str):
    # version should be of the form "1.2.3" or "1.2.3-alpha.1"
    version_split = version.split("-")
    version_semver = version_split[0]
    version_prerelease = version_split[1] if len(version_split) == 2 else ""
    if len(version_semver.split(".")) != 3:
        raise ValueError("Version should be of the form 1.2.3 or 1.2.3-alpha1")

    return version_semver, version_prerelease


def get_apt_repo_url(public: bool = False) -> str:
    """If we have API_TOKEN_GITHUB, use https, otherwise use ssh"""
    packages_repo = GR_APT_REPO_PUBLIC if public else GR_APT_REPO_PRIVATE

    if "API_TOKEN_GITHUB" in os.environ:
        return f"https://x-access-token:{os.environ['API_TOKEN_GITHUB']}@github.com/{packages_repo}.git"

    return f"git@github.com:{packages_repo}.git"


def apt_clone(public: bool = False, sparse: bool = False):
    """Checks out the GR apt repo"""
    if GR_APT_REPO_PATH.is_dir():
        echo(f"Packages repo has already been cloned to {GR_APT_REPO_PATH}", "blue")
        return

    github_repo_url = get_apt_repo_url(public)
    try:
        clone_command = "git clone --filter=blob:none --depth=1"
        if sparse:
            clone_command += " --sparse"
        call(f"{clone_command} {github_repo_url} {GR_APT_REPO_PATH}")
    except Exception as e:
        raise click.ClickException(f"Error cloning apt repo: {e}")


def apt_push():
    """Pushes to the GR apt repo"""
    attempt = 0
    while True:
        call("git fetch", cwd=GR_APT_REPO_PATH)
        call("git rebase -Xtheirs origin/main", cwd=GR_APT_REPO_PATH)
        ret = call("git push", cwd=GR_APT_REPO_PATH, abort=False)

        if ret.returncode == 0:
            break

        attempt += 1

        if attempt > 4:
            raise click.ClickException("Failed to push to apt repo")


def apt_add(deb: Optional[Path] = None, sparse: bool = False):
    """Adds a .deb to the GR apt repo"""

    if not GR_APT_REPO_PATH.exists():
        raise click.ClickException("GR apt repo has not been cloned.")

    if deb:
        if deb.is_dir():
            debs = get_debs(deb, debug_files=False)
        else:
            debs = [deb]
    else:
        debs = get_debs(Path.cwd(), debug_files=False)

    if not debs:
        raise click.ClickException("No debs found.")
    for d in debs:
        echo(f"Copying {d} info {GR_APT_REPO_PATH / 'debian'}", "blue")
        shutil.copy(d, GR_APT_REPO_PATH / "debian")
        add_command = "git add"
        if sparse:
            add_command += " --sparse"
        call(f"{add_command} debian/{d.name}", cwd=GR_APT_REPO_PATH)

    call(
        f"git commit -a -m 'feat: add debian package: {' '.join(d.name for d in debs)}'",
        cwd=GR_APT_REPO_PATH,
    )


class Packaging(PlatformCliGroup):
    def create(self, cli: click.Group):
        @cli.group(help="Packaging commands")
        def pkg():
            pass

        @pkg.command(name="setup")
        @click.option(
            "--auth",
            type=bool,
            default=True,
            help="If true, will setup the apt auth file",
        )
        def setup(auth: bool):  # type: ignore reportUnusedFunction
            """Sets up the greenroom apt and rosdep lists"""
            if not os.environ.get("API_TOKEN_GITHUB"):
                raise click.ClickException(
                    "API_TOKEN_GITHUB environment variable not set. "
                    "Please set this to a github personal access token with the 'repo' and 'package:read' scope."
                )

            call(
                f"curl -s https://{os.environ['API_TOKEN_GITHUB']}@raw.githubusercontent.com/Greenroom-Robotics/rosdistro/main/scripts/setup-rosdep.sh | bash -s"
            )
            call(
                f"curl -s https://{os.environ['API_TOKEN_GITHUB']}@raw.githubusercontent.com/Greenroom-Robotics/packages/main/scripts/setup-apt-list.sh | bash -s"
            )
            if auth:
                call(
                    f"curl -s https://{os.environ['API_TOKEN_GITHUB']}@raw.githubusercontent.com/Greenroom-Robotics/packages/main/scripts/setup-apt-auth.sh | bash -s"
                )
            call(
                "curl -s https://raw.githubusercontent.com/Greenroom-Robotics/public_packages/main/scripts/setup-apt.sh | bash -s"
            )
            call("rosdep init", sudo=True, abort=False)

        @pkg.command(name="clean")
        def clean():  # type: ignore reportUnusedFunction
            """Removes debians and log directories"""
            dirs = [".obj-x86_64-linux-gnu", ".obj-aarch64-linux-gnu", "debian", "log"]

            for d in dirs:
                p = Path(d)
                if p.is_dir():
                    shutil.rmtree(p)

        @pkg.command(name="refresh-deps")
        @click.option(
            "--no-apt-update",
            is_flag=True,
            default=False,
            help="Skip `sudo apt-get update` (still runs rosdep update)",
        )
        def refresh_deps(no_apt_update: bool):
            """Refresh rosdeps"""
            if not no_apt_update:
                call("sudo apt-get update")
            distro = get_ros_distro()
            if distro == "iron":
                distro = "iron --include-eol-distros"
            call(f"rosdep update --rosdistro {distro}")

        @pkg.command(name="install-deps")
        @click.option(
            "--package",
            type=str,
            help="The package to install deps for (defaults to all)",
            default=None,
        )
        @click.option(
            "--no-apt-update",
            is_flag=True,
            default=False,
            help="Skip `sudo apt-get update` when refreshing rosdeps",
        )
        def install_deps(package: str, no_apt_update: bool):
            """Installs rosdeps"""
            package_dir = Path.cwd()
            packages = find_packages_with_colcon(package_dir)
            if package and package not in packages:
                raise click.ClickException(f"Package '{package}' not found in workspace")

            # If we find a package with that name, only install the deps for that package
            from_paths = packages[package] if package else package_dir
            refresh_deps.callback(no_apt_update=no_apt_update)  # type: ignore
            distro = get_ros_distro()
            if distro == "iron":
                distro = "iron --include-eol-distros"

            call(f"rosdep install -y --rosdistro {distro} --from-paths {from_paths} -i")

        @pkg.command(name="get-sources")
        def get_sources():  # type: ignore reportUnusedFunction
            """Imports items from the .repo file"""
            if Path(".repos").is_file():
                call("vcs import --recursive < .repos")
            else:
                raise click.ClickException("No '.repos' file found. Unsure how to obtain sources.")

        @pkg.command(name="build")
        @click.option("--version", type=str, help="The version to call the debian", default=None)
        @click.option(
            "--output",
            type=str,
            default="debs",
            help="The output directory for the debs",
        )
        @click.option("--no-tests", type=bool, is_flag=True, default=True)
        def build(version: str, output: str, no_tests: bool):  # type: ignore reportUnusedFunction
            """Builds the package using bloom"""

            pkg_name = Path.cwd().name
            pkg_type = "rosdebian"
            src_dir = Path("src")
            bloom_args = ""

            if version is not None:
                version_semver, version_prerelease = parse_version(version)
                echo(f"Updating package.xml version to {version_semver}", "blue")
                # This will replace anything between the <version></version> tags in the package.xml
                call(
                    f'sed -i ":a;N;\\$!ba; s|<version>.*<\\/version>|<version>{version_semver}<\\/version>|g" package.xml'
                )

                if version_prerelease:
                    bloom_args += f'-i "{version_prerelease}"'

            # need to make this more generic
            if src_dir.is_dir():
                pkgs = find_packages_with_colcon(src_dir)
                if pkgs and pkg_name in pkgs:
                    bloom_args += f" --src-dir={pkgs[pkg_name]}"

            deb_build_opts = []

            if no_tests:
                bloom_args += " --no-tests"
                deb_build_opts.append("nocheck")

            # this is the equivalent of turning off type safety for compiled libraries.
            # TODO rework the build process to build deps debs first if required, then install debs then build pkgs
            bloom_args += " --ignore-shlibs-missing-info"

            call(f"bloom-generate {pkg_type} --ros-distro {get_ros_distro()} {bloom_args}")

            jobs = cpu_count() or 1

            deb_build_opts.append(f"parallel={jobs}")
            deb_env = {"DEB_BUILD_OPTIONS": " ".join(deb_build_opts)} if deb_build_opts else {}

            call("fakeroot debian/rules binary", env=deb_env)

            # the .deb and .ddeb files are in the parent directory
            # move .deb/.ddeb files into the output folder
            Path(output).mkdir(parents=True, exist_ok=True)
            debs = get_debs(Path.cwd().parent, debug_files=True)
            echo(f"Moving {len(debs)} .deb / .ddeb files to {output}", "blue")
            if debs:
                for d in debs:
                    try:
                        shutil.move(str(d), output)
                    except Exception as e:
                        raise click.ClickException(
                            f"Error moving .deb. You may need to chown the output folder: {e}"
                        )

            else:
                raise click.ClickException("No debs found.")

            echo("Build complete", "green")

        @pkg.command(name="apt-clone")
        @click.option(
            "--public",
            type=bool,
            help="Should this package be published to the public PPA",
            default=False,
        )
        @click.option(
            "--sparse",
            type=bool,
            help="Should we do a sparse checkout of the apt repo",
            default=False,
            flag_value=True,
        )
        def apt_clone(public: bool, sparse: bool):  # type: ignore reportUnusedFunction
            apt_clone(public, sparse)

        @pkg.command(name="apt-push")
        def apt_push():  # type: ignore reportUnusedFunction
            apt_push()

        @pkg.command(name="apt-update")
        def apt_update():  # type: ignore reportUnusedFunction
            """Update the GR apt repo"""
            if not GR_APT_REPO_PATH.exists():
                raise click.ClickException("GR apt repo has not been cloned.")
            call("git pull --rebase", cwd=GR_APT_REPO_PATH)

        @pkg.command(name="apt-add")
        @click.option(
            "--sparse",
            type=bool,
            help="Should we do a sparse add to the apt repo",
            default=False,
            flag_value=True,
        )
        @click.argument("deb", type=click.Path(exists=True), required=False)
        def apt_add(sparse: bool, deb: str):  # type: ignore reportUnusedFunction
            """Adds a .deb to the GR apt repo"""
            apt_add(deb, sparse)
