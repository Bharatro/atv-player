# Telegram Release Notes Notification Design

## Summary

让 GitHub Actions 在 tag 发布时发送的 Telegram 通知包含本次 GitHub Release 的正文内容，而不是只发送版本号和链接。通知与发布页共用同一份 release notes，避免两套文案分叉。

## Goals

- Telegram 通知复用 GitHub Release 的正文作为 release notes。
- 保持现有发布顺序：先创建 GitHub Release，再发送 Telegram 通知。
- release notes 为空时，通知仍然成功发送基础版本信息。

## Non-Goals

- 不修改本地 `build.py` 打包逻辑。
- 不改变 release notes 的生成来源或格式策略。
- 不新增独立的提交摘要生成逻辑。

## Design

### Workflow Ownership

改动只发生在 `.github/workflows/build.yml` 的 `release` job，以及对应的 workflow 断言测试。

- `build` job 继续只负责构建产物。
- `release` job 继续负责创建 GitHub Release 和发送 Telegram 通知。
- release notes 的读取发生在 `Create GitHub Release` 之后、`send telegram message` 之前。

### Data Flow

1. `softprops/action-gh-release@v2` 创建或更新 tag 对应的 GitHub Release。
2. 后续步骤通过 `gh release view ${{ github.ref_name }}` 读取该 release 的 `body`。
3. 读取到的正文写入 step output 或环境变量，供 Telegram 消息模板引用。
4. Telegram 消息保留版本、仓库、发布人、Release 链接，并在其后追加 release notes 段落。

### Fallback Behavior

- 如果 release body 为空，Telegram 仍发送基础版本通知。
- 不因为 notes 为空而让整个 release job 失败。
- 不引入第二套 notes 来源；唯一来源就是 GitHub Release 正文。

## Testing

需要覆盖：

- workflow 在 `Create GitHub Release` 后新增读取 release body 的步骤。
- Telegram 消息模板引用读取到的 release notes，而不是只发送固定文本。
- workflow 仍保持 tag 触发发布、上传构建产物、创建 GitHub Release 的原有结构。
