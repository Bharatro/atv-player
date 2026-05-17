# Telegram Release Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the tag-release Telegram notification include the GitHub Release body as release notes.

**Architecture:** Keep the existing `release` job in `.github/workflows/build.yml`. After `softprops/action-gh-release@v2` creates the release, add a narrow shell step that reads the release body with `gh release view`, exports a multi-line environment variable, and lets the existing Telegram action append it to the message body. Update the workflow text assertions in `tests/test_build.py` to lock in the new release-notes flow.

**Tech Stack:** GitHub Actions YAML, GitHub CLI, pytest text-based workflow assertions

---

### Task 1: Lock the workflow expectations with a failing test

**Files:**
- Modify: `tests/test_build.py`
- Read: `.github/workflows/build.yml`

- [ ] **Step 1: Write the failing test**

Add this test near the other workflow assertions in `tests/test_build.py`:

```python
def test_github_workflow_includes_release_notes_in_telegram_notification() -> None:
    workflow = Path(".github/workflows/build.yml").read_text(encoding="utf-8")

    assert "gh release view \"$GITHUB_REF_NAME\" --json body --jq .body" in workflow
    assert "RELEASE_NOTES<<EOF" in workflow
    assert "更新内容:" in workflow
    assert "${{ env.RELEASE_NOTES }}" in workflow
    assert workflow.index("Create GitHub Release") < workflow.index("Read release notes")
    assert workflow.index("Read release notes") < workflow.index("send telegram message")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_build.py::test_github_workflow_includes_release_notes_in_telegram_notification -v`
Expected: FAIL because the workflow does not yet contain the `Read release notes` step or the `RELEASE_NOTES` message segment.

- [ ] **Step 3: Commit the red test**

```bash
git add tests/test_build.py
git commit -m "test: cover release notes telegram notification"
```

### Task 2: Read release notes after release creation and append them to the Telegram message

**Files:**
- Modify: `.github/workflows/build.yml`
- Test: `tests/test_build.py`

- [ ] **Step 1: Add the release-notes reader step**

Insert this step between `Create GitHub Release` and `send telegram message`:

```yaml
      - name: Read release notes
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          RELEASE_BODY="$(gh release view "$GITHUB_REF_NAME" --json body --jq .body || true)"
          {
            echo "RELEASE_NOTES<<EOF"
            printf '%s\n' "$RELEASE_BODY"
            echo "EOF"
          } >> "$GITHUB_ENV"
```

- [ ] **Step 2: Append release notes to the Telegram message**

Update the Telegram message block to:

```yaml
          message: |
            atv-player 发布新版本
            版本: ${{ github.ref_name }}
            仓库: ${{ github.repository }}
            发布人: ${{ github.actor }}
            Release: ${{ github.server_url }}/${{ github.repository }}/releases/tag/${{ github.ref_name }}

            更新内容:
            ${{ env.RELEASE_NOTES }}
```

- [ ] **Step 3: Run the focused test to verify it passes**

Run: `uv run pytest tests/test_build.py::test_github_workflow_includes_release_notes_in_telegram_notification -v`
Expected: PASS.

- [ ] **Step 4: Commit the workflow update**

```bash
git add .github/workflows/build.yml tests/test_build.py
git commit -m "feat: include release notes in telegram release message"
```

### Task 3: Re-run the existing workflow regression checks

**Files:**
- Test: `tests/test_build.py`

- [ ] **Step 1: Run the workflow assertion subset**

Run: `uv run pytest tests/test_build.py -k "github_workflow" -v`
Expected: all workflow-related tests pass, including the new release-notes notification assertion.

- [ ] **Step 2: Review the final diff**

Run: `git diff -- .github/workflows/build.yml tests/test_build.py`
Expected: only the new release-notes reader step, Telegram message expansion, and the added workflow assertion test appear.

- [ ] **Step 3: Commit the verification state if needed**

```bash
git add .github/workflows/build.yml tests/test_build.py
git commit -m "test: verify workflow release notification coverage"
```
