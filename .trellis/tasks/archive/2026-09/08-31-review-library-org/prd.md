# 审查：知识库组织

父任务：`08-31-feature-code-review`

## Goal

审查文件夹、条目、标签、关系、journal、catalog/view 组织能力的五个角度。只出报告。

## Scope

- `src/library/services/folders.py` `entries.py` `recommend.py` `relation_vetting.py`
- `src/library/api/routes_folders.py` `routes_file_entries.py` `routes_files.py`
- `src/library/repositories/folders.py` `entries.py` `files.py` `tags.py` `entry_tags.py` `entry_relations.py` `journal.py` `catalogs.py` `views.py`
- handlers：`enrich_tags` `normalize_tags` `tag_quality` `mine_relations` `mine_citation_graph` `mine_session_cooccurrence` `mine_tag_overlap` `vet_relations` `propose_views` `restructure_catalogs` `restructure_catalogs_apply` `refresh_entry_extra` `suggest_lifecycle`
- 测试：`test_folders*` `test_file_entry*` `test_enrich_tags*` `test_normalize_tags*` `test_mine_*` `test_vet_relations*` `test_propose_views*` `test_restructure*` `test_journal*` `test_lazy_relation*` `test_related_prefill*` `test_refresh_entry*` `test_lifecycle*`

## Extra angles

- `parent_id` 写路径是否都走环检查（WebDAV 导入归 webdav 子任务，本任务查 GUI/API move 与 catalog 树）
- 软删除 / purge 与 journal 失效

## Out of Scope

- WebDAV 导入写 parent（归 webdav）；存储物理删除（归 worker purge 与 cross-cutting storage）

## Acceptance Criteria

- [ ] 五个角度均有结论
- [ ] 文件夹树与关系挖掘的写路径均被点名检查
- [ ] finding 含 `file:line` + 失败场景
- [ ] 无产品代码改动
