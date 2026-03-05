#!/usr/bin/env bash

set -euo pipefail

# -----------------------------------------------------------------------------
# 卸载 "vipe" 全局命令
# -----------------------------------------------------------------------------
#
# 默认卸载位置:
# - ~/.local/bin/vipe
#
# 自定义卸载位置(二选一):
# - `VIPE_CLI_BIN_DIR=/some/bin ./scripts/pixi/uninstall_cli.sh`
# - `./scripts/pixi/uninstall_cli.sh --bin-dir /some/bin`
#
# 保护措施:
# - 只会删除由 `install_cli.sh` 生成的脚本(通过 marker 识别)。
# - 如果目标文件不是我们生成的,会拒绝删除,避免误伤用户自己的命令。

printUsage() {
  cat <<'USAGE'
用法:
  scripts/pixi/uninstall_cli.sh [--bin-dir <DIR>]

说明:
  - 默认从 ~/.local/bin/vipe 卸载
  - 可通过环境变量 VIPE_CLI_BIN_DIR 或 --bin-dir 指定目录
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

target="${binDir}/vipe"

if [ ! -e "${target}" ]; then
  echo "未发现需要卸载的入口: ${target}"
  exit 0
fi

if ! grep -q "vipe-cli-shim: generated-by=scripts/pixi/install_cli.sh" "${target}"; then
  echo "拒绝删除: ${target}" >&2
  echo "原因: 目标文件不是由 scripts/pixi/install_cli.sh 生成(找不到 marker)" >&2
  echo "如果你确认要删除,请手动处理." >&2
  exit 1
fi

rm -f "${target}"
echo "已卸载: ${target}"

