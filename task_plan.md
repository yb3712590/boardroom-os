# Task Plan

## Goal

在 `doc/` 下落地一套可续跑的新架构重构计划资产：

- 计划模板
- 可直接续跑的主计划
- 新会话专用提示词
- 文档入口更新

## Phases

| Phase | Status | Notes |
|---|---|---|
| 初始化工作记忆 | completed | 已确认目录结构、现有提示词和 `new-architecture` 入口 |
| 创建计划模板和主计划 | completed | 已写入 `doc/refactor/` |
| 创建配套提示词 | completed | 已写入 `doc/refactor/` |
| 更新文档索引并验证 | completed | 已更新 `doc/README.md` 并验证目标文件存在 |

## Decisions

- `doc/new-architecture/**` 作为架构决策文档，默认只读。
- 计划资产放在 `doc/refactor/`，避免和现有设计文档混在一起。
- 同时提供模板和主计划，减少第一次实施前的额外整理动作。

## Errors Encountered

| Error | Attempt | Resolution |
|---|---|---|
| None | 0 | N/A |
