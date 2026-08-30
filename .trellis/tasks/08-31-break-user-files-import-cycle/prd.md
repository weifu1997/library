# 打断 `services.user_files` 循环导入

父任务：`08-31-full-code-review`
来源：实施 `08-31-frontend-coverage-surface` 期间的顺带发现

## Problem

```
user_files → pipelines.registry → pipelines.archive → tasks
  → tasks.runner → tasks.handlers → mine_relations
  → mine_citation_graph → services.exports → user_files
```

裸解释器里 `import library.services.user_files` 直接 ImportError
（"cannot import name 'get_user_metadata' from partially initialized module"）。

测试套件碰不到它——因为其它模块先被导入，环在别处闭合。
只有"第一个就导入某个 service"的场景会炸：脚本、REPL、
以及任何不启动整个 app 就想用一个 service 的代码。

`test_ingest_coverage_surface_unit.py` 当时被迫在顶部写
`import library.main` 来绕开，这本身就是味道。

## Requirements

- 打断环，`import library.services.user_files` 在裸解释器中可用
- 不改变运行时行为（延迟导入只是把 import 时机后移）
- 需要测试锁定，且必须在**独立进程**中验证——同进程里导入顺序会掩盖回归
- 移除此前为绕开该环加的 workaround

## Acceptance Criteria

- [x] `python -c "import library.services.user_files"` 成功
- [x] 新测试在**子进程**中逐个导入 8 个模块，均成功
- [x] 该测试在修复前会红（实测：`user_files` 与 `exports` 两条失败）
- [x] `test_ingest_coverage_surface_unit.py` 的 `import library.main` workaround 已删除
- [x] `uv run pytest tests/` 全量通过；`ruff` 通过

## 选择的修法

`services/exports.py` 只在一个函数里用到 `get_user_metadata`，
模块顶层并不需要该符号。改为**函数内延迟导入**，并在模块顶部留注释
写明完整的环路径——否则下一个人会顺手把它挪回顶层。

考虑过但未采用：把 `get_user_metadata` 下沉到 repository 层。
那会把"用户可见元数据聚合"这个业务概念错放到仓储层，
为了解一个导入环而扭曲分层，代价更大。

## Non-Goals

- 不重构 `pipelines ↔ tasks` 之间更大的依赖网（环上的其余部分）
