# V2-090K Agent Team Autonomy Remediation 设计规格

## 结论

V2-090K（Agent Team Autonomy Remediation，智能体团队自治整改）承接 V2-090F first run（首次运行）专家评审结论：V2-090F 已证明 real provider worker implementation chain（真实模型供应商支撑的工人实施链路）能跑通，但没有证明 full agent team autonomy（完整智能体团队自治）成立。

090K 的目标不是放松 closeout（收尾）门禁，也不是把 `python -m app.server`、`app/server.py` 或 `LIBRARY_API_*` 等固定接口写成新规范；目标是把“必须能启动、能探测、能证明”的责任交回 agent role（智能体角色），并让 Boardroom OS（董事会系统）通过 PackageContract（包合同）、RunManifest（运行清单）、ProviderAttempt（模型调用尝试记录）和 CloseoutGate（收尾门禁）验证这些职责真实完成。

V2-090F first run（首次运行）应保持 `REVIEW_REQUIRED` / `BLOCKED` 语义。V2-090K 完成并通过真实 provider full run（完整真实模型运行）之前，不得把 V2-090F 标记为 `DONE`。

## 背景

V2-090F first run（首次运行）产生了真实证据：

- worker tickets（工人任务）通过 atomic-agent（原子智能体）真实 provider loop（模型循环）写入源码、运行命令并提交结果；
- command evidence（命令证据）、workspace mutation（工作区变更）、source lineage input（源码来源链输入）和 live blackbox probe（真实黑盒探针）存在；
- 用户人工验证 basic CRUD（基础增删改查）可用。

但评审发现自治边界被 runner / helper（运行器/辅助器）侵入：

- planning prompt（规划提示词）硬性指定 backend / SQLite / static frontend / integration / docs 五类 implementation tickets（实施任务）；
- planning prompt（规划提示词）和 ticket graph validator（任务图校验器）硬性指定 `app/server.py`、`python -m app.server`、`LIBRARY_API_HOST`、`LIBRARY_API_PORT` 和 `LIBRARY_DB_PATH`；
- Checker（检查者）和 Closeout（收尾者）没有各自的 provider attempt（模型调用尝试记录），而是由程序化 helper（辅助器）写出 checker verdict（检查结论）和 closeout package（收尾包）；
- default golden sample check（默认黄金样例检查）路径与真实通过产物路径不一致，`examples/generated-workspaces/tiny-fullstack` 未被可靠发布；
- 人工验证依赖 review proxy（评审代理），暴露 frontend/backend topology（前后端拓扑）没有被 agent team（智能体团队）明确成可运行合同。
- closeout runner（收尾运行器）仍内置 `/books`、`Dune`、`checked_out` 和 `{"books": []}` 等 library domain（图书馆业务域）行为探针；
- final evidence table（最终证据表）、SourceInventory（源码清单）的 acceptance refs（验收引用）和 source surface（源码面）映射仍由 runner 内置 `AC-V2-090F-*`、`app/`、`static/`、`tests/` 前缀推断，而不是来自 agent-generated AcceptanceContract / PackageContract（智能体生成验收合同 / 包合同）。

## 非目标

V2-090K 不做以下事情：

- 不把固定源码布局、固定模块名、固定环境变量名或固定启动命令写成 V2-090F public package interface（公开包接口）；
- 不接受 helper-approved closeout（辅助器批准收尾）作为 Checker / Closeout agent role（智能体角色）的替代；
- 不弱化 existing evidence gates（既有证据门禁），包括 command evidence（命令证据）、service readiness（服务就绪）、live blackbox evidence（真实黑盒证据）、source inventory（源码清单）和 provider attempt（模型调用尝试记录）；
- 不用 mocked success path（模拟成功路径）、fallback success（降级成功）或 static acceptance criteria（静态验收项）证明实施完成；
- 不让 runner（运行器）内置业务行为探针、静态 acceptance refs（验收引用）或 path-prefix source surface mapping（路径前缀源码面映射）来证明 agent team 产物正确；
- 不修改 legacy runtime（旧运行时）或从旧实现迁移设计。

## 整改原则

1. Role goal first（角色目标优先）：提示词应要求角色承担职责和结果，例如“声明并证明服务可启动”，不得要求具体文件名或环境变量名。
2. Contract output first（合同产物优先）：Agent team（智能体团队）必须生成 PackageContract（包合同）和 RunManifest（运行清单），作为 closeout runner（收尾运行器）启动服务和探测系统的权威输入。
3. Runtime bounded（运行时有界）：runner（运行器）只能读取、执行和验证 agent 产出的合同；不得反向把自己的固定实现假设塞进 planning（规划）。
4. Provider-backed roles（模型支撑角色）：Checker（检查者）和 Closeout（收尾者）必须产生 provider attempt（模型调用尝试记录）和 role-context evidence（角色上下文证据）。
5. No second source of truth（无第二权威源）：active AcceptanceContract（当前验收合同）、PackageContract（包合同）、RunManifest（运行清单）和 verification plan（验证计划）必须来自 agent role artifacts（智能体角色产物），runner 不得维护平行的业务验收常量或源码面映射。
6. Fail closed（失败关闭）：缺 PackageContract（包合同）、缺 RunManifest（运行清单）、缺启动声明、缺 readiness probe（就绪探针）、缺 behavioral probe plan（行为探针计划）、缺 checker/closeout provider attempt（检查/收尾模型调用尝试）或缺默认发布样例均失败。

## 介入点清单与整改归因

| 介入点 | 090F first run 行为 | 归因 | 090K 整改要求 |
|---|---|---|---|
| Planning prompt（规划提示词）固定五类 implementation tickets（实施任务） | `_direct_planning_prompt` 要求 backend API、SQLite persistence、static frontend、integration tests、run documentation | Role prompt / autonomy issue（角色提示词/自治问题） | 移除固定任务类别；Architect（架构师）只被要求从 PRD（产品需求）生成足够覆盖 acceptance（验收）的 TicketGraph（任务图），任务数量、名称、依赖由 agent 决定 |
| Planning prompt（规划提示词）固定 `app/server.py` | backend ticket（后端任务）必须写 `app/server.py` | Role prompt / protocol issue（角色提示词/协议问题） | 改为要求 PackageContract（包合同）声明 backend service entry（后端服务入口）和 source surface（源码面）；文件路径由 agent 选择 |
| Planning prompt（规划提示词）固定 `python -m app.server` | closeout backend command（后端收尾命令）被硬编码 | Role prompt / protocol issue（角色提示词/协议问题） | 改为要求 RunManifest（运行清单）声明 `service_commands`（服务命令）；closeout 按声明启动并验证 |
| Planning prompt（规划提示词）固定 `LIBRARY_API_HOST/PORT/DB_PATH` | env names（环境变量名）被硬塞进 ticket graph（任务图） | Role prompt / protocol issue（角色提示词/协议问题） | 改为 RunManifest（运行清单）声明 `env_contract`（环境合同）和 dynamic binding（动态绑定）；runner 可提供端口/临时 DB 值，但变量名由 agent 声明 |
| Ticket graph validator（任务图校验器）检查硬入口 | `_validate_v2_090f_hard_backend_entrypoint` 要求 `app/`、`app/server.py` 和 `LIBRARY_*` 文本 | Framework / gate issue（框架/门禁问题） | 替换为 `validate_package_run_contract_for_closeout`（包运行合同收尾校验），只验证 agent 产出的 PackageContract / RunManifest 可执行且完备 |
| CRUD hard acceptance（硬验收）检查 | 强制覆盖 add/list/checkout/return/delete | 合理门禁，但表达需收敛 | 保留行为验收；不得把行为验收转译成固定源码布局或固定 ticket refs（任务引用） |
| Commands（命令）必须为 argv array（参数数组）且 bounded（有界） | planning prompt（规划提示词）要求有限命令，拒绝 long-running worker commands（长运行工人命令） | 合理框架门禁 | 保留为 protocol validation（协议校验）；角色可选择具体测试命令，但必须可运行、可记录、可终止 |
| Tests path writable gate（测试路径可写门禁） | 声明测试命令时必须允许写测试文件 | 合理门禁 | 保留，属于 command/evidence consistency（命令/证据一致性） |
| Latest command result（最新命令结果） | 同一 command_id（命令 ID）先失败后成功时取 latest（最新） | 合理门禁修正 | 保留；同时要求 latest failure（最新失败）仍 fail closed |
| Closeout live probe（收尾真实探针）固定启动逻辑 | helper（辅助器）按固定 command/env 启动后端 | Framework / protocol issue（框架/协议问题） | closeout runner（收尾运行器）必须读取 RunManifest（运行清单）的 service graph（服务图）、env binding（环境绑定）和 readiness probes（就绪探针） |
| Checker verdict（检查结论）由 helper 写出 | `run_v2_090f_closeout_stage` 程序化写 approved verdict | Framework / gate issue（框架/门禁问题） | Checker seat（检查者席位）必须获得 ExecutionPackage（执行包），调用 provider，输出 verdict artifact（结论产物）；helper 只能验证其结构和证据引用 |
| Closeout package（收尾包）由 helper 直接写 passed | helper（辅助器）生成 closeout package（收尾包）并更新 role context（角色上下文） | Framework / gate issue（框架/门禁问题） | Closeout seat（收尾席位）必须产生 closeout draft（收尾草案）和 audit summary（审计摘要）；CloseoutGate（收尾门禁）程序化决定 passed/failed |
| Role context（角色上下文）被程序化改为 `checker_approved` / `closeout_gate_passed` | 缺少 checker/closeout LLM attempt（大模型调用尝试） | Framework / evidence issue（框架/证据问题） | role context（角色上下文）只能记录事实状态和 provider attempt refs（模型调用尝试引用）；不得让 helper 冒充角色工作产物 |
| 默认 sample publish（样例发布）缺失 | 真实通过产物在 pytest temp（测试临时目录），默认 `--check` 对 `examples/generated-workspaces/tiny-fullstack` 失败 | Release / protocol issue（发布/协议问题） | 090K 必须定义 promotion protocol（发布提升协议），真实通过后发布默认样例并让 `scripts/build_tiny_closeout_sample.py --check` 通过 |
| Review proxy（评审代理）用于人工验证 | frontend 使用同源 API，backend 不托管 static（静态文件） | Role prompt / DevOps responsibility（角色提示词/运维职责） | DevOps / Release role（运维/发布角色）必须声明 frontend/backend topology（前后端拓扑）：同源托管、代理、CORS 或可配置 API base，并由 RunManifest（运行清单）证明 |
| CRUD behavior probe（业务行为探针）硬编码 library 域 | `_probe_v2_090f_crud_workflow` 内置 `/books`、请求体、状态码和响应形状 | Framework / protocol issue（框架/协议问题） | Tester / Release DevOps（测试/发布运维）必须生成 BehavioralProbePlan（行为探针计划）；runner 只执行声明的 HTTP steps（HTTP 步骤）和 assertions（断言） |
| Acceptance refs（验收引用）由 runner 内置 | `_v2_090f_acceptance_refs` 和 `_statement_for_acceptance_ref` 写死 5 个 `AC-V2-090F-*` | Framework / evidence issue（框架/证据问题） | final evidence table（最终证据表）必须从 agent-generated AcceptanceContract（智能体生成验收合同）构造，runner 不得维护静态 AC 列表 |
| Source surface（源码面）由路径前缀推断 | `_source_surface_for_project_path` 用 `app/`、`static/`、`tests/` 推断源码面 | Framework / evidence issue（框架/证据问题） | SourceInventory（源码清单）必须按 PackageContract.source_surfaces.paths（包合同源码面路径）匹配；未匹配文件 fail closed |
| 真实 provider config（真实模型配置）来自 `.env` | secret（密钥）可在 `.env`，但模型/预算/timeout 不应临时覆盖 | Framework / config issue（框架/配置问题） | `.env` 只提供 secret/path（密钥/路径）；runtime/providers/roles baseline（运行时/供应商/角色基线）必须进入 baseline hash（基线哈希） |

## Role Prompt（角色提示词）可整改事项

以下问题主要通过调整 RolePromptHook（角色提示词钩子）、RoleProfile（角色模板）和 role-specific objective（按角色目标）推动 AI 树立正确目标：

- CEO（决策者）必须明确成功标准是可运行、可验证、可审计的交付包，而不是源码片段。
- Architect（架构师）必须输出 PackageContract（包合同）、RunManifest（运行清单）、TicketGraph（任务图）和 acceptance map（验收映射），并把 service startup（服务启动）、env mapping（环境映射）、readiness probe（就绪探针）和 frontend/backend topology（前后端拓扑）纳入合同。
- Tester（测试者）必须设计 live probes（真实探针）、behavioral probe steps（行为探针步骤）和 verification plan（验证计划），覆盖 PRD 的行为命题，而不是只设计单元测试或依赖 runner 内置业务工作流。
- Worker（工人）必须实现能够满足合同的源码和测试，不能依赖 seeded-only behavior（只依赖种子数据的行为）或未声明代理。
- Checker（检查者）必须审查 evidence gaps（证据缺口）、contract mismatch（合同不一致）和 run manifest operability（运行清单可操作性），输出 provider-backed verdict（模型支撑检查结论）。
- Closeout（收尾者）必须整理 evidence map（证据映射）、audit summary（审计摘要）和 package release notes（包发布说明），但不能自行通过门禁。
- 新增或扩展 DevOps / Release responsibility（运维/发布职责）：可以作为 `seat.release.devops`（发布运维席位）显式席位，也可以作为 Architect / Closeout 的 required responsibility（必备职责）先行落地。090K 推荐新增显式 `seat.release.devops`，职责是把“必须能启动”转成 RunManifest（运行清单）和发布合同。

## 仍属于框架 / 门禁 / 协议的问题

以下问题不能只靠提示词解决，必须改框架、门禁或协议：

- PackageContract（包合同）和 RunManifest（运行清单）的 schema（结构）必须足够表达 service commands（服务命令）、env contract（环境合同）、readiness probes（就绪探针）、frontend/backend topology（前后端拓扑）和 published sample path（发布样例路径）。
- Verification plan / RunManifest（验证计划/运行清单）必须足够表达 behavioral probe steps（行为探针步骤）和 assertions（断言）；runner 不得内置 `/books`、seed data（种子数据）或响应形状。
- Closeout runner（收尾运行器）必须动态读取 RunManifest（运行清单）启动服务，不能内置特定 command/env/file layout（命令/环境变量/文件布局）。
- Checker / Closeout provider attempts（检查/收尾模型调用尝试）必须成为 completion gate（完成门禁）的必需证据。
- TicketGraph validator（任务图校验器）必须拒绝 runner-authored fixed graph（运行器编写固定任务图），但不能拒绝 agent 自主选择的合理布局。
- EvidenceVerifier（证据验证器）必须验证 latest command evidence（最新命令证据）、service evidence（服务证据）、live evidence（真实证据）和 source lineage（源码来源链），并拒绝 helper-written verdict（辅助器写结论）冒充角色产物。
- FinalEvidenceTable（最终证据表）和 SourceInventory（源码清单）必须消费 agent-generated AcceptanceContract / PackageContract（智能体生成验收合同 / 包合同）；runner 内置 acceptance ref 常量和路径前缀源码面映射不得作为权威源。
- Sample promotion（样例发布提升）必须成为可审计步骤；默认 `examples/generated-workspaces/tiny-fullstack` 的 `--check` 必须验证已发布产物，而不是 pytest temp（测试临时目录）。
- Config baseline（配置基线）必须把 role seats（角色席位）、provider profiles（供应商配置档）、budgets（预算）、timeouts（超时）和 retry policy（重试策略）写入 baseline hash（基线哈希）。

## PackageContract 与 RunManifest 要求

V2-090K 必须让 agent team（智能体团队）生成如下运行合同。字段名可在实施时按现有 schema（结构）收敛，但语义必须覆盖：

```yaml
package_contract:
  package_root: 10-project
  project_type: software
  source_surfaces:
    - source_surface_ref: backend
      paths: [...]
      acceptance_refs: [...]
    - source_surface_ref: frontend
      paths: [...]
      acceptance_refs: [...]
  integration_boundaries:
    - boundary_ref: frontend-to-backend
      protocol: http
      producer_surface_ref: frontend
      consumer_surface_ref: backend
  run_manifest_ref: 20-evidence/tests/run-manifest.json

run_manifest:
  service_commands:
    - command_id: backend-service
      role: backend
      command: [...]
      cwd: 10-project
      env_contract:
        required:
          - name: <agent-declared-host-env>
            value_source: runtime_host
          - name: <agent-declared-port-env>
            value_source: runtime_port
          - name: <agent-declared-db-env>
            value_source: temp_sqlite_path
      readiness_probe:
        method: GET
        path: /health
        expect_status: 200
  frontend:
    mode: served-by-backend | static-server | proxy-required | configurable-api-base
    service_command_ref: ...
    api_base_binding: ...
  behavioral_probes:
    - probe_id: prd-behavior-001
      service_command_ref: backend-service
      steps:
        - step_id: create-item
          method: POST
          path: <agent-declared-path>
          json_body: <agent-declared-json-or-null>
          expect_status: 200 | 201 | 204
          capture:
            item_id: <json-path-or-response-field>
        - step_id: verify-state
          method: GET
          path: <agent-declared-path-using-captures>
          expect_status: 200
          assertions:
            - type: json_equals | json_contains | field_equals | field_absent
              target: <json-path>
              expected: <literal>
  test_commands:
    - command_id: ...
      command: [...]
      cwd: 10-project
```

允许 agent 自主选择：

- backend package layout（后端包布局）；
- service entrypoint（服务入口）；
- env names（环境变量名）；
- frontend topology（前端拓扑）：同源托管、独立静态服务、代理或可配置 API base；
- behavioral probe steps（行为探针步骤）：HTTP method/path/body、状态码、capture（捕获值）和 assertions（断言）；
- tests layout（测试布局）和 command IDs（命令编号）。

不允许缺失：

- 至少一个可启动 backend service command（后端服务命令）；
- 可绑定动态端口和临时 SQLite path（SQLite 路径）的 env contract（环境合同）或等价配置机制；
- readiness probe（就绪探针）；
- frontend-to-backend live probe path（前后端真实探针路径）和 PRD behavior probe（需求行为探针）；
- test commands（测试命令）和 evidence obligations（证据义务）。

AcceptanceContract（验收合同）和 PackageContract（包合同）还必须成为证据构造权威源：

- FinalEvidenceTable.rows（最终证据表行）必须逐项来自 AcceptanceContract.criteria（验收合同条目）；
- SourceInventory.entries.source_surface_ref（源码清单源码面引用）必须来自 PackageContract.source_surfaces.paths（包合同源码面路径）；
- SourceInventory.entries.acceptance_refs（源码清单验收引用）必须来自对应 source surface（源码面）和 active acceptance criteria（当前验收条目）；
- 未被任一 source surface 覆盖的 materialized source file（物化源码文件）必须 fail closed，不能落入 docs（文档）默认面。
- Agent 产出的 JSON artifact（产物）只允许作为输入格式；进入 gate（门禁）前必须通过现有强类型 AcceptanceContract（验收合同）、PackageContract（包合同）、SourceSurface（源码面）、RunManifest（运行清单）和 SourceLineageRecord（源码来源链记录）校验。
- FinalEvidenceTable（最终证据表）必须由现有 FinalEvidenceTableBuilder（最终证据表构建器）从 FinalEvidenceTableInput（最终证据表输入）构造；SourceInventory（源码清单）必须由现有 build_source_inventory（源码清单构建器）构造；runner 不得新建 dict-only（仅字典）平行 helper（辅助器）手工拼接证据表、ID 规则或源码面路径匹配规则。
- AcceptanceContract（验收合同）与 PackageContract（包合同）必须通过 validate_contract_gate（合同门禁校验），保证 package source surfaces（包源码面）引用的 acceptance refs（验收引用）属于 active contract（当前合同），blocking criteria（阻断验收条目）的 source surface refs（源码面引用）属于 package contract（包合同），evidence obligations（证据义务）由 active contract（当前合同）派生。

## 验收

V2-090K 完成必须同时满足：

1. Negative tests（负例测试）：规划 prompt（提示词）和 validator（校验器）不得包含 `app/server.py`、`python -m app.server`、`LIBRARY_API_HOST`、`LIBRARY_API_PORT`、`LIBRARY_DB_PATH`、固定五票任务图、固定 ticket refs（任务引用）、`/books` 域探针、`AC-V2-090F-*` 静态验收列表或 `app/` / `static/` 路径前缀源码面权威映射。
2. Role prompt tests（角色提示词测试）：Architect / Tester / Checker / Closeout / DevOps-Release responsibilities（架构/测试/检查/收尾/运维发布职责）覆盖 PackageContract（包合同）、RunManifest（运行清单）、service startup（服务启动）、env mapping（环境映射）、readiness（就绪）、live probe（真实探针）和 evidence gaps（证据缺口）。
3. Protocol tests（协议测试）：缺 PackageContract（包合同）、缺 RunManifest（运行清单）、缺 service command（服务命令）、缺 env binding（环境绑定）、缺 readiness probe（就绪探针）、缺 frontend/backend topology（前后端拓扑）、缺 behavioral probe plan（行为探针计划）、缺 active AcceptanceContract（当前验收合同）或缺 source surface path mapping（源码面路径映射）均 fail closed（失败关闭）。
4. Checker/Closeout tests（检查/收尾测试）：缺 Checker 或 Closeout ProviderAttempt（模型调用尝试记录）不得 closeout；helper-written approved verdict（辅助器批准结论）不得满足角色产物要求。
5. Dynamic closeout tests（动态收尾测试）：closeout runner（收尾运行器）只消费 agent 生成的 RunManifest（运行清单）启动服务并执行声明式 behavioral probes（行为探针），不含固定 command/env names（命令/环境变量名）或业务域 HTTP workflow（HTTP 工作流）。
6. Evidence authority tests（证据权威源测试）：final evidence table（最终证据表）只从现有强类型 AcceptanceContract（验收合同）和 FinalEvidenceTableBuilder（最终证据表构建器）构造；SourceInventory（源码清单）只从现有强类型 PackageContract.source_surfaces（包合同源码面）和 build_source_inventory（源码清单构建器）构造；validate_contract_gate（合同门禁校验）必须通过；runner 内置 AC/source surface fallback（验收/源码面降级）或 dict-only（仅字典）平行实现不得满足 closeout。
7. Real provider proving（真实模型供应商证明）：移除硬编码后，从 short PRD（简短需求）触发 agent team（智能体团队）真实 provider full run（完整运行），生成可启动 package（项目包）并通过 live blackbox closeout（真实黑盒收尾）。
8. Default sample check（默认样例检查）：真实通过产物被发布到 `examples/generated-workspaces/tiny-fullstack`，`PYTHONPATH=src:. python scripts/build_tiny_closeout_sample.py --check` exit 0。
9. Documentation sync（文档同步）：backlog（待办）、acceptance criteria（验收标准）、project log（项目日志）、INDEX（索引）和 V2-090F/V2-090K 状态说明同步；V2-090F checkbox（复选项）只在 090K 真实证据齐全后才允许勾选。

## 自审

- Contract first（合同优先）：090K 要求 PackageContract（包合同）和 RunManifest（运行清单）成为运行探测权威源。
- Reducer first（归约器优先）：agent role（智能体角色）输出结论，但 completion（完成）和 closeout passed（收尾通过）仍由 gate/reducer（门禁/归约器）决定。
- Evidence first（证据优先）：Checker / Closeout provider attempts（检查/收尾模型调用尝试）和 live service evidence（真实服务证据）缺一不可。
- Fail closed（失败关闭）：缺运行合同、缺角色尝试、缺默认发布样例均失败。
- Runtime bounded（运行时有界）：runner（运行器）不指定源码布局或启动命令，只执行和验证 agent 生成的合同。
- No second source of truth（无第二权威源）：runner（运行器）不维护业务域探针、静态验收列表、路径前缀源码面映射或绕过强类型 Contract/Evidence（契约/证据）模型的 dict-only（仅字典）平行链路。
- Negative tests first（负例优先）：先证明 090F first run 的硬编码路径无法再悄悄通过，再运行真实 provider happy path（正向路径）。
