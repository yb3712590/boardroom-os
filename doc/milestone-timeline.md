# Boardroom OS 里程碑时间线

> 版本：1.0
> 日期：2026-04-05
> 作者：CTO
> 假设：1-2 名全职开发人员

---

## 一、执行摘要

Boardroom OS 在控制面基础设施方面已经建立了扎实的事件溯源架构、完整的 Ticket 生命周期、Maker-Checker 质量门和 React 治理壳。但核心 Agent 智能（CEO 调度器、真实 Worker 执行、人格模型）完全缺失，这是与 feature-spec 最大的偏离。

本时间线从 2026-04-07 开始，总计 13 周（至 2026-07-04），分 9 个里程碑推进。关键路径是 M1（CEO Agent）→ M2（Worker 执行）→ M7（集成），前端重构（M4）可与后端工作并行。

---

## 二、里程碑总览

```
周次  W1    W2    W3    W4    W5    W6    W7    W8    W9    W10   W11   W12   W13
      ├─M0──┤
            ├────M1────────────┤
                              ├────M2────────────┤
                                                ├──M3──┤
            ├────M4────────────────────┤
                                      ├──M5──┤
                                            ├──M6──┤
                                                  ├────M7────────────┤
                                                                    ├──M8──┤
```

| 里程碑 | 名称 | 起止日期 | 周数 | 优先级 |
|--------|------|----------|------|--------|
| M0 | 基础重置 | 04-07 → 04-11 | 1 | P0 |
| M1 | 最小可行 CEO | 04-14 → 04-25 | 2 | P0 |
| M2 | 最小可行 Worker | 04-28 → 05-09 | 2 | P0 |
| M3 | 人格模型与治理模板 | 05-12 → 05-16 | 1 | P1 |
| M4 | 前端重构 | 04-14 → 05-02 | 3 | P0 |
| M5 | 会议室协议 | 05-05 → 05-09 | 1 | P1 |
| M6 | 检索与 Provider | 05-12 → 05-16 | 1 | P2 |
| M7 | 集成与打磨 | 05-19 → 05-30 | 2 | P0 |
| M8 | 发布候选 | 06-02 → 06-06 | 1 | P0 |

---

## 三、各里程碑详细说明

### M0：基础重置

**日期**：2026-04-07 (周一) → 2026-04-11 (周五)

**目标**：清理代码膨胀，建立干净的开发基线

**交付物**：
1. 将已降级代码（worker-admin、多租户、对象存储、远程 handoff）移入 `backend/app/_frozen/` 目录
2. 更新 import 路径，确保主线代码不依赖 frozen 模块
3. 后端测试全部通过（移除或标记 frozen 模块的测试）
4. 前端目录结构按架构指南重组（创建 types/、api/、stores/、pages/、hooks/ 目录）
5. 安装 Zustand
6. 提取类型定义到 `types/domain.ts` 和 `types/api.ts`

**成功标准**：
- `pytest tests/ -q` 全部通过
- `npm run build` 成功
- frozen 目录中的代码不被主线 import
- 新目录结构存在且 TypeScript 编译通过

**依赖**：无

**风险**：低。主要是文件移动和 import 调整。

**feature-spec 条目**：无直接对应，但为后续所有里程碑扫清障碍

---

### M1：最小可行 CEO

**日期**：2026-04-14 (周一) → 2026-04-25 (周五)

**目标**：用 LLM 驱动的调度器替换 `workflow_auto_advance.py` 中的硬编码逻辑

**交付物**：
1. CEO Action Schema 定义（Pydantic 模型）
   - `CREATE_TICKET`：创建新工单
   - `RETRY_TICKET`：重试失败工单
   - `REASSIGN_TICKET`：重新分派工单
   - `HIRE_EMPLOYEE`：招聘新员工
   - `ESCALATE_TO_BOARD`：升级到董事会
   - `ADVANCE_STAGE`：推进阶段
   - `NO_ACTION`：无需操作
2. CEO State Snapshot Reader
   - 从投影中读取当前工作流状态、工单状态、员工状态、incident 状态
   - 产出结构化的 CEO 输入上下文
3. CEO Action Proposer
   - 通过 OpenAI Compat 调用 LLM
   - 输入：CEO 上下文 + 角色提示 + 输出 schema
   - 输出：一组受控动作
4. CEO Action Validator
   - 对每个提议的动作进行 Reducer 级别的校验
   - 拒绝无效动作，记录原因
5. CEO Trigger Mechanism
   - 事件驱动唤醒：工单完成、工单失败、审批完成、incident 恢复
   - 定时唤醒：每 60 秒检查一次是否有需要推进的工作
6. 集成测试：至少 10 个测试覆盖 CEO 的核心决策路径
7. 确定性回退：当 LLM 不可用时，回退到当前的硬编码逻辑

**成功标准**：
- CEO 能在 `project-init` 后自主创建第一批工单
- CEO 能在工单完成后自主推进到下一阶段
- CEO 能在工单失败后自主决定重试或升级
- 确定性回退路径在 LLM 不可用时正常工作
- 所有新测试通过

**依赖**：M0 完成

**风险**：
- 高：LLM 输出不稳定，需要严格的 schema 校验和回退策略
- 中：CEO 决策质量取决于提示工程，可能需要多次迭代

**feature-spec 条目**：1, 6, 8, 22, 23, 24

---

### M2：最小可行 Worker

**日期**：2026-04-28 (周一) → 2026-05-09 (周五)

**目标**：让至少 3 种 Worker 角色能通过 OpenAI Compat 真实执行工单

**交付物**：
1. Worker 执行管道重构
   - 将 `runtime.py` 中的确定性 mock 替换为真实 LLM 调用
   - 保留确定性路径作为回退
2. 扩展 OpenAI Compat 适配层
   - 支持所有 5 种输出 schema（consensus_document、implementation_bundle、delivery_check_report、ui_milestone_review、delivery_closeout_package）
   - 结构化输出解析和校验
3. 实现 3 种 Worker 角色
   - `frontend_engineer`：能执行 implementation_bundle 工单
   - `checker`：能执行 delivery_check_report 工单
   - `ui_designer`：能执行 ui_milestone_review 工单
4. Schema 校验增强
   - 真实 LLM 输出的 schema 校验
   - 写集验证
   - 失败时的结构化错误报告
5. Provider 健康监控
   - 请求成功率追踪
   - 超时和错误分类
   - 自动降级到确定性路径
6. 集成测试：至少 15 个测试覆盖真实执行路径

**成功标准**：
- 端到端链路：project-init → CEO 创建工单 → Worker 真实执行 → 结果提交 → Maker-Checker → 董事会审查
- 3 种 Worker 角色都能产出有效的结构化输出
- Provider 不可用时自动降级到确定性路径
- 所有新测试通过

**依赖**：M1 完成（CEO 能创建工单）

**风险**：
- 高：LLM 输出格式不稳定，需要健壮的解析和重试
- 中：Token 消耗可能超出预算控制
- 中：不同模型的输出质量差异大

**feature-spec 条目**：26, 28, 33, 38, 39

---

### M3：人格模型与治理模板

**日期**：2026-05-12 (周一) → 2026-05-16 (周五)

**目标**：为 Agent 定义真实的人格维度，让不同角色有可感知的差异

**交付物**：
1. 人格维度定义
   - `skill_profile`：技术能力维度（如 frontend_mastery、testing_rigor、architecture_sense）
   - `personality_profile`：工作风格维度（如 risk_tolerance、detail_orientation、communication_style）
   - `aesthetic_profile`：审美偏好维度（如 minimalism、color_sensitivity、typography_awareness）
2. 预设人格模板
   - 至少 6 种预设：cautious_craftsman、bold_innovator、meticulous_reviewer、pragmatic_builder、visual_perfectionist、systematic_thinker
3. 人格注入 Context Compiler
   - 在编译执行包时，将员工人格注入角色提示
   - 人格影响输出风格，但不影响 schema 结构
4. 多样性约束
   - CEO 招聘时检查团队人格分布
   - 避免所有员工使用相同人格模板
5. 更新 staffing_catalog.py 中的模板
6. 文档型治理角色模板
   - 新增 CTO / 架构师这类低频、高成本、以文档为主的角色模板
   - 这类角色默认产出架构、选型、里程碑、详细设计、TODO 等治理文档
   - CEO 可按治理模板决定何时拉起这些角色参与，而不是默认常驻编码

**成功标准**：
- 同一工单由不同人格的 Worker 执行，输出风格有可感知差异
- CEO 招聘时考虑团队多样性
- 人格数据在 Review Pack 中可见
- CTO / 架构师类角色与日常实施 Worker 的职责边界清晰
- CEO 可以依据治理模板按需拉起文档型角色，而不是把高成本角色常驻在日常链路里

**依赖**：M2 完成（Worker 能真实执行）

**风险**：低。主要是数据定义和提示工程。

**feature-spec 条目**：12, 13, 14, 15, 20, 60, 61, 62

---

### M4：前端重构

**日期**：2026-04-14 (周一) → 2026-05-02 (周五)

**目标**：将 monolithic App.tsx 重构为模块化架构

**交付物**：
1. 第一周（04-14 → 04-18）：基础设施
   - 完成目录结构创建
   - 提取所有类型到 types/
   - 创建 API 客户端层（api/client.ts、api/projections.ts、api/commands.ts）
   - 创建 SSE 管理器（api/sse.ts）
   - 创建 3 个 Zustand stores
   - 创建 ErrorBoundary 组件
2. 第二周（04-21 → 04-25）：组件提取
   - 提取布局组件（AppShell、TopChrome、ThreeColumnLayout）
   - 提取仪表盘组件（InboxWell、WorkflowRiver、OpsStrip、RuntimeStatusCard、BoardGateIndicator、CompletionCard、ProjectInitForm）
   - 提取 WorkforcePanel 和 EventTicker
   - 创建通用 Drawer 组件
3. 第三周（04-28 → 05-02）：覆盖层和测试
   - 重构 ReviewRoomDrawer 使用通用 Drawer
   - 重构 IncidentDrawer
   - 重构 DependencyInspectorDrawer
   - 重构 ProviderSettingsDrawer
   - 拆分 CSS 到多个文件
   - 添加核心测试（stores、API 客户端、关键组件）
   - 简化 App.tsx 到 < 50 行

**成功标准**：
- App.tsx < 50 行
- 所有功能与重构前完全一致
- `npm run build` 成功
- `npm run test:run` 通过至少 20 个测试
- 无 TypeScript 编译错误

**依赖**：M0 完成（目录结构已创建）

**风险**：
- 中：重构过程中可能引入回归
- 低：功能不变，只是结构调整

**feature-spec 条目**：51, 52, 53, 54, 55

**注意**：M4 可与 M1/M2 并行执行（前端和后端独立）

---

### M5：会议室协议

**日期**：2026-05-05 (周一) → 2026-05-09 (周五)

**目标**：实现最小结构化多角色协作

**交付物**：
1. 会议事件类型定义
   - `MEETING_REQUESTED`、`MEETING_STARTED`、`MEETING_ROUND_COMPLETED`、`MEETING_CONCLUDED`
2. 最小会议执行器
   - 支持 2 种会议类型：`SCOPE_ALIGNMENT`（范围对齐）、`TECHNICAL_DECISION`（技术决策）
   - 3 轮结构：立场轮 → 质疑轮 → 收敛轮
   - 每轮产出结构化输出
3. 共识文档生成
   - 会议结束后自动生成 `consensus_document@1`
   - 进入 Maker-Checker 闭环
4. CEO 触发会议的决策逻辑
   - 当检测到多个 Worker 对同一问题有分歧时，CEO 可以发起会议

**成功标准**：
- 至少一种会议类型能端到端执行
- 会议产出的共识文档通过 Maker-Checker
- 会议事件在事件流中可见

**依赖**：M2 完成（Worker 能真实执行）

**风险**：中。多角色协作的提示工程复杂度较高。

**feature-spec 条目**：41, 42, 43, 44, 45

---

### M6：检索与 Provider 增强

**日期**：2026-05-12 (周一) → 2026-05-16 (周五)

**目标**：增强 Context Compiler 的检索能力和 Provider 配置

**交付物**：
1. FTS5 关键词检索
   - 在 SQLite 中创建 FTS5 虚拟表
   - 索引工单结果、审查摘要、incident 摘要
   - Context Compiler 在编译时查询相关历史
2. Provider 路由基础
   - 支持多 Provider 配置（不同角色可绑定不同 Provider）
   - 基础健康检查（ping endpoint）
   - 简单 fallback：主 Provider 不可用时切换到备用
3. 能力标签
   - 为每个 Provider 定义支持的能力标签
   - Worker 分派时匹配能力标签
4. 角色-模型路由策略
   - 支持角色级默认模型绑定
   - 支持任务级覆盖与 `preferred model / actual model` 追踪
   - 支持高价模型低频参与策略，让 CEO、文档型角色、实施 Worker 可走不同模型池

**成功标准**：
- Context Compiler 能检索到相关历史摘要
- 至少支持 2 个 Provider 配置
- Provider 不可用时自动 fallback
- 同一角色的期望模型与实际执行模型可在审计中追踪
- 可以配置“高价模型只给少量高杠杆角色使用”的策略，而不影响常规 Worker 日常执行

**依赖**：M2 完成

**风险**：低到中。FTS5 实现成本低，但模型路由策略需要控制复杂度和成本漂移。

**feature-spec 条目**：32, 56, 58, 59, 62

---

### M7：集成与打磨

**日期**：2026-05-19 (周一) → 2026-05-30 (周五)

**目标**：端到端集成测试、视觉打磨、文档更新

**交付物**：
1. 端到端集成测试
   - 完整链路：project-init → CEO 调度 → Worker 执行 → Maker-Checker → 董事会审查 → closeout
   - 至少 5 个完整链路测试场景
   - 故障场景：Worker 失败 → incident → 恢复 → 继续
2. 前端视觉打磨
   - 实现 Workflow River 粒子动画（CSS）
   - 实现 Board Gate 呼吸动画
   - 加载骨架屏
   - 响应式布局调整
3. 性能基准
   - 事件写入延迟 < 10ms
   - 投影重建延迟 < 100ms（1000 事件）
   - Context 编译延迟 < 500ms
   - 前端首屏加载 < 2s
4. 文档更新
   - 更新 README.md
   - 更新 doc/TODO.md
   - 更新 memory-log.md
   - 编写运维指南

**成功标准**：
- 端到端链路在真实 LLM 下能完整跑通
- 前端视觉符合 visual-spec 要求
- 性能基准全部达标
- 文档完整且准确

**依赖**：M1-M6 全部完成

**风险**：
- 中：集成时可能发现跨模块问题
- 低：视觉打磨风险可控

**feature-spec 条目**：全部

---

### M8：发布候选

**日期**：2026-06-02 (周一) → 2026-06-06 (周五)

**目标**：最终验证、打包、准备发布

**交付物**：
1. 全量回归测试
   - 后端：所有测试通过
   - 前端：所有测试通过 + 构建成功
   - 端到端：至少 3 次完整链路成功执行
2. 安全审查
   - API Key 存储安全性
   - 输入校验完整性
   - 无硬编码凭证
3. 打包
   - Docker Compose 配置（后端 + 前端）
   - 一键启动脚本
   - 环境变量文档
4. 发布说明

**成功标准**：
- 新用户能在 5 分钟内启动系统
- 完整链路在全新环境中能跑通
- 无已知 P0 bug

**依赖**：M7 完成

**风险**：低。主要是验证和打包。

---

## 四、关键路径

```
M0 ──→ M1 ──→ M2 ──→ M3 ──→ M7 ──→ M8
         │                    ↑
         └──→ M4 ────────────→┘
              M2 ──→ M5 ──→ M7
              M2 ──→ M6 ──→ M7
```

**最长路径**：M0 → M1 → M2 → M7 → M8 = 1 + 2 + 2 + 2 + 1 = 8 周

**并行机会**：
- M4（前端重构）与 M1/M2（后端 CEO/Worker）完全并行
- M3（人格模型）、M5（会议室）、M6（检索）可在 M2 完成后并行

---

## 五、风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LLM 输出不稳定导致 CEO 决策质量差 | 高 | 高 | 严格 schema 校验 + 确定性回退 + 多次迭代提示 |
| Token 消耗超出预算 | 中 | 中 | Context Compiler 预算控制 + 模型选择优化 |
| 前端重构引入回归 | 中 | 中 | 逐步迁移 + 每步验证 + 保留旧代码直到确认 |
| 不同 LLM 模型输出差异大 | 中 | 中 | 标准化输出 schema + 模型无关的解析层 |
| 集成时发现跨模块问题 | 中 | 高 | M7 预留 2 周 + 持续集成测试 |
| 单人开发瓶颈 | 高 | 中 | 前后端并行 + 优先级严格排序 |

---

## 六、资源需求

| 资源 | 数量 | 说明 |
|------|------|------|
| 后端开发 | 1 人 | Python/FastAPI/事件溯源经验 |
| 前端开发 | 1 人 | React/TypeScript/Zustand 经验 |
| LLM API 额度 | ~$200/月 | 开发和测试用量 |
| 测试环境 | 1 套 | 本地 SQLite + OpenAI Compat API |

---

## 七、需要董事会决策的节点

| 时间点 | 决策内容 |
|--------|----------|
| M1 结束 | CEO Agent 的决策质量是否达到可接受水平？是否需要调整策略？ |
| M2 结束 | Worker 执行质量是否达标？是否需要更换 LLM 模型？ |
| M4 结束 | 前端重构后的视觉效果是否符合预期？ |
| M7 中期 | 端到端链路是否稳定？是否需要延长打磨时间？ |
| M8 结束 | 是否准备好发布？ |
