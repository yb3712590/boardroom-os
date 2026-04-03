# 主线真相表

> 最后更新：2026-04-03
> 这份文档只回答一个问题：**当前代码里到底什么是真的**。如果 `README`、设计文档和这里冲突，先以代码现实和这份表为准。

## 1. 主链阶段对照表

| 阶段 | 当前状态 | 代码现实 | 直接结论 |
|------|----------|----------|----------|
| `project-init -> scope review` | 真实运行 | `project-init` 会自动推进到首个 scope review | 不是只建 workflow 的空壳 |
| `BUILD` 内部 maker-checker | 真实运行 | 先产出 `implementation_bundle@1`，再走 `maker -> checker -> fix / incident` | `BUILD` 不会直接放行到 `CHECK` |
| `CHECK` 内部 maker-checker | 真实运行 | `delivery_check_report@1` 也有独立内审闭环 | `CHECK` 不会直接放行到最终董事会 |
| 最终 `REVIEW` | 真实运行 | 只有真正 board-facing 的 review 才进入 `Inbox -> Review Room` | 董事会只看真实审批点 |
| `closeout` 内部 maker-checker | 真实运行 | final review 通过后会自动补 `delivery_closeout_package@1`，closeout 完成后才算 workflow 完成 | completion 不是 board approve 就立刻出现 |

补充差异：

- 当前主链 follow-up 里的 `frontend_engineer` 只是 **owner role 名字**，代码里仍映射到 `ui_designer_primary`
- 也就是说，当前并没有独立的 `frontend_engineer` worker 角色

## 2. Runtime 支持矩阵

当前 runtime 默认走本地 `LOCAL_DETERMINISTIC`。如果员工 `provider_id=prov_openai_compat`，并且本地保存了完整 provider 配置，同一批主线角色和输出会走 `OPENAI_COMPAT_LIVE`。

| owner role | role profile | 输出 | Deterministic | OpenAI Compat Live | 备注 |
|------------|--------------|------|---------------|--------------------|------|
| `frontend_engineer` | `ui_designer_primary` | `consensus_document` | 支持 | 支持 | 当前共识文档仍由主线 maker 角色产出 |
| `frontend_engineer` | `ui_designer_primary` | `implementation_bundle` | 支持 | 支持 | `BUILD` 产物当前仍由 `ui_designer_primary` 产出 |
| `checker` | `checker_primary` | `delivery_check_report` | 支持 | 支持 | `CHECK` 报告当前由 checker 产出 |
| `frontend_engineer` | `ui_designer_primary` | `ui_milestone_review` | 支持 | 支持 | 最终董事会 review 包当前仍由主线 maker 产出 |
| `frontend_engineer` | `ui_designer_primary` | `delivery_closeout_package` | 支持 | 支持 | closeout package 当前仍由主线 maker 产出 |
| `checker` | `checker_primary` | `maker_checker_verdict` | 支持 | 支持 | 主线 maker-checker verdict 当前都走 checker |

当前不应误判的点：

- `OpenAI Compat` live path **不只** 支持 `ui_milestone_review` 和 `maker_checker_verdict`
- 但它也**没有**扩成独立的一套 worker roster；仍然只覆盖当前这两类 role profile：`ui_designer_primary`、`checker_primary`

## 3. 冻结边界清单

下面这些能力在仓库里还在，部分路由也还挂着，但**默认不继续扩张**。只有直接解堵本地 MVP 时，才允许最小修改。

| 能力 | 代码是否还在 | 路由是否还挂载 | 当前处理 |
|------|--------------|----------------|----------|
| `worker-admin` 管理面 | 是 | 是，`/api/v1/worker-admin` | 冻结，默认不继续扩 |
| 多租户 scope / binding | 是 | 没有单独入口路由 | 冻结，保留兼容和现有数据结构 |
| 控制面上传 / 可选对象存储 | 是 | 是，`/api/v1/artifact-uploads` | 冻结，只保留最小解堵 |
| 外部 worker handoff | 是 | 是，`/api/v1/worker-runtime` | 冻结，不作为当前主线继续推进 |

这张边界表的目的不是否认这些代码存在，而是避免再次把它们误写成当前 MVP 主线。
