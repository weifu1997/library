# 技术设计 — 修复目录环

## 决策 1：`_would_cycle` 放在哪里

现状：`services/folders.py:223`，私有，仅 `move_folder` 使用。
`services/webdav_sync.py` 目前**不 import** `services.folders`，也不 import `repositories.folders`。

| 方案 | 评价 |
|---|---|
| A. webdav_sync 直接 import `services.folders._would_cycle` | 跨 service 引用私有函数，破坏分层 |
| B. 提升到 `repositories/folders.py` 作为公开函数 ✅ | 纯数据结构遍历 + `db.get`，本就是仓储层职责；`repositories/folders.py:227` 已有同类的 `list_live_descendant_ids` 环保护先例 |
| C. 各自复制一份 | 违反 PRD"只有一份实现" |

**选 B**：移到 `repositories/folders.py`，命名 `would_create_cycle(db, *, child_id, new_parent_id) -> bool`，
签名与语义不变。`services/folders.py:_would_cycle` 改为薄转发或直接替换调用点。

## 决策 2：`_folder_path` 成环时返回什么

不能抛异常——它在 publish 主路径上（`:1068`），抛错会让一次同步整体失败，
而目录环是**数据问题**而非本次同步的问题。

选择：`seen` 集合，检测到重复即停止向上遍历，用已收集到的 `parts` 拼出一个**部分路径**返回，
并 `log.warning` 带上 folder_id。这样 publish 继续进行，路径退化但不丢文件，且留下可排查的痕迹。

```python
seen: set[str] = set()
cur = folder_id
while cur:
    if cur in seen:
        log.warning("folder parent cycle detected at %s; truncating path for %s", cur, folder_id)
        break
    seen.add(cur)
    ...
```

> **实施时修正**：本节初稿写的是用 `while cur and cur not in seen:` + `while/else` 来区分
> "正常走到根"和"撞环"。**这是错的**——`else` 在循环条件为假时都会执行，而 `cur` 变成
> `None`（正常到根）同样使条件为假，两种情况分不开。已改为循环内显式 `if cur in seen: break`。

## 决策 3：导入路径成环时的行为

`_import_metadata` 的既有约定是"有冲突就 re-home 并计数"，不是"报错中断"
（见 `:1623-1626` 对缺失/软删父目录的处理）。保持一致：

```python
parent_id = await _nearest_live_folder_id(session, parent_id)
if parent_id is not None and await folders_repo.would_create_cycle(
    session, child_id=folder_id, new_parent_id=parent_id,
):
    log.warning("webdav import: folder %s -> %s would cycle; re-homing to root",
                folder_id, parent_id)
    parent_id = None
    imported["conflicts"] += 1
```

放在 `_nearest_live_folder_id` **之后**：该函数可能把 parent 上移到某个 live 祖先，
必须对**最终写入的值**做校验。

### 顺序依赖

导入是逐行 `flush()` 的，所以 `would_create_cycle` 每次看到的是**当前已 flush 的状态**——
这正是需要的语义：它能看见同一批次里先前写入的行。

## 影响面

- `repositories/folders.py`：+1 公开函数
- `services/folders.py`：删除私有实现，改调仓储层
- `services/webdav_sync.py`：+1 import，+1 校验块，`_folder_path` 加 seen
- 无 schema 变更、无 API 变更、无迁移

## 回滚

纯代码改动，`git revert` 即可。无数据迁移，已成环的历史数据在 revert 后仍会挂死——
这也是为什么止血（决策 2）必须独立于治本（决策 3）落地。
