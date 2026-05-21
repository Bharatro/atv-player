#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

WORKDIR="${PROJECT_ROOT}/build/mpv-build"
if command -v nproc >/dev/null 2>&1; then
  JOBS="$(nproc)"
else
  JOBS="4"
fi
DISABLE_X86ASM=0
DO_INSTALL=1
DRY_RUN=0
USE_MASTER=0
DO_CLEAN=0

usage() {
  cat <<'EOF'
Usage: scripts/build_mpv.sh [options]

Build mpv/libmpv with mpv-build in a separate workspace.

Options:
  --workdir <dir>        mpv-build working directory (default: build/mpv-build)
  --jobs <n>             parallel build jobs (default: nproc)
  --disable-x86asm       add --disable-x86asm to ffmpeg_options
  --master               use mpv/ffmpeg master instead of release
  --clean                run ./clean before rebuilding
  --no-install           skip sudo ./install
  --dry-run              print commands without executing external build steps
  -h, --help             show this help
EOF
}

log() {
  printf '[build_mpv] %s\n' "$*"
}

die() {
  printf '%s\n' "$*" >&2
  exit 1
}

run() {
  if [[ "${DRY_RUN}" == "1" ]]; then
    printf '+'
    for arg in "$@"; do
      printf ' %s' "$arg"
    done
    printf '\n'
    return 0
  fi
  "$@"
}

sanitize_build_environment() {
  unset PYENV_VERSION
  unset PYENV_DIR
  if [[ -n "${PYENV_ROOT:-}" ]]; then
    local sanitized_path=""
    local entry
    IFS=':' read -r -a path_entries <<< "${PATH}"
    for entry in "${path_entries[@]}"; do
      if [[ "${entry}" == "${PYENV_ROOT}/shims" ]]; then
        continue
      fi
      if [[ -n "${sanitized_path}" ]]; then
        sanitized_path="${sanitized_path}:"
      fi
      sanitized_path="${sanitized_path}${entry}"
    done
    PATH="${sanitized_path}"
  fi
}

require_cmd() {
  local name="$1"
  command -v "${name}" >/dev/null 2>&1 || die "Missing required command: ${name}"
}

has_pkg_config_dep() {
  local dep="$1"
  pkg-config --exists "${dep}" >/dev/null 2>&1
}

install_lua_dev_package() {
  if ! command -v apt-get >/dev/null 2>&1; then
    die "Missing required Lua development package for mpv scripts. Install liblua5.2-dev, then rebuild."
  fi
  log "Installing missing Lua development package: liblua5.2-dev"
  run sudo apt-get install -y liblua5.2-dev
}

has_active_x11_session() {
  [[ "${XDG_SESSION_TYPE:-}" == "x11" ]]
}

require_lua_dev_package() {
  local dep
  for dep in luajit lua lua52 lua5.2 lua-5.2 lua51 lua5.1 lua-5.1; do
    if has_pkg_config_dep "${dep}"; then
      return 0
    fi
  done
  install_lua_dev_package
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  for dep in luajit lua lua52 lua5.2 lua-5.2 lua51 lua5.1 lua-5.1; do
    if has_pkg_config_dep "${dep}"; then
      return 0
    fi
  done
  die "Missing required Lua development package for mpv scripts after install. Verify liblua5.2-dev is available to pkg-config, then rebuild."
}

install_x11_dev_package() {
  if ! command -v apt-get >/dev/null 2>&1; then
    die "Missing required X11 development package for mpv video output. Install libxpresent-dev, then rebuild."
  fi
  log "Installing missing X11 development package: libxpresent-dev"
  run sudo apt-get install -y libxpresent-dev
}

require_x11_support_dependencies() {
  if ! has_active_x11_session; then
    return 0
  fi
  if has_pkg_config_dep "xpresent"; then
    return 0
  fi
  install_x11_dev_package
  if [[ "${DRY_RUN}" == "1" ]]; then
    return 0
  fi
  if has_pkg_config_dep "xpresent"; then
    return 0
  fi
  die "Missing required X11 development package for mpv video output after install. Verify libxpresent-dev is available to pkg-config, then rebuild."
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --workdir)
        [[ $# -ge 2 ]] || die "--workdir requires a value"
        WORKDIR="$2"
        shift 2
        ;;
      --jobs)
        [[ $# -ge 2 ]] || die "--jobs requires a value"
        JOBS="$2"
        shift 2
        ;;
      --disable-x86asm)
        DISABLE_X86ASM=1
        shift
        ;;
      --master)
        USE_MASTER=1
        shift
        ;;
      --clean)
        DO_CLEAN=1
        shift
        ;;
      --no-install)
        DO_INSTALL=0
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        die "Unknown option: $1"
        ;;
    esac
  done
}

check_dependencies() {
  require_cmd git
  require_cmd meson
  require_cmd ninja
  require_cmd pkg-config
  require_lua_dev_package
  require_x11_support_dependencies

  if [[ "${DISABLE_X86ASM}" != "1" ]]; then
    if ! command -v nasm >/dev/null 2>&1; then
      die "nasm not found or too old. Please install/update nasm or rerun with --disable-x86asm."
    fi
  fi
}

ensure_repo() {
  local parent_dir
  parent_dir="$(dirname "${WORKDIR}")"
  mkdir -p "${parent_dir}"

  if [[ -d "${WORKDIR}/.git" ]]; then
    log "Using existing mpv-build repo: ${WORKDIR}"
    return 0
  fi

  log "Cloning mpv-build into ${WORKDIR}"
  run git clone https://github.com/mpv-player/mpv-build.git "${WORKDIR}"
}

ensure_repo_layout() {
  local required
  for required in rebuild install use-mpv-release use-ffmpeg-release use-mpv-master use-ffmpeg-master; do
    [[ -e "${WORKDIR}/${required}" ]] || die "mpv-build repo missing helper script: ${required}"
  done
}

write_option_files() {
  : > "${WORKDIR}/ffmpeg_options"
  if [[ "${DISABLE_X86ASM}" == "1" ]]; then
    printf '%s\n' "--disable-x86asm" > "${WORKDIR}/ffmpeg_options"
  fi
}

build_mpv() {
  pushd "${WORKDIR}" >/dev/null
  if [[ "${USE_MASTER}" == "1" ]]; then
    run ./use-mpv-master
    run ./use-ffmpeg-master
  else
    run ./use-mpv-release
    run ./use-ffmpeg-release
  fi
  if [[ "${DO_CLEAN}" == "1" ]]; then
    run ./clean
  fi
  run ./rebuild "-j${JOBS}"
  if [[ "${DO_INSTALL}" == "1" ]]; then
    run sudo ./install
    run sudo ldconfig
  fi
  popd >/dev/null
}

print_follow_up() {
  if [[ "${DO_INSTALL}" == "1" ]]; then
    log "Build finished. Verify the runtime with:"
    printf '  hash -r\n'
    printf '  which mpv\n'
    printf '  /usr/local/bin/mpv --version\n'
    printf '  ldconfig -p | grep libmpv\n'
  else
    log "Build finished without install. Built artifacts remain under:"
    printf '  %s\n' "${WORKDIR}"
  fi
}

main() {
  parse_args "$@"
  sanitize_build_environment
  check_dependencies
  ensure_repo
  ensure_repo_layout
  write_option_files
  build_mpv
  print_follow_up
}

main "$@"
