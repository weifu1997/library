# Design — WEBDAV-H1/H2

H1：`_merge_snapshot_rows` scoped 分支把 relation 的 scope 从 `selected_entry_ids` 改为：本地关系先按 selected 过滤，merge 全部 remote relations，再按 merged `entry_ids` 过滤。与 views/journals「远端全留」一致。

H2：`publish_selected` 调 `_read_remote_snapshot(..., recover=False, allow_missing=True)`。`publish_snapshot` 可保留 recover（注释写的是 full snapshot）。JSONL 解析失败不要变成 empty snapshot 再 MOVE latest。
