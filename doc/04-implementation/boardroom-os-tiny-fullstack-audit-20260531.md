# Boardroom OS V2 tiny-fullstack 失败复审报告

## 结论

此次失败不是旧 V1 runtime fallback 问题的简单复发。V2 已经具备 provider attempt、typed evidence、source inventory、closeout gate、process audit 等新结构，但 tiny-fullstack 进入了更隐蔽的伪闭环：

> 真实 provider 生成了代码，真实 pytest 也执行通过，typed audit 也生成了；但合同、测试和证据证明的是错误命题，而不是“生成项目包可启动、前后端真实串联、SQLite 经 HTTP 工作流持久化”。

附件中的 generated package 声明 `run-backend` 为 `python -m uvicorn backend.app:app`，但实际 `backend/app.py` 只是若干 Python 函数，没有 ASGI `app` 对象，也没有 HTTP route。因此项目包按声明命令无法启动。

## 本地复现

在 `examples/generated-workspaces/tiny-fullstack/10-project` 中：

- `python -X utf8 -m pytest backend/tests --basetemp=.pytest-tmp-backend -q` 通过；
- `python -X utf8 -m pytest tests/integration --basetemp=.pytest-tmp-integration -q` 通过；
- `python -m uvicorn backend.app:app` 报错：`Attribute "app" not found in module "backend.app"`。

`run-manifest.json` 声明 4 个命令：`run-backend`、`run-frontend`、`test-backend`、`test-integration`。`verification-runs.json` 只有两个测试命令，没有 `run-backend` 和 `run-frontend` 的运行证据。

## 关键证据

1. `examples/generated-workspaces/tiny-fullstack/10-project/backend/app.py:20-73` 只定义 `create_store`、`create_book`、`list_books`、`checkout_book`、`return_book`、`delete_book` 和 `__all__`，没有 ASGI `app` 对象。
2. `examples/generated-workspaces/tiny-fullstack/10-project/run-manifest.json:3-31` 声明 `run-backend` 为 `python -m uvicorn backend.app:app`，`run-frontend` 为 `python -m http.server 5173 --directory frontend`。
3. `examples/generated-workspaces/tiny-fullstack/20-evidence/tests/verification-runs.json:1-92` 只记录 `test-backend` 和 `test-integration`，没有 run command evidence。
4. `examples/generated-workspaces/tiny-fullstack/10-project/backend/tests/test_api.py:12-17` 直接 import `backend.app` 并调用函数；`test_api.py:100-169` 通过函数调用和 SQLite 文件验证后端，不验证 HTTP 服务。
5. `examples/generated-workspaces/tiny-fullstack/10-project/tests/integration/test_frontend_backend.py:29-54` 使用 `fakeFetch` 捕获 URL；`test_frontend_backend.py:58-82` 只断言 `/books` 和 `DELETE` 路径，没有启动后端或前端服务。
6. `tests/fixtures/contracts/tiny_fullstack_contract.py:200-208` 把前端集成和运行命令验收写得过弱，只要求“fetches backend API”和“declares local run and test commands”；同文件 `301-304` 又声明 uvicorn/http.server run commands，形成合同内自相矛盾。
7. `tests/proving/fixtures/tiny_provider_attempts.py:532-545` provider 指令禁止 Flask/FastAPI/requests/npm 等第三方，并要求后端暴露函数和 sqlite3 BookStore；这与 uvicorn `backend.app:app` 启动命令不一致。
8. `tests/proving/fixtures/tiny_package_assembly.py:714-715` 只执行 `test-backend` 和 `test-integration`；`run-backend` 和 `run-frontend` 从未运行。
9. `tests/proving/fixtures/tiny_package_assembly.py:870-935` 对 package functional scope 的验证是源码标记/函数签名/字符串级检查，不要求 ASGI app、HTTP route 或服务启动。
10. `tests/proving/fixtures/tiny_package_assembly.py:1101-1150` 对 frontend integration 的验证要求调用函数、捕获 URL/options、看到 `/books`/`DELETE`，但允许 fake fetch；这不是 live integration。
11. `tests/proving/fixtures/tiny_package_assembly.py:1268-1276` 把 `run_manifest` 和 `command_evidence` obligations 映射到 `test-integration`，使“声明并执行运行命令”的证据被一个 fake-fetch integration test 代替。
12. `tests/proving/fixtures/tiny_closeout.py:1493-1542` closeout command bindings 只从已有 verification runs 派生；既然 verification runs 只有测试命令，run commands 自然不会进入 closeout gate。
13. `src/boardroom_os/closeout/gate.py:707-771` 只要求每个 verification run 有绑定且命令匹配；没有要求 run manifest 中的每个 command 都有 final evidence。
14. `src/boardroom_os/execution/runtime_executor.py:327-352` 只执行调用方传入的 `command_ids`；`tests/proving/fixtures/tiny_provider_attempts.py:276` 和 `tests/proving/fixtures/tiny_closeout.py:761` 均传入空 command_ids。

## 根因

### 根因 1：架构合同自相矛盾

合同声明 `uvicorn backend.app:app`，但 provider 指令禁止第三方框架并要求后端函数式 API。worker 生成的是符合 provider prompt 的函数库，而不是符合 run manifest 的 HTTP 服务。

### 根因 2：验收标准证明的是“路径被调用”，不是“前后端真实串联”

`AC-TINY-UI-FETCH-BACKEND` 没有要求 live backend、live frontend、真实 HTTP 请求、端到端 CRUD、SQLite 经 HTTP 持久化。fakeFetch 捕获 `/books` 就能满足集成证据。

### 根因 3：run command 没有成为硬门槛

run manifest 有 run commands，但 closeout 只检查已有 verification runs。因为 fixture 只跑 test commands，run commands 的失败完全不会进入 final evidence table。

### 根因 4：测试由同一闭环生成，并被当作独立证据

后端测试直接调用函数，前端集成测试使用 fakeFetch。它们对“函数库正确”有一定价值，但不能证明生成项目包可启动。

### 根因 5：checker/closeout 仍然偏向引用一致性，而非行为语义

source inventory、evidence verifier、final evidence table、process audit 都在证明“这些 evidence refs、artifact refs、provider attempts 和 verification runs 结构上绑定正确”。它们没有独立黑盒运行 generated package。

### 根因 6：golden sample 是 fixture 驱动的闭环，不是真实运行闭环

`examples/README.md` 描述 golden sample 由脚本与 provider artifact lock 重生成。这个机制有利于稳定，但如果 fixture 的验证边界过弱，golden sample 会稳定地重放错误闭环。

## 修正方向

### P0：立即阻断不可启动包 closeout

1. `CloseoutGate` 必须要求 run manifest 中的每个 command 都有最终证据。
2. 引入 `RunCommandEvidence` / `ServiceRunEvidence`，区分一次性 test command 和长运行 service command。
3. `run-backend`、`run-frontend` 缺少 startup/readiness evidence 时 closeout blocked。
4. `AC-TINY-RUN-TEST-COMMANDS` 改为“declares and verifies local run and test commands”。
5. negative test：当前附件中的 package 应被 closeout gate 拒绝，blocker 至少包含 `RUN_MANIFEST_COMMAND_UNVERIFIED` / `RUN_COMMAND_EVIDENCE_MISSING`。

### P1：修正 tiny-fullstack 合同

必须选择一个一致路线：

- 路线 A：标准库 HTTP 服务。保留“不使用第三方框架”，后端用 `http.server` 实现 `/health`、`/books`、`/books/{id}/checkout`、`/books/{id}/return`、`DELETE /books/{id}`；run command 改为 `python -m backend.app` 或 `python backend/app.py`。
- 路线 B：ASGI 服务。保留 `python -m uvicorn backend.app:app`，但 provider prompt 必须允许并要求 ASGI app、依赖清单和 route contract。

不能继续同时保留“uvicorn run command”和“stdlib-only/function API prompt”。

### P2：把集成测试升级为黑盒端到端

1. backend startup probe：启动后端，探测 `/health`。
2. backend HTTP CRUD probe：通过 HTTP 创建、列表、checkout、return、delete。
3. SQLite persistence probe：通过 HTTP 写入后检查 DB file/schema/data。
4. frontend startup probe：启动静态前端服务并获取 `/` / `app.js`。
5. live frontend-backend probe：从真实 frontend code 调用真实 backend base URL，不允许 fakeFetch-only 满足 AC。

### P3：收紧 provider prompt 和 architect compiler

1. architect compiler 应检查 run command 与 source contract 的一致性：`uvicorn backend.app:app` 必须产生 `backend/app.py` 中的 `app` 对象和 route obligations。
2. third-party 禁止规则与命令依赖冲突时，contract compilation fail closed。
3. integration boundary 如果是 HTTP API，evidence obligation 必须是 live service probe，不得退化为 fake path capture。

### P4：修正 fixture 和 sample materializer

1. `tests/proving/fixtures/tiny_package_assembly.py::_command_results_by_id` 不能只跑 `test-backend` / `test-integration`。
2. `_command_id_for_obligation` 不能把 `command_evidence` 映射到 `test-integration`。
3. `_validate_tiny_package_functional_scope` 必须检查合同要求的真实服务入口。
4. `_validate_frontend_integration_behavior_evidence` 必须拒绝 fakeFetch-only 作为最终集成证据。
5. exported generated workspace 应从 clean manifest staging 输出，禁止 `__pycache__` 等非清单文件混入最终样例。

## 优先 patch 列表

1. `src/boardroom_os/closeout/gate.py`
   - 新增 all-manifest-command evidence coverage。
2. `src/boardroom_os/workspace/run_manifest.py`
   - 给 `run` command 增加 probe requirement / evidence obligation。
3. `src/boardroom_os/adapters/process_runner.py`
   - 增加 service command runner 或 readiness probe runner。
4. `tests/fixtures/contracts/tiny_fullstack_contract.py`
   - 修正合同与 provider prompt 的矛盾。
5. `tests/proving/fixtures/tiny_provider_attempts.py`
   - provider 指令必须与合同一致。
6. `tests/proving/fixtures/tiny_package_assembly.py`
   - 执行 run command probes 和 live integration probes。
7. `tests/proving/fixtures/tiny_closeout.py`
   - closeout input 必须包含所有 command evidence。
8. `tests/negative/`
   - 增加当前失败包的 regression negative tests。

## 最终判断

V2 重构方向是正确的，已明显脱离 V1 的 runtime synthetic success。但当前 tiny-fullstack 证明了 V2 仍存在一个关键系统性漏洞：

> 从“证据必须真实”进化到了“证据真实但证明对象错误”。

下一阶段不要继续堆更多角色或 audit renderer，应先把 tiny-fullstack 降级为一个严格黑盒 proving scenario：声明什么命令，就必须运行或 probe；声明 HTTP 集成，就必须启动服务并通过 HTTP 验证；声明 closeout，就必须证明最终 package root 在 clean staging 中可启动、可测试、可审计。
