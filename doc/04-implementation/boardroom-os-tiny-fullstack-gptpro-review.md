结论先说直白一点：**你的怀疑基本成立。**

这次不是旧版那种“runtime fallback 伪造 source / verification”的同类问题，而是 V2 进入了更隐蔽的一层：

```text
provider 真的跑了；
测试也真的跑了；
evidence / source inventory / closeout / audit 也真的生成了；
但它们证明的是一个错误命题。
```

当前 tiny-fullstack 证据链证明的是：

```text
后端函数库可以被 Python 单测直接调用；
前端 JS 函数会调用 fakeFetch('/books')；
run-manifest 文件中声明了 run/test 命令；
这些 artifact/ref/hash/evidence 结构能互相绑定。
```

它**没有证明**：

```text
生成项目包能按 run-manifest 启动；
backend.app:app 存在；
后端提供真实 HTTP API；
前端真实调用后端服务；
SQLite 通过 HTTP 工作流被写入和读取；
最终 10-project 是一个完整可运行项目包。
```

我整理了一份 Markdown 审计报告，也可以下载保存：

[下载审计报告](boardroom-os-tiny-fullstack-audit-20260531.md)

---

# 1. 我复现到的直接事实

我在附件内的生成项目包执行了关键命令，路径是：

```text
examples/generated-workspaces/tiny-fullstack/10-project
```

测试命令可以通过：

```text
python -X utf8 -m pytest backend/tests --basetemp=.pytest-tmp-backend -q
python -X utf8 -m pytest tests/integration --basetemp=.pytest-tmp-integration -q
```

但后端启动命令失败：

```text
python -m uvicorn backend.app:app
```

失败原因是：

```text
Attribute "app" not found in module "backend.app"
```

这和代码一致。生成包里的 `backend/app.py` 只定义了 `create_store`、`create_book`、`list_books`、`checkout_book`、`return_book`、`delete_book` 等普通 Python 函数，到 `__all__` 结束，没有 ASGI `app` 对象，也没有 HTTP route。见：

```text
examples/generated-workspaces/tiny-fullstack/10-project/backend/app.py:20-73
```

但同一个包的 `run-manifest.json` 明确声明：

```text
run-backend = python -m uvicorn backend.app:app
run-frontend = python -m http.server 5173 --directory frontend
```

见：

```text
examples/generated-workspaces/tiny-fullstack/10-project/run-manifest.json:3-31
```

同时，生成出来的 verification evidence 只有两个测试命令：

```text
test-backend
test-integration
```

没有 `run-backend` 和 `run-frontend` 的运行证据。见：

```text
examples/generated-workspaces/tiny-fullstack/20-evidence/tests/verification-runs.json:1-92
```

我也抽取了命令覆盖情况：

```text
run-manifest commands:
- run-backend
- run-frontend
- test-backend
- test-integration

verification-runs:
- test-backend
- test-integration

missing evidence:
- run-backend
- run-frontend
```

所以这不是“偶然启动失败”，而是 closeout 允许一个**从未启动过的项目包**通过。

---

# 2. 当前 tiny-fullstack 的真实工作方式

## 2.1 后端测试不是 API 测试，而是函数库测试

生成包里的后端测试直接 import `backend.app`：

```text
examples/generated-workspaces/tiny-fullstack/10-project/backend/tests/test_api.py:12-17
```

随后直接调用：

```text
app.create_book(...)
app.list_books(...)
app.checkout_book(...)
app.return_book(...)
app.delete_book(...)
```

见：

```text
examples/generated-workspaces/tiny-fullstack/10-project/backend/tests/test_api.py:100-169
```

这验证了“一个 Python 函数库 + SQLite BookStore”是否工作，但没有验证：

```text
HTTP server 是否存在；
backend.app:app 是否存在；
GET /books 是否存在；
POST /books 是否存在；
checkout / return / delete 路由是否存在；
run-backend 是否能启动。
```

## 2.2 前后端集成测试是 fake fetch，不是 live integration

`tests/integration/test_frontend_backend.py` 里定义了 `fakeFetch`，它直接返回假的 `/books` 响应，并记录 URL/options：

```text
examples/generated-workspaces/tiny-fullstack/10-project/tests/integration/test_frontend_backend.py:29-54
```

真正的测试只断言：

```text
calls[0].url == '/books'
calls[1].url == '/books/42'
calls[1].options.method == 'DELETE'
```

见：

```text
examples/generated-workspaces/tiny-fullstack/10-project/tests/integration/test_frontend_backend.py:58-82
```

这不是 full-stack 集成测试。它证明的是：

```text
frontend/app.js 的 loadBooks 和 deleteBook 会调用某个注入的 fetchImpl。
```

它没有证明：

```text
后端服务已启动；
前端服务已启动；
前端从真实页面发起请求；
请求抵达后端；
后端读写 SQLite；
返回真实数据；
前后端协议一致。
```

---

# 3. 根因分层

## 根因 1：架构合同自相矛盾

这是最上游的问题。

合同里声明后端运行命令是：

```text
python -m uvicorn backend.app:app
```

见：

```text
tests/fixtures/contracts/tiny_fullstack_contract.py:301-304
```

但 provider prompt 又明确要求：

```text
Use only Python standard library modules.
Do not use Flask, FastAPI, requests, npm, or other third-party packages.
Backend scope must expose create_store, create_book, list_books, checkout_book, return_book, delete_book in backend/app.py and a sqlite3-backed BookStore in backend/db.py.
```

见：

```text
tests/proving/fixtures/tiny_provider_attempts.py:532-545
```

这两个要求不可同时成立。

如果要 `uvicorn backend.app:app`，就必须允许并要求 ASGI app，例如 FastAPI / Starlette / bare ASGI app，并且要有依赖声明。

如果要坚持标准库，就不应该写 `uvicorn backend.app:app`，而应该让后端用 `http.server` 或 `wsgiref` 之类的标准库服务启动，例如：

```text
python -m backend.app
```

或：

```text
python backend/app.py
```

当前 worker 实际上遵循了 provider prompt，生成了函数式 backend；但 closeout 又按 package contract 宣称它是可运行的 HTTP backend。**这是架构师/contract 层的错误，后续 worker、test、evidence 都是在放大这个错误。**

---

## 根因 2：验收标准过弱，证明对象错了

Acceptance contract 中 `AC-TINY-UI-FETCH-BACKEND` 的表述是：

```text
Frontend fetches the backend API instead of serving static placeholder data.
```

见：

```text
tests/fixtures/contracts/tiny_fullstack_contract.py:200-203
```

`AC-TINY-RUN-TEST-COMMANDS` 的表述是：

```text
Package declares local run and test commands.
```

见：

```text
tests/fixtures/contracts/tiny_fullstack_contract.py:206-209
```

这两个都太弱。

“fetches backend API” 被实现成了 fakeFetch path capture；“declares local run and test commands” 被实现成了 run-manifest 文件存在，而不是 run commands 真实可用。

这类验收标准会天然导向伪闭环：

```text
有 /books 字符串 -> 认为前端调用后端；
有 run-manifest.json -> 认为项目可运行；
有 pytest passed -> 认为 generated package 可启动；
有 evidence refs -> 认为 closeout 成立。
```

正确验收应写成：

```text
backend run command starts a live service and exposes required HTTP endpoints;
frontend run command serves the UI;
frontend code, when loaded from served frontend package, calls the live backend service;
SQLite persistence is verified through the HTTP workflow;
every declared run/test command has final execution or startup-probe evidence.
```

---

## 根因 3：run command 没有成为 closeout 硬门槛

核心代码缺口在 closeout gate。

`RunManifest` 会把 package contract 中的 run/test commands 编译进去。`run_manifest.py` 只要求 software/mixed package 至少有 run commands 和 test commands：

```text
src/boardroom_os/workspace/run_manifest.py:209-215
```

但它没有规定：

```text
每个 run command 必须有运行证据；
每个 run command 必须有 readiness probe；
每个 package command 必须进入 closeout evidence coverage。
```

`CloseoutGate` 的 command evidence 检查逻辑只要求：

```text
已有 verification runs 必须 passed；
每个 verification run 必须有一个 run manifest binding；
binding 的 command 必须匹配。
```

见：

```text
src/boardroom_os/closeout/gate.py:707-771
```

它没有检查：

```text
run_manifest.commands 中是否还有未验证的 command。
```

所以只要 verification runs 里有：

```text
test-backend
test-integration
```

并且这两个测试通过，closeout gate 就不会追问：

```text
run-backend 为什么没跑？
run-frontend 为什么没跑？
```

这就是不可启动包能 closeout 的直接机制原因。

---

## 根因 4：fixture 只执行测试命令，不执行运行命令

tiny package assembly 里只跑两个命令：

```text
for command_id in ("test-backend", "test-integration"):
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:714-715
```

provider attempt 阶段也显式传了空 `command_ids`：

```text
"command_ids": (),
```

见：

```text
tests/proving/fixtures/tiny_provider_attempts.py:276
```

locked provider replay closeout 阶段同样传空 `command_ids`：

```text
"command_ids": (),
```

见：

```text
tests/proving/fixtures/tiny_closeout.py:761
```

也就是说，当前 V2 runtime executor 本身有能力执行命令，但它只执行调用方传入的 command ids：

```text
for command_id in runtime_input.command_ids:
    command_runner.run(...)
```

见：

```text
src/boardroom_os/execution/runtime_executor.py:327-352
```

问题不在于 runner 完全不能跑命令，而在于 proving fixture 和 closeout policy 没有把 run commands 编译成必须执行的 obligations。

---

## 根因 5：evidence obligation 被错误映射

在 tiny package assembly 中，所有 evidence obligations 都被映射到两个测试命令之一：

```text
frontend_backend_integration_evidence
frontend_source_inventory
run_manifest
command_evidence
=> test-integration

其他
=> test-backend
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:1268-1276
```

于是 `command_evidence` 被 `test-integration` 代替了。

这导致 final evidence table 里 `AC-TINY-RUN-TEST-COMMANDS` 显示 satisfied，但实际 evidence ref 指向的是 `test-integration`，不是 `run-backend` 或 `run-frontend`。见：

```text
examples/generated-workspaces/tiny-fullstack/20-evidence/closeout/final-evidence-table.json:113-128
```

这正是“证据真实但证明对象错误”。

---

## 根因 6：功能验证仍是静态标记和签名验证

`_validate_tiny_package_functional_scope` 检查了：

```text
backend/app.py 中有 def delete_book
backend/db.py 中有 sqlite3.connect / CREATE TABLE / INSERT / UPDATE / DELETE
frontend/app.js 中有 loadBooks(fetchImpl) / deleteBook(fetchImpl, bookId)
frontend/app.js 中有 /books / DELETE 字符串
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:870-935
```

这些检查比旧版 placeholder 检查强很多，但仍然不是行为级验证。它不会发现：

```text
backend.app:app 不存在；
uvicorn 无法启动；
HTTP routes 不存在；
frontend 没有和 live backend 串联。
```

前端 integration evidence 的验证也只是要求测试代码里出现：

```text
loadBooks
deleteBook
url/options capture
subprocess/node
/books
DELETE
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:1101-1150
```

这会允许 fakeFetch-only 测试通过。

---

## 根因 7：审计材料是“投影正确”，不是“产品正确”

当前 V2 的 process audit / final evidence table / source inventory 比旧版结构化很多，但它们是从已有 provider attempts、verification runs、evidence obligations 投影出来的。

当上游 contract 和 tests 证明错了东西时，下游 audit 会非常整齐地证明这个错误链路：

```text
所有 refs 都在；
所有 hashes 都有；
所有 evidence rows satisfied；
所有 provider attempts successful；
closeout package 完整；
但项目仍然无法启动。
```

这是 V2 当前最重要的教训：

```text
不要只防 synthetic evidence；
还要防 real evidence for the wrong claim。
```

---

# 4. 对你的两个怀疑的判断

## 4.1 “后端开发和测试采用了 mock，没有真实串联闭环”

基本成立，但需要精确表述。

后端不是 mock，它是一个真实的 SQLite-backed Python 函数库。问题是：

```text
它不是 run-manifest 声称的 HTTP backend。
```

测试层确实高度 mock / white-box：

```text
backend test = 直接调用 Python 函数；
frontend integration = fakeFetch 捕获 URL；
没有 live backend；
没有 live frontend；
没有 HTTP E2E。
```

所以“没有真实串联起零散产物形成完整闭环”是准确的。

## 4.2 “根因可能是架构师给出了错误或有缺陷的实施方案，错误被逐层放大”

成立。

更精确地说，是：

```text
architect/package contract/provider prompt 三者不一致；
acceptance criteria 语义过弱；
execution/evidence/closeout 没有把这种不一致 fail closed；
worker 和 tests 都在错误合同下完成了局部正确产物；
audit 最后忠实记录了一个错误闭环。
```

---

# 5. 必须立即修的 P0

## P0-1：closeout gate 必须覆盖所有 run-manifest commands

当前 closeout 只检查已有 verification runs。应改成：

```text
run_manifest.commands - final_command_bindings.command_id == empty
```

否则直接 blocker：

```text
RUN_MANIFEST_COMMAND_UNVERIFIED
```

最低要求：

```text
run-backend 必须有 evidence；
run-frontend 必须有 evidence；
test-backend 必须有 evidence；
test-integration 必须有 evidence。
```

改动位置：

```text
src/boardroom_os/closeout/gate.py
```

当前漏洞位置：

```text
src/boardroom_os/closeout/gate.py:707-771
```

---

## P0-2：区分 test command 与 service run command

不能把 long-running `run-backend` 当成普通 pytest command。需要新增概念：

```text
RunCommandEvidence
ServiceRunEvidence
StartupProbe
ReadinessProbe
```

建议字段：

```yaml
command_id:
command:
process_started:
pid:
port:
readiness_probe:
  url:
  expected_status:
  expected_body_marker:
startup_timeout_ms:
stdout_ref:
stderr_ref:
shutdown_status:
verified_at:
```

对于 tiny-fullstack，至少要有：

```text
run-backend:
  start process
  probe /health
  POST /books
  GET /books
  POST /books/{id}/checkout
  POST /books/{id}/return
  DELETE /books/{id}
  verify SQLite file exists and contains expected data

run-frontend:
  start static server
  GET /
  GET /app.js
  optionally execute frontend against live backend base URL
```

---

## P0-3：当前失败包必须加入 negative regression

把附件里的失败形态做成固定反例：

```text
backend/app.py has no app object
run-manifest declares uvicorn backend.app:app
backend tests pass
fakeFetch integration passes
closeout must be blocked
```

期望 blocker：

```text
RUN_BACKEND_STARTUP_FAILED
RUN_MANIFEST_COMMAND_UNVERIFIED
LIVE_FRONTEND_BACKEND_EVIDENCE_MISSING
```

放到：

```text
tests/negative/
```

不要只加一个 unit test。要覆盖：

```text
run manifest validation
package assembly
evidence verification
closeout gate
tiny proving fixture
```

---

# 6. tiny-fullstack 合同必须二选一

当前不能继续同时要求：

```text
不使用第三方框架
```

和：

```text
python -m uvicorn backend.app:app
```

这两条互相冲突。

## 路线 A：标准库 HTTP 服务

如果坚持标准库，合同应改成：

```text
run-backend = python -m backend.app
```

后端必须实现：

```text
GET /health
GET /books
POST /books
POST /books/{id}/checkout
POST /books/{id}/return
DELETE /books/{id}
```

可用标准库：

```text
http.server
json
sqlite3
urllib.parse
```

provider prompt 也要明确要求：

```text
backend/app.py must expose a runnable HTTP server entrypoint.
```

而不是只要求 Python 函数。

## 路线 B：ASGI / FastAPI

如果要保留：

```text
python -m uvicorn backend.app:app
```

那就必须允许：

```text
uvicorn
FastAPI 或 Starlette
```

并且 generated package 要包含依赖说明，例如：

```text
requirements.txt
```

或：

```text
pyproject.toml
```

后端合同必须要求：

```text
backend.app:app exists
GET /health route exists
CRUD routes exist
```

我的建议是：**tiny proving scenario 用路线 A，标准库 HTTP。**
理由是它减少外部依赖，能更快把“run command / service probe / live integration / closeout gate”这条主链打硬。

---

# 7. Acceptance criteria 应重写

当前：

```text
AC-TINY-UI-FETCH-BACKEND
AC-TINY-RUN-TEST-COMMANDS
```

需要拆细。建议改为：

```text
AC-TINY-BACKEND-STARTUP
后端 run command 能启动 live service，并通过 readiness probe。

AC-TINY-BACKEND-HTTP-CRUD
通过 HTTP 完成 create/list/checkout/return/delete。

AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP
通过 HTTP 写入后，SQLite 文件和表数据可验证。

AC-TINY-FRONTEND-STARTUP
前端 run command 能启动并服务 index/app.js。

AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION
前端代码在 live backend base URL 下执行真实 fetch，不允许 fakeFetch-only 作为最终证据。

AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED
run-manifest 中每个 run/test command 都有最终证据。

AC-TINY-CLEAN-PACKAGE-EXPORT
最终 package export 不含 __pycache__、pytest tmp、未清单化文件。
```

原来的单元测试仍然可以保留，但只能作为 supporting evidence，不能单独满足 full-stack closeout。

---

# 8. 代码级修正方案

## Phase 1：先堵 closeout 漏洞

修改：

```text
src/boardroom_os/closeout/gate.py
src/boardroom_os/workspace/run_manifest.py
tests/closeout/test_closeout_gate.py
tests/negative/
```

验收：

```text
run_manifest 有 4 个命令而 verification_runs 只有 2 个时，closeout 必须 blocked。
```

不要等 service runner 完成再做这个。这个 blocker 可以先只做覆盖检查。

---

## Phase 2：新增 service runner / startup probe

新增或扩展：

```text
src/boardroom_os/adapters/service_runner.py
src/boardroom_os/execution/service_run.py
src/boardroom_os/workspace/run_manifest.py
```

或在现有 `process_runner.py` 外另开模块。不要把长运行服务硬塞进 `VerificationRun`，否则会把“进程持续运行”错误建模为“命令退出 0”。

新增证据类型：

```text
backend_startup_evidence
frontend_startup_evidence
http_api_flow_evidence
sqlite_persistence_http_flow_evidence
live_frontend_backend_integration_evidence
run_command_evidence
test_command_evidence
```

---

## Phase 3：修正 tiny contract 和 provider prompt

修改：

```text
tests/fixtures/contracts/tiny_fullstack_contract.py
tests/proving/fixtures/tiny_provider_attempts.py
```

核心是消除矛盾：

```text
route A: stdlib HTTP + python -m backend.app
route B: ASGI + uvicorn + dependencies
```

同时把 provider prompt 从“写函数库”改成“写可启动项目包”。

---

## Phase 4：修正 package assembly fixture

修改：

```text
tests/proving/fixtures/tiny_package_assembly.py
```

当前只跑：

```text
test-backend
test-integration
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:714-715
```

应改成：

```text
run-backend startup probe
run-frontend startup probe
test-backend
test-integration-live
```

并删除这个错误映射：

```text
run_manifest / command_evidence => test-integration
```

见：

```text
tests/proving/fixtures/tiny_package_assembly.py:1268-1276
```

---

## Phase 5：修正 integration evidence validator

当前 `_validate_frontend_integration_behavior_evidence` 允许 fakeFetch-only。应改成：

```text
fakeFetch 可以作为 unit-level evidence；
但不能满足 live_frontend_backend_integration_evidence。
```

修改位置：

```text
tests/proving/fixtures/tiny_package_assembly.py:1101-1150
```

新增要求：

```text
测试必须启动或连接 live backend；
必须从 run manifest 获取 backend base URL 或 probe context；
必须通过真实 HTTP fetch 完成至少 list/delete 或完整 CRUD；
不得仅靠 captured fake fetch call 满足最终 AC。
```

---

## Phase 6：修正 golden sample 生成

修改：

```text
scripts/build_tiny_closeout_sample.py
tests/proving/fixtures/tiny_closeout.py
```

当前 closeout input 的 command bindings 是从已有 verification runs 派生的：

```text
command_bindings = tuple(
    _closeout_command_binding(package_fixture, run)
    for run in verification_runs
)
```

见：

```text
tests/proving/fixtures/tiny_closeout.py:1493-1507
```

这会天然漏掉未执行命令。应改成：

```text
closeout input 从 run_manifest.commands 派生 required command obligations；
再绑定实际 evidence；
缺一个就 blocked。
```

---

# 9. Checker 应该怎么改

Checker 不能只读 evidence refs。它必须做一个独立黑盒检查：

```text
1. 从 clean staging checkout 最终 10-project。
2. 读取 package-contract.json / run-manifest.json。
3. 执行或 probe 每个 run/test command。
4. 对 HTTP integration boundary 执行 live probe。
5. 对 source inventory 只做辅助校验，不把 source inventory 当行为证据。
6. 发现任何 declared run command 不可用，直接 REWORK_REQUIRED。
```

Checker verdict 需要区分：

```text
APPROVED
APPROVED_WITH_NON_BLOCKING_NOTES
REWORK_REQUIRED
ESCALATE
```

不可启动项目包不允许是 notes，必须是 blocker。

---

# 10. 这次 V2 重构哪些地方是有价值的

这点也要客观说：V2 不是完全失败。

相比旧系统，当前已经有明显进步：

```text
provider attempts 存在；
fallback 不再是主成功路径；
source inventory / evidence table / closeout gate / replay / process audit 有结构；
runtime 不再直接完成 ticket；
大量 fail-closed 测试已经存在。
```

问题是主风险从：

```text
synthetic evidence
```

升级成了：

```text
real evidence for the wrong claim
```

所以不要推翻 V2 全部设计。应该把修复重点放在：

```text
contract semantic consistency；
run command evidence；
live integration evidence；
black-box package verification；
closeout all-command coverage。
```

---

# 11. 直接修正路线

我建议按这个顺序做，不要并行乱铺：

```text
Step 1:
新增 negative test：当前失败包必须 closeout blocked。

Step 2:
CloseoutGate 增加 all run-manifest commands coverage。

Step 3:
重写 tiny-fullstack contract，二选一：stdlib HTTP 或 ASGI。

Step 4:
新增 ServiceRunner / StartupProbe。

Step 5:
tiny package assembly 执行 run-backend / run-frontend probes。

Step 6:
integration test 改为 live backend + live frontend，不再 fakeFetch-only。

Step 7:
重建 examples/generated-workspaces/tiny-fullstack。

Step 8:
把 README / docs 状态从 foundation-only 更新到当前实现状态。
```

另外我注意到根 `README.md` 仍写着：

```text
status: foundation-only
code status: no implementation yet
```

见：

```text
README.md:7-14
```

这已经和仓库现实不一致。这个不是启动失败的根因，但会污染后续 agent 上下文。应作为文档一致性修复一起处理。

---

# 12. 最终判断

当前重构路线不需要推翻，但 tiny-fullstack 的 proving scenario 必须降级重做。

准确判断是：

```text
V2 框架基座可保留；
当前 tiny-fullstack 证明链不可信；
当前 golden sample 不应继续作为 golden；
必须把它改成 negative regression，再重建新的 live full-stack golden。
```

最核心的一句话：

```text
不要再让“测试通过 + evidence refs 完整 + closeout passed”替代“最终项目包按声明命令真实启动并完成端到端行为”。
```

这次失败的根因不是模型没写好代码，而是 Boardroom OS V2 的合同和证据系统允许 worker 写出“局部正确、整体不可运行”的项目，并允许 checker/closeout 把它认证成完成。下一轮修复必须从 contract 和 closeout gate 下手，而不是继续调 provider prompt。
