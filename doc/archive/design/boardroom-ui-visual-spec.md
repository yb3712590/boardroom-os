# Boardroom UI Visual Spec

## Status
- Draft locked to approved concept
- Date: 2026-04-01
- Scope: MVP dashboard shell, Inbox, workflow river, Board Gate reminder, supporting visual rules

## 1. Role Of This Document

这份文档把已确认的首页视觉方向翻译成可执行的实现约束，供 React / CSS / motion 实现时参考。

它回答的问题不是“产品有哪些功能”，而是：

- 哪些信息必须放在第一屏
- 这些信息应该通过什么几何、颜色和动效表达
- 哪些视觉手法必须避免

## 2. Core Visual Direction

视觉主旨：

`premium near-future operating surface`

关键词：

- seamless
- dark glass
- pale blue
- low saturation
- soft internal glow
- sparse copy
- embedded workflow
- rare gold escalation

首页体验应该更接近一块高端未来产品的 OS 表面，而不是“深色后台 + 卡片 + 表格”的常规 SaaS 模板。

## 3. Information Hierarchy

首页第一屏的优先级固定如下：

1. `workflow river`
2. `ticket flow and active stage`
3. `board reminder state`
4. `inbox / alert summary`
5. 低频全局控制

被降级到二级或折叠区域的信息：

- 全量 workforce 名册
- event explorer 明细
- dependency graph
- developer inspector
- 大段审计正文

这意味着首页默认不是“什么都看见”，而是先保证“系统当下正在发生什么”一眼可读。

## 4. Layout Model

### 4.1 Overall Shell

- 页面表现为一整块大玻璃面板
- 默认桌面宽屏采用 `single slab`，避免并排大卡片
- 分区依靠雾度、切线、轨道和密度变化，不依靠厚重容器

建议比例：

- top chrome: `56px - 72px`
- left inbox well: `22% - 28%`
- workflow stage: `60% - 68%`
- board branch and reminder: `12% - 18%`

### 4.2 Left Inbox Well

- 作为浅雾蓝玻璃井存在
- 默认展示 4 到 6 条摘要项
- 每条项高度保持一致，靠色条与符号表达优先级
- 列表项只保留最短必要文案

建议状态形状：

- neutral: 冷蓝灰条目
- board required: 香槟金高亮条
- incident: 暗红高亮条
- completed / archived: 更低对比的退场样式

### 4.3 Workflow River

- 主河道必须横向穿过主视图
- 轨道不应厚重，但必须稳定可见
- 阶段名浮于轨道上下，不能抢过 ticket 粒子
- 活跃阶段通过局部泛光、微增雾度和聚光感体现

阶段建议保持固定顺序：

- `Intake`
- `Plan`
- `Build`
- `Check`
- `Review`

### 4.4 Board Branch

- 只在需要审批的 ticket 存在时提亮
- 默认情况下可弱化为一条几乎不可见的潜在支路
- 激活后从蓝色主轨道平滑偏转到金色支路
- 终点为 `Board Gate` 节点，而不是大面积金色门形 logo

## 5. Ticket Rendering Rules

`ticket` 在首页不采用卡片表达，默认采用：

- 光点
- 小型发光 capsule
- 极短拖尾
- 沿轨道的定向运动

视觉要求：

- 单个 ticket 的轮廓足够清晰
- 多个 ticket 同屏时，仍能分辨前进方向
- 粒子大小稳定，不做脉冲式尺寸变化
- 拖尾很短，只用于提示方向，不应像长曝光特效

状态语义：

- pending on main path: 低亮蓝白
- active build: 更亮的冰蓝
- in check: 稍收敛，速度减缓或在节点附近停驻
- board required: 进入金色支路
- incident interrupted: 脱离主河道，进入红色异常语义

## 6. Board Reminder Semantics

当 ticket 进入董事会审查链路时，提醒必须是联动的，但仍然克制。

必须同时出现的 3 个反馈：

1. 顶栏右侧出现一枚金色提醒灯
2. 左侧 Inbox 对应项切换为金色高亮
3. `Board Gate` 节点边缘进入慢速呼吸

不应该做的事：

- 全屏弹窗
- 大面积闪烁
- 高频震动或抖动
- 在首页直接展开完整 review pack

完整审查内容仍应通过 `Inbox -> Review Room` 进入。

## 7. Surface And Material Rules

材质要求：

- dark glass
- frosted translucency
- subtle inner highlight
- very light edge reflection

禁止事项：

- 普通深色卡片阴影堆叠
- 厚边框拼接后台
- 金属拉丝工业件质感过强
- 过于明显的 3D 挤压按钮

实现上建议优先使用：

- 低透明度渐变背景
- 1px 到 1.5px 的半透明描边
- 极弱内高光
- `backdrop-filter` 或等效的雾化表面效果

## 8. Color Tokens

以下颜色不是品牌定稿，只是当前实现建议基线：

- page background: `#0A111B`
- deep glass: `#101927`
- mid glass: `#172334`
- line blue: `#C7E1FF`
- soft blue fill: `#DDEEFF`
- active ice glow: `#ECF7FF`
- muted label: `#9EB3CA`
- board gold: `#E1C68B`
- board gold deep: `#C7A45E`
- incident rose: `#A34F63`
- incident deep: `#6E2433`

语义规则：

- 首页 80% 以上区域应维持在深蓝黑和低饱和浅蓝内
- 金色只给董事会升级语义
- 红色只给异常态

## 9. Typography

首页文本必须服从图形，不允许反过来。

建议：

- 使用现代无衬线 UI 字体
- 标题轻中等字重
- 标签和阶段名尽量短
- 不在首页使用大段正文说明
- 不默认使用控制台风格等宽字做主体阅读

标题、标签与状态文案应做到：

- 扫一眼就能读完
- 被删掉后仍不影响大结构理解

## 10. Motion

动效节奏应接近高端操作系统，而不是营销页面。

建议范围：

- hover / focus: `140ms - 200ms`
- stage emphasis: `220ms - 320ms`
- ticket drift: 匀速或轻微 easing
- board reminder pulse: `2.4s - 3.2s` 的慢速呼吸

动效规则：

- 不做夸张位移
- 不用重弹性 spring
- 不使用持续粒子喷发
- 保持 `prefers-reduced-motion` 兼容

## 11. Responsive Behavior

桌面优先，但必须提前考虑窄屏退化：

- 小于 `1280px` 时，Inbox 可以缩窄
- 小于 `1100px` 时，次级控制入口折叠
- 小于 `900px` 时，Workflow River 仍必须保持可读，不应碎成很多卡片
- 移动端不要求复刻桌面构图，但必须保留：
  - 主流程阶段
  - 当前 ticket 流转
  - Board 提醒
  - Inbox 入口

## 12. Mapping To Product Surfaces

### Dashboard

- 使用这套视觉语言作为第一屏默认视图
- 首页重点只放 `Inbox summary + Workflow River + Board reminder`

### Inbox

- 保持同样的浅蓝玻璃体系
- 列表项颜色和首页提醒语义完全一致

### Review Room

- 保持同一套材质，但允许信息密度更高
- 进入 Review Room 后才展开完整证据、差异、风险和操作按钮

### Workforce / Event Pulse

- 当前阶段不要求始终占据首页主舞台
- 更适合作为 secondary inspector、可切换面板或下钻视图
- 不应破坏首页的主河道叙事

## 13. Implementation Notes

前端实现时建议先建立稳定的 design tokens：

- colors
- blur levels
- glow levels
- border alpha
- motion durations
- corner radii

再在这些 token 上实现：

1. glass shell
2. inbox well
3. workflow river
4. ticket particle
5. board reminder branch

不要先堆业务列表，再事后贴一层视觉皮。

## 14. Non-Negotiables

以下规则在 MVP 前端开发中默认视为硬约束：

- 首页第一眼必须以 `workflow river` 为主，不准退回卡片后台拼盘
- `ticket` 必须以光点 / 发光 capsule 流转，不准默认退回列表卡片
- `Board Gate` 的提醒必须使用独立金色语义
- `incident` 红色语义不能被普通执行态复用
- workforce 与 event pulse 不得抢占首页主舞台
- 首页不能变成大段文字说明页

## 15. Related Documents

- [boardroom-ui-visual-concept.md](boardroom-ui-visual-concept.md)
- [boardroom-ui-design.md](boardroom-ui-design.md)
- [boardroom-data-contracts.md](boardroom-data-contracts.md)
