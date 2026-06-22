"""Standalone checks for the pixi.toml bump + commit wiring in release.py.

Run: python tests/test_release_pixi_bump.py   (or pytest if available)

Key invariant: the per-arch BUILD legs (skip_build=False) must never commit/push
(no @semantic-release/git) or they desync the central release job's checkout
("a new version won't be published"). pixi.toml is bumped + committed ONLY in the
release job (skip_build=True).
"""
from pathlib import Path
import tempfile

from platform_cli.groups.release import set_pixi_version, get_releaserc


def _git_assets(rc):
    git = [p for p in rc["plugins"] if p[0] == "@semantic-release/git"]
    return git[0][1]["assets"] if git else None


def _exec_plugin(rc):
    ex = [p for p in rc["plugins"] if p[0] == "@semantic-release/exec"]
    return ex[0][1] if ex else None


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


def test_release_job_commits_pixi_toml():
    # Release job: skip_build=True -> bump via set-pixi-version + commit pixi.toml.
    rc = get_releaserc(changelog=False, skip_build=True)
    assets = _git_assets(rc)
    assert assets is not None, "release job must commit pixi.toml"
    assert "pixi.toml" in assets
    assert "CHANGELOG.md" not in assets
    ex = _exec_plugin(rc)
    assert ex and "set-pixi-version" in ex["prepareCmd"], "release job bumps pixi.toml"
    assert "publishCmd" not in ex, "release job must not publish debs (build legs do)"


def test_release_job_adds_changelog_when_requested():
    rc = get_releaserc(changelog=True, skip_build=True)
    assets = _git_assets(rc)
    assert "pixi.toml" in assets and "CHANGELOG.md" in assets


def test_build_leg_never_commits():
    # The regression guard: build legs (skip_build=False) must NOT have a git
    # plugin, or their push leaves the release job behind remote.
    rc = get_releaserc(changelog=False, skip_build=False)
    assert _git_assets(rc) is None, "build legs must not commit/push (would desync release job)"
    ex = _exec_plugin(rc)
    assert ex and "deb-prepare" in ex["prepareCmd"] and "deb-publish" in ex["publishCmd"]


def test_build_leg_commits_only_changelog_when_requested():
    # Original behavior preserved: if a build context ever runs with changelog,
    # it commits CHANGELOG.md only -- never pixi.toml.
    rc = get_releaserc(changelog=True, skip_build=False)
    assets = _git_assets(rc)
    assert assets == ["CHANGELOG.md"]


if __name__ == "__main__":
    test_set_pixi_version_bumps_package_table_preserving_comments()
    test_release_job_commits_pixi_toml()
    test_release_job_adds_changelog_when_requested()
    test_build_leg_never_commits()
    test_build_leg_commits_only_changelog_when_requested()
    print("OK")
