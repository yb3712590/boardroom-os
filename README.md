# Boardroom OS V2

Boardroom OS V2 是一个从干净分支重新铺陈的 agent team framework 基座。

本分支的目标不是修复旧 runtime，也不是整理旧实现资产，而是重新建立一个可信的、CEO-governed、contract-first、evidence-first 的项目生成与审计框架。

## 当前状态

```text
status: foundation-only
code status: no implementation yet
legacy status: archived history only, abandoned by default
first implementation entrypoint: src/boardroom_os/ after Phase 0 acceptance
```

## 一句话定位

Boardroom OS V2 接收自然语言需求或 PRD，由 CEO / Architect / Worker / Checker 等 agent seat 在显式 ticket graph 和合同约束下协作，最终生成一个可运行、可验证、可审计的目标项目包。

## 为什么 V2 近似另起项目

旧主链的失败不是局部 bug，而是权力结构错误：runtime 可以制造 source delivery、verification runs 和 workflow completion，CEO / architect / checker / closeout 只能在事后发现证据缺口。V2 不以旧 runtime 为实现基础。

V2 的基本原则：

1. CEO / architect 产出的合同和 ticket graph 是项目推进的治理源。
2. runtime 只执行、记录、校验、投影事实，不替代治理判断。
3. source、test、acceptance、closeout 证据必须来自真实执行或明确分类的可审计事实。
4. fallback 默认不能满足 implementation evidence。
5. 最终交付物是 generated project package，不是一组离散 source artifact。

## 新分支建议

可在现有仓库历史上创建干净 orphan 分支：

```bash
git switch --orphan rebuild/v2-clean-foundation
git rm -rf .
# 解压本基座包到仓库根目录
git add .
git commit -m "docs: establish Boardroom OS V2 clean foundation"
```

也可在全新仓库中直接解压使用。

## 入口文件

建议后续 AI 和人类先按以下顺序阅读：

1. `README.md`
2. `AGENTS.md`
3. `doc/README.md`
4. `doc/01-product/prd.md`
5. `doc/02-solution/construction-plan.md`
6. `doc/03-architecture/technical-architecture.md`
7. `doc/04-implementation/acceptance-criteria.md`
8. `doc/06-reference/legacy-boundary.md`

## 当前不做什么

- 不迁移旧 `backend/app/core/runtime.py`。
- 不整理旧模块资产图。
- 不保留旧 workflow compatibility。
- 不把 workflow completed 当作项目完成。
- 不把 synthetic verification 当作 evidence。
- 不在没有 active acceptance contract 的情况下写实现。

## 目录概览

```text
.
├── AGENTS.md
├── README.md
├── doc/
├── src/
├── tests/
├── scripts/
└── examples/
```

详细文档目录见 `doc/README.md`。

## atomic-agent 本地集成

V2-090G 起，Boardroom OS 通过外部 `atomic-agent`（原子智能体）Python package（Python 包）执行 implementation ticket（实施任务）的受控 agent loop（智能体循环）。Boardroom OS 不复制 `atomic-agent` 源码，也不要求 `atomic-agent` 作为 HTTP/gRPC service（服务）运行。

推荐本地目录布局：

```text
~/projects/boardroom-os
~/projects/atomic-agent
```

在 Boardroom OS 的 Python 环境中安装 atomic-agent：

```bash
cd ~/projects/boardroom-os
python -m pip install -e ../atomic-agent
python -c "from atomic_agent import AgentRuntimePort; print('atomic-agent import ok')"
```

`.worktrees/atomic-agent/` 仅是历史探索副本，不得用于 V2-090G 实施安装、import 验证或契约检查。

职责边界：

- `atomic-agent` 负责 agent loop（智能体循环）、tool dispatch（工具调度）、permission policy（权限策略）、event stream（事件流）和 workspace mutation（工作区变更）。
- Boardroom OS 继续负责 AcceptanceContract（验收合同）、PackageContract（包合同）、reducer（归约器）、EvidenceVerifier（证据验证器）、Checker（检查者）和 CloseoutGate（收尾门禁）。
- `AgentRunResult.status == completed`（原子智能体运行完成）不等于 `TICKET_COMPLETED`（任务完成）或 `CloseoutPackage.passed`（收尾包通过）。缺 event stream、workspace mutation、command evidence 或 source inventory lineage 时必须 fail closed（失败关闭）。

### V2-090H atomic-agent executor config

Boardroom OS 现在分离 runtime（运行时）、provider（供应商）和 role-slot（角色席位）配置：

- `config/boardroom-runtime.example.yaml` — atomic executor mode（原子执行器模式）、event/artifact roots（事件/产物根目录）、tool limits（工具限制）、budgets（预算）和 default-deny network policy（默认拒绝网络策略）。
- `config/boardroom-providers.example.yaml` — OpenAI-compatible provider profiles（OpenAI 兼容供应商配置档）。模型、base URL、timeout、stream 和 request 参数只放在这里。
- `config/boardroom-roles.example.yaml` — Boardroom seats（董事会席位）到 provider profile refs（供应商配置档引用）、skills（技能）、tools（工具）和 budget overrides（预算覆盖）的绑定。

`.env` / `.env.template` 只承载 config paths（配置路径）、secrets（密钥）和 local bootstrap paths（本地启动路径）。旧 `BOARDROOM_OPENAI_*` 模型参数在新配置路径存在时会被拒绝。
