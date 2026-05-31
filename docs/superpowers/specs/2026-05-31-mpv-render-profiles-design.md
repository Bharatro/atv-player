# MPV Render Profiles Design

## Summary

Replace the current single "解码模式" setting with a small set of user-facing MPV render profiles. The profiles hide low-level MPV terms such as `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=nvdec`, and `d3d11va` behind stable options: automatic, compatibility, balanced, Vulkan, high quality, extreme performance, and software decode.

The implementation targets ATV-Player's current PySide6 desktop player. Android TV policy is intentionally out of scope for this desktop codebase.

## Goals

- Add more practical MPV playback modes, including Vulkan.
- Keep the settings UI understandable for non-MPV users.
- Preserve existing configs that store `mpv_hwdec_mode`.
- Choose safe automatic defaults per platform and GPU vendor where detection is possible.
- Allow MPV creation fallback from Vulkan to less demanding output modes when initialization fails.

## Non-Goals

- Do not implement Android TV / `mediacodec` behavior in this desktop player.
- Do not detect visual corruption or "花屏" from rendered frames in this change; MPV may not expose that as an error.
- Do not build a full custom MPV profile editor.
- Do not remove "更多 MPV 配置"; advanced users can still override profile options.

## User-Facing Design

In `高级设置 > 播放设置`, rename the existing `解码模式` control to `渲染模式`.

Options:

- `自动（推荐）`
- `兼容模式（OpenGL）`
- `平衡模式（gpu-next）`
- `Vulkan 模式`
- `高画质模式`
- `极限性能模式`
- `软解`

The help text should state that Vulkan and high-quality modes need newer drivers, and users can switch to compatibility mode if playback is black, corrupted, or unstable.

## Profile Semantics

Persist a new field:

- `mpv_render_profile: str = "auto"`

Valid values:

- `auto`
- `compat`
- `balanced`
- `vulkan`
- `quality`
- `performance`
- `software`

Keep `mpv_hwdec_mode` for database compatibility and legacy config loading.

Legacy mapping:

- `no` -> `software`
- `auto-copy` -> `balanced`
- `auto-safe` or invalid -> `auto`

Profile options:

- `compat`
  - `vo=gpu`
  - `hwdec=auto-safe`
  - `profile=fast`
- `balanced`
  - `vo=gpu-next`
  - `hwdec=auto-safe`
- `vulkan`
  - `vo=gpu-next`
  - `gpu-api=vulkan`
  - `hwdec=auto-safe`
- `quality`
  - Vulkan options
  - `scale=ewa_lanczossharp`
  - `cscale=ewa_lanczossharp`
  - `sigmoid-upscaling=yes`
  - `deband=yes`
- `performance`
  - Vulkan options
  - `profile=sw-fast`
  - `vd-lavc-threads=1`
  - `deband=no`
  - `interpolation=no`
- `software`
  - `vo=gpu`
  - `hwdec=no`

Automatic profile resolution:

- Linux NVIDIA: `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=nvdec`
- Windows NVIDIA: `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=nvdec`
- Windows Intel/AMD: `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=d3d11va`
- Linux AMD/Intel: `vo=gpu-next`, `gpu-api=vulkan`, `hwdec=auto-safe`
- macOS or unknown platform/vendor: `vo=gpu-next`, `hwdec=auto-safe`
- Existing Linux NVIDIA driver mismatch detection forces `compat` with `hwdec=no`, preserving the current safety behavior.

GPU vendor detection should be best-effort and side-effect free. It may use environment overrides for tests and local diagnosis:

- `ATV_GPU_VENDOR=nvidia|amd|intel|unknown`

## Runtime Priority

MPV option priority remains:

1. Built-in base startup options
2. Render profile options
3. Source-specific stream profile
4. `更多 MPV 配置`

This means advanced users can still override `vo`, `gpu-api`, `hwdec`, and quality options manually.

## Fallback Behavior

When MPV creation fails for a Vulkan-based profile, retry with lower-risk profile options:

1. Requested or automatic Vulkan options
2. Balanced (`gpu-next` without forced Vulkan)
3. Compat (`gpu` OpenGL)

Only creation failures are handled in this change. Runtime playback failures and visual corruption can be added later via the existing playback-failure path.

Each fallback should be logged with the attempted profile name and error.

## Testing

Add focused tests for:

- settings repository round-trips and normalizes `mpv_render_profile`
- old databases without `mpv_render_profile` still load and derive a sensible profile from `mpv_hwdec_mode`
- advanced settings dialog shows the new render profile options and saves the selected value
- MPV widget applies each profile's expected MPV options
- auto profile picks NVIDIA/Windows/Intel cases using controlled vendor overrides
- MPV creation falls back from Vulkan to balanced/compat when creation raises
