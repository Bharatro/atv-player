#!/usr/bin/env bash
set -euo pipefail

die() {
  printf '%s\n' "$1" >&2
  exit 1
}

require_clean_release_notes_only() {
  local line path normalized
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    path="${line:3}"
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

git add RELEASE_NOTES.md
git commit -m "docs: add release notes for $tag"
git push origin "$branch"
git tag "$tag"
git push origin "$tag"

run_id="$(
  gh run list \
    --workflow "Build Packages" \
    --limit 20 \
    --json databaseId,url,headSha,event \
    --jq ".[] | select(.event == \"push\" and .headSha == \"$head_sha\") | .databaseId" \
    | head -n 1
)"
[[ -n "$run_id" ]] || die "未找到 tag 对应的 GitHub Actions run"

run_url="$(gh run view "$run_id" --json url --jq .url)"
if ! gh run watch "$run_id" --exit-status; then
  die "发布 workflow 失败: $run_url"
fi

release_url="$(gh release view "$tag" --json url --jq .url)"
printf '%s\n' "$release_url"
