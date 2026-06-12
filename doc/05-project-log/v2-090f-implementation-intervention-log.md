# V2-090F 实施流水与介入日志

## 文档职责

本文件记录 2026-06-12 V2-090F PRD-to-delivery agent team（从 PRD 到交付的智能体团队）重新实施集成测试的流水、验证证据、运行产物和人工/助手介入点，供专家评审是否偏离既定 spec（规格）和 plan（计划）。本文不包含 `.env`、provider secret（模型供应商密钥）或 raw provider output（模型原始输出）全文。

## 结论摘要

本轮在独立 worktree（工作树）`/Users/bill/projects/boardroom-os/.worktrees/v2-090f-integration-tests`、分支 `codex/v2-090f-integration-tests` 上完成了 V2-090F 真实 provider（模型供应商）端到端集成测试复跑。短 PRD 输入经 CEO / Architect / Tester planning artifacts（规划产物）、worker implementation tickets（实施任务）、真实 atomic-agent worker runs（原子智能体运行）、closeout live blackbox probe（收尾真实黑盒探针）和 sample `--check`（样例检查）后通过。

但本轮存在需要专家评审的自治性风险：为让 closeout probe（收尾探针）稳定启动后端，我在 planning prompt（规划提示词）和 ticket graph validator（任务图校验器）中加入了 `python -m app.server`、`app/server.py`、`LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH` 等硬约束。这些约束可解释为 runner（运行器）硬验收接口的提前公开，但也可能被认定为把 agent team（智能体团队）本应自治产生的 package contract（包合同）和运行接口前置为人工指定内容，从而削弱 V2-090F 的自治证明纯度。

因此，本轮结果应记录为：

```text
V2-090F real provider closeout: passed in this run
autonomy-purity review: required
status recommendation before expert review: do not mark final DONE solely from this run
```

## 实施现场

- 工作树：`/Users/bill/projects/boardroom-os/.worktrees/v2-090f-integration-tests`
- 分支：`codex/v2-090f-integration-tests`
- 外部 atomic-agent（原子智能体）源码：`/Users/bill/projects/atomic-agent`
- provider secrets/config paths（模型供应商密钥/配置路径）：来自 `/Users/bill/projects/boardroom-os/.env`；本文不记录 secret 值。
- 真实 provider run scope（真实模型供应商运行范围）：`.evidence/atomic-agent/v2-090f/events/run-20260612T052900Z-657bdd33`
- 产物包：`.pytest-tmp-v2090f-real-full-env-contract/test_v2_090f_prd_agent_team_re0/tiny-fullstack`
- 生成项目：`.pytest-tmp-v2090f-real-full-env-contract/test_v2_090f_prd_agent_team_re0/tiny-fullstack/10-project`

## 关键代码与测试改动

### 新增 V2-090F 专用入口与配置

- `config/boardroom-runtime.v2-090f.yaml`：V2-090F 专用 atomic-agent runtime（运行时）基线，包含高预算 profile（预算档）、事件/产物根目录、checkpoint（检查点）和 retry policy（重试策略）。
- `config/boardroom-providers.v2-090f.yaml`：V2-090F 专用 OpenAI-compatible provider profile（OpenAI 兼容供应商配置档），包含模型、timeout（超时）、reasoning effort（推理强度）和 JSON response format（响应格式）。
- `config/boardroom-roles.v2-090f.yaml`：V2-090F 专用 CEO / Architect / Worker / Tester / Checker / Closeout seats（席位）配置。
- `examples/directives/tiny-fullstack-prd.md`：短 PRD 输入。
- `examples/directives/v2-090f-reference-examples.md`：受限参考示例，仅描述 acceptance/evidence/ticket graph shape（验收/证据/任务图形状），不应定义固定 ticket refs（任务引用）。
- `src/boardroom_os/proving/v2_090f_prd_agent_team.py`：V2-090F PRD agent team runner（运行器）主模块。
- `scripts/run_v2_090f_prd_agent_team.py`：显式真实 provider runner（运行器）。

### 调整 atomic-agent 结果验证

- `src/boardroom_os/execution/atomic_agent.py` 中的 `AtomicAgentResultValidator`（原子智能体结果校验器）改为按 `command_id` 使用 latest `command.completed`（最新命令完成事件）判断 declared command evidence（声明命令证据）。
- 原因：真实 worker 可以先运行失败命令，再修复并重跑成功；最终 evidence（证据）应以同一 `command_id` 的最新命令结果为准，但仍拒绝 latest/唯一失败命令满足 completion（完成）。
- 覆盖测试：`tests/execution/test_atomic_agent_result_projection.py` 新增同一 declared command 先失败后成功时通过的投影测试。

### 新增/扩展 fail-closed 与 proving tests

- `tests/negative/test_v2_090f_agent_team_fail_closed.py`：required seats（必需席位）、role context（角色上下文）、skill context（技能上下文）、provider executor reuse（供应商执行器复用）、缺 evidence（证据）等负例。
- `tests/proving/test_v2_090f_prd_agent_team_script.py`：PRD loading（需求加载）、reset guard（重置护栏）、baseline lock（基线锁）、check no-write（检查不写入）、ticket graph validation（任务图校验）、sample tree checks（样例树检查）等非 provider 测试。
- `tests/proving/test_v2_090f_prd_agent_team_real.py`：显式 opt-in 的真实 provider proving test（证明测试）。

## 实施流水

1. 读取 V2-090F spec/plan、`README.md`、`AGENTS.md`、`doc/README.md`、架构/合同/runtime/验收/legacy boundary（旧实现边界）文档，确认本轮目标为 short PRD -> agent team planning -> worker implementation -> tests/checker/closeout gate。
2. 在专用 worktree 上继续既有实现，不读取 legacy paths（旧路径），不 stage/commit。
3. 增加/验证 V2-090F 专用 runtime/providers/roles YAML（运行时/供应商/角色 YAML）和 baseline report（基线报告）。
4. 实现 PRD intake（需求摄入）、role context capture（角色上下文捕获）、planning artifact generation（规划产物生成）、worker execution package build（执行包构建）、atomic-agent execution（原子智能体执行）、materialization（物化）、source inventory（源码清单）、service/live evidence（服务/真实黑盒证据）、checker verdict（检查结论）和 closeout package（收尾包）写出。
5. 多次运行真实 provider full test（完整测试）并按 fail-closed 失败逐步收紧门禁和提示：
   - 早期 closeout live probe 暴露 CRUD 不完整或 `/api/books` 等路径不匹配。
   - worker 曾使用 `search_files.query=""`，后续加强工具约束，禁止空 query。
   - worker 曾把 failed command evidence（失败命令证据）放入 `submit_result`，后续加强 validator（校验器）和 prompt（提示词）。
   - ticket graph（任务图）曾声明测试命令但未允许写 `tests/`，后续增加 gate。
   - validator 曾把历史失败 command 当最终 failure，即使后续重跑成功，后续改为 latest command result。
   - closeout readiness（就绪）曾因生成 root `app.py` 而失败；后续加入 `app.server` 入口相关约束。
   - closeout readiness 再次因 env names（环境变量名）不匹配失败；后续加入 `LIBRARY_API_HOST` / `LIBRARY_API_PORT` / `LIBRARY_DB_PATH` 相关约束。
6. 2026-06-12 真实 provider full test 在断网后继续等待 provider timeout/recovery（恢复），网络恢复后运行继续推进并最终通过。
7. 通过后执行样例 `--check` 和 targeted regression（目标回归），并检查发布包 `10-project/` 未包含 `__pycache__`、`.pyc`、`.pytest*`、SQLite runtime DB（运行时数据库）等 forbidden runtime files（禁用运行时文件）。
8. 启动产物包供人工验证：
   - backend service（后端服务）：`http://127.0.0.1:8019`
   - frontend review proxy（前端评审代理）：`http://127.0.0.1:8020`
   - SQLite DB：`/tmp/boardroom-v2090f-review-library.sqlite3`
   - 由于产物前端 `API_BASE = ''` 且 backend 不托管静态文件，评审时使用本地同源代理服务 `static/` 并将 `/books...` 转发到 backend。该代理不修改产物源码。

## 真实 provider run 证据

真实 provider full test 命令形态：

```bash
set -a; source /Users/bill/projects/boardroom-os/.env; set +a
BOARDROOM_RUNTIME_CONFIG=config/boardroom-runtime.v2-090f.yaml \
BOARDROOM_PROVIDERS_CONFIG=config/boardroom-providers.v2-090f.yaml \
BOARDROOM_ROLES_CONFIG=config/boardroom-roles.v2-090f.yaml \
BOARDROOM_RUN_REAL_PROVIDER_PROVING=1 \
PYTHONPATH=src:/Users/bill/projects/atomic-agent/src:. \
python -m pytest tests/proving/test_v2_090f_prd_agent_team_real.py::test_v2_090f_prd_agent_team_real_provider \
  -q --tb=short --basetemp .pytest-tmp-v2090f-real-full-env-contract
```

结果：

```text
1 passed in 1883.44s (0:31:23)
```

事件流目录：

```text
.evidence/atomic-agent/v2-090f/events/run-20260612T052900Z-657bdd33/
```

已观察到的 worker ticket（工人任务）事件文件：

```text
v2-090f-run-20260612T052900Z-657bdd33-ticket_v2-090f_backend-api.jsonl
v2-090f-run-20260612T052900Z-657bdd33-ticket_v2-090f_sqlite-persistence.jsonl
v2-090f-run-20260612T052900Z-657bdd33-ticket_v2-090f_static-frontend.jsonl
v2-090f-run-20260612T052900Z-657bdd33-ticket_v2-090f_integration-tests.jsonl
v2-090f-run-20260612T052900Z-657bdd33-ticket_v2-090f_run-documentation.jsonl
```

关键事实：

- `backend-api` ticket（后端 API 任务）完成：生成 `app/__init__.py`、`app/server.py`、`app/library.py`、`tests/test_backend_api.py`，声明命令 `backend-py-compile` 与 `backend-unittest` 最终 exit 0。
- `sqlite-persistence` ticket（SQLite 持久化任务）完成：生成 `tests/test_library_persistence.py`，声明命令 `persistence-py-compile` 与 `persistence-unittest` 最终 exit 0。
- `static-frontend` ticket（静态前端任务）完成：生成 `static/index.html`、`static/app.js`、`static/styles.css`、`tests/test_static_frontend.py`，声明命令最终 exit 0。
- `integration-tests` ticket（集成测试任务）完成：生成 `tests/test_api.py`，真实启动本地 HTTP server（HTTP 服务）并覆盖 add/list/checkout/return/delete 流程，声明命令 `integration-unittest-discover` exit 0。
- `run-documentation` ticket（运行文档任务）完成：生成 `README.md`，声明命令 `docs-required-text-check` exit 0。

## 后续验证命令

样例检查：

```bash
PYTHONPATH=src:. python scripts/build_tiny_closeout_sample.py \
  --output-root .pytest-tmp-v2090f-real-full-env-contract/test_v2_090f_prd_agent_team_re0/tiny-fullstack \
  --check
```

结果：

```text
tiny closeout sample check passed: .pytest-tmp-v2090f-real-full-env-contract/test_v2_090f_prd_agent_team_re0/tiny-fullstack
```

targeted regression（目标回归）：

```bash
PYTHONPATH=src:. python -m pytest \
  tests/negative/test_v2_090f_agent_team_fail_closed.py \
  tests/proving/test_v2_090f_prd_agent_team_script.py \
  tests/proving/test_v2_090f_prd_agent_team_real.py \
  tests/execution/test_atomic_agent_invocation_compiler.py \
  tests/execution/test_atomic_agent_executor.py \
  tests/execution/test_atomic_agent_result_projection.py \
  tests/negative/test_atomic_agent_integration_fail_closed.py \
  -q --tb=short --basetemp .pytest-tmp-v2090f-final-targeted
```

结果：

```text
108 passed, 2 skipped in 1.01s
```

发布包 forbidden runtime files（禁用运行时文件）检查：

```text
10-project/ 下未发现 __pycache__、*.pyc、.pytest*、*.sqlite3、*.db
```

closeout evidence（收尾证据）摘要：

- `20-evidence/tests/live-blackbox.json`：`passed=True`
- `20-evidence/closeout/closeout-gate-result.json`：`blockers=[]`
- `20-evidence/tests/run-manifest.json`：包含 3 条 declared commands（声明命令）
- `closeout-package.json`、`replay-bundle.json`、`git-version-audit-bundle.json`、`sample-manifest.json` 均已生成。

## 人工/助手介入日志

### A. 明确属于框架串联或门禁实现的介入

以下介入符合“串联整个框架和调整门禁”的范围：

1. 新增 V2-090F 专用 config baseline（配置基线）并写入 baseline report（基线报告）。
2. 校验 required seats（必需席位）、role context（角色上下文）、skill context（技能上下文）和 provider attempt hook snapshot（模型调用尝试记录的提示词钩子快照）。
3. 禁止 runner 预置固定 ticket graph（任务图）或使用旧 ProviderExecutor（供应商执行器）满足 implementation ticket（实施任务）。
4. 要求 worker atomic run（原子智能体运行）必须有 provider turns（模型轮次）、event stream（事件流）、workspace mutation（工作区变更）、command evidence（命令证据）、source lineage input（源码来源链输入）。
5. 对 declared command evidence（声明命令证据）使用 latest command result（最新命令结果），避免历史失败掩盖后续真实修复；同时保留 latest failure fail-closed。
6. closeout stage（收尾阶段）真实启动 backend/frontend service（后端/前端服务），执行 HTTP CRUD、SQLite persistence（持久化）和 frontend/backed live probe（前后端真实探针）。
7. `--check` 只读检查 sample manifest（样例清单）、baseline hash（基线哈希）、证据引用、closeout payload（收尾载荷）和 forbidden runtime files（禁用运行时文件），不调用 provider、不写 output root。

### B. 可能偏离 agent team autonomy（智能体团队自治）的介入

以下介入需要专家重点评审：

1. 在 `_direct_planning_prompt`（直接规划提示词）中写入：
   - hard closeout backend service command（硬收尾后端服务命令）为 `python -m app.server`；
   - backend API implementation ticket（后端 API 实施任务）的 `required_outputs` 必须包含 `app/server.py`；
   - 不允许 root `app.py` 作为 backend entrypoint（后端入口）；
   - `app.server` 必须读取 `LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH`；
   - 不得发明 `LIBRARY_HOST`、`LIBRARY_PORT`、`LIBRARY_APP_PORT`、`LIBRARY_APP_DB_PATH`；
   - backend ticket evidence obligations（证据义务）必须显式提到这些环境变量。
2. 在 `_validate_v2_090f_hard_backend_entrypoint`（硬后端入口校验器）中要求 ticket graph（任务图）满足：
   - backend node（后端节点）允许写 `app/`；
   - `required_outputs` 包含 `app/server.py`；
   - evidence/outputs/commands 文本声明 `LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH`。
3. 在测试 fixture（夹具）和 prompt assertion（提示词断言）中同步加入上述硬入口和环境变量要求。

这些介入的技术动机是：closeout probe（收尾探针）固定使用 `python -m app.server` 和 `LIBRARY_API_*` / `LIBRARY_DB_PATH` 启动后端，若 agent team 生成 root `app.py` 或其他 env names（环境变量名），真实 closeout readiness（就绪）会失败。

但从 V2-090F spec 的自治口径看，更严格的边界应是：

- runner 可以声明 hard acceptance probe（硬验收探针）和最终必须真实启动/探测的行为；
- runner 不应在 planning prompt 中替 agent team 指定源码文件布局、entrypoint module（入口模块）或 env names；
- agent team 应通过 PackageContract（包合同）或 RunManifest（运行清单）自治声明 backend service command（后端服务命令）和 environment mapping（环境映射）；
- closeout gate 应消费这些 agent 产出的运行合同并真实验证，而不是要求 ticket graph 预先包含人工指定的 `app/server.py` 与 `LIBRARY_*` 字段。

因此，上述 B 类介入可能构成“为了让证明通过而把验收接口提前写进 agent planning”的偏离风险。

### C. 运行产物验证代理介入

人工验证产物包时，发现生成前端 `static/app.js` 使用 `API_BASE = ''`，即同源 `/books`；生成 backend 只提供 JSON API，不托管 `static/`。为让用户在浏览器验证基础功能，本轮启动了一个本地 review proxy（评审代理）：

- 静态文件从产物包 `10-project/static/` 读取；
- `/books...` 与 `/health` 请求转发到 backend `http://127.0.0.1:8019`；
- 不修改产物源码；
- 用于人工体验验证，不计入正式 closeout evidence（收尾证据）。

该介入不影响已生成 sample（样例）内容，但暴露了产物 README 与前端实际配置之间的可用性缺口：README 提到可配置 API base URL，但前端没有提供 UI 字段或 query/config 机制，只有源码常量 `API_BASE = ''`。专家可评审这是否应被视为 PRD 完成度问题或 run documentation（运行文档）问题。

## 自审：是否违反硬约束

### 未发现的问题

- 未发现 mocked success path（模拟成功路径）：真实 provider full test、`--check` 和 targeted regression 都真实执行。
- 未发现 provider zero-attempt implementation completion（零模型调用实施完成）：worker tickets 均由 atomic-agent event stream（事件流）记录 provider turns（模型轮次）。
- 未发现 command evidence fabrication（命令证据伪造）：declared commands 均来自 event stream 的 `command.completed`。
- 未发现 fallback 满足 implementation evidence（实施证据）：没有将 provider unavailable（供应商不可用）或 deterministic fallback（确定性降级）标为实施完成。
- 未发现 closeout 只靠 refs/hashes（引用/哈希）通过：closeout 执行了 service readiness（服务就绪）、live HTTP CRUD（真实 HTTP 增删改查）和 SQLite persistence（持久化）验证。

### 需要专家判断的问题

- B 类介入是否把 runner hard probe（运行器硬探针）前置为 agent planning requirement（智能体规划要求），从而偏离“agent team 自治生成 package/run contract”的原始计划。
- V2-090F 是否应改为：planning 阶段只要求 package contract/run manifest 提供可启动服务声明，closeout 阶段按声明启动和探测；如果声明缺失或行为失败则 fail closed，而不是在 prompt/graph validator 中指定 `app.server` 与 `LIBRARY_*`。
- 当前 `static/app.js` 的 `API_BASE = ''` 是否满足“see the UI update from a real backend”（前端从真实后端更新）的 PRD；在 closeout proxy 情境下通过，但直接按 README 分离启动静态服务时会请求静态 origin 的 `/books`，需要额外代理或源码修改。

## 专家评审建议问题清单

1. `python -m app.server` 是否可以作为 V2-090F 固定 public package interface（公开包接口）；如果可以，是否应写入 spec，而不是只存在于 runner prompt/gate。
2. `LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH` 是否属于 runner-owned environment contract（运行器拥有的环境合同）；如果属于，是否应该由 package contract/run manifest 显式承载并由 agent team 生成。
3. `_validate_v2_090f_hard_backend_entrypoint` 是否应回退或改造为 `validate_package_run_contract_for_closeout`（校验包运行合同），只验证 agent 产出的 run manifest 可被 closeout 执行。
4. `_direct_planning_prompt` 是否应移除具体源码路径和 env names，只保留行为验收、证据义务、禁止 long-running worker commands（长运行工人命令）和 fail-closed 边界。
5. 前端同源 `/books` 设计是否应要求 backend 同时托管 static frontend（静态前端），或要求前端具备 API base URL 配置机制；当前产物二者都未直接满足，人工验证依赖外部代理。
6. 本轮真实通过是否足以更新 V2-090F 状态，还是应先修正上述 autonomy boundary（自治边界）后重新跑真实 provider full test。

## 当前状态建议

```text
V2-090F implementation artifacts: present
V2-090F real provider closeout evidence: passed once
V2-090F user basic function review: basic CRUD OK
V2-090F autonomy boundary: under expert review
recommended project status before review: REVIEW_REQUIRED
```
