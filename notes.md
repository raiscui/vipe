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

## 2026-03-05: MoGe v2 适配(vipe)

### 现象

- `vipe infer -p lyra` 在构建关键帧深度模型阶段报错,提示 `moge is not found in the environment`.
- 在 lyra 的经验里,当用 v1 的 `MoGeModel` 去加载 v2 checkpoint(例如 `Ruicheng/moge-2-vitl`)时,还会触发:
  - `TypeError: getattr(): attribute name must be string`

### 根因(推断 + 代码证据)

- `vipe/priors/depth/moge.py` 当前写死:
  - import: `from moge.model.v1 import MoGeModel`
  - checkpoint: `Ruicheng/moge-vitl`
- 当环境里安装的是 MoGe v2 代码,或用户想用 v2 checkpoint 时,上述固定写法会导致:
  - import 路径/版本不匹配(表现为 import 失败,被当作 "moge 未安装")
  - 或 v1/v2 结构不匹配(表现为 getattr 的 TypeError)

### 方案

- 在 `make_depth_model(...)` 支持 `moge-v1`/`moge-v2` 这种可读的选择方式。
- `MogeModel` 内部按 version 选择 `moge.model.v1` 或 `moge.model.v2`,并分别加载:
  - v1: `Ruicheng/moge-vitl`
  - v2: `Ruicheng/moge-2-vitl`
- `configs/pipeline/lyra.yaml` 默认切换为 `keyframe_depth: moge-v2`。

### 最小验证(省流量)

- `python -m py_compile` 覆盖改动文件,确保语法正确。
- `python -c "import moge; import moge.model.v2"` 做 import 级验证,避免触发权重下载。

## 2026-03-05: Video-Depth-Anything 权重缓存损坏(vipe)

### 现象

- `vipe infer -p lyra` 在 SLAM 跑完后进入后处理阶段崩溃.
- 堆栈显示在加载 Video-Depth-Anything 权重时失败:
  - `RuntimeError: PytorchStreamReader failed reading zip archive: failed finding central directory`

### 根因

- 本地缓存的 `video_depth_anything_vitl.pth` 文件不完整/损坏.
- 典型触发场景:
  - 网络抖动/代理不稳定
  - 下载过程中进程被中断(例如 Ctrl+C/kill)
  - 结果是缓存文件已落盘,但内容不完整,下次直接复用缓存就必崩.

### 修复策略(省流量优先)

1. 优先复用 `torch.hub` 已有缓存:
   - 如果缓存文件可正常 `torch.load`,直接用,不重新下载.
2. 如果检测到缓存损坏:
   - 自动删除坏缓存,然后改用 `huggingface_hub.hf_hub_download` 下载(更稳,支持更好的缓存语义).
3. 兜底:
   - 极简环境缺少 `huggingface_hub` 时,回退到 `torch.hub.load_state_dict_from_url`,并在损坏时自动清理缓存后重试 1 次.
