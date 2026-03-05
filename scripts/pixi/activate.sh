#!/usr/bin/env bash

# -----------------------------------------------------------------------------
# Pixi 激活脚本: 固定 CUDA 工具链来源
# -----------------------------------------------------------------------------
#
# 目的:
# - 避免继承宿主机的 `CUDA_HOME=/usr/local/cuda`,导致 torch 在 JIT 编译扩展时误用系统 nvcc.
# - 强制使用 pixi/conda 环境内的 CUDA 工具链,提升可复现性,也避免常见的 "nvcc 不支持当前 GCC"
#   这类报错.
#
# 背景:
# - ViPE 会在首次 import 时通过 `torch.utils.cpp_extension.load` JIT 编译扩展.
# - torch 的 cpp_extension 会优先读取 `CUDA_HOME` 来定位 CUDA headers/libs.
# - 在一些镜像/主机环境中,系统 CUDA 版本可能偏旧,对 GCC 版本支持滞后,导致编译直接失败.
#
# 约定:
# - pixi 会设置 `CONDA_PREFIX` 指向当前环境目录.
# - conda 的 CUDA headers 通常位于 `$CONDA_PREFIX/targets/x86_64-linux/include`.

if [ -z "${CONDA_PREFIX:-}" ]; then
  # 没有激活 conda/pixi 环境时,不做任何事.
  return 0 2>/dev/null || exit 0
fi

# 使用 pixi 环境内的 nvcc(优先级高于 PATH 与系统 CUDA)
if [ -x "${CONDA_PREFIX}/bin/nvcc" ]; then
  export PYTORCH_NVCC="${CONDA_PREFIX}/bin/nvcc"
fi

# 让 torch/cpp_extension 使用 conda 提供的 CUDA headers/libs
if [ -d "${CONDA_PREFIX}/targets/x86_64-linux" ]; then
  export CUDA_HOME="${CONDA_PREFIX}/targets/x86_64-linux"
  export CUDA_PATH="${CUDA_HOME}"
fi
