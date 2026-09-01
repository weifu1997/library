# Design — SEARCH-1

推荐：写入 `*.tmp` 齐套后，用**一代目录** `gen-<id>/` 放三文件，再 `os.replace` 把 `current` 指针（或目录）一次切过去。Windows 上目录 replace 可能不行，则：三文件写完后先写 `manifest.json` 含 `generation` + `n_entries` + `vector_bytes`，加载时三者不一致则视为缺失。

最小可用：保持三文件，但

1. 先写新向量和 metadata 到 tmp，replace 顺序改为 **manifest 最后**（已是），并在 load 校验 counts；
2. 校验失败 → 当作无索引（refresh 会 rebuild），**禁止** `min()` 混用。

读者：search 可不拿写锁，若只读一代完整快照。校验失败即空结果 + 可 log。

不要在本任务做 sqlite-vec 双写重构。
