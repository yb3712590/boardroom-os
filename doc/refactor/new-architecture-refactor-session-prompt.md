# 新架构重构会话提示词

> 用途：每次新开会话时，整段复制给开发代理。  
> 目标：让会话高幂等地继续推进新架构重构，不乱改架构决策文档，不把计划文档格式改乱。

```md
基于当前 Boardroom OS 仓库继续推进新架构重构，只做增量实现，不重建骨架，不把仓库当成空白项目。

这轮的最高规则先写死：

1. `doc/new-architecture/**` 是架构决策文档，默认只读，不允许修改
2. `doc/new-architecture/Audit/**` 是审计材料，默认只读，不允许修改
3. 本轮真正允许持续更新的主文档只有：
   - `doc/refactor/new-architecture-implementation-plan.md`
   - 本轮实际受影响的运行文档，例如 `doc/TODO.md`、`doc/history/memory-log.md`
4. 不要重写 `doc/refactor/new-architecture-implementation-plan.md` 的结构，不要改标题层级，不要重排章节，不要把格式改乱
5. 只允许更新主计划里的这些内容：
   - 顶部状态和时间戳
   - 阶段状态
   - 切片状态
   - 勾选框
   - “任务清单核对区”
   - “偏差与待决策”
   - “本轮会话记录”
   - “当前快照”

先建立上下文，顺序固定：

1. 读 `README.md`
2. 读 `doc/README.md`
3. 读 `doc/mainline-truth.md`
4. 读 `doc/roadmap-reset.md`
5. 读 `doc/TODO.md`
6. 读 `doc/new-architecture/README.md`
7. 读 `doc/refactor/new-architecture-implementation-plan.md`
8. 只读当前阶段相关的 `doc/new-architecture/*.md`
9. 只有在需要历史原因时，才读 `doc/history/context-baseline.md` 和 `doc/history/memory-log.md`

如果 `doc/refactor/new-architecture-implementation-plan.md` 不存在：

1. 从 `doc/refactor/new-architecture-implementation-plan-template.md` 复制一份到固定路径
2. 填好顶部元信息
3. 根据 `doc/new-architecture/10-migration-map.md` 和审计报告锁定当前阶段
4. 再开始实现

高幂等推进规则：

- 每次新会话必须先判断“我现在是在继续哪个阶段、哪个切片”
- 如果主计划里某个切片已经是 `done`，不要重新开一个同义切片
- 如果某个切片没做完，继续原切片，不要换名字重建
- 如果发现新问题但不影响当前切片闭环，只记录到“新发现但不在本轮做”
- 如果发现问题会影响当前切片继续推进，记录到“偏差与待决策”并显式标状态
- 不要把“计划做”“理论上支持”“后面补”写成已完成
- 只有代码、验证、文档同步都完成后，才能把对应项勾成完成

本轮必须遵守的新架构边界：

- 文档不是真相源，事件、图、资产才是真相源
- Worker 必须朝 `CompiledExecutionPackage` 收口
- Hook 必须朝正式门禁收口
- 错误必须显式化，不要用静默 fallback 掩盖
- 审批和审计档位只能影响运行时，不得改写真相底座

每轮只允许选一个主方向推进，默认连续完成 `2` 到 `4` 个强相关切片。
如果当前计划已经锁了切片，优先继续当前切片，不要重新规划一轮新路线。

开始实现前，必须先输出：

1. 当前代码状态总结
2. 当前阶段
3. 当前切片
4. 本轮要做的 `2` 到 `4` 个连续动作
5. 本轮明确不做的内容
6. 然后直接开始实现，不要停在计划阶段等确认

实现要求：

- 必须交付真实代码，不写空计划
- 必须补最小验证
- 必须同步必要文档
- 如果环境缺依赖导致无法完成验证，要明确写出缺什么、卡在哪里
- 不要顺手改无关模块，不要大面积重命名，不要重排目录

每一阶段实施后，固定按这个顺序收尾：

1. 跑本轮验证命令
2. 对照主计划的“当前阶段出口条件”和“任务清单核对区”
3. 勾选已完成项
4. 保留未完成项，不删除
5. 把新问题写进“偏差与待决策”或“新发现但不在本轮做”
6. 追加一条“本轮会话记录”
7. 更新“当前快照”
8. 如有必要，更新 `doc/TODO.md`
9. 如本轮影响实现判断，更新 `doc/history/memory-log.md`

如果某轮没有改 `doc/TODO.md` 或 `doc/history/memory-log.md`，收尾时必须明确说明原因。

完成后按这个顺序汇报：

1. 改了哪些文件
2. 落地了哪些能力
3. 哪些仍未完成
4. 做了哪些验证，哪些因环境限制没法做
5. 主计划更新了哪些部分
6. `doc/TODO.md` 是否更新；如果没更新，说明原因
7. `doc/history/memory-log.md` 是否更新；如果没更新，说明原因
8. 下一轮应该从哪个切片继续
```
