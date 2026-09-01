# 修复审查 Medium：SET / CROSS / FE

## Goal

落实 `.trellis/tasks/08-31-feature-code-review/report.md` §3 Medium 中用户点名的三簇：SET-M1/M2、CROSS-M1/M2、FE-M1/M2。每个子任务独立可验收。

## Requirements

- R1. 只修下表；不顺手做 ACCESS-M*、CHAT-M*、ESLint 清零、A-1。
- R2. 每个子任务带回归测试（前端无 runner 时用后端 e2e 或可测的纯函数 + 代码路径）。
- R3. 不改变无缺陷的成功路径（完好 overlay 的 merge PUT、带 Host 的正常请求、ASCII token、目录树单次展开）。

## Task Map

| 顺序 | 子任务 | 来源 | 验收口径 |
|---|---|---|---|
| 1 | `fix-settings-overlay-merge` | SET-M1+M2 | 损坏 overlay 的 merge PUT 拒绝；掩码密钥 422 |
| 2 | `fix-host-token-auth` | CROSS-M1+M2 | 空 Host → 421；非 ASCII token 不 500 |
| 3 | `fix-folder-tree-meta-errors` | FE-M1+M2 | 目录树有 generation 守卫；metadata 失败可见 |

## Out of Scope

- High 未完成项（ORG-H1 软删文件夹 unique 仍 open）
- ACCESS-M1–M3、CHAT-M*、其余 Medium
- Low（SET-L 掩码回显、FE-L i18n/ESLint）

## Acceptance Criteria

- [x] 三个子任务验收项均勾选
- [x] 相关 pytest / frontend lint 绿
