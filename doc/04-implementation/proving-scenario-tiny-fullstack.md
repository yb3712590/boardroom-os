# Tiny Full-stack Proving Scenario

## 文档职责

本文件定义 V2 第一个端到端证明场景。它用于证明 agent team framework 能生成一个真实、可运行、可审计的项目包。

## 用户需求

```text
Build a tiny anonymous book availability tracker.
```

## 功能范围

必须实现：

- add book；
- list books；
- checkout book；
- return book；
- delete book；
- book state: `IN_LIBRARY` or `CHECKED_OUT`；
- SQLite persistence；
- frontend calls backend API；
- local run/test commands。

不实现：

- auth；
- multi-user history；
- reports；
- cloud deployment；
- styling polish；
- admin roles。

## 目标项目包建议

```text
10-project/
├── README.md
├── AGENTS.md
├── package-contract.json
├── run-manifest.json
├── backend/
│   ├── app.py
│   ├── db.py
│   └── tests/
├── frontend/
│   ├── index.html
│   └── app.js
└── tests/
    └── integration/
```

具体技术栈可由 architect 决定，但必须满足 package contract。

## 验收标准

### Functional

- API 可创建书籍；
- API 可列出书籍；
- API 可 checkout；
- API 可 return；
- API 可 delete；
- 状态转换正确；
- SQLite 持久化存在；
- 前端真实 fetch backend API。

### Package

- package root 明确；
- run manifest 存在；
- backend start command 存在；
- frontend run/open instruction 存在；
- test command 存在；
- dependency manifest 或 bootstrap instruction 存在。

### Evidence

必须有：

- provider attempt for implementation；
- backend source inventory；
- frontend source inventory；
- SQLite schema or persistence evidence；
- API test run；
- frontend-backend integration evidence；
- final evidence map；
- git version audit；
- replay bundle；
- process audit。

### Negative checks

以下任一情况必须失败：

- provider attempt count 为 0；
- frontend 只是静态占位，没有调用 backend；
- tests 是 synthetic output；
- SQLite evidence 缺失；
- source inventory 没有 producer/evidence refs；
- acceptance map 不完整；
- closeout 无 replay bundle；
- process audit 无 CEO decision timeline。

## 成功定义

成功不是 workflow completed，而是：

```text
Generated project package runnable
+ all blocking acceptance criteria satisfied
+ verified evidence complete
+ source inventory valid
+ checker approved
+ closeout committed
+ replay materialized
+ process audit readable
```

