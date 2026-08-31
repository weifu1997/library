# Design — catalog cycle

把 `restructure_catalogs_apply._would_cycle` 挪到 `repositories/catalogs.py`，签名对齐 `folders.would_create_cycle(session, child_id=, new_parent_id=)`。seen 集、缺失节点不当成环。

WebDAV：对齐文件夹导入（check 之后 re-home + conflicts++），不要静默写环。

merge_into：对每个 child 在赋值前 check；任一 child 会环则整个 soft_delete op reject（避免半更新）。
