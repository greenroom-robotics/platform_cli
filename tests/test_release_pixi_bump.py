"""Standalone checks for the pixi.toml bump + commit wiring in release.py.

Run: python tests/test_release_pixi_bump.py   (or pytest if available)
"""
from pathlib import Path
import tempfile

from platform_cli.groups.release import set_pixi_version, get_releaserc


def test_set_pixi_version_bumps_package_table_preserving_comments():
    body = (
        "[workspace]\n"
        'name = "foo"\n'
        'version = "0.0.0"\n'
        "[package]\n"
        'name = "foo"\n'
        "# keep me\n"
        'version = "1.0.0"\n'
    )
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "pixi.toml"
        p.write_text(body)
        set_pixi_version(p, "1.2.3")
        out = p.read_text()
        assert 'version = "1.2.3"' in out
        assert "# keep me" in out
        # workspace.version untouched
        assert 'version = "0.0.0"' in out


def test_get_releaserc_commits_pixi_toml_with_changelog():
    rc = get_releaserc(changelog=True)
    git = [p for p in rc["plugins"] if p[0] == "@semantic-release/git"]
    assert git, "git plugin must be present"
    assets = git[0][1]["assets"]
    assert "pixi.toml" in assets
    assert "CHANGELOG.md" in assets


def test_get_releaserc_commits_pixi_toml_without_changelog():
    rc = get_releaserc(changelog=False)
    git = [p for p in rc["plugins"] if p[0] == "@semantic-release/git"]
    assert git, "git plugin must run even without changelog (to commit pixi.toml)"
    assets = git[0][1]["assets"]
    assert "pixi.toml" in assets
    assert "CHANGELOG.md" not in assets


if __name__ == "__main__":
    test_set_pixi_version_bumps_package_table_preserving_comments()
    test_get_releaserc_commits_pixi_toml_with_changelog()
    test_get_releaserc_commits_pixi_toml_without_changelog()
    print("OK")
