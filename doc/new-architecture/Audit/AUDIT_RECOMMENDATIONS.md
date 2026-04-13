# Boardroom OS 新架构审计建议

## 执行摘要

新架构设计**总体良好**（4/5 分），但存在**12 个关键问题**需要在实现前解决，特别是在以下几个方面：

1. **初始化顺序不明** - ProjectionSnapshot、Graph、Projection 之间的循环依赖需要破解
2. **并发冲突无保护** - 多个写者（CEO、Hook、Materializer）竞争同一资源缺乏机制
3. **重要参数缺失** - CIRCUIT_BREAKER 阈值、fingerprint 算法等缺乏规范
4. **版本管理不一致** - 文档版本、资产版本、档位版本的管理策略不统一

---

## 详细建议

### 区域 A: 系统初始化与循环依赖

**问题：** `00-autonomous-machine-overview.md` 的系统架构图显示：
- ProjectionSnapshot 依赖 Graph 和 Projection
- Graph 引擎也依赖 Projection
- Projection 由事件派生，但初始时事件为空

**风险：** 冷启动时陷入循环依赖，系统无法启动

**建议方案：**

```markdown
### 初始化序列

**第一阶段：Bootstrap**
1. 初始化空的 EventLog
2. 初始化空的 TicketGraph（只有根节点）
3. 生成初始 ProjectionSnapshot（空状态）

**第二阶段：Constitution 加载**
1. 加载 Constitution 记录（角色、权限、hook、schema）
2. 创建初始 GovernanceProfile
3. 更新 Projection 包含 Constitution 信息

**第三阶段：首次 Graph 初始化**
1. 根据 Charter 生成初始 TicketGraph 版本
2. 计算 ReadyIndex 和其他派生索引
3. 更新 Projection 的 graph_version 和 ready_queue

**关键不变量：**
- 任何 Projection 更新都必须原子性修改 ProjectionSnapshot 的 version 字段
- Graph 重算必须基于特定 EventLog 版本号
- 循环依赖通过"快照版本"打破
```

**实现建议：**
- 使用 version_seal 机制确保一致性
- 定义 BootstrapEvent 和 BootstrapPhase 状态
- 提供 Health Check 验证初始化正确性

---

### 区域 B: 并发冲突与写保护

**问题：** 以下写者可能同时写入同一资源：
1. Hook 写 ProcessAsset 和文档
2. Materializer 重算 ProjectionSnapshot 和 ProjectMap
3. CEO 写 graph patch
4. Scheduler 写租约和 lease 信息

**风险：** 数据不一致、脏写、版本冲突

**建议方案：**

```markdown
### 并发控制模式

**Pattern 1: 事件日志原子性**
- 所有状态变化都必须先写 EventRecord
- EventLog 是单一真相源
- Projection 和其他视图由 EventLog 派生

**Pattern 2: 版本化快照**
- ProjectionSnapshot 必须带 version 和 content_hash
- 任何派生操作都基于特定版本
- 更新时检查 version 一致性（CAS 模式）

**Pattern 3: 写集隔离**
- ProcessAsset 写: Hook + Materializer
  → 分离 hook 产出和扩展审计材料
- ProjectMap 写: Compiler + Hook
  → 定义清晰的更新顺序
- 文档写: Materializer 独占
  → 禁止 Hook 直接改文档

**Pattern 4: 租约机制**
- Scheduler 保持对 TicketNode 的排他性租约
- 只有租约持有者可以改节点状态
- 租约超时自动释放（防止僵死）
```

**实现建议：**
- 实现 OptimisticLocking（基于 version_hash）
- 定义 LeaseAcquisition 和 LeaseRelease 事件
- 提供死锁检测和解决机制

---

### 区域 C: 重要参数和阈值规范

**问题列表：**

| 参数 | 文档 | 当前定义 | 需求 |
|-----|------|--------|------|
| CIRCUIT_BREAKER 阈值 | 05 | "达到阈值" | 建议 3 次失败或 30 分钟 |
| HOT_NODE_THRASH 阈值 | 02 | "反复被替换" | 建议 5 次替换/小时 |
| 上下文预算（token） | 03, 04 | "小、中、大" | 建议 CEO: 8000, Worker: 4000 |
| 版本压缩触发点 | 04 | M3 > 20% | 建议 M3 > 25% 时启动 |
| Hook 超时 | 06 | 未定义 | 建议 300 秒 |
| freezes 传播深度 | 02 | "必要下游" | 建议 transitive closure |
| 资产保留期 | 09 | "retention_policy" | 建议基于 asset_type |

**建议方案：**

```markdown
### 系统常数表

**执行和恢复**
- INCIDENT_CIRCUIT_BREAKER_THRESHOLD = 3
- INCIDENT_CIRCUIT_BREAKER_WINDOW = 30min
- HOT_NODE_THRASH_THRESHOLD = 5
- HOT_NODE_THRASH_WINDOW = 1hour
- RECOVERY_ATTEMPT_MAX = 5
- HOOK_EXECUTION_TIMEOUT = 300s
- ADVISORY_SESSION_TIMEOUT = 2hour

**上下文预算**
- CEO_TOTAL_TOKENS = 8000
  - M0: 800 (10%)
  - M1: 3200 (40%)
  - M2: 1600 (20%)
  - M3: 1600 (20%)
  - Reserve: 800 (10%)
- WORKER_TOTAL_TOKENS = 4000
  - W0: 400 (10%)
  - W1: 1200 (30%)
  - W2: 1600 (40%)
  - W3: 800 (20%)

**存储和清理**
- ASSET_RETENTION_DEFAULT = 180days
  - FAILURE_FINGERPRINT: 365days
  - EVIDENCE_PACK: 90days
  - TICKET_TRACE_PACK: 30days
```

**实现建议：**
- 将常数表定义在配置文件中，可运行时调整
- 提供参数调优指南和性能测试结果
- 实现参数变更的影响分析工具

---

### 区域 D: 文档物化时序与冲突

**问题：** `01-document-constitution.md` 说 REPLACE_VIEW 文档"每次全量重算"，但未定义：
1. 何时触发重算？
2. 重算过程中若有新写入怎么办？
3. 多个 materializer 同时重算怎么办？

**建议方案：**

```markdown
### 文档物化协议

**REPLACE_VIEW 触发条件**
1. 显式事件：`ProjectionSnapshot 版本变化`
2. 定时事件：`Materializer 定期检查（5min 一次）`
3. 按需事件：`CEO 显式请求 REFRESH_PROJECTION`

**物化流程**
1. Materializer 读取最新 ProjectionSnapshot（version: V）
2. 计算应该在文档中的内容（基于 V）
3. 原子性更新文档（原文档 hash 校验）
4. 写 DocumentMaterializationEvent(document_path, old_hash, new_hash, source_version: V)

**冲突处理**
- 如果原文档 hash 不匹配：abort，不执行更新
- 同时多个 materializer 竞争：
  → 第一个写入成功
  → 后续重新读 Projection 再试
- 文档更新过程中新 Projection 来了：
  → 完成当前物化
  → 下一轮再物化新版本

**不变量**
- 文档内容的 hash 和 ProjectionSnapshot 版本必须在事件日志中可追溯
- 文档不能比 Projection 更新
- 允许文档滞后（缓存失效），不允许文档超前
```

**实现建议：**
- 为每份文档维护 (path, version, content_hash) 三元组
- 实现 Materializer 的工作队列
- 提供文档一致性检查工具

---

### 区域 E: Hook 依赖和执行顺序

**问题：** `06-role-hook-system.md` 列出 9 个 hook，但没定义：
1. 执行顺序
2. Hook 之间的数据依赖
3. 上游 Hook 失败时下游 Hook 是否执行

**建议方案：**

```markdown
### Hook 执行拓扑

**生命周期：PACKAGE_COMPILED**
- worker_preflight (无依赖)

**生命周期：RESULT_ACCEPTED**
执行顺序（按依赖）：
1. evidence_capture (需要: Worker 结果)
2. documentation_sync (需要: evidence_capture 的 git 信息)
3. git_closeout (需要: Worker 结果)
4. ticket_trace_capture (需要: 上面三个完成)
5. review_request (需要: ticket_trace_capture)

**生命周期：VERDICT_ACCEPTED**
- review_followup_generation (需要: review verdict)

**生命周期：BOARD_APPROVED**
- board_pack_archive (无依赖)
- closeout_release (需要: board_pack_archive)

**生命周期：INCIDENT_RESOLVED**
- project_map_refresh (需要: incident root cause)

**依赖定义**
每个 hook 明确定义：
- required_inputs[]: 哪些前驱 hook 的输出
- produced_assets[]: 产出哪些资产
- failure_policy: BLOCK_DOWNSTREAM / OPTIONAL / RETRY

**失败处理**
- 如果 required hook 失败：后续 hook 不执行，节点进入 PENDING_HOOKS
- 如果 optional hook 失败：记录 incident，后续 hook 继续
- 同一 hook 失败 3 次：升级为 incident
```

**实现建议：**
- 定义 HookDAG 结构
- 实现拓扑排序和执行引擎
- 提供 Hook 健康指标和重试策略

---

### 区域 F: 版本管理一致性

**问题：** 系统中有多种"版本"，但管理策略不统一：
- graph_version
- GovernanceProfile 版本
- 文档版本
- ProcessAsset 版本
- TicketTrace 版本

**建议方案：**

```markdown
### 统一版本协议

**版本标识**
所有可版本化对象使用：`(entity_type, entity_id, version_number, created_timestamp, content_hash)`

**版本生命周期**
1. DRAFT: 创建但未提交
2. ACTIVE: 当前使用版本
3. SUPERSEDED: 被新版本替代，但可查询
4. ARCHIVED: 进入不可变归档（仅 FULL_TIMELINE 模式）

**版本链**
- 每个新版本都记录 supersedes_ref 指向前一版本
- 允许查询完整的版本链和变更历史
- 提供版本间的 diff 视图

**版本发布规则**
- 所有版本变化都必须落事件日志
- 版本号只能递增，不能回退
- 同一对象不能有多个 ACTIVE 版本

**消费方的版本绑定**
- CEO: 必须知道当前 active graph_version 和 GovernanceProfile
- Worker: ExecutionPackage 中明确绑定 graph_version 和 profile_version
- Compiler: 基于特定版本组合生成执行包
```

**实现建议：**
- 实现通用的 VersionedEntity 基类
- 提供版本查询和链追溯的 API
- 实现版本合并和冲突解决工具

---

### 区域 G: 技能系统的冲突完整性

**问题：** `07-skill-runtime.md` 给出 3 条冲突解法规则，但没有证明这些规则是否覆盖所有场景

**建议方案：**

```markdown
### 技能冲突分类和解法

**冲突类型**

1. **Type 1: 注入级别冲突**
   - 场景: 同时有 REQUIRED 和 PREFERRED 技能
   - 规则: REQUIRED 优先
   - 例: 实现功能(REQUIRED) vs 快速编写(PREFERRED)

2. **Type 2: 互斥冲突**
   - 场景: 两个技能有相同的 conflict_tags
   - 规则: 选择和任务类别最相关的
   - 例: DETAILED_LOGGING vs MINIMAL_OUTPUT 不能同时用

3. **Type 3: 模式冲突**
   - 场景: 不同 approval_mode 需要不同技能
   - 规则: 按 approval_mode 优先
   - 例: AUTO_CEO 不注入 EXPERT_REVIEW 技能

4. **Type 4: 故障态势冲突**
   - 场景: 故障恢复时需要特殊技能
   - 规则: 故障技能覆盖普通技能
   - 例: 调试技能 overrides 实现技能

5. **Type 5: 审计模式冲突**
   - 场景: 不同 audit_mode 需要不同 trace 技能
   - 规则: 按 audit_mode 优先
   - 例: FULL_TIMELINE 强制注入 TIMELINE_TRACE 技能

**完整性验证**
- 覆盖所有 (approval_mode, audit_mode, task_category, failure_status) 的组合
- 对每个组合给出唯一的技能绑定结果
- 提供决策树或真值表
```

**实现建议：**
- 建立技能冲突的完整分类体系
- 实现决策树算法进行冲突解决
- 提供冲突分析和诊断工具
- 编写测试用例覆盖所有冲突场景

---

### 区域 H: 上下文预算超限处理

**问题：** 当 CEO 或 Worker 的上下文预算超限时，缺乏具体的压缩策略

**建议方案：**

```markdown
### 上下文压缩策略

**CEO 压缩（当 M0+M1+M2+M3 > 8000 tokens）**

优先级顺序（从高到低保留）：
1. M1 (ProjectionSnapshot 完整版) - 不压缩
2. M2 (Replan Focus) - 必要时完整保留
3. M0 (Constitution Slice) - 不压缩
4. M3 (ProcessAssets) 开始压缩：
   - 只保留最新版本的 ADR 摘要（删除历史）
   - FAILURE_FINGERPRINT 只保留最热的 5 个
   - 其他资产只保留 digest 而非全文
   - 旧的 DECISION_SUMMARY 只保留标题

**Worker 压缩（当 W0+W1+W2+W3 > 4000 tokens）**

优先级顺序（从高到低保留）：
1. W0 (Constitution Slice) - 不压缩
2. W1 (Task Frame) - 不压缩
3. W2 (Evidence Slice) - 按优先级压缩：
   - 代码片段: 保留最相关的模块（按 ProjectMap hotness）
   - 文档: 保留最新版本和最相关章节
   - ADR: 只保留标题和决策结论
4. W3 (Runtime Guard) - 压缩配置详情

**压缩触发**
- 硬限: 超过 budget 的 110% 立即压缩
- 软限: 超过 budget 的 90% 警告并开始采样
- 预测: 如果当前 add 操作会超限，先压缩再 add

**不可压缩的最小集合**
- M1 的 workflow_status、graph_version、governance_profile_ref
- W0 的 allowed_write_set、required_doc_surfaces
```

**实现建议：**
- 实现上下文大小追踪和预测
- 定义 digest 生成算法（截断 + 哈希链接）
- 提供压缩前后的可读性对比

---

### 区域 I: ProcessMap 的实时性vs性能

**问题：** `09-process-assets-and-project-map.md` 说"地图由资产、事件和代码结构共同派生"，但实时更新可能成为性能瓶颈

**建议方案：**

```markdown
### ProjectMap 更新策略

**三层模式**

1. **即时层** (Snapshot)
   - 更新频率: 每个 RESULT_ACCEPTED 事件后
   - 包含: 最近改动的模块切片
   - 延迟: < 1 秒
   - 用途: Worker 执行包的即时参考

2. **定期层** (Periodical)
   - 更新频率: 5 分钟一次
   - 包含: 完整 ProjectMap（OwnershipMap、FailureHeatMap 等）
   - 延迟: < 5 分钟
   - 用途: CEO 重规划时的参考

3. **离线层** (Offline)
   - 更新频率: 小时级或日级
   - 包含: 完整历史分析（趋势、模式、预测）
   - 延迟: < 1 小时
   - 用途: 项目分析和审计

**增量更新策略**
- 只更新受影响的地图模块
- 使用 versioned diff 格式
- 支持追踪每次地图变化的来源事件

**缓存和一致性**
- 地图查询默认返回最新快照
- 如果需要特定版本的地图，显式指定 timestamp
- 提供一致性检查：确保地图版本和关键事件版本一致
```

**实现建议：**
- 实现增量地图更新引擎
- 建立地图版本索引
- 提供地图一致性验证工具
- 性能测试各层模式的吞吐量

---

## 实现路线

### Phase 0: 前置准备（周 1-2）
- [ ] 定义初始化序列和 bootstrap 协议
- [ ] 明确系统常数表
- [ ] 建立版本管理协议
- [ ] 编写审计工具（检查一致性）

### Phase 1: 核心约束（周 3-4）
- [ ] 实现事件日志和原子性写
- [ ] 实现 OptimisticLocking 和租约机制
- [ ] 实现 ProjectionSnapshot 快照引擎
- [ ] 编写并发测试

### Phase 2: 文档和 Hook（周 5-6）
- [ ] 实现文档物化器
- [ ] 实现 Hook 依赖图和拓扑排序
- [ ] 实现 Hook 执行引擎
- [ ] 编写文档一致性检查

### Phase 3: 上下文管理（周 7-8）
- [ ] 实现 CEO 记忆压缩
- [ ] 实现 Worker 执行包编译
- [ ] 实现上下文预算追踪
- [ ] 编写预算测试

### Phase 4: 技能和优化（周 9-10）
- [ ] 实现技能绑定和冲突解决
- [ ] 实现 ProjectMap 多层更新
- [ ] 性能调优和负载测试
- [ ] 完整集成测试

---

## 验收标准

### 功能完整性
- [ ] 所有 13 文档中描述的协议都有对应的代码实现
- [ ] 每个协议都有对应的自动化测试覆盖
- [ ] 审计工具能验证系统满足所有不变量

### 一致性
- [ ] 无循环依赖或死锁场景
- [ ] 所有并发冲突都有明确的解决机制
- [ ] 版本管理一致且可追溯

### 性能
- [ ] CEO 唤醒时间 < 500ms
- [ ] Worker 执行包编译 < 1s
- [ ] ProjectMap 更新 < 5s（定期层）
- [ ] Hook 链完成 < 60s（大多数情况）

### 可维护性
- [ ] 所有参数可配置，支持运行时调整
- [ ] 有完整的监控和日志
- [ ] 有恢复和故障转移机制
- [ ] 文档和代码保持同步

