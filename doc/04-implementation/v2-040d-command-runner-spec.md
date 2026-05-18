# V2-040D CommandRunner 设计 Spec

## 1. 现实场景

本轮对应的现实场景是：agent 或 runtime 声称“测试跑过 / 命令成功”时，Boardroom OS V2 必须能证明这不是口头声明、伪造 payload 或 synthetic verification（合成验证成功），而是由受控 runner（运行器）真实执行 package contract（包合同）中声明的命令后留下的审计事实。

通俗地说，V2-040D 要做的是给 generated project package（生成项目包）装一个“验票机”：只有合同里登记过、执行包里携带过、由 runner 真正执行过的命令结果，才能成为后续 EvidenceVerifier（证据验证器）可消费的 command evidence（命令证据）。

## 2. 目标

实现 CommandRunner（命令执行器）和 VerificationRun（验证运行）最小闭环：

1. 真实执行 declared command（已声明命令）。
2. 捕获 `exit_code`、`stdout_ref`、`stderr_ref`、`duration_ms`、`started_at`、`finished_at`、`runner_ref`、`environment_profile_ref`。
3. 校验命令必须同时存在于 `ExecutionPackage.commands`（执行包命令）和 `PackageContract.run_commands/test_commands`（包合同运行/测试命令）。
4. 拒绝 synthetic verification success（合成验证成功）、缺 stdout/stderr refs、缺 exit_code、未声明命令。
5. 产出可用于 V2-050 EvidenceClaim / EvidenceVerifier（证据声明 / 证据验证器）的 typed fact（类型化事实），但不在本工作包内完成 evidence verification（证据验证）。

## 3. 非目标

V2-040D 不做以下事情：

1. 不实现 EvidenceClaim（证据声明）或 VerifiedEvidenceTable（已验证证据表），这些属于 V2-050。
2. 不实现 RunManifest（运行清单）或 workspace/package assembler（工作区/项目包装配器），这些属于 V2-060。
3. 不做 SourceInventory（源码清单）构建、artifact hash lineage（产物哈希来源链）闭合或 closeout gate（收尾门禁）。
4. 不让 runtime 根据命令结果完成 ticket（任务），ticket completion（任务完成）仍由 reducer/evidence/checker 链路决定。
5. 不把失败命令当成异常吞掉；失败命令也应作为真实 VerificationRun 事实返回，由后续 verifier/checker 判定能否满足验收。
6. 不 emit `COMMAND_RUN_RECORDED`（命令运行已记录）事件；事件封装由 V2-040E runtime executor（运行时执行器）统一处理。
7. 不计算 workspace snapshot hash（工作区快照哈希）；本期只记录调用方传入的 `workspace_snapshot_ref`。

## 4. 选型结论

采用“合同绑定 runner”方案，且该方案足以闭合 V2-040D。V2-040D 的验收目标是“command evidence（命令证据）只能来自 runner 真实运行且命令必须是合同声明命令”，不要求本期验证 artifact hash（产物哈希）、source inventory（源码清单）或 final evidence table（最终证据表）。

### 4.1 被采用方案：合同绑定 runner

CommandRunner 同时接收：

- `ExecutionPackage`（执行包）：表示当前 agent 被允许执行哪些命令；
- `PackageContract`（包合同）：表示最终 generated project package 声明了哪些 run/test commands（运行/测试命令）；
- command id（命令 ID）：表示本次要运行哪条命令；
- package root（包根）：表示命令实际执行边界；
- `workspace_snapshot_ref`（工作区快照引用）：由调用方注入，runner 只记录不构造；
- `environment_profile_ref`（环境配置引用）：由调用方注入，runner 只记录不解析 registry。

只有同一 `command_id` 同时出现在执行包和包合同中，且两边的完整 `PackageCommand` 完全一致，runner 才能执行。

优点：

- 直接满足 V2-040D “命令不在 package contract 中必须失败”；
- 保持 contract-first（合同优先），不把执行包当成唯一真相；
- 为 V2-060 run manifest（运行清单）保留清晰接入点。

代价：

- runner 输入比“仅执行包 runner”多一个 PackageContract；
- 测试 fixture（夹具）需要同时构造 ExecutionPackage 和 PackageContract。

### 4.2 未采用方案：仅执行包 runner

只校验命令在 `ExecutionPackage.commands` 中。

不采用原因：无法直接证明命令属于 active PackageContract（活跃包合同），会把 package contract 约束转嫁给 compiler（编译器）前置假设，fail-closed 边界偏弱。

### 4.3 未采用方案：完整证据 runner

runner 同时做 artifact hash、workspace snapshot、EvidenceVerifier 结论。

不采用原因：会提前侵入 V2-050/V2-060 职责，扩大 V2-040D 范围，降低阶段边界清晰度。

## 5. 已决实施决定

1. 合同绑定 runner 足以闭合 V2-040D；EvidenceVerifier（证据验证器）和 RunManifest（运行清单）接入留给 V2-050/V2-060。
2. `VerificationRun.status` 是持久化字段，但由 `exit_code` 决定；直接构造时允许显式传入，validator 必须强校验 `exit_code == 0` 对应 `passed`，非 0 对应 `failed`。CommandRunner 生成 VerificationRun 时不得让调用方选择 status。
3. stdout/stderr 首版使用 deterministic output refs（确定性输出引用）：`command-output.<verification_run_id>.stdout` 与 `command-output.<verification_run_id>.stderr`。V2-040D 捕获输出内容并返回在 `CommandRunnerResult`（命令执行器结果）中，但不负责导出到 `20-evidence/`。
4. `workspace_snapshot_ref` 在 V2-040D 必填，由 `CommandRunnerInput`（命令执行器输入）注入；runner 不构造、不计算 hash、不读取 workspace manifest。
5. `environment_profile_ref` 在 V2-040D 必填，由 `CommandRunnerInput` 注入并原样记录到 VerificationRun；runner 不解析环境 registry。
6. `COMMAND_RUN_RECORDED` 事件不在 V2-040D 生成；V2-040D 只返回 VerificationRun，V2-040E 负责 runtime event boundary（运行时事件边界）。
7. 执行包和包合同中的命令匹配口径是完整 `PackageCommand` 相等：同一 `command_id` 下，`label`、`command`、`cwd` 必须完全一致。
8. 测试可注入 deterministic clock（确定性时钟）；默认 runner 使用 UTC system clock（UTC 系统时钟）。
9. 测试命令必须使用 `sys.executable` 构造，避免 Windows / shell PATH 差异导致环境敏感失败。

## 6. 模块设计

### 6.1 `src/boardroom_os/execution/verification_run.py`

新增 typed schema（类型化结构）：

- `VerificationRunRef`（验证运行引用）
- `CommandOutputRef`（命令输出引用）
- `RunnerRef`（运行器引用）
- `EnvironmentProfileRef`（环境配置引用）
- `WorkspaceSnapshotRef`（工作区快照引用）
- `VerificationRunStatus`（验证运行状态）：`passed | failed`
- `VerificationRun`（验证运行）

字段：

```yaml
version: 1
verification_run_id:
execution_package_ref:
ticket_ref:
command_id:
command:
cwd:
exit_code:
status:
stdout_ref:
stderr_ref:
duration_ms:
started_at:
finished_at:
runner_ref:
environment_profile_ref:
workspace_snapshot_ref:
```

关键校验：

1. 必填字段缺失必须失败。
2. `exit_code` 必须存在且为整数。
3. `stdout_ref` / `stderr_ref` 必须存在，即使内容为空也要有 ref。
4. `runner_ref`、`environment_profile_ref`、`workspace_snapshot_ref` 必须存在且非空。
5. `started_at` / `finished_at` 必须是 timezone-aware datetime（带时区时间）。
6. `finished_at < started_at` 必须失败。
7. `duration_ms` 必须非负，并且不得大于 `finished_at - started_at` 毫秒区间。
8. `status` 必须与 `exit_code` 一致：`0 -> passed`，非 `0 -> failed`。
9. `command` tuple 必须非空且不含空参数。
10. `cwd` 必须非空。
11. `extra="forbid"`，拒绝未知字段。

### 6.2 `src/boardroom_os/adapters/process_runner.py`

新增执行适配层：

- `CommandRunnerInput`（命令执行器输入）
- `CommandRunnerResult`（命令执行器结果）
- `CommandRunnerError`（命令执行器错误）
- `ProcessResult`（进程结果）
- `ProcessExecutor` protocol（进程执行协议）
- `SubprocessExecutor`（subprocess 执行器）
- `CommandRunner`（命令执行器）
- `Clock` protocol（时钟协议）
- `SystemClock`（系统时钟）

`ProcessExecutor` 协议固定为：

```python
class ProcessExecutor(Protocol):
    def run(self, *, command: tuple[str, ...], cwd: Path) -> ProcessResult:
        ...
```

`ProcessResult` 固定字段：

```python
class ProcessResult(BaseModel):
    exit_code: int
    stdout: str | bytes
    stderr: str | bytes
```

Runner 负责在调用 `ProcessExecutor.run` 前后用 `Clock.now()` 记录 `started_at` / `finished_at`。`ProcessExecutor` 不返回 VerificationRun，也不负责构造 stdout/stderr refs。

`Clock` 协议固定为：

```python
class Clock(Protocol):
    def now(self) -> datetime:
        ...
```

`SystemClock.now()` 返回 timezone-aware UTC datetime。

`CommandRunnerInput` 固定字段：

```yaml
execution_package:
package_contract:
command_id:
package_root:
runner_ref:
environment_profile_ref:
workspace_snapshot_ref:
```

职责：

1. 用 `command_id` 在 `execution_package.commands` 中找到 exactly one `PackageCommand`。
2. 用同一 `command_id` 在 `package_contract.run_commands + package_contract.test_commands` 中找到 exactly one `PackageCommand`。
3. 要求两个 `PackageCommand` 完全相等，包括 `label`、`command`、`cwd`。
4. 将 declared `cwd` 解析到 `package_root` 内；解析后的工作目录必须等于 `package_root / command.cwd` 且不能越过 `package_root`。
5. 调用 `ProcessExecutor.run(command=command.command, cwd=resolved_cwd)` 真实执行命令。
6. 捕获 stdout/stderr 内容，生成 deterministic stdout/stderr refs，并返回 `VerificationRun`。

进程执行层在测试中可以替换，但替换对象只能返回 `ProcessResult`，不能直接返回 `VerificationRun`，避免测试绕过 runner。

### 6.3 stdout/stderr refs 策略

V2-040D 使用 deterministic in-memory output refs（确定性内存输出引用）：

```text
command-output.<verification_run_id>.stdout
command-output.<verification_run_id>.stderr
```

CommandRunnerResult 同时携带：

```yaml
verification_run:
stdout:
stderr:
```

stdout/stderr 内容来自真实 process result；VerificationRun 只保存 refs。V2-060E 后续负责把 refs 和内容导出为 `20-evidence/` bundle（证据包）。

## 7. 数据流

```text
PackageContract（包合同）
  + ExecutionPackage（执行包）
  + requested command_id（请求命令 ID）
  + package_root（包根）
  + environment_profile_ref（环境配置引用）
  + workspace_snapshot_ref（工作区快照引用）
      -> CommandRunner（命令执行器）
          -> declared command validation（声明命令校验）
          -> process execution（进程执行）
          -> stdout/stderr refs（输出引用）
          -> VerificationRun（验证运行）
              -> V2-050 EvidenceClaim / EvidenceVerifier
```

CommandRunner 只产出事实，不决定 acceptance satisfied（验收满足）、ticket completed（任务完成）或 closeout passed（收尾通过）。

## 8. Fail-closed 规则

以下情况必须失败：

1. 直接构造 synthetic `VerificationRun(status=passed)` 但缺 `exit_code`。
2. `VerificationRun` 缺 `stdout_ref` 或 `stderr_ref`。
3. `VerificationRun` 缺 `runner_ref`。
4. `VerificationRun` 缺 `environment_profile_ref`。
5. `VerificationRun` 缺 `workspace_snapshot_ref`。
6. `VerificationRun.status` 与 `exit_code` 不一致。
7. 请求运行的 `command_id` 不在 `PackageContract.run_commands/test_commands`。
8. 请求运行的 `command_id` 不在 `ExecutionPackage.commands`。
9. 同一 `command_id` 在执行包和包合同中的完整 `PackageCommand` 不一致，包括 `label`、`command` 或 `cwd` 任一差异。
10. declared `cwd` 解析后越过 package root。
11. process result 缺 `exit_code`、`stdout` 或 `stderr`。
12. injected clock 返回 naive datetime（无时区时间）必须失败。
13. command tuple 为空或包含空参数时由现有 `PackageCommand` / `VerificationRun` 校验失败。

## 9. Happy path

最小正例：

1. 构造 active `PackageContract`，包含一个 test command，测试中使用 `sys.executable -c "print('ok')"`。
2. 构造 `ExecutionPackage`，携带完全相同的 `PackageCommand`。
3. CommandRunner 在临时 package root 内运行该命令。
4. 返回 `VerificationRun`：
   - `exit_code == 0`
   - `status == passed`
   - `stdout_ref` / `stderr_ref` 非空
   - `environment_profile_ref` 非空
   - `workspace_snapshot_ref` 非空
   - `duration_ms >= 0`
   - `started_at` / `finished_at` 带时区
   - `command_id`、`command`、`cwd` 与声明命令一致
5. `CommandRunnerResult.stdout` 包含真实 stdout 内容，`CommandRunnerResult.stderr` 包含真实 stderr 内容。

失败命令正例：

1. declared command 真实执行并返回非 0 exit code。
2. runner 返回 `VerificationRun(status=failed)`，不抛出治理异常。
3. 后续 EvidenceVerifier / Checker 决定该 run 是否阻断验收。

## 10. 测试计划

新增 `tests/execution/test_command_runner.py`。

### 10.1 Negative tests（先写）

1. `test_verification_run_rejects_synthetic_success_without_exit_code`
2. `test_verification_run_requires_stdout_and_stderr_refs`
3. `test_verification_run_rejects_status_that_disagrees_with_exit_code`
4. `test_verification_run_requires_environment_profile_ref`
5. `test_command_runner_rejects_command_not_in_package_contract`
6. `test_command_runner_rejects_command_not_in_execution_package`
7. `test_command_runner_rejects_command_contract_mismatch`
8. `test_command_runner_rejects_cwd_outside_package_root`
9. `test_command_runner_rejects_process_result_without_exit_code`
10. `test_command_runner_rejects_naive_clock_timestamp`

### 10.2 Happy path tests

1. `test_command_runner_records_successful_declared_command`
2. `test_command_runner_records_failed_declared_command_as_fact`
3. `test_command_runner_captures_stdout_stderr_and_duration`

### 10.3 Regression scope

完成后至少运行：

```bash
PYTHONPATH="src;." pytest tests/execution/test_command_runner.py -q
PYTHONPATH="src;." pytest tests/execution tests/negative -q
PYTHONPATH="src;." pytest tests/contracts tests/reducers tests/execution tests/negative -q
```

## 11. 与现有模块的关系

1. 复用 `PackageCommand`（包命令），不新增第二套 command schema。
2. 复用 `ExecutionPackage.commands`（执行包命令集合）。
3. 复用 `PackageContract.run_commands/test_commands`（包合同命令集合）。
4. `COMMAND_RUN_RECORDED`（命令运行已记录事件）已存在于 `EventType`，V2-040D 只产出 `VerificationRun`；事件封装由 V2-040E runtime executor（运行时执行器）统一接入。
5. `VerificationRun` 后续会被 V2-050 EvidenceClaim（证据声明）引用，而不是直接成为 verified evidence（已验证证据）。
6. `environment_profile_ref` 是 V2-040D 对 execution-and-runtime-boundary.md 中 environment profile（环境配置）要求的最小记录，不替代后续 workspace/run manifest 的环境解析。

## 12. 验收映射

本 spec 对应 backlog 工作包：V2-040D。

覆盖 `acceptance-criteria.md` Phase 4：

- AC-V2-EVIDENCE-001（command evidence from runner）：由 `tests/execution/test_command_runner.py` 证明 synthetic verification success（合成验证成功）和未声明命令必须失败，真实 runner 记录可生成 VerificationRun。

完成 V2-040D 后应按 backlog 完成协议更新：

1. `doc/04-implementation/backlog.md`：V2-040D 状态改为 DONE，当前未完成工作包指向 V2-040E，Phase 4 进度 4/5。
2. `doc/04-implementation/acceptance-criteria.md`：勾选 AC-V2-EVIDENCE-001。
3. `doc/05-project-log/2026-05.md`：追加 V2-040D 记录，包含 negative / happy tests 和验证命令。
4. 不需要更新 `decisions.md`，因为本 spec 只收敛 V2-040D 内部实现口径，没有改变 runtime/evidence 架构边界。

## 13. 已收敛评审点

1. 合同绑定 runner 足以闭合 V2-040D。
2. `VerificationRun.status` 存储但必须与 `exit_code` 一致，CommandRunner 按 exit code 生成。
3. stdout/stderr refs 使用 deterministic refs，本期不写 evidence bundle。
4. `workspace_snapshot_ref` 本期必填且由调用方注入，runner 不构造。
5. `COMMAND_RUN_RECORDED` 事件留给 V2-040E。
6. `environment_profile_ref` 本期作为必填字段显式记录。
7. PackageCommand 等值口径是完整对象相等。
8. ProcessExecutor / Clock 协议已固定。
9. 测试命令使用 `sys.executable` 保证可移植性。
