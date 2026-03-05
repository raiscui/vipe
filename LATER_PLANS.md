# LATER_PLANS

## 2026-03-04

- 暂无

## 2026-03-05

- 可选: 将 conda 侧 CUDA 版本进一步 pin 到 12.8(例如显式加入 `cuda-version=12.8`),让 conda 工具链与 torch `cu128` 更一致。
- 可选: 为 CI 增加 pixi 安装与基础检查,例如 `pixi lock --check` + `pixi install --locked` + 最小 smoke command。
- 可选: 优化 CLI 的 import 链路,避免仅执行 `--help` 就触发 JIT 编译扩展(体验更好,也更省时间)。
