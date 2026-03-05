#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# 安装 "vipe" 全局命令(不需要手动进入 pixi 环境)
# -----------------------------------------------------------------------------
#
# 你得到什么:
# - 安装后你可以在任意目录直接执行 `vipe ...`。
# - 这个 `vipe` 实际会固定使用当前仓库的 `.pixi/envs/default` 作为运行环境。
#
# 为什么要这样做:
# - `pixi run install-vipe` 只会把入口装进 `.pixi/envs/default/bin/vipe`。
# - 这个路径默认不在 PATH 里,所以你在普通 shell 里直接输入 `vipe` 会找不到命令。
# - 另外,直接跑也容易继承宿主机的 `CUDA_HOME=/usr/local/cuda`,导致 torch JIT 编译扩展失败。
#
# 默认安装位置:
# - ~/.local/bin/vipe
#
# 自定义安装位置(二选一):
# - `VIPE_CLI_BIN_DIR=/some/bin ./scripts/pixi/install_cli.sh`
# - `./scripts/pixi/install_cli.sh --bin-dir /some/bin`
#
# 卸载:
# - `./scripts/pixi/uninstall_cli.sh`

printUsage() {
  cat <<'USAGE'
用法:
  scripts/pixi/install_cli.sh [--bin-dir <DIR>]

说明:
  - 默认安装到 ~/.local/bin/vipe
  - 可通过环境变量 VIPE_CLI_BIN_DIR 或 --bin-dir 指定安装目录

示例:
  ./scripts/pixi/install_cli.sh
  ./scripts/pixi/install_cli.sh --bin-dir /tmp/vipe-bin
USAGE
}

binDir="${VIPE_CLI_BIN_DIR:-${HOME}/.local/bin}"
while [ $# -gt 0 ]; do
  case "${1}" in
    --bin-dir)
      if [ $# -lt 2 ]; then
        echo "错误: --bin-dir 需要一个参数" >&2
        exit 2
      fi
      binDir="${2}"
      shift 2
      ;;
    -h | --help)
      printUsage
      exit 0
      ;;
    *)
      echo "错误: 未知参数: ${1}" >&2
      printUsage >&2
      exit 2
      ;;
  esac
done

scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
repoRoot="$(cd "${scriptDir}/../.." && pwd -P)"
pixiEnv="${repoRoot}/.pixi/envs/default"

mkdir -p "${binDir}"

target="${binDir}/vipe"

escapeForDoubleQuotes() {
  local raw="${1}"
  # 让路径可以安全写进 bash 的双引号字符串里
  raw="${raw//\\/\\\\}"
  raw="${raw//\"/\\\"}"
  printf '%s' "${raw}"
}

repoRootEscaped="$(escapeForDoubleQuotes "${repoRoot}")"
pixiEnvEscaped="$(escapeForDoubleQuotes "${pixiEnv}")"

cat >"${target}" <<EOF
#!/usr/bin/env bash

set -euo pipefail

# vipe-cli-shim: generated-by=scripts/pixi/install_cli.sh
# -----------------------------------------------------------------------------
# 说明:
# - 这是一个"入口包装脚本",让你不必每次都手动执行 pixi 命令。
# - 它会固定使用当前仓库的 pixi 环境来运行 ViPE CLI。
#
# 注意:
# - 这个脚本绑定了仓库路径. 如果你移动/重命名仓库目录,请重新执行安装脚本生成新的入口。
# -----------------------------------------------------------------------------

repoRoot="${repoRootEscaped}"
pixiEnv="${pixiEnvEscaped}"

if [ ! -x "\${pixiEnv}/bin/python" ]; then
  echo "vipe: 找不到 pixi 环境的 python: \${pixiEnv}/bin/python" >&2
  echo "vipe: 请先在仓库目录执行: pixi install --locked" >&2
  exit 1
fi

# 把 pixi 环境的可执行文件优先放到 PATH,避免调用到系统同名命令。
export PATH="\${pixiEnv}/bin:\${PATH}"

# 固定 CUDA 工具链来源,避免继承宿主机 CUDA_HOME 导致 JIT 编译失败。
if [ -d "\${pixiEnv}/targets/x86_64-linux" ]; then
  export CUDA_HOME="\${pixiEnv}/targets/x86_64-linux"
  export CUDA_PATH="\${CUDA_HOME}"
fi
if [ -x "\${pixiEnv}/bin/nvcc" ]; then
  export PYTORCH_NVCC="\${pixiEnv}/bin/nvcc"
fi

cd "\${repoRoot}"

# 从源码运行,避免必须先做 editable 安装。
exec "\${pixiEnv}/bin/python" -m vipe.cli.main "\$@"
EOF

chmod +x "${target}"

echo "已安装: ${target}"
echo "提示: 如果终端提示 'command not found: vipe',通常是 PATH 里没有 '${binDir}'"
echo "提示: 如果你移动了仓库目录,需要重新运行本脚本更新入口里的 repoRoot"

