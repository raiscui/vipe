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
