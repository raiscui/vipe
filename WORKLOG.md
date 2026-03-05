# WORKLOG

## 2026-03-04

- 初始化: 采用"文件上下文工作模式",创建 `task_plan.md` / `notes.md` / `WORKLOG.md` / `LATER_PLANS.md`。

## 2026-03-05

- 环境迁移: 在 `pyproject.toml` 中落地 pixi 配置,用 pixi 替代 `envs/base.yml` + `pip install -r envs/requirements.txt` 的手工流程。
- 依赖锁定: 生成 `pixi.lock`,并完成一次 `pixi install --locked` 的安装验证(包含 torch/cu128)。
- 网络兼容: 遇到 DNS/网络不可达时,使用代理环境变量临时兜底,避免反复 install/lock 浪费流量。
- CUDA 工具链一致性: 发现宿主机 `CUDA_HOME=/usr/local/cuda` 会污染 JIT 编译,增加 pixi tasks 显式注入 `CUDA_HOME` 与 `PYTORCH_NVCC` 指向 pixi 环境内的 nvcc/headers,确保可复现编译。
- 文档同步: 更新 README 安装方式为 pixi,并提供 legacy conda+pip 作为备选。
- 代码交付: 提交并推送到 `https://github.com/raiscui/vipe`(commit: `5205f37`),仅包含 pixi 迁移相关文件。

## 2026-03-05

- 直接 CLI: 新增 `pixi run install-cli`/`pixi run uninstall-cli`,在不手动进入 pixi 环境的情况下也能直接执行 `vipe ...`(通过全局 wrapper 固定使用 `.pixi/envs/default`)。
- 体验优化: `install_cli.sh`/`uninstall_cli.sh` 兼容 `--` 分隔符,减少 pixi run 传参时的歧义与踩坑。
- 默认路径: 将 wrapper 默认安装目录改为 `/usr/local/bin`,并在权限不足时给出明确提示,降低首次使用的困惑。
- 修复路径解析: wrapper 不再 `cd` 到仓库目录,相对路径改为按用户调用 vipe 时的当前目录解析,避免跨仓库/跨目录运行时误判 "文件不存在"。
- 兼容 transformers 5.x: 修复 GroundingDINO 的 `BertModelWarper` 对已移除 API(`get_head_mask`)的依赖,并适配 `get_extended_attention_mask` 的新签名,避免运行期崩溃。
- Git 默认推送: 设置 `origin` 的 push URL 为 `https://github.com/raiscui/vipe.git`,避免误推到上游仓库导致 403,并保持 pull 仍从上游获取更新。
- SOCKS 代理兼容: 增加 `socksio` 到 pixi PyPI 依赖并更新 lock,修复 `all_proxy=socks5://...` 场景下 huggingface_hub/httpx 报 "socksio not installed"。
