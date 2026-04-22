# 下一轮会话提示词：继续收口极简图书馆场景测试

你在 `/Users/bill/projects/boardroom-os` 继续完成“极简图书馆场景阶段测试”的本地 material 与主线收口。

先读这些文件，再动手：

- `/Users/bill/projects/boardroom-os/backend/app/core/command_handlers.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/workflow_progression.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/workflow_controller.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/ceo_proposer.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/ceo_executor.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/requirement_elicitation.py`
- `/Users/bill/projects/boardroom-os/backend/app/core/approval_handlers.py`
- `/Users/bill/projects/boardroom-os/backend/tests/scenario/_runner.py`
- `/Users/bill/projects/boardroom-os/backend/tests/scenario/_seed_builder.py`
- `/Users/bill/projects/boardroom-os/backend/data/scenario-tests/library-management.toml`

当前已知状态：

- provider 模块本身可用
  - `provider_openai_compat` 直连验证通过
  - `ceo_action_batch` 在 `strict=true` 下会稳定触发上游 `502 upstream_error`
  - 已把 CEO shadow 的 `ceo_action_batch` 调用改成 `strict=false`
- Stage 06 seed builder 已补齐
  - 先 upsert runtime provider
  - 校验 `ticket-lease` / `ticket-start`
  - `retry_budget = 0`
  - 生成 git receipts
  - 生成最小 ticket context archive
- prepared seed runner 顺序问题已修
  - `run_configured_stage()` 不会再在 driver 初始化前因为 snapshot 校验直接炸
- project-init 老逻辑已收一轮
  - `architecture_brief` kickoff 不再默认走 `frontend_engineer_primary`
  - 缺对应治理角色时，controller 会先返回 `HIRE_EMPLOYEE`
  - CEO direct hire 这条路径已作为主线的一部分参与 project-init / governance kickoff
  - requirement elicitation review pack 已补 `source_graph_node_id`

这轮最重要的现场事实：

- Stage 01 新 run 已经不再卡 provider 502
- 新 run 能看到：
  - workflow `current_stage = plan`
  - `emp_architect_governance` 已注册
  - `tkt_wf_<id>_ceo_architecture_brief` 已起跑
- 但 Stage 01 还没被真正跑到 checkpoint 并冻结成 Stage 02 seed
- `stage_02_outline_to_detailed_design` seed 目录目前仍不存在

当前优先目标：

1. 先把 Stage 01 真正跑到 checkpoint
2. 一旦通过，立刻冻结成 Stage 02 seed
3. 回写 `/Users/bill/projects/boardroom-os/backend/data/scenario-tests/library-management.toml` 的 `seeds.stage_02_outline_to_detailed_design.workflow_id`
4. 再继续 Stage 02 -> Stage 05 的真实 freeze 链路
5. 最后再回头看 Stage 06 从 `review` 推进到 `closeout` 的真实 runtime 阻塞

严格要求：

- 不要改模板，只改本地 TOML
- 不要删 `backend/tests/live/*`
- 不要引入新依赖
- 用 `apply_patch` 改文件
- 默认中文输出
- 不要再停留在方案层，优先跑通 Stage 01 -> Stage 02 freeze

建议先跑这些命令确认现场：

```bash
cd /Users/bill/projects/boardroom-os/backend

/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m pytest \
  /Users/bill/projects/boardroom-os/backend/tests/test_scenario_config.py \
  /Users/bill/projects/boardroom-os/backend/tests/test_scenario_seed_copy.py \
  /Users/bill/projects/boardroom-os/backend/tests/test_scenario_runner.py \
  /Users/bill/projects/boardroom-os/backend/tests/test_scenario_seed_builder.py -q

/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m pytest \
  /Users/bill/projects/boardroom-os/backend/tests/test_workflow_progression.py \
  /Users/bill/projects/boardroom-os/backend/tests/test_ceo_scheduler.py -k "project_init or architect_hire or required_governance_ticket_plan or non_strict_ceo_action_batch_schema or live_provider_to_hire_architect" -q

/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m pytest \
  /Users/bill/projects/boardroom-os/backend/tests/test_workflow_autopilot.py::test_autopilot_project_init_auto_resolves_requirement_elicitation_and_restarts_with_architecture_brief \
  /Users/bill/projects/boardroom-os/backend/tests/test_workflow_autopilot.py::test_standard_workflow_still_waits_at_requirement_elicitation_review -q

BOARDROOM_OS_SCENARIO_TEST_ENABLE=1 \
BOARDROOM_OS_SCENARIO_TEST_CONFIG_PATH=/Users/bill/projects/boardroom-os/backend/data/scenario-tests/library-management.toml \
/Users/bill/projects/boardroom-os/backend/.venv/bin/python -m pytest \
  /Users/bill/projects/boardroom-os/backend/tests/scenario/test_library_management_stage_01_requirement_to_architecture.py -q
```

如果 Stage 01 还没返回，不要干等：

- 直接看最新 run 目录：
  - `/Users/bill/projects/boardroom-os/backend/data/scenario-tests/library-management/runs/stage_01_requirement_to_architecture`
- 看 `runtime/state.db`
- 看 `audit/records/timeline/tick_*.json`
- 明确它卡在：
  - provider
  - employee hire
  - architecture_brief runtime
  - maker/checker
  - 还是 checkpoint 断言

成功标准：

- Stage 01 真实通过
- `stage_02_outline_to_detailed_design` seed 真落盘
- 本地 TOML 真回写 `workflow_id`
- 结果里明确区分：
  - `seed material 缺失`
  - `provider/key 问题`
  - `build-stage06 生成逻辑不够`
  - `runtime / workflow 真实行为问题`
