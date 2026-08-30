# 执行计划：产出并验证「知识库概览仪表盘」基准任务规格

> 本任务交付物 = 一份可转交给其他 AI 的编码评测任务规格（不含功能代码实现）。

## 交付清单（ordered）

- [ ] **1. 规格定稿**：`prd.md`（需求/验收）+ `design.md`（技术设计/API 契约）已可交付。
- [ ] **2. 便携任务文档**：生成一份自包含的 `dashboard-benchmark-task.md`（可直接拷贝给目标 AI），内容 = 背景 + 需求（R1–R8）+ API 契约 + 测试要求 + 验收标准。
- [ ] **3. 规格可落地性验证**（下述验证命令）。
- [ ] **4. 可选：预置演示数据**：把 `samples/` 素材灌入库，让验收"目视有东西可看"。

## 验证命令（规格声明必须可复现）

```bash
# 后端起得来（当前已跑，探活确认）
curl -s http://127.0.0.1:8000/health && echo

# 规格里引用的现有端点真实存在（已验证，复核一遍）
curl -s http://127.0.0.1:8000/v1/tasks/running-count
curl -s http://127.0.0.1:8000/v1/settings/server | head -c 300
curl -s http://127.0.0.1:8000/v1/semantic-index/status

# 前端 dev server 起来且 /v1 代理通
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:5173/

# 测试运行方式（供规格引用；目标 AI 实现后跑）
.venv/bin/python -m pytest tests/ -q -x
```

## 关键文件 / 风险点

- `src/library/main.py`：新 router 挂载点（`app.include_router(...)`）——规格需提示目标 AI 别漏注册。
- `desktop/src/App.tsx` + `desktop/src/components/Sidebar.tsx`：路由与侧栏入口，漏改则页面无法到达。
- `desktop/src/api/client.ts` + `desktop/src/types/api.ts`：前后端契约锁点，类型与 JSON 需同步。
- `desktop/src/lib/i18n.ts`：新增文案必须走 i18n，否则中文界面缺字。
- 风险：目标 AI 可能找不到 tags/entries 计数入口 → 规格已给 repositories 路径与计数模式示例（`repositories/tasks.py:337`）。

## 回滚点

- 本任务是规格编写，不产生产品代码；无代码回滚需求。
- 若目标 AI 实现时遇到契约不一致，以 `desktop/src/types/api.ts` 与 `routes_*.py` 为准修订规格。

## 完成前检查（review gate）

- [ ] 规格自包含：目标 AI 无需追问即可开工。
- [ ] 验收标准可目视判断 + 有测试兜底。
- [ ] 改动不入库说明清晰（R8）。
- [ ] 提交最终规划摘要，等用户明确批准后再 `task.py start`。
