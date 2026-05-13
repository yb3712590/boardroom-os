# Boardroom OS V2

Boardroom OS V2 是一个从干净分支重新铺陈的 agent team framework 基座。

本分支的目标不是修复旧 runtime，也不是整理旧实现资产，而是重新建立一个可信的、CEO-governed、contract-first、evidence-first 的项目生成与审计框架。

## 当前状态

```text
status: foundation-only
code status: no implementation yet
legacy status: archived history only, abandoned by default
first implementation entrypoint: src/boardroom_os/ after Phase 0 acceptance
```

## 一句话定位

Boardroom OS V2 接收自然语言需求或 PRD，由 CEO / Architect / Worker / Checker 等 agent seat 在显式 ticket graph 和合同约束下协作，最终生成一个可运行、可验证、可审计的目标项目包。

## 为什么 V2 近似另起项目

旧主链的失败不是局部 bug，而是权力结构错误：runtime 可以制造 source delivery、verification runs 和 workflow completion，CEO / architect / checker / closeout 只能在事后发现证据缺口。V2 不以旧 runtime 为实现基础。

V2 的基本原则：

1. CEO / architect 产出的合同和 ticket graph 是项目推进的治理源。
2. runtime 只执行、记录、校验、投影事实，不替代治理判断。
3. source、test、acceptance、closeout 证据必须来自真实执行或明确分类的可审计事实。
4. fallback 默认不能满足 implementation evidence。
5. 最终交付物是 generated project package，不是一组离散 source artifact。

## 新分支建议

可在现有仓库历史上创建干净 orphan 分支：

```bash
git switch --orphan rebuild/v2-clean-foundation
git rm -rf .
# 解压本基座包到仓库根目录
git add .
git commit -m "docs: establish Boardroom OS V2 clean foundation"
```

也可在全新仓库中直接解压使用。

## 入口文件

建议后续 AI 和人类先按以下顺序阅读：

1. `README.md`
2. `AGENTS.md`
3. `doc/README.md`
4. `doc/01-product/prd.md`
5. `doc/02-solution/construction-plan.md`
6. `doc/03-architecture/technical-architecture.md`
7. `doc/04-implementation/acceptance-criteria.md`
8. `doc/06-reference/legacy-boundary.md`

## 当前不做什么

- 不迁移旧 `backend/app/core/runtime.py`。
- 不整理旧模块资产图。
- 不保留旧 workflow compatibility。
- 不把 workflow completed 当作项目完成。
- 不把 synthetic verification 当作 evidence。
- 不在没有 active acceptance contract 的情况下写实现。

## 目录概览

```text
.
├── AGENTS.md
├── README.md
├── doc/
├── src/
├── tests/
├── scripts/
└── examples/
```

详细文档目录见 `doc/README.md`。

