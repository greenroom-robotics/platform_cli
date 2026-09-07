"""Standalone checks for the pixi.toml bump + commit wiring in release.py.

Run: python tests/test_release_pixi_bump.py   (or pytest if available)

Key invariant: the per-arch BUILD legs (skip_build=False) must never commit/push
(no @semantic-release/git) or they desync the central release job's checkout
("a new version won't be published"). pixi.toml is bumped + committed ONLY in the
release job (skip_build=True).
"""
from pathlib import Path
import json
import tempfile

from platform_cli.groups.release import (
    PackageInfo,
    RecordedRelease,
    get_releaserc,
    prepend_changelog,
    read_recorded,
    release_commit_message,
    set_pixi_version,
)


def _git_assets(rc):
    git = [p for p in rc["plugins"] if p[0] == "@semantic-release/git"]
    return git[0][1]["assets"] if git else None


def _exec_plugin(rc):
    ex = [p for p in rc["plugins"] if p[0] == "@semantic-release/exec"]
    return ex[0][1] if ex else None


def _git_message(rc):
    git = [p for p in rc["plugins"] if p[0] == "@semantic-release/git"]
    return git[0][1].get("message") if git else None


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
    assert assets is not None
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


def test_commit_message_names_the_package():
    # commit_package -> release commit subject names the package (not a bare
    # version), so `git log` shows what each chore(release) bumped.
    rc = get_releaserc(changelog=False, skip_build=True, commit_package="object_tracker")
    msg = _git_message(rc)
    assert msg is not None, "commit_package must set an explicit git message"
    assert msg.startswith("chore(release): object_tracker ${nextRelease.version} [skip ci]")
    assert "${nextRelease.notes}" in msg, "release notes must still ride in the body"


def test_default_commit_message_when_package_unset():
    # Without commit_package, fall back to @semantic-release/git's default subject.
    rc = get_releaserc(changelog=False, skip_build=True)
    assert _git_message(rc) is None


def _pkg(name, path=Path(".")):
    return PackageInfo(
        package_path=path, package_name=name, package_version="0.0.0", module_info=None
    )


def test_record_pass_adds_record_plugin_and_no_changelog():
    rc = get_releaserc(
        changelog=True, skip_build=True, commit_package="x", record_dir=Path("/rec")
    )
    names = [p[0] for p in rc["plugins"]]
    assert "@semantic-release/changelog" not in names
    record = [p for p in rc["plugins"] if p[0].endswith("record_release.js")]
    assert record and record[0][1] == {"dir": "/rec", "name": "x"}


def test_release_pass_skips_changelog_plugin_once_committed():
    def names(rc):
        return [p[0] for p in rc["plugins"]]

    assert "@semantic-release/changelog" not in names(
        get_releaserc(changelog=True, skip_build=True, changelog_committed=True)
    )
    assert "@semantic-release/changelog" in names(get_releaserc(changelog=True, skip_build=True))


def test_prepend_changelog_matches_semantic_release_changelog_layout():
    assert prepend_changelog("", "## x 1.1.0\n\n* a\n") == "## x 1.1.0\n\n* a\n"
    assert (
        prepend_changelog("## x 1.0.0\n\n* old\n", "## x 1.1.0\n\n* a")
        == "## x 1.1.0\n\n* a\n\n## x 1.0.0\n\n* old\n"
    )


def test_release_commit_message_names_every_package():
    msg = release_commit_message(
        [
            RecordedRelease(_pkg("a"), "1.1.0", "## a 1.1.0\n\n* one"),
            RecordedRelease(_pkg("b"), "2.0.0", ""),
        ]
    )
    assert msg == "chore(release): a 1.1.0, b 2.0.0 [skip ci]\n\n## a 1.1.0\n\n* one"


def test_read_recorded_keeps_package_order_and_skips_unreleased():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "b.json").write_text(json.dumps({"version": "2.0.0", "notes": "nb"}))
        (Path(d) / "a.json").write_text(json.dumps({"version": "1.1.0", "notes": "na"}))
        recorded = read_recorded(Path(d), [_pkg("a"), _pkg("skipped"), _pkg("b")])
        assert [(r.package.package_name, r.version, r.notes) for r in recorded] == [
            ("a", "1.1.0", "na"),
            ("b", "2.0.0", "nb"),
        ]


if __name__ == "__main__":
    test_set_pixi_version_bumps_package_table_preserving_comments()
    test_release_job_commits_pixi_toml()
    test_release_job_adds_changelog_when_requested()
    test_build_leg_never_commits()
    test_build_leg_commits_only_changelog_when_requested()
    test_commit_message_names_the_package()
    test_default_commit_message_when_package_unset()
    test_record_pass_adds_record_plugin_and_no_changelog()
    test_release_pass_skips_changelog_plugin_once_committed()
    test_prepend_changelog_matches_semantic_release_changelog_layout()
    test_release_commit_message_names_every_package()
    test_read_recorded_keeps_package_order_and_skips_unreleased()
    print("OK")
