# tests

V2 测试未来进入本目录。

建议结构：

```text
tests/
├── negative/
├── contracts/
├── reducers/
├── execution/
├── evidence/
├── closeout/
└── proving/
```

第一批测试应优先覆盖 negative acceptance：

- fallback source delivery must fail；
- provider zero-attempt must fail；
- synthetic verification must fail；
- checker notes must not clear blockers；
- missing acceptance map must block closeout。

详见 `doc/TEST_CONVENTIONS.md`。

