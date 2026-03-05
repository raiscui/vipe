# 笔记: pixi 迁移要点(vipe)

## 来源

### 来源1: pixi 官方文档(通过 Context7 查询)

- 要点:
  - pixi 支持两种 manifest: `pixi.toml` 和 `pyproject.toml`。
  - 当 `pyproject.toml` 包含 `[tool.pixi.workspace]` 且没有 `pixi.toml` 时,会自动把 `pyproject.toml` 当作 manifest。
  - 在 `pyproject.toml` 中:
    - conda 依赖写在 `[tool.pixi.dependencies]`
    - PyPI 依赖可以来自 `[project.dependencies]`,也可以写在 `[tool.pixi.pypi-dependencies]`
  - torch 这类需要特定 index 的包,可用:
    - `torch = { version = \"...\", index = \"https://download.pytorch.org/whl/cu128\" }`
  - 如果某个包构建时需要访问环境里的依赖(例如需要 torch),要在 `pypi-options` 里关闭 build isolation:
    - `no-build-isolation = [\"package-name\"]`
    - 或者全局 `no-build-isolation = true`
  - `pixi run` 可以直接运行任意命令,不要求预先定义 tasks:
    - `pixi run python script.py`
    - `pixi run vipe infer xxx.mp4`

## 综合发现(和本项目的关联)

### 1. 优先用 `pyproject.toml` 承载 pixi 配置

- 可以减少新文件,也更贴合当前项目结构。

### 2. vipe 安装需要禁用 build isolation

- `setup.py` 会 import torch 并编译 CUDAExtension。
- 因此 pixi 里需要:
  - 先装 torch/torchvision(来自指定 index)
  - 再装本项目(可用 editable path)
  - 并对本项目设置 `no-build-isolation`。

### 3. 如果无法访问 `conda.anaconda.org`,可改用 prefix.dev channel URL

- 现象: `pixi lock` 可能在拉取 repodata 时因 DNS/网络策略失败。
- 处理: 在 `[tool.pixi.workspace]` 的 `channels` 里直接写完整 URL,例如:
  - `https://prefix.dev/conda-forge`
  - `https://prefix.dev/nvidia`

### 4. pixi 的解算阶段不会先安装 PyPI 包,本项目不适合直接作为 path 依赖写入 `pypi-dependencies`

- 现象: 把 `vipe = { path = \".\", editable = true }` 写进 `pypi-dependencies` 后,`pixi lock` 会在解算阶段触发 metadata build。
- 结果: metadata build 会执行 `setup.py`,而 `setup.py` 需要 import torch,但此时 torch(PyPI)尚未被安装,导致 lock 失败。
- 处理策略(更省流量,也更稳):
  - pixi 只负责安装运行环境(含 torch/cu128,nvcc 等)。
  - CLI 默认用 `pixi run python -m vipe.cli.main ...` 从源码运行。
  - 如果确实需要 `vipe` 可执行入口,再显式执行一次 `pip install -e .`。

### 5. 网络不可达时的最小干预方案(代理)

- 如果确实遇到 DNS/网络策略导致的不可达,可以临时设置代理再执行 pixi 命令。
- 注意: 这会走代理流量,尽量避免反复 `pixi install`。

### 6. 宿主机的 `CUDA_HOME` 可能污染 pixi 环境,导致 JIT 编译失败

- 现象: pixi 环境里虽然有 conda 的 `nvcc`,但如果宿主机预先设置了 `CUDA_HOME=/usr/local/cuda`,
  torch 的 cpp_extension 仍可能优先使用系统 CUDA,进而出现:
  - nvcc 与 GCC 版本不兼容(例如系统 CUDA 不支持 GCC 14)
  - include/lib 指向系统路径,导致编译或链接异常
- 处理: 在执行 CLI/脚本时显式注入:
  - `PYTORCH_NVCC=$CONDA_PREFIX/bin/nvcc`
  - `CUDA_HOME=$CONDA_PREFIX/targets/x86_64-linux`
  - 建议把它们封装进 pixi tasks,避免每次手打。
