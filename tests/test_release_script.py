from pathlib import Path
import os
import subprocess
import textwrap


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "release.sh"


def _write_fake_git(fake_bin: Path) -> None:
    (fake_bin / "git").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'git:%s\\n' "$*" >> "${FAKE_LOG}"
            case "$*" in
              "rev-parse --abbrev-ref HEAD") printf '%s\\n' "${FAKE_BRANCH:-master}" ;;
              "rev-parse HEAD") printf '%s\\n' "${FAKE_HEAD_SHA:-abc123}" ;;
              "status --porcelain") printf '%s' "${FAKE_STATUS_PORCELAIN:-}" ;;
              "remote get-url origin") printf '%s\\n' "${FAKE_REMOTE_URL:-https://github.com/power721/atv-player.git}" ;;
              "fetch origin master --tags") ;;
              "rev-list --left-right --count origin/master...HEAD") printf '%s\\n' "${FAKE_REV_LIST:-0\t0}" ;;
              "tag --list v0.49.0") printf '%s' "${FAKE_LOCAL_TAG:-}" ;;
              "ls-remote --tags origin v0.49.0") printf '%s' "${FAKE_REMOTE_TAG:-}" ;;
              "add RELEASE_NOTES.md") ;;
              "commit -m docs: add release notes for v0.49.0") ;;
              "push origin master") ;;
              "tag v0.49.0") ;;
              "push origin v0.49.0") ;;
              *) printf 'unexpected git call: %s\\n' "$*" >&2; exit 1 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    os.chmod(fake_bin / "git", 0o755)


def _write_fake_gh(fake_bin: Path) -> None:
    (fake_bin / "gh").write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            printf 'gh:%s\\n' "$*" >> "${FAKE_LOG}"
            case "$*" in
              "release view v0.49.0 --json url --jq .url")
                if [[ "${FAKE_RELEASE_VIEW_FAIL:-0}" == "1" ]]; then
                  exit 1
                fi
                printf 'https://github.com/power721/atv-player/releases/tag/v0.49.0\\n'
                ;;
              *) printf 'unexpected gh call: %s\\n' "$*" >&2; exit 1 ;;
            esac
            """
        ),
        encoding="utf-8",
    )
    os.chmod(fake_bin / "gh", 0o755)


def _run_release_script(
    tmp_path: Path,
    *,
    status_porcelain: str = "",
    rev_list: str = "0\t0",
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _write_fake_git(fake_bin)
    _write_fake_gh(fake_bin)
    (tmp_path / "RELEASE_NOTES.md").write_text("## 新增\n\n- 支持一键发布\n", encoding="utf-8")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "FAKE_STATUS_PORCELAIN": status_porcelain,
        "FAKE_REV_LIST": rev_list,
        **(extra_env or {}),
    }
    return subprocess.run(
        ["bash", str(SCRIPT_PATH), "0.49.0"],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_release_script_rejects_dirty_files_beyond_release_notes(tmp_path) -> None:
    result = _run_release_script(tmp_path, status_porcelain=" M RELEASE_NOTES.md\n M src/atv_player/app.py\n")

    assert result.returncode == 1
    assert "RELEASE_NOTES.md 之外存在未提交改动" in result.stderr


def test_release_script_rejects_branch_behind_origin(tmp_path) -> None:
    result = _run_release_script(tmp_path, rev_list="1\t0")

    assert result.returncode == 1
    assert "当前分支落后远端" in result.stderr


def test_release_script_rejects_existing_local_tag(tmp_path) -> None:
    result = _run_release_script(
        tmp_path,
        status_porcelain=" M RELEASE_NOTES.md\n",
        extra_env={"FAKE_LOCAL_TAG": "v0.49.0\n"},
    )

    assert result.returncode == 1
    assert "本地已存在 tag: v0.49.0" in result.stderr


def test_release_script_rejects_existing_remote_tag(tmp_path) -> None:
    result = _run_release_script(
        tmp_path,
        status_porcelain=" M RELEASE_NOTES.md\n",
        extra_env={"FAKE_REMOTE_TAG": "deadbeef\trefs/tags/v0.49.0\n"},
    )

    assert result.returncode == 1
    assert "远端已存在 tag: v0.49.0" in result.stderr


def test_release_script_allows_untracked_docs_when_releasing(tmp_path) -> None:
    result = _run_release_script(
        tmp_path,
        status_porcelain=" M RELEASE_NOTES.md\n?? docs/superpowers/plans/plan.md\n",
    )

    assert result.returncode == 0
    assert "https://github.com/power721/atv-player/releases/tag/v0.49.0" in result.stdout


def test_release_script_pushes_branch_before_tag_and_does_not_wait_for_actions(tmp_path) -> None:
    result = _run_release_script(tmp_path, status_porcelain=" M RELEASE_NOTES.md\n")

    assert result.returncode == 0
    assert "https://github.com/power721/atv-player/releases/tag/v0.49.0" in result.stdout
    log_lines = (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()
    assert log_lines.index("git:push origin master") < log_lines.index("git:tag v0.49.0")
    assert log_lines.index("git:tag v0.49.0") < log_lines.index("git:push origin v0.49.0")
    assert all(not line.startswith("gh:run ") for line in log_lines)


def test_release_script_prints_release_page_when_release_is_not_ready(tmp_path) -> None:
    result = _run_release_script(
        tmp_path,
        status_porcelain=" M RELEASE_NOTES.md\n",
        extra_env={"FAKE_RELEASE_VIEW_FAIL": "1"},
    )

    assert result.returncode == 0
    assert "https://github.com/power721/atv-player/releases/tag/v0.49.0" in result.stdout
