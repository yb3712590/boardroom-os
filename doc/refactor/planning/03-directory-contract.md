# 目录契约

## 目标

目录结构必须让人和机器都能立即判断：什么是源码，什么是证据，什么是 runtime 状态，什么是归档，什么可以写，什么只能物化，什么永远不能由 worker 直接改。

第 15 轮暴露的问题之一是：产物、证据、runtime 快照、closeout refs 和人工审计材料边界不够硬。重构后，目录不再只是约定俗成，而是 runtime contract 的一部分。

## 仓库根目录契约

```text
boardroom-os/
├── backend/              # 后端源码、后端测试、后端配置
├── frontend/             # 前端源码、前端测试、前端构建配置
├── doc/                  # 工作文档控制面
├── docs/                 # 若存在，只能作为发布级快照，不承载 active planning
├── scripts/              # 跨 backend/frontend 的维护脚本，后续可新增
├── .claude/              # Claude/worktree/tooling 状态，不进入产品真相
├── .worktrees/           # 本地 worktree/runtime 操作区，不进入产品真相
├── .tmp/                 # 临时文件，不入库
└── README.md             # 人类入口和开发快速说明
```

## `doc/` 契约

`doc/` 是工作文档控制面，不是杂项资料堆。

```text
doc/
├── README.md             # 文档入口和阅读规则
├── mainline-truth.md     # 当前代码事实锚点
├── new-architecture/     # 目标架构 canon，不直接代表当前实现
├── refactor/             # 当前重构控制面
├── tests/                # 历史测试审计和 verification history
├── archive/              # 退出当前主线的历史材料
└── history/              # 历史上下文和旧 memory/log
```

规则：

- 当前事实优先看 `mainline-truth.md`。
- 目标架构看 `new-architecture/`。
- 本轮重构看 `refactor/planning/`。
- 历史愿景看 `archive/specs/feature-spec.md`。
- 015 证据看 `tests/intergration-test-015-20260429*.md`。
- 不允许把新计划散写到 `doc/` 根目录。
- 不允许把一次性 session prompt 放在 backend/docs 作为稳定文档。

## Runtime workspace 契约

每个 workflow 的可交付 workspace 应采用固定骨架：

```text
workflow-root/
├── 00-boardroom/
│   ├── 00-constitution/
│   ├── 10-charter/
│   ├── 20-graph/
│   ├── 30-decisions/
│   ├── 40-runtime/
│   └── 50-project-map/
├── 10-project/
│   ├── src/
│   ├── docs/
│   └── assets/
├── 20-evidence/
│   ├── tests/
│   ├── reviews/
│   ├── git/
│   └── delivery/
├── 50-closeout/
└── 90-archive/
    ├── events/
    ├── projections/
    └── transcripts/
```

## 目录职责

| 目录 | 职责 | 写入者 | 更新模式 |
|---|---|---|---|
| `00-boardroom/00-constitution` | workflow 局部规则 | governance materializer | `VERSION_SUPERSEDE` |
| `00-boardroom/10-charter` | PRD/目标/约束 | Board/charter materializer | `VERSION_SUPERSEDE` |
| `00-boardroom/20-graph` | graph current view | graph materializer | `REPLACE_VIEW` |
| `00-boardroom/30-decisions` | ADR/决策资产 | policy/materializer | `VERSION_SUPERSEDE` |
| `00-boardroom/40-runtime` | runtime ledger/readable receipts | runtime materializer | `APPEND_LEDGER` |
| `00-boardroom/50-project-map` | 项目地图视图 | project-map materializer | `REPLACE_VIEW` |
| `10-project/src` | 真实源码 | source modification capability | controlled write |
| `10-project/docs` | 交付文档 | documentation capability | `VERSION_SUPERSEDE` |
| `20-evidence/tests` | 测试证据 | test/evidence capability | `APPEND_LEDGER` |
| `20-evidence/reviews` | review/check evidence | checker capability | `APPEND_LEDGER` |
| `20-evidence/git` | git closeout evidence | hook/runtime | `APPEND_LEDGER` |
| `20-evidence/delivery` | delivery reports | checker/runtime | `APPEND_LEDGER` |
| `50-closeout` | final closeout package | closeout capability | append/versioned |
| `90-archive` | 原始事件、投影、transcript | archiver only | `IMMUTABLE_ARCHIVE` |

## Artifact ref 映射

Artifact refs 必须能映射到稳定路径：

```text
art://workspace/<ticket_id>/source/<encoded-path>
  -> workflow-root/10-project/<path>

art://workspace/<ticket_id>/tests/<encoded-path>
  -> workflow-root/20-evidence/tests/<ticket_id>/<path>

art://runtime/<ticket_id>/delivery-check-report.json
  -> workflow-root/20-evidence/delivery/<ticket_id>/delivery-check-report.json

art://runtime/<ticket_id>/delivery-closeout-package.json
  -> workflow-root/50-closeout/<ticket_id>/delivery-closeout-package.json
```

规则：

- artifact ref 不能指向任意项目文档作为 final delivery evidence。
- closeout final refs 只能引用已登记的 source/evidence/delivery/check/verification 类资产。
- artifact index 必须记录 content hash、source ticket、graph version、supersedes。

## 禁止事项

1. Worker 不能直接写 `00-boardroom/20-graph`。
2. Worker 不能直接写 `90-archive`。
3. Checker 不能直接改 `10-project/src`。
4. Closeout 不能回写源码或测试。
5. Runtime 不能把 placeholder fallback 写成真实 source delivery。
6. 文档不能反向成为状态真相。
7. 临时 `.tmp`、cache、provider raw stream dump 不能进入 final evidence，除非被显式封装为 audit archive。

## Generated / Cache / Archive 区分

| 类型 | 例子 | 是否入库 | 说明 |
|---|---|---|---|
| source | backend/frontend 源码 | 是 | 真实实现 |
| working doc | `doc/refactor/planning/*` | 是 | 当前控制面 |
| audit evidence | integration final report | 是 | 可追溯证据 |
| runtime DB | live scenario DB | 通常否 | 除非作为 replay fixture 明确登记 |
| cache | `.pytest_cache`, `__pycache__` | 否 | 删除 |
| build output | `frontend/dist` | 否 | 删除 |
| temp | `.tmp` | 否 | 删除 |
| archive | `doc/archive/*` | 是 | 历史材料，但不默认读取 |

## 验收标准

- 所有新 runtime 产物路径都能归类到本契约。
- 所有 write-set validation 都以目录契约为输入。
- closeout 不能引用目录契约禁止的 final refs。
- replay bundle 能根据 artifact refs 重建人类可读目录。
