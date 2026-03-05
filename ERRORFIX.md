# ERRORFIX

## 2026-03-05

### 问题

- 运行 `vipe infer -p lyra` 时,在构建关键帧深度模型阶段崩溃.
- 报错信息为:
  - `RuntimeError: moge is not found in the environment ...`

### 根因

- `vipe/priors/depth/moge.py` 固定 import `moge.model.v1` 并写死加载 v1 checkpoint(`Ruicheng/moge-vitl`).
- 当环境里安装的是 MoGe v2,或者 pipeline 想用 v2 checkpoint 时:
  - 轻则 import 路径/版本不匹配,被误判为 "moge 未安装".
  - 重则出现 v1/v2 结构不匹配,加载阶段直接崩溃(lyra 侧已遇到 `getattr()` 的 TypeError).

### 修复

- `make_depth_model(...)` 支持 `moge-v1`/`moge-v2`,并且只按第一个 "-" 分割参数,避免多段子参数导致解包报错.
- `MogeModel` 按版本选择对应实现并加载对应模型:
  - v1: `moge.model.v1.MoGeModel` + `Ruicheng/moge-vitl`
  - v2: `moge.model.v2.MoGeModel` + `Ruicheng/moge-2-vitl`
- `configs/pipeline/lyra.yaml` 默认改为 `keyframe_depth: moge-v2`.

### 验证(省流量)

- 语法检查:
  - `python -m py_compile vipe/priors/depth/__init__.py vipe/priors/depth/moge.py`
- import 级验证(不触发权重下载):
  - `import moge.model.v1` 和 `import moge.model.v2` 均可用.
  - `_normalize_moge_version(...)` 对空值默认返回 `v2`.

## 2026-03-05

### 问题

- 运行 `vipe infer -p lyra` 时,SLAM 已完成,在后处理阶段崩溃.
- 报错信息为:
  - `RuntimeError: PytorchStreamReader failed reading zip archive: failed finding central directory`

### 根因

- Video-Depth-Anything 的权重文件缓存损坏/不完整(典型是下载被中断或网络抖动).
- 旧实现用 `torch.hub.load_state_dict_from_url` 直接复用缓存文件,一旦缓存坏了就会稳定复现崩溃.

### 修复

- `vipe/priors/depth/videodepthanything/__init__.py` 增加"损坏缓存自动恢复"逻辑:
  1. 先尝试复用 `torch.hub` 的本地缓存(可用就不下载,省流量).
  2. 如果检测到缓存损坏,自动删除坏文件.
  3. 优先用 `huggingface_hub.hf_hub_download` 下载并加载(更稳的缓存/下载语义).
  4. 如果环境缺少 `huggingface_hub`,回退到 `torch.hub.load_state_dict_from_url`,并在损坏时清缓存后重试 1 次.

### 验证(不走真实下载)

- `python -m py_compile vipe/priors/depth/videodepthanything/__init__.py`
- 用 monkeypatch 模拟:
  - 第一次加载抛 "failed finding central directory"
  - 断言缓存文件会被删除,并且第二次能成功返回 state_dict
