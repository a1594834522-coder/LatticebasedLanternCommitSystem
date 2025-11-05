# Repository Guidelines

## 项目结构与模块组织
- `lantern_zk/`：核心 RLWE 承诺与证明逻辑，按 `core/commitments/params/rules/proofs` 模块划分，新增算法请保持同级子模块结构。
- `backend/`：FastAPI 服务，`routers/` 暴露 REST 与 SSE 接口，`services/` 处理会话与 Redis 交互，`events/` 定义消息流。
- `frontend/`：Streamlit 三端界面；共用状态存放在 `state.py`，API 适配器集中在 `api.py`。验证者创建会话后，证明者/协调面板可通过列表直接加入；证明者端只需提交向量后由后端生成证明包。
- `tests/` 与 `backend/tests/`：Pytest 用例，涵盖 CLI、规则 DSL 与后端契约；示例数据置于仓库根目录的 JSON 文件。
- `docs/`：架构、拓展、API 参考文档；新增特性时同步更新相应概览。

## 构建、测试与开发命令
- 快速自检：`sage -python quickstart.py` 核对 Sage 与依赖是否就绪。
- 演示流程：`sage -python demo_lantern_system.py` 或运行 `lantern_commit_system.py prover` 生成样例证明。
- 后端服务：`docker compose up --build` 启动 API + Redis；本地调试可用 `uvicorn backend.main:app --reload`.
- 前端面板：`BACKEND_URL=... streamlit run frontend/prover_app.py`（其它端口对应 verifier/dashboard）。
- 单元与集成测试：`sage -python -m pytest tests` 覆盖核心库；`pytest backend/tests` 校验 API 行为。

## 协作流程提示
- 验证者创建会话后，可通过 `GET /sessions` 被三个前端自动发现，无需手动分发会话 ID。
- 证明者只需在前端提供向量，后端在获得验证者同意后会负责生成承诺与证明，过程中不会将向量在 UI 中展示。
- 后端生成完成后会依次触发 `vector_submitted`、`proof_started`、`proof_completed/failed` 事件，协调面板可实时观测。
- 需要重新校验时调用 `POST /sessions/{id}/execute`，会在服务器端重新跑一次证明流程。

## 代码风格与命名约定
- Python 使用 4 空格缩进、PEP 8 命名；公共接口需添加类型注解与 docstring，复杂流程辅以短行内注释。
- 模块命名采用蛇形，类使用帕斯卡命名，CLI 子命令与 JSON 字段保持全小写连字符或下划线一致。
- 库级常量放入 `params.py` 或 `config.py`，避免在脚本中硬编码安全参数。
- 提交前运行 `python -m compileall lantern_zk backend frontend` 以捕获语法错误，建议本地启用 `ruff` 或 `flake8` 静态检查。

## 测试准则
- 新增规则或证明路径时至少补充一个 CLI 流程用例（参考 `tests/test_cli_workflow.py`），并更新 `fakeredis` 场景覆盖后端缓存。
- 测试文件命名遵循 `test_<模块>.py`，用例函数命名 `test_<行为>`；异步 API 使用 `pytest.mark.asyncio`.
- 若引入重型样例数据，请放入 `tests/fixtures/` 并在测试里使用懒加载，避免拖慢默认运行时间。
- 目标是在关键加密模块维持高覆盖率；若因 Sage 依赖无法在 CI 运行，请在 PR 中说明手工验证方式。

## 提交与拉取请求指南
- Commit 信息使用英文祈使句开头（例如 `feat: add prover transcript export`），主题行 ≤ 72 字符，必要时添加解释性正文。
- 每个 PR 需：概述意图、列出验证步骤（命令输出可文字描述）、关联 Issue 或说明产生动机，并附上影响范围。
- 变更前后如涉及接口或 CLI 参数调整，必须同步更新 `docs/` 与示例 JSON。
- 自检通过后再请求评审；若依赖外部服务（Redis/Sage），提供复现所需的 `.env` 修改或容器命令。

## 安全与配置提示
- `.env` 中的 `API_TOKEN`、`DEFAULT_PROOF_SEED` 等敏感字段禁止写入版本库；本地调试使用 `.env.local`。
- 任何影响密码学参数的修改需在 PR 描述中明确安全假设，并附加链接到参考论文或内部评审记录。
- 在演示或集成环境中启用 Docker 时，请确保 Redis 使用私有网络或访问控制，避免对外暴露 6379 端口。
