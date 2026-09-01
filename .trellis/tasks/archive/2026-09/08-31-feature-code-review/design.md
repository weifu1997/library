# Design — 按功能切片的全量代码审查

本任务不改产品架构。本文件约定审查方法、归属边界、报告契约，以及审查结果如何变成后续修复任务。

可加载副本：`research/review-protocol.md`。

## Boundaries

- **父任务**：需求源、任务地图、跨子任务验收、集成去重。不审某一功能面的代码。
- **子任务**：独立的只读审查，交付自己的 `report.md`。可独立 start / check / archive。
- **产品代码**：只读。审查过程中的笔记只写在任务目录。

## Review method

每个子任务按这个顺序做，并在报告 §0 写清覆盖深度：

1. 读本子任务 `prd.md`、父任务 `research/prior-findings.md` 与 `research/review-protocol.md`。
2. 列出 in-scope 文件与对应测试模块（以该子任务 `implement.md` 清单为准，发现遗漏则补进报告而不是默默跳过）。
3. 跑与本面相关的只读信号（测试收集、已有单测名字、ruff/tsc 如需要）。不加 `--fix`。
4. 对清单里的每个文件做模式扫描（异常吞掉、原始 SQL、路径拼接、`except Exception`、未鉴权路由、TODO/死代码）。
5. 对高风险函数做逐行阅读。超过 ~200 行的函数必须在报告里标明「逐行」或「未逐行 + 原因」。
6. 五个角度各写结论。
7. 回归核对 Fixed 表中属于本面的项。
8. 写出 `report.md`。不创建修复任务。

## Overlap / ownership

| 主题 | 归属 |
|---|---|
| 某格式如何解析、coverage 如何标记 | ingest |
| 文件夹树、条目、标签、关系、journal、catalog/view 挖掘 | library-org |
| HTTP 上传、用户文件、scan/sync/reprocess | upload-scan-sync |
| FTS / embedding / sqlite-vec / rerank | search |
| Agent 循环、工具、引用、Chat 页、SSE | agent-chat |
| overlay、LLM profile、Settings 页 | settings |
| WebDAV 快照、导入、冲突、publish | webdav |
| 任务表 CAS、runner、启停、tend、periodic/prune 通用机制 | worker-tasks |
| 某功能自己的 `tasks/handlers/*.py` | 该功能子任务，不是 worker |
| MCP / CLI / eval / 导出 / knowledge pack | access-surfaces |
| Library/Search/Overview 页、OpenAPI↔TS 契约、ESLint 基线 | frontend-pages |
| `main.py` 中间件、storage 后端、DB session/bootstrap/bootstrap、全库测试密度收口 | cross-cutting |

同一缺陷只记一次。横切执行时必须先读 1–10 的 `report.md`。

## Report contract

子任务 `report.md` 固定六段：覆盖与方法、回归、按严重级的 finding、已检查未发现、测试盲区、建议修复子任务。

严重级：Critical / High / Medium / Low。定义见 `research/review-protocol.md`。

父任务总报告：合并去重、校准严重级、按修复任务（不是按原功能面）给出拆分建议，使后续每个修复任务仍可独立验收。

## Compatibility and rollback

- 无 schema、无 API、无前端行为变化。
- 若误改产品文件：`git checkout -- <file>`。
- 不与 `08-27-architecture-audit-open-source-options` 抢结论；那边是选型，这边是缺陷。

## Follow-up shape (after this round)

修复任务在本轮全部报告完成、父任务集成之后再创建。每个修复任务：一个可验证的缺陷簇、有失败场景、有测试验收。不要把「重构 runtime.py」和「修一个 OCR 配置生效」捆在同一个修复任务里。
