# V2-080C/D ProviderAttempt 与 Evidence 修补 Spec

## 背景

V2-080C / V2-080D 首轮提交存在两个完成度缺口：

1. V2-080C（真实 ProviderAttempt，模型调用尝试记录）依赖 ignored `.env.test`，但 provider 配置仍有 `base_url`、`model`、`api_protocol` 静默默认，且 OpenAIProviderTransport（OpenAI 兼容模型传输层）只生成 raw/parsed ref（原始/解析产物引用），没有物化真实 provider output（模型输出）。
2. V2-080D（EvidenceVerifier，证据验证器）用 fake provider result（伪模型结果）和临时恒真 pytest 证明 runner pipeline（命令运行管线），却把 FinalEvidenceTable（最终证据表）提前构造成 complete（完成）。

## 决策

- V2-080C live provider test（真实模型测试）保持默认运行，按 `.env.test` → `.env` 查找 ignored env 文件；缺 env、缺 key 或缺部署配置直接 fail closed（失败关闭）。
- `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`BOARDROOM_OPENAI_MODEL`、`BOARDROOM_OPENAI_API_PROTOCOL` 是必填部署配置；timeout / retry / verbosity 等策略配置可使用 `.env.example` 中的显式默认。
- OpenAIProviderTransport 必须把 raw response（原始响应）和 parsed provider text（解析模型文本）写入 typed FileProviderOutputStore（文件型模型输出存储），artifact ref（产物引用）必须包含稳定 sha256（内容摘要）。
- V2-080D 只证明真实 CommandRunner（命令运行器）产生的 command evidence（命令证据）可被 EvidenceVerifier 验证；它不补 SourceInventory（源码清单）、RunManifest（运行清单）、SQLite persistence evidence（SQLite 持久化证据）或 package assembly（项目包装配）。
- FinalEvidenceTableBuilder（最终证据表构建器）判定 satisfied（满足）时，必须覆盖该 blocking criterion（阻塞验收项）的全部 `evidence_required`（证据需求）。只有部分 required artifact type（必需产物类型）时 row 保持 missing（缺失），并保留已验证 evidence refs 与 `missing_required_artifact_types`（缺失必需产物类型）供审计。

## 修补范围

- Provider 配置：`OpenAIProviderSettings.from_env_files(...)` 支持 `.env.test` → `.env` 顺序；缺必填部署配置不回退。
- Provider artifact：新增 `FileProviderOutputStore`、`ProviderOutputArtifact`、`ProviderOutputContentHash`，真实调用成功后 raw/parsed refs 可读取、可 hash 校验。
- Tiny fixture：`build_tiny_provider_attempt_fixture` 明确区分 fake / real，不再用 `model_construct` 绕过 `ExecutionPackageCompilerInput`（执行包编译输入）或 `RuntimeExecutionInput`（运行时执行输入）校验。
- Evidence table：`FinalEvidenceRow` 增加 `missing_required_artifact_types`；CheckerService（检查服务）接受“部分 evidence 已验证但 required artifact 仍缺失”的 missing row。
- V2-080D proving：只验证 `api_test_run`、`frontend_backend_integration_evidence`、`command_evidence` 三类 command evidence；缺 `backend_source_inventory`、`frontend_source_inventory`、`sqlite_persistence_evidence`、`run_manifest` 时 CompletionGate（完成门禁）必须阻断。

## 验收

- 缺 `.env.test` / `.env` 或缺必填部署配置时，080C live provider test 失败。
- Provider 成功返回后，raw/parsed artifact 可读取，artifact ref 内 sha256 与文件内容一致。
- Tiny fixture 源码不包含 `.model_construct(`，也不再暴露 `build_tiny_real_provider_attempt_fixture` 命名。
- FinalEvidenceTable 对同一 acceptance_ref 缺任一 required artifact type 时不 complete。
- V2-080D command-only table 不通过 CheckerService / CompletionGate；V2-080E 才负责补齐 package/source/run/persistence evidence。
