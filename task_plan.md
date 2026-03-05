# 任务计划: 将环境改为 pixi 管理

## 目标

把项目的"可复现运行环境"从"conda env + pip requirements"迁移为"pixi + pixi.lock"。
最终效果是: 新人只需要执行 `pixi install` 就能把依赖装好,并且能用 `pixi run ...` 直接运行 `vipe` CLI 和 `run.py`。

## 方案备选(需要做出选择)

### 方案A(推荐): 以 `pyproject.toml` 作为 pixi manifest

- 做法: 在现有 `pyproject.toml` 里新增 `[tool.pixi.*]` 配置,不新增 `pixi.toml`。
- 优点: 配置集中,改动更少,更符合 Python 项目习惯,也符合 pixi 官方推荐用法。
- 风险/代价: 需要处理"本项目安装时会编译 CUDA 扩展,且依赖 torch"这类构建顺序问题(通过 `no-build-isolation` 解决)。

### 方案B: 新增 `pixi.toml` 作为 pixi manifest

- 做法: 新增 `pixi.toml` 并迁移 conda/pypi 依赖到里面,`pyproject.toml` 只保留打包信息。
- 优点: pixi 配置更独立,不影响 Python packaging 元数据。
- 风险/代价: 文件新增和维护成本更高,且项目已有 `pyproject.toml` 时容易形成"双入口"困惑。

## 阶段

- [x] 阶段1: 建立迁移计划与记录
- [x] 阶段2: 研究 pixi 配置要点
- [x] 阶段3: 落地 pixi 配置与文档
- [x] 阶段4: 生成 lock 并验证可用
- [x] 阶段5: 收尾记录与后续建议

## 关键问题

1. 继续保留 `envs/base.yml` 和 `envs/requirements*.txt` 吗?
2. torch 的安装源需要 CUDA 版本专用 index, pixi 要怎么写才稳定?
3. 本项目安装会编译 CUDAExtension,如何保证 pixi 安装顺序正确(先装 torch,再装 vipe)?

## 做出的决定

- [决定] 默认采用"方案A": 在 `pyproject.toml` 里添加 `[tool.pixi.*]`。
  - [理由] 现有项目已使用 `pyproject.toml`,新增 `pixi.toml` 反而增加入口数量,维护成本更高。
- [决定] pixi 默认不把本项目作为 `pypi-dependencies` 的 path 依赖安装,改为"从源码运行 + 可选再安装"。
  - [理由] pixi 的 conda-first 解算阶段不会先安装 PyPI 包,而 `setup.py` 的 metadata 阶段会 import torch,会导致 `pixi lock` 失败。

## 遇到错误

- 2026-03-04: `pixi lock` 访问默认 conda channel 时 DNS 解析失败(无法解析 `conda.anaconda.org`)。
  - 决议: 将 pixi channels 改为 prefix.dev 的完整 URL,避免依赖 `conda.anaconda.org`。
- 2026-03-04: `pixi lock` 需要构建本项目 metadata 时,因环境里尚未安装 torch 导致失败(`Pytorch not found`)。
  - 决议: 从 pixi 的 `pypi-dependencies` 中移除本项目 path 依赖,改为提供 `pixi run infer`/`pixi run vipe ...` 的源码运行方式,并提供 `install-vipe` task 作为可选步骤。
- 2026-03-05: `pixi lock` 访问 `pypi.org` 时出现 DNS 解析失败。
  - 决议: 在需要联网的 pixi 操作上临时设置代理(`https_proxy/http_proxy/all_proxy`),成功生成 `pixi.lock`。
- 2026-03-05: 默认继承宿主机 `CUDA_HOME=/usr/local/cuda`,导致 torch JIT 编译扩展时误用系统 nvcc,报 "unsupported GNU version"。
  - 决议: 增加 pixi task,在运行 vipe CLI / run.py 时显式注入 `CUDA_HOME` 与 `PYTORCH_NVCC` 指向 pixi 环境内的 CUDA 工具链。

## 状态

**已完成**: pixi 配置、lock 生成、安装验证、文档同步、以及常见网络/CUDA 工具链问题的兜底都已落地。

### 2026-03-05

- 完成了什么: `pyproject.toml` 增加 `[tool.pixi.*]` 配置与 tasks,生成 `pixi.lock`,更新 README,并完成 `pixi install --locked` + `pixi run --locked ...` 的最小可用验证。
- 交付物: `pixi.lock` + README 安装说明 + pixi tasks(含 CUDA_HOME/PYTORCH_NVCC 兜底)。

### 2026-03-05

- Git 提交与推送: 已提交并推送到 `https://github.com/raiscui/vipe`。
- 提交范围: 仅提交 pixi 迁移相关文件(包含 `pixi.lock`),未包含本地的 `.vscode/settings.json` 变更与四文件上下文记录(避免污染上游仓库历史)。

### 2026-03-04

- 正在做什么: 研究 pixi 在 `pyproject.toml` 里的配置映射,以及 PyPI options(尤其是 `no-build-isolation`)。
- 为什么这样做: 本项目 `setup.py` 安装时会编译 CUDAExtension,需要 torch 与 nvcc 先就绪,否则安装会失败。
- 接下来要做什么: 在 `pyproject.toml` 里加入 `[tool.pixi.*]` 配置,再更新 README 安装说明为 `pixi install`。

### 2026-03-04

- 正在做什么: 开始把 `envs/base.yml` 与 `envs/requirements.in` 的内容落到 `pyproject.toml` 的 `[tool.pixi.*]`。
- 为什么这样做: 让 `pixi install` 一步完成 conda 依赖 + PyPI 依赖 + 本项目 editable 安装,替代手工 conda/pip 步骤。

### 2026-03-04

- 正在做什么: 准备运行 pixi 解算与安装,生成 `pixi.lock` 并做一次最小可用性验证。
- 为什么这样做: 环境迁移的价值是"可复现",必须产出 lock 并验证命令能跑起来,否则只是改了配置但不可用。

### 2026-03-04

- 发生了什么: `pixi lock` 在拉取 `conda-forge` repodata 时出现 DNS error,无法解析 `conda.anaconda.org`。
- 我将怎么处理: 把 `[tool.pixi.workspace].channels` 改成 `https://prefix.dev/...` 的 channel URL,再重新 lock。

### 2026-03-05

- 发生了什么: `pixi lock` 在构建本项目 metadata 时缺少 torch,导致解算失败。
- 我将怎么处理: pixi 先只管理运行环境(含 torch/cu128),默认从源码运行 CLI,需要 `vipe` 可执行入口时再 `pixi run install-vipe`。

### 2026-03-05

- 发生了什么: `pixi lock` 访问 PyPI 时出现 DNS 失败,但本机可用代理(`127.0.0.1:7897`)。
- 我将怎么处理: 文档里增加"代理仅在不可达时临时开启"的说明,并尽量减少重复 install/lock 以节省流量。

### 2026-03-05

- 发生了什么: 本机环境 `CUDA_HOME=/usr/local/cuda`,与 pixi 环境的 GCC 版本不兼容,导致 JIT 编译失败。
- 我将怎么处理: 通过 pixi tasks 固定 `CUDA_HOME`/`PYTORCH_NVCC`,确保 JIT 走 pixi 环境的 nvcc(12.9)与 headers。

### 2026-03-05

- 正在做什么: 增加"无需手动 `pixi run` 也能直接 `vipe ...`"的安装方式(全局入口脚本)。
- 为什么这样做: `pixi run install-vipe` 只把入口装进 `.pixi/envs/default/bin`,默认不在 PATH,并且直接跑可能继承错误的 `CUDA_HOME`。
- 接下来要做什么: 新增 `scripts/pixi/install_cli.sh`/`scripts/pixi/uninstall_cli.sh`,补充 pixi tasks,并更新 README 说明。

### 2026-03-05

- 完成了什么: 已新增 `install-cli`/`uninstall-cli`(全局 wrapper),并更新 README 使用说明。
- 代码交付: 已推送到 `https://github.com/raiscui/vipe`(commit: `126a02b`)。

### 2026-03-05

- 微调: `install_cli.sh`/`uninstall_cli.sh` 兼容 `--` 分隔符,避免 `pixi run install-cli -- --bin-dir ...` 这类写法直接报错。
- 代码交付: 已推送到 `https://github.com/raiscui/vipe`(commit: `6edb16e`)。

### 2026-03-05

- 微调: `install-cli`/`uninstall-cli` 的默认安装目录改为 `/usr/local/bin`(更常见地已在 PATH 中),并增加权限不足时的明确提示与处理建议。
- 代码交付: 已推送到 `https://github.com/raiscui/vipe`(commit: `198f67b`)。

### 2026-03-05

- 问题修复: 发现全局 wrapper 在执行时会 `cd` 到仓库目录,导致用户传入的相对路径被错误解析(例如在 `/workspace/lyra` 运行却去找 `/workspace/vipe/./assets/...`)。
- 修复方式: wrapper 不再切换 cwd,改为通过 `PYTHONPATH` 注入源码路径以确保可导入,从而让相对路径始终基于"调用 vipe 的当前目录"解析。
- 代码交付: 已推送到 `https://github.com/raiscui/vipe`(commit: `2f3b98c`)。

### 2026-03-05

- 发生了什么: 在 pixi 环境中 `transformers==5.3.0` 时,`BertModel` 已移除 `get_head_mask` 方法,导致 GroundingDINO 的 `BertModelWarper` 初始化直接崩溃(`AttributeError: 'BertModel' object has no attribute 'get_head_mask'`)。
- 我将怎么处理: 在 `BertModelWarper` 内实现兼容版 `get_head_mask`(复刻旧 transformers 的 head_mask 处理逻辑),避免依赖已被移除的 API,并用一个最小自测确保 forward 可跑。

### 2026-03-05

- 完成了什么: 已在 `BertModelWarper` 内实现 `get_head_mask`,并用 try/except 兼容 `get_extended_attention_mask` 在 transformers 4.x/5.x 的不同签名。
- 验证方式: 用随机初始化的 `BertModel` 做最小 forward 自测,确认 wrapper 不再因 API 变动崩溃。

### 2026-03-05

- 配置调整: 将 git 的 `origin` remote 的 push URL 改为 `https://github.com/raiscui/vipe.git`,让 `git push` 默认推送到 fork(`raiscui/vipe`),同时 `git pull` 仍从上游(`nv-tlabs/vipe`)获取更新。

### 2026-03-05

- 发生了什么: 用户在设置 `all_proxy=socks5://...` 后运行 `vipe infer`,huggingface_hub 通过 httpx 初始化代理时报错:
  - `ImportError: Using SOCKS proxy, but the 'socksio' package is not installed.`
- 我将怎么处理: 将 `socksio` 加入 pixi 的 PyPI 依赖,并更新 `pixi.lock`,确保在 SOCKS 代理场景下可用。
