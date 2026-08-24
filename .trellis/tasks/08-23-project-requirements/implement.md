# 执行计划：交付编码评测基准任务套件（父任务）

> 父任务交付物 = 基准任务套件的**任务地图 + 集成评审**；各子任务交付自己的规格文档。

## 交付清单（ordered）

- [ ] **1. 子任务规格完成**：`08-23-dashboard`、`08-23-settings-llm-rework` 的 `prd.md` / `design.md` / `implement.md` 均已定稿。
- [ ] **2. 便携任务文档**：为每个子任务生成自包含的 `.md`（`dashboard-benchmark-task.md`、`llm-settings-rework-task.md`），可直接拷给目标 AI。
- [ ] **3. 环境验证**：前后端可跑、规格引用的端点真实存在。
- [ ] **4. 集成评审**：任务地图与实际工件一致，无孤儿/错位。

## 验证命令（父任务级别）

```bash
# 环境探活
curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/
# dashboard 引用的现有端点
curl -s http://127.0.0.1:8000/v1/tasks/running-count
curl -s http://127.0.0.1:8000/v1/settings/server | head -c 300
curl -s http://127.0.0.1:8000/v1/semantic-index/status
# llm-rework 引用的端点
curl -s http://127.0.0.1:8000/v1/settings/llm | head -c 400
curl -s http://127.0.0.1:8000/v1/settings/llm/test | head -c 300
```

## 回滚点

- 无产品代码改动；若子任务规格间出现契约冲突，以实际代码（`desktop/src/types/api.ts`、`routes_*.py`）为准修订。

## 完成前检查（review gate）

- [ ] 任务地图准确，两份任务各自独立可交付。
- [ ] 每个子任务规格自包含、可目视验收、明确不入库。
- [ ] 提交最终规划摘要（覆盖全部子任务），等用户明确批准后再 `task.py start`。
