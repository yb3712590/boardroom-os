# Integration Live Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跑通上个提交新增的 live 集成场景，持续观察状态，出现问题时做最小修复，直到产出可查看的 closeout 结果。

**Architecture:** 先以 `backend/tests/live/library_management_autopilot_live.py` 为唯一主入口建立基线，再围绕 `run_report.json`、`failure_snapshots/`、`ticket_context_archives/` 和运行日志做 30 秒轮询。若失败，先补能稳定复现的测试，再做单点修复，最后用新的 scenario 数据拉起可查看环境。

**Tech Stack:** Python 3.12, FastAPI, pytest, React, Vite, SQLite

---

### Task 1: 建立基线运行

**Files:**
- Modify: `docs/superpowers/plans/2026-04-10-integration-live-closeout.md`
- Inspect: `backend/tests/live/library_management_autopilot_live.py`
- Inspect: `doc/backend-runtime-guide.md`

- [ ] **Step 1: 确认 live 入口和必需环境变量**

Run: `sed -n '1,260p' backend/tests/live/library_management_autopilot_live.py`
Expected: 能看到 `BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_BASE_URL`、`BOARDROOM_OS_PROVIDER_OPENAI_COMPAT_API_KEY`

- [ ] **Step 2: 记录 closeout 验收口径**

Expected:
- workflow `status=COMPLETED`
- workflow `current_stage=closeout`
- ticket 数量不少于 30
- `run_report.json` 已写出

- [ ] **Step 3: 启动 live 场景**

Run: `cd backend && ./.venv/bin/python -m tests.live.library_management_autopilot_live --clean`
Expected: 进入长测，最终输出 JSON 报告或失败快照路径

### Task 2: 30 秒轮询观察

**Files:**
- Inspect: `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- Inspect: `backend/data/scenarios/library_management_autopilot_live/failure_snapshots/`
- Inspect: `backend/data/scenarios/library_management_autopilot_live/ticket_context_archives/`

- [ ] **Step 1: 每 30 秒轮询一次关键状态**

Run:
- `find backend/data/scenarios/library_management_autopilot_live -maxdepth 2 -type f | sort`
- `ls -lt backend/data/scenarios/library_management_autopilot_live/failure_snapshots`

Expected: 能看到 run report、失败快照或上下文归档持续变化

- [ ] **Step 2: 记录 stall / timeout / assertion 失败点**

Expected: 对每个失败点保留根因、复现方式、最小修复方案

### Task 3: 最小修复

**Files:**
- Test: `backend/tests/...`
- Modify: `backend/app/...`

- [ ] **Step 1: 先写失败测试，证明 root cause**

Run: 针对具体 bug 选择最小 `pytest` 命令
Expected: 新增或调整的测试先失败，而且失败原因对得上 bug

- [ ] **Step 2: 写最小实现**

Expected: 只修当前 root cause，不顺手重构

- [ ] **Step 3: 回跑最小测试和 live 场景**

Run:
- `cd backend && ./.venv/bin/python -m pytest <targeted-tests> -q`
- `cd backend && ./.venv/bin/python -m tests.live.library_management_autopilot_live --clean`

Expected: 目标测试通过，live 场景进入 closeout

### Task 4: 可查看收口

**Files:**
- Inspect: `backend/data/scenarios/library_management_autopilot_live/run_report.json`
- Inspect: `backend/data/scenarios/library_management_autopilot_live/artifacts/`

- [ ] **Step 1: 用成功 scenario 数据拉起后端**

Run: `cd backend && BOARDROOM_OS_DB_PATH=... BOARDROOM_OS_RUNTIME_PROVIDER_CONFIG_PATH=... ./.venv/bin/uvicorn app.main:app --reload`
Expected: 用户可查看对应 workflow 投影和产物

- [ ] **Step 2: 如前端需要，拉起前端查看页**

Run: `cd frontend && npm run dev`
Expected: 浏览器可查看 Dashboard / Inbox / Review Room

- [ ] **Step 3: 验证并输出 closeout**

Run:
- `cd backend && ./.venv/bin/python -m pytest <targeted-tests> -q`
- `cd backend && ./.venv/bin/python -m tests.live.library_management_autopilot_live --clean`

Expected: fresh 证据表明 bug 已修、closeout 已产出、环境可查看
