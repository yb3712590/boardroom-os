# Boardroom OS V2 每轮启动提示词

当前工作目录 `/Users/bill/projects/boardroom-os`，分支 `rebuild/v2-clean-foundation`。这是 V2 clean foundation（从零实施的新基座），不是旧 runtime 的修补分支。

最终目标：实现一个 CEO-governed、contract-first、reducer-protected、evidence-backed、package-oriented、audit-readable、replayable 的 agent team framework；最终交付物是 generated project package（生成项目包），不是离散 source artifact（源码片段）。

## 启动必读（按序）

1. `AGENTS.md`
2. `doc/04-implementation/backlog.md` —— 顶部 TL;DR、Pre-flight 一致性检查、幂等更新协议；从"当前未完成工作包"入口
3. `doc/04-implementation/acceptance-criteria.md` —— 分批验收 checkbox 与本批产出
4. 当前工作包"输入文档"列出的架构文件（位于 `doc/03-architecture/`）
5. 任务目录下的 `INDEX.md`

仅当用户明确要求 forensic lookup（事故复盘）或寻找 negative test inspiration（反例测试灵感）时，才允许读取旧实现（`backend/app/core/`、`doc/refactor`、`doc/live-report`、`doc/tests` 等）。

## 不可越线的硬约束

- **Contract first**：无 active AcceptanceContract（验收合同）+ PackageContract（包合同）不写 implementation（实施）主路径
- **Reducer first**：关键状态变更必须经 reducer（状态归约器）/ validator（校验器）
- **Evidence first**：无真实 evidence（证据）不得 closeout（收尾）
- **Fail closed**：缺字段 / 缺 provider attempt（模型调用尝试记录）/ 缺 command evidence（命令证据）/ 缺 acceptance map（验收映射）/ 缺 source inventory lineage（源码清单来源链）必须失败
- **Runtime bounded**：runtime（运行时）只执行、记录、校验、投影事实，不做 CEO / Architect（架构师）/ Checker（检查者）/ Closeout 决策；workflow completed ≠ 项目完成
- **Negative tests first**：先证伪交付（fallback / placeholder / synthetic verification）无法通过，再证 happy path（正向路径）可通过
- **旧实现 abandoned by default**：不迁移、不复制、不整理；仅作 forensic 用途读取

## 代码与目录

- 主代码进 `src/boardroom_os/`，测试进 `tests/`，脚本进 `scripts/`
- 不要把 generated project workspace（生成项目工作区，`00-boardroom` / `10-project` / `20-evidence` / `30-audit`）的目录结构误用为本框架仓库结构

## 工作流

1. 读 `backlog.md` 顶部 TL;DR，找到"当前未完成工作包"
2. 执行 backlog.md 中的 **Pre-flight 一致性检查**；发现 drift（漂移）停下并报告，不擅自补齐
3. 实施时坚持 negative tests first；fake provider transport（模拟模型传输）可用，但 provider attempt count、source inventory hash、evidence verifier（证据验证器）结论、closeout gate（收尾门禁）不可被 mock 掉
4. 完成前运行与变更直接相关的验证命令，真实报告结果，不得编造通过状态
5. 完成后严格按 backlog.md 中的 **工作包完成更新协议** 六项依次更新（backlog 状态、acceptance checkbox、月度项目日志、必要时 decisions.md、必要时 INDEX.md）

## Worktree 与临时路径

若开辟 worktree 或把实现暂落在被 `.gitignore` 忽略的路径，完成后必须把有效成果合并回 `rebuild/v2-clean-foundation` 并清理临时目录。不允许把最终实现遗留在 gitignore 路径。

## 沟通

全中文。英文模块名 / 类名 / 函数名 / 路径 / 架构术语必须附中文解释，例如 "ExecutionPackage（执行包）"、"ProviderAttempt（模型调用尝试记录）"、"SourceInventory（源码清单）"。
