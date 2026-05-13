# Generated Project Workspace

## 文档职责

本文件定义 Boardroom OS V2 生成目标项目包时应创建的 workspace 模板。它不是本 repo 自身的目录结构。

## 基本结构

```text
workspace/<workflow_id>/
├── 00-boardroom/
│   ├── workflow/
│   ├── tickets/
│   ├── agents/
│   └── process-audit/
├── 10-project/
│   ├── AGENTS.md
│   ├── README.md
│   ├── package-contract.json
│   ├── run-manifest.json
│   ├── docs/
│   ├── src/ or backend/frontend/
│   └── tests/
├── 20-evidence/
│   ├── tests/
│   ├── integration/
│   ├── git/
│   ├── source-inventory/
│   └── closeout/
└── 30-audit/
    ├── process-audit.md
    ├── timeline.json
    ├── decision-log.md
    ├── agent-context-index.json
    ├── evidence-map.json
    ├── git-version-audit.md
    └── replay-bundle-report.json
```

## 00-boardroom

记录 Boardroom OS 对此生成项目的治理材料。

包括：

- workflow metadata；
- ticket graph snapshots；
- CEO decisions；
- seat assignments；
- execution package refs；
- raw provider attempt refs；
- checker verdicts。

## 10-project

真正交付给用户的目标项目包。

必须包含：

- source code；
- docs；
- run manifest；
- test commands；
- package contract；
- project-level AGENTS.md；
- README。

## 20-evidence

机器可验证和人类可审计的证据。

包括：

- verification runs；
- command stdout/stderr；
- integration evidence；
- database/schema evidence；
- source inventory；
- final evidence table；
- closeout summary。

## 30-audit

人类可读审计资料。

必须能回答：

- 谁做了什么决策？
- agent 接收了什么上下文？
- 哪些 ticket 被创建、执行、返工、完成？
- 哪些 source files 被生产？
- 哪些 evidence 满足哪些 acceptance criteria？
- 最终 git 状态是什么？
- replay 是否可重建？

## 文档模板选择

生成项目可选择模板：

1. Minimal Prototype；
2. Agile / AI-native；
3. Compliance / Waterfall；
4. Hybrid。

选择依据：

- 用户显式要求；
- 项目风险；
- 是否需要追溯；
- 交付生命周期；
- 文档密度要求。

## 重要边界

本文件定义的是 generated project workspace，不是 Boardroom OS V2 repo 的自身目录。

Boardroom OS V2 自身目录见根 `README.md` 和 `doc/README.md`。

