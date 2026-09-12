from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from atv_player.player.mpv_library import custom_mpv_library_search_dirs

MPV_CONFIG_FILE_NAME = "mpv.conf"
SHADER_DIR_NAME = "shaders"
SHADER_FILE_SUFFIXES = (".glsl", ".hook")
LOOSE_SHADER_PRESET_NAME = "默认"


@dataclass(frozen=True, slots=True)
class ShaderPreset:
    name: str
    shader_files: tuple[str, ...]


def _search_dirs(search_dirs: Iterable[Path] | None) -> list[Path]:
    if search_dirs is not None:
        return list(search_dirs)
    return custom_mpv_library_search_dirs()


def resolve_mpv_config_dir(search_dirs: Iterable[Path] | None = None) -> Path | None:
    """约定同自定义 libmpv(~/mpv、应用目录/lib、应用目录):首个包含 mpv.conf 的目录生效。

    该目录同时成为 libmpv 的 config-dir,input.conf/scripts 等存在即生效;
    播放器自身的 wid/vo/hwdec 等关键选项优先级更高,用户配置不会破坏嵌入渲染。
    """
    for directory in _search_dirs(search_dirs):
        if (directory / MPV_CONFIG_FILE_NAME).is_file():
            return directory
    return None


def _collect_shader_files(directory: Path) -> list[Path]:
    return sorted(
        (
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() in SHADER_FILE_SUFFIXES
        ),
        key=lambda path: path.name,
    )


def _preset(name: str, files: list[Path]) -> ShaderPreset | None:
    if not files:
        return None
    return ShaderPreset(name=name, shader_files=tuple(str(path) for path in files))


def discover_shader_presets(search_dirs: Iterable[Path] | None = None) -> list[ShaderPreset]:
    """shaders/ 下每个子目录是一个预设(如 Anime4K 的 Mode A/B/C × High/Low 分组),散放的着色器归入"默认"预设。

    多个搜索目录出现同名预设时先者胜,与自定义 libmpv 的优先级一致。
    """
    presets: list[ShaderPreset] = []
    seen_names: set[str] = set()
    for directory in _search_dirs(search_dirs):
        shaders_dir = directory / SHADER_DIR_NAME
        if not shaders_dir.is_dir():
            continue
        candidates: list[ShaderPreset | None] = [
            _preset(sub_dir.name, _collect_shader_files(sub_dir))
            for sub_dir in sorted(
                (entry for entry in shaders_dir.iterdir() if entry.is_dir()),
                key=lambda path: path.name,
            )
        ]
        candidates.append(_preset(LOOSE_SHADER_PRESET_NAME, _collect_shader_files(shaders_dir)))
        for candidate in candidates:
            if candidate is not None and candidate.name not in seen_names:
                seen_names.add(candidate.name)
                presets.append(candidate)
    return presets
