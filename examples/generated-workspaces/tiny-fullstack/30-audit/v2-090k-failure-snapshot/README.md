# V2-090K Failure Snapshot

本目录保留 V2-090K 整改后真实 provider full run（完整模型供应商运行）的精选失败现场。它是 audit material（审计材料）和后续 V2-100 rework loop（返工循环）输入，不是 passed golden sample（通过黄金样例）。

## 保存目的

- 保护 090K fail-closed（失败关闭）现场，避免后续整理 `git status` 时丢失关键证据。
- 为 V2-100C CEO rework planner boundary（CEO 返工规划边界）提供真实 BlockerReport（阻塞报告）样例来源。
- 为 V2-100E multi-round rework proving scenario（多轮返工证明场景）提供真实失败输入，同时后续还应补一个可重置 failing fixture（失败夹具）。

## 090K 完成语义

V2-090K 的完成语义不是 single-pass full run passed（单轮完整运行通过）。090K 要证明的是：

- runner/helper（运行器/辅助器）不再把固定源码布局、启动命令、环境变量名、业务探针、静态验收引用或源码面映射作为第二权威源；
- AcceptanceContract（验收合同）、PackageContract（包合同）、RunManifest（运行清单）和 BehavioralProbePlan（行为探针计划）由 agent artifact（智能体产物）声明并成为 gate（门禁）输入；
- Checker/Closeout（检查/收尾）需要 provider attempt（模型调用尝试记录）留痕；
- 当合同、实现和探针不一致时，系统必须 fail closed 并留下结构化失败证据。

V2-090F golden sample（黄金样例）仍保持 blocked/review_required（阻塞/需复判），需要在 090K 的合同权威源基础上叠加 V2-100 的 CEO-governed rework loop（项目经理治理返工循环）后再复判。

## 关键失败点

1. BehavioralProbePlan（行为探针计划）与 backend implementation（后端实现）响应 shape（形状）不一致。
   - `00-boardroom/generated-run-manifest.json` 中 `probe.add_and_list_book` 对创建响应断言 `$.title`、`$.author`、`$.checked_out`，并从 `$.id` 捕获 `book_id`。
   - `10-project/backend/server.py` 实际创建响应为 `{"ok": true, "book": {...}, "id": ...}`；`title` / `author` / `checked_out` 位于 `$.book.*`。
2. Env binding（环境绑定）仍不收敛。
   - RunManifest service contract（运行清单服务合同）声明 `HOST` / `PORT` / `DATABASE_PATH`。
   - 实现仍读取 `LIBRARY_DB_PATH`，并保留 `LIBRARY_HOST` / `LIBRARY_PORT` fallback（降级路径）。
3. FinalEvidenceTable（最终证据表）仍投影到旧 `AC-TINY-*` 验收引用。
   - Agent artifacts（智能体产物）中出现 `acceptance.add_book`、`AC.add_book`、`AC.add-book` 等不同命名。
   - `20-evidence/closeout/final-evidence-table.json` 使用 `AC-TINY-API-*` / `AC-TINY-RUN-TEST-COMMANDS`。
4. Closeout/audit（收尾/审计）仍引用旧 run。
   - `30-audit/process-audit.md` 和 `30-audit/replay-bundle-report.json` 仍包含 `run-v2-080f`。

其中 `library` / `books` 业务词来自 PRD，不单独作为 runner hardcoding（运行器硬编码）证据；问题在于合同、实现、探针和收尾投影没有通过 agent team（智能体团队）治理收敛。

## 保留内容

本快照保留 29 个文件，约 336K：

- `00-boardroom/`：PRD intake（需求导入）、agent role context（角色上下文）、board directive（董事会指令）、contracts（合同）、ticket graph（工单图）、run manifest（运行清单）、verification plan（验证计划）、baseline（基线）。
- `10-project/`：backend implementation（后端实现）、backend tests（后端测试）、run docs（运行说明）。
- `20-evidence/`：worker execution（实施执行）、provider attempts summary（模型调用尝试摘要）、run manifest projection（运行清单投影）、verification runs（验证运行）、source inventory（源码清单）、final evidence table（最终证据表）。
- `30-audit/`：process audit（流程审计）、git version audit（Git 版本审计）、replay report（重放报告）、timeline（时间线）、artifact lineage（产物血缘）和 evidence map（证据映射）。

## 未保留内容

- 未复制 `20-evidence/provider-artifacts/` 下约 330 个 raw/parsed provider artifact（原始/解析模型产物）全文。当前仓库工作区仍保留原始目录，必要时可另行归档。
- 未复制 SQLite database、WAL/SHM 或其他 runtime state（运行时状态）。
- 未把本快照包装为可通过 `--check` 的 sample output（样例输出）。

## Key Hashes

- `00-boardroom/generated-run-manifest.json`: `3fcafccdfb05b06f31d86640885802d5ab1554abb36bbc4ab2780bea945fa798`
- `10-project/backend/server.py`: `81b2eff66688c13416e23cfa70e2ed4488f1029ba75b2303ead7dd99145dc385`
- `20-evidence/closeout/final-evidence-table.json`: `274b04230c8029287fc9a2c83be4cff5a06c2229e4a4d0b37b2f5669cec71f01`
- `30-audit/process-audit.md`: `472925d91b04422a2947dbc9ba828ac1c55b7e740f212ff90f3a872ab5c17262`
- `30-audit/git-version-audit.md`: `d930d109b225e54b7059a2baa2f2ca7dafb9e82eb7f6cff1242d2dad62bd344d`
