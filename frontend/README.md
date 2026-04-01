# Boardroom UI

`frontend/` 是当前本地 MVP 的独立 React 治理壳。它不拥有工作流真相，只消费后端投影并提交治理命令。

## 当前已落地

- 首页会并行拉取 `dashboard` 和 `inbox`
- 没有 active workflow 时，会显示最小 `project-init` 表单，并明确提示它会把 workflow 推进到首个 scope review
- 主舞台是 `Workflow River`，使用 `dashboard.pipeline_summary.phases` 的固定五段摘要：`Intake / Plan / Build / Check / Review`
- `Inbox` 里的 review 项可以直接打开 `Review Room`
- 可以直接提交 `board approve / reject / modify constraints`
- 前端会在命令成功后立即重新拉取，并用 `events/stream` 做失效通知

## 当前边界

- 前端只是最薄治理壳，不复刻后端工作流引擎
- `events/stream` 只做刷新提示，不作为浏览器里的第二真相源
- `project-init` 现在会同步尝试推进到首个 scope review；如果没有 eligible worker，或途中出现 incident，前端只展示后端停下来的真实状态
- 本轮没有做 provider/model 设置页、incident 详情页、workforce 深入视图和 dependency inspector

## 本地运行

先启动后端：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

再启动前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8000`。

## 验证

运行前端测试：

```bash
cd frontend
npm run test:run
```

运行生产构建：

```bash
cd frontend
npm run build
```
