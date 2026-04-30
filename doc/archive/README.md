# 文档归档索引

> 说明：这里收口已经退出当前主线的旧 spec、旧计划、旧分析、旧设计、旧路线、旧任务流水、旧会话提示词和历史测试日志。默认不要把这些文件放进实现上下文；只有在需要追溯历史判断、旧口径来源或审计证据时再打开。

## 当前真相层不在这里

当前仍在用的文档，统一看：

- [../mainline-truth.md](../mainline-truth.md)
- [../refactor/planning/INDEX.md](../refactor/planning/INDEX.md)
- [../backend-runtime-guide.md](../backend-runtime-guide.md)
- [../api-reference.md](../api-reference.md)
- [../new-architecture/README.md](../new-architecture/README.md)

## 本轮归档（2026-05-01）

### 旧前端与 UI 设计材料

- [design/](design/)：旧 Boardroom UI、前端架构、组件规格、视觉稿和相关数据契约。当前 frontend 源码已删除，这些材料只保留历史设计依据。

### 旧路线、任务和工作记忆

- [roadmap/](roadmap/)：旧 roadmap reset、rationale、agent reset prompt 和 milestone timeline。当前阶段改由 refactor planning 控制面驱动。
- [task-backlog/](task-backlog/)：旧 TODO、任务 backlog、active/done/index。当前不再作为默认任务来源。
- [history/](history/)：旧 context baseline、memory log 和 detailed history。当前不再默认进入上下文。
- [todo/](todo/)：旧 completed/postponed capability 列表。当前只作历史追溯。

### integration logs

- [integration-logs/backend-live-configs/](integration-logs/backend-live-configs/)：旧图书馆 live PRD 和 013/015 配置，包含旧界面交付要求；当前不再放在 backend 根目录作为 active fixture。
- 015 长日志与最终结论仍保留在 [../tests/intergration-test-015-20260429.md](../tests/intergration-test-015-20260429.md) 和 [../tests/intergration-test-015-20260429-final.md](../tests/intergration-test-015-20260429-final.md)，作为本轮重构压力审计锚点。

### 旧重构实施资料

- [refactor-legacy/new-architecture-implementation-plan.md](refactor-legacy/new-architecture-implementation-plan.md)：旧新架构重构实施计划。
- [refactor-legacy/new-architecture-implementation-plan-template.md](refactor-legacy/new-architecture-implementation-plan-template.md)：旧实施计划模板。
- [refactor-legacy/new-architecture-refactor-session-prompt.md](refactor-legacy/new-architecture-refactor-session-prompt.md)：旧重构会话提示词。

### 一次性会话提示词

- [session-prompts/library-management-scenario-next-session-prompt.md](session-prompts/library-management-scenario-next-session-prompt.md)：极简图书馆场景 Stage 01/02 收口 handoff，包含旧机器绝对路径，只保留历史追溯意义。
- [session-prompts/dev-prompts-legacy.md](session-prompts/dev-prompts-legacy.md)：旧多客户端开发推进提示词，包含已删除 frontend 的收尾流程，不再作为当前会话模板。

## 本轮归档（2026-04-10）

### 旧 spec

- [specs/feature-spec.md](specs/feature-spec.md)：旧愿景条目总表。现在只保留历史参照意义，不再作为当前主线输入。

### 旧计划

- [plans/MVP到正式落地版本v1.0实施计划.md](plans/MVP到正式落地版本v1.0实施计划.md)：MVP 时代的实施计划，当前已过期。
- [plans/新愿景文档更新与路线重整计划.md](plans/新愿景文档更新与路线重整计划.md)：上一次路线整理的 handoff 计划，当前只保留历史决策背景。

### 旧分析 / 评估报告

- [reports/项目新愿景分析报告claude.md](reports/项目新愿景分析报告claude.md)：旧分析稿，不能再当当前路线依据。
- [reports/cto-assessment-report.md](reports/cto-assessment-report.md)：阶段性评估报告，保留历史判断，不代表现在。
