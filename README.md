# Boardroom OS

事件源、无状态、可审计、可重放的 AI 自治 runtime 实验项目。

本分支已进入后端自治 runtime 重建基线：旧浏览器界面已从当前源码树移除，当前目标是先把后端事件日志、ticket graph、provider、scheduler、replay/resume、evidence 和 closeout 链路跑稳。

## 当前定位

- **后端 runtime**：FastAPI + Pydantic + SQLite(WAL) + pytest。
- **真相来源**：事件日志、确定性投影、ticket graph、process asset 和 artifact index。
- **执行模型**：worker/checker 消费 compiled execution package，所有动作由 reducer / policy / guard 校验。
- **文档入口**：从 [`doc/README.md`](doc/README.md) 进入当前真相、重构控制面和必要历史归档。

## 快速开始

```bash
cd backend
python -m pytest tests/test_scenario_config.py -q
python -m pytest tests/test_live_configured_runner.py -q
```

本地服务入口仍在后端：

```bash
cd backend
uvicorn app.main:app --reload
```

## 当前重构控制面

- [`doc/mainline-truth.md`](doc/mainline-truth.md)：当前代码事实锚点。
- [`doc/refactor/planning/INDEX.md`](doc/refactor/planning/INDEX.md)：自治 runtime 大重构控制面。
- [`doc/refactor/planning/00-refactor-north-star.md`](doc/refactor/planning/00-refactor-north-star.md)：本轮北极星与非目标。
- [`doc/refactor/planning/09-refactor-plan.md`](doc/refactor/planning/09-refactor-plan.md)：分阶段执行计划。
- [`doc/refactor/planning/10-refactor-acceptance-criteria.md`](doc/refactor/planning/10-refactor-acceptance-criteria.md)：可验证验收标准。

## 历史材料

旧愿景、旧设计、旧路线、旧任务流水、旧界面材料和 integration logs 已集中到 [`doc/archive/`](doc/archive/)；默认不要把它们作为当前实现上下文。

## License

MIT
