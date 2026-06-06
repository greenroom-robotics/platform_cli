import click

from typing import List
from platform_cli.groups.base import PlatformCliGroup
from platform_cli.groups.ros import Ros
from platform_cli.groups.ws import Workspace
from platform_cli.groups.poetry import Poetry
from platform_cli.groups.packaging import Packaging
from platform_cli.groups.release import Release
from platform_cli.groups.py import Py
from platform_cli.groups.dev import Dev


base_groups: List[PlatformCliGroup] = [
    Ros(),
    Poetry(),
    Packaging(),
    Release(),
    Py(),
    Workspace(),
    Dev(),
]

help = f"""
{click.style('Greenroom Platform CLI', bg='green', fg='black', bold=True)}

{click.style('A CLI for common scripts shared between Greenroom platform modules and platform CI.', fg='green', bold=True)}"""


def init_platform_cli(help: str = help, extra_groups: List[PlatformCliGroup] = []):
    """
    This will initialise the platform_cli.
    A list of PlatformCliGroups can be passed in, these will also be initialised as cli_groups

    Example:

    class SomeOtherGroup(PlatformCliGroup):
        def create(cli: click.group):
            @cli.group(help="Help for some other CLI group")
            def some_other_group():
                pass

            @poetry.command(name="example")
            def example():
                pass

    init_platform_cli(extra_groups=[SomeOtherGroup()])
    """
    groups = [*base_groups, *extra_groups]

    @click.group(help=help)
    def cli():  # type: ignore
        pass

    # Create all the groups
    for group in groups:
        group.create(cli)

    cli()


if __name__ == "__main__":
    init_platform_cli()
