# One-Click Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make release publishing a one-command flow where AI only updates `RELEASE_NOTES.md`, a local script commits and tags the release, and GitHub Actions is the only component that creates or updates the GitHub Release.

**Architecture:** Keep the existing tag-triggered packaging workflow, but make the release job check out the repository and publish the body from `RELEASE_NOTES.md` instead of GitHub-generated notes. Add a repo-local `scripts/release.sh` preflight wrapper that validates release state, creates a notes-only commit, pushes the branch, pushes the tag, then waits for the tag-triggered Actions run and prints the resulting release URL.

**Tech Stack:** Bash, Git, GitHub CLI, GitHub Actions YAML, pytest

---

### Task 1: Lock Release Notes To `RELEASE_NOTES.md`

**Files:**
- Modify: `.github/workflows/build.yml`
- Modify: `tests/test_build.py`

- [ ] **Step 1: Write the failing workflow assertions**

```python
def test_github_workflow_uses_repo_release_notes_file_for_release_body() -> None:
    workflow = Path(".github/workflows/build.yml").read_text(encoding="utf-8")

    assert "body_path: RELEASE_NOTES.md" in workflow
    assert "generate_release_notes: true" not in workflow
    assert "Checkout code" in workflow
    assert workflow.index("Checkout code") < workflow.index("Create GitHub Release")


def test_github_workflow_checks_out_repo_before_release_notes_lookup() -> None:
    workflow = Path(".github/workflows/build.yml").read_text(encoding="utf-8")

    assert "actions/checkout@v4" in workflow
    assert workflow.index("Checkout code") < workflow.index("Read release notes")
```

- [ ] **Step 2: Run the workflow assertions to verify they fail**

Run: `uv run pytest tests/test_build.py -k "repo_release_notes_file_for_release_body or checks_out_repo_before_release_notes_lookup" -v`

Expected: FAIL because the workflow still contains `generate_release_notes: true` and the `release` job does not check out the repository.

- [ ] **Step 3: Update the release job to publish the committed notes file**

```yaml
  release:
    name: Publish Release
    runs-on: ubuntu-latest
    needs: build
    if: startsWith(github.ref, 'refs/tags/v')
    permissions:
      contents: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Download build artifacts
        uses: actions/download-artifact@v4
        with:
          path: artifacts

      - name: Prepare release assets
        run: |
          mkdir -p release-assets
          find artifacts -type f \( -name "*.AppImage" -o -name "*.zip" -o -name "*.exe" \) -exec cp {} release-assets/ \;
          ls -la release-assets

      - name: Create GitHub Release
        uses: softprops/action-gh-release@v2
        with:
          files: release-assets/*
          body_path: RELEASE_NOTES.md
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 4: Re-run the workflow assertions**

Run: `uv run pytest tests/test_build.py -k "repo_release_notes_file_for_release_body or checks_out_repo_before_release_notes_lookup" -v`

Expected: PASS with both new assertions green.

- [ ] **Step 5: Run the broader workflow regression slice**

Run: `uv run pytest tests/test_build.py -k "release or workflow" -v`

Expected: PASS, including the existing Telegram release-notes assertion and the new body-path assertions.

- [ ] **Step 6: Commit the workflow-source change**

```bash
git add .github/workflows/build.yml tests/test_build.py
git commit -m "feat: publish release notes from repo file"
```

### Task 2: Add Release Script Tests Around Preflight And Push Order

**Files:**
- Create: `tests/test_release_script.py`
- Test: `scripts/release.sh`

- [ ] **Step 1: Write the failing release script harness and preflight tests**

```python
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
              "run list --workflow Build Packages --limit 20 --json databaseId,url,headSha,event --jq .[] | select(.event == \"push\" and .headSha == \"abc123\") | .databaseId") printf '12345\\n' ;;
              "run view 12345 --json url --jq .url") printf 'https://github.com/power721/atv-player/actions/runs/12345\\n' ;;
              "run watch 12345 --exit-status") ;;
              "release view v0.49.0 --json url --jq .url") printf 'https://github.com/power721/atv-player/releases/tag/v0.49.0\\n' ;;
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
    (tmp_path / "RELEASE_NOTES.md").write_text("## 新增\\n\\n- 支持一键发布\\n", encoding="utf-8")
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
    result = _run_release_script(tmp_path, status_porcelain=" M RELEASE_NOTES.md\\n M src/atv_player/app.py\\n")

    assert result.returncode == 1
    assert "RELEASE_NOTES.md 之外存在未提交改动" in result.stderr


def test_release_script_rejects_branch_behind_origin(tmp_path) -> None:
    result = _run_release_script(tmp_path, rev_list="1\t0")

    assert result.returncode == 1
    assert "当前分支落后远端" in result.stderr


def test_release_script_pushes_branch_before_tag_and_prints_release_url(tmp_path) -> None:
    result = _run_release_script(tmp_path, status_porcelain=" M RELEASE_NOTES.md\\n")

    assert result.returncode == 0
    assert "https://github.com/power721/atv-player/releases/tag/v0.49.0" in result.stdout
    log_lines = (tmp_path / "calls.log").read_text(encoding="utf-8").splitlines()
    assert log_lines.index("git:push origin master") < log_lines.index("git:tag v0.49.0")
    assert log_lines.index("git:tag v0.49.0") < log_lines.index("git:push origin v0.49.0")
```

- [ ] **Step 2: Run the release script tests to verify they fail**

Run: `uv run pytest tests/test_release_script.py -v`

Expected: FAIL because `scripts/release.sh` does not exist yet.

- [ ] **Step 3: Extend the test harness with tag-exists coverage before implementation**

```python
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
```

- [ ] **Step 4: Re-run the release script tests**

Run: `uv run pytest tests/test_release_script.py -v`

Expected: FAIL with missing-script or command-not-found errors, confirming the harness is exercising the intended entrypoint.

- [ ] **Step 5: Commit the test harness**

```bash
git add tests/test_release_script.py
git commit -m "test: cover one-click release script"
```

### Task 3: Implement `scripts/release.sh`

**Files:**
- Create: `scripts/release.sh`
- Modify: `tests/test_release_script.py`

- [ ] **Step 1: Write the minimal script that satisfies the version and notes preflight**

```bash
#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '%s\n' "$1" >&2
  exit 1
}

require_clean_release_notes_only() {
  local status path normalized
  while IFS= read -r status; do
    [[ -z "$status" ]] && continue
    path="${status:3}"
    normalized="${path#./}"
    if [[ "$normalized" != "RELEASE_NOTES.md" ]]; then
      die "RELEASE_NOTES.md 之外存在未提交改动: $normalized"
    fi
  done < <(git status --porcelain)
}

version="${1:-}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "版本号必须是 X.Y.Z"
tag="v$version"
[[ -s RELEASE_NOTES.md ]] || die "RELEASE_NOTES.md 不能为空"
```

- [ ] **Step 2: Expand the script with branch, sync, and tag checks**

```bash
branch="$(git rev-parse --abbrev-ref HEAD)"
head_sha="$(git rev-parse HEAD)"
printf 'branch=%s\nHEAD=%s\nversion=%s\ntag=%s\n' "$branch" "$head_sha" "$version" "$tag"

[[ "$branch" == "master" ]] || die "只能在 master 分支执行发布脚本"
require_clean_release_notes_only

git fetch origin master --tags
read -r behind ahead < <(git rev-list --left-right --count origin/master...HEAD)
[[ "$behind" == "0" ]] || die "当前分支落后远端，请先同步 origin/master"

[[ -z "$(git tag --list "$tag")" ]] || die "本地已存在 tag: $tag"
[[ -z "$(git ls-remote --tags origin "$tag")" ]] || die "远端已存在 tag: $tag"
```

- [ ] **Step 3: Implement the release commit, push, tag, and CI wait sequence**

```bash
git add RELEASE_NOTES.md
git commit -m "docs: add release notes for $tag"
git push origin "$branch"
git tag "$tag"
git push origin "$tag"

run_id="$(gh run list \
  --workflow "Build Packages" \
  --limit 20 \
  --json databaseId,url,headSha,event \
  --jq ".[] | select(.event == \"push\" and .headSha == \"$head_sha\") | .databaseId" | head -n 1)"
[[ -n "$run_id" ]] || die "未找到 tag 对应的 GitHub Actions run"

run_url="$(gh run view "$run_id" --json url --jq .url)"
if ! gh run watch "$run_id" --exit-status; then
  die "发布 workflow 失败: $run_url"
fi

release_url="$(gh release view "$tag" --json url --jq .url)"
printf '%s\n' "$release_url"
```

- [ ] **Step 4: Keep the helper signature and fake `gh` output aligned with the final lookup sequence**

```python
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
```

- [ ] **Step 5: Run the script-focused test slice**

Run: `uv run pytest tests/test_release_script.py -v`

Expected: PASS with the dirty-tree, behind-origin, tag-exists, and push-order coverage all green.

- [ ] **Step 6: Run shell syntax verification**

Run: `bash -n scripts/release.sh`

Expected: exit 0 with no output.

- [ ] **Step 7: Commit the script implementation**

```bash
git add scripts/release.sh tests/test_release_script.py
git commit -m "feat: add one-click release script"
```

### Task 4: Final Verification Sweep

**Files:**
- Verify only: `.github/workflows/build.yml`, `scripts/release.sh`, `tests/test_build.py`, `tests/test_release_script.py`

- [ ] **Step 1: Run the targeted verification suite**

Run: `uv run pytest tests/test_build.py tests/test_release_script.py -v`

Expected: PASS with all workflow and release-script tests green.

- [ ] **Step 2: Inspect the final diff for scope control**

Run: `git diff --stat HEAD~3..HEAD`

Expected: only workflow release-body changes, the new release script, and the associated tests appear.

- [ ] **Step 3: Only create a follow-up commit if Step 2 exposed unintended scope**

```bash
git add .github/workflows/build.yml scripts/release.sh tests/test_build.py tests/test_release_script.py
git commit -m "test: verify one-click release flow"
```
