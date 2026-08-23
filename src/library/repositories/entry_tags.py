"""entry_tags repository — pure SA queries against the EntryTag table.

Caller owns the transaction.
"""
from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from library.db.models import EntryTag, Tag


async def list_tag_ids_for_entry(
    db: AsyncSession, entry_id: str,
) -> list[str]:
    """All tag_ids attached to `entry_id`. Used by upload's dedup path to
    copy tags from a seed entry onto the new entry."""
    rows = (
        await db.execute(
            select(EntryTag.tag_id).where(EntryTag.entry_id == entry_id)
        )
    ).scalars().all()
    return list(rows)


async def list_tags_with_source_for_entry(
    db: AsyncSession, entry_id: str,
) -> list[tuple[str, str, str | None, str | None]]:
    """Return `(tag_id, name, facet, source)` for every tag attached to
    `entry_id`. Used by read_entries_metadata to surface per-tag provenance."""
    rows = (
        await db.execute(
            select(Tag.id, Tag.name, Tag.facet, EntryTag.source)
            .join(EntryTag, Tag.id == EntryTag.tag_id)
            .where(EntryTag.entry_id == entry_id)
        )
    ).all()
    return [(tid, n, f, src) for tid, n, f, src in rows]


async def list_name_facet_for_entry(
    db: AsyncSession, entry_id: str,
) -> list[tuple[str, str | None]]:
    """Return `(name, facet)` for every tag attached to `entry_id`.
    Used by reflect_turn when packing entry context for the LLM — it
    doesn't need ids or source."""
    rows = (
        await db.execute(
            select(Tag.name, Tag.facet)
            .join(EntryTag, Tag.id == EntryTag.tag_id)
            .where(EntryTag.entry_id == entry_id)
        )
    ).all()
    return [(n, f) for n, f in rows]


async def list_id_name_facet_for_entries(
    db: AsyncSession, entry_ids: list[str],
) -> list[tuple[str, str, str, str | None]]:
    """`(entry_id, tag_id, name, facet)` for every entry_tag row whose entry
    is in `entry_ids` and whose tag is canonical (alias_of IS NULL). Used by
    enrich_tags + refresh_entry_extra to pack tag context for the LLM."""
    if not entry_ids:
        return []
    rows = (
        await db.execute(
            select(EntryTag.entry_id, Tag.id, Tag.name, Tag.facet)
            .join(Tag, Tag.id == EntryTag.tag_id)
            .where(
                EntryTag.entry_id.in_(entry_ids),
                Tag.alias_of.is_(None),
            )
        )
    ).all()
    return [(e, tid, n, f) for e, tid, n, f in rows]


async def list_existing_for_entry(
    db: AsyncSession, entry_id: str,
) -> list[tuple[str, str, str | None]]:
    """`(tag_id, name, facet)` for every tag attached to `entry_id`. Used
    by enrich_tags when summarising what the entry already wears."""
    rows = (
        await db.execute(
            select(Tag.id, Tag.name, Tag.facet)
            .join(EntryTag, Tag.id == EntryTag.tag_id)
            .where(EntryTag.entry_id == entry_id)
        )
    ).all()
    return [(tid, n, f) for tid, n, f in rows]


async def find_one(
    db: AsyncSession, *, entry_id: str, tag_id: str,
) -> EntryTag | None:
    """Existence check for a (entry, tag) pair. Used by ingest_file before
    INSERT to honour the composite PK without a try/except round-trip."""
    return (
        await db.execute(
            select(EntryTag).where(
                EntryTag.entry_id == entry_id,
                EntryTag.tag_id == tag_id,
            )
        )
    ).scalar_one_or_none()


async def list_live_entry_tag_pairs(
    db: AsyncSession,
) -> list[tuple[str, str]]:
    """`(entry_id, tag_id)` for every entry_tags row whose entry is live.
    Used by mine_tag_overlap and propose_views — they need the full
    entry × tag bipartite graph."""
    from library.db.models import FileEntry  # local to keep top imports tight

    rows = (
        await db.execute(
            select(EntryTag.entry_id, EntryTag.tag_id)
            .join(FileEntry, FileEntry.id == EntryTag.entry_id)
            .where(FileEntry.deleted_at.is_(None))
        )
    ).all()
    return [(e, t) for e, t in rows]


async def list_live_entry_ids_page(
    db: AsyncSession,
    *,
    after_entry_id: str | None,
    limit: int,
) -> list[str]:
    """A keyset page of live entry ids used by bounded relation mining."""
    from library.db.models import FileEntry

    stmt = select(FileEntry.id).where(FileEntry.deleted_at.is_(None))
    if after_entry_id is not None:
        stmt = stmt.where(FileEntry.id > after_entry_id)
    rows = (
        await db.execute(
            stmt.order_by(FileEntry.id.asc()).limit(max(1, int(limit)))
        )
    ).scalars().all()
    return [str(row) for row in rows]


async def list_distinct_tag_ids_for_entries(
    db: AsyncSession,
    entry_ids: list[str],
) -> list[str]:
    if not entry_ids:
        return []
    rows = (
        await db.execute(
            select(EntryTag.tag_id)
            .where(EntryTag.entry_id.in_(entry_ids))
            .distinct()
        )
    ).scalars().all()
    return [str(row) for row in rows]


async def list_eligible_live_tag_ids(
    db: AsyncSession,
    *,
    tag_ids: list[str],
    max_fanout: int,
    limit: int,
) -> list[str]:
    """Tags with a bounded live fan-out, returning at most ``limit`` rows."""
    from library.db.models import FileEntry

    if not tag_ids:
        return []
    rows = (
        await db.execute(
            select(EntryTag.tag_id)
            .join(FileEntry, FileEntry.id == EntryTag.entry_id)
            .where(
                EntryTag.tag_id.in_(tag_ids),
                FileEntry.deleted_at.is_(None),
            )
            .group_by(EntryTag.tag_id)
            .having(
                func.count(func.distinct(EntryTag.entry_id)).between(
                    2, max(2, int(max_fanout)),
                )
            )
            .order_by(EntryTag.tag_id.asc())
            .limit(max(1, int(limit)))
        )
    ).scalars().all()
    return [str(row) for row in rows]


async def list_live_pairs_for_tags(
    db: AsyncSession,
    tag_ids: list[str],
) -> list[tuple[str, str]]:
    from library.db.models import FileEntry

    if not tag_ids:
        return []
    rows = (
        await db.execute(
            select(EntryTag.entry_id, EntryTag.tag_id)
            .join(FileEntry, FileEntry.id == EntryTag.entry_id)
            .where(
                EntryTag.tag_id.in_(tag_ids),
                FileEntry.deleted_at.is_(None),
            )
        )
    ).all()
    return [(str(entry_id), str(tag_id)) for entry_id, tag_id in rows]


async def list_live_active_entry_tag_pairs(
    db: AsyncSession,
) -> list[tuple[str, str]]:
    """`(entry_id, tag_id)` restricted to live entries with lifecycle
    in {active, manual_active}. Used by propose_views' tag-cooccurrence
    cluster builder."""
    from library.db.models import FileEntry

    rows = (
        await db.execute(
            select(FileEntry.id, EntryTag.tag_id)
            .join(EntryTag, EntryTag.entry_id == FileEntry.id)
            .where(
                FileEntry.deleted_at.is_(None),
                FileEntry.lifecycle.in_(("active", "manual_active")),
            )
        )
    ).all()
    return [(e, t) for e, t in rows]


async def list_tag_ids_for_entries(
    db: AsyncSession, entry_ids: list[str],
) -> list[tuple[str, str]]:
    """`(entry_id, tag_id)` for every entry_tag row whose entry is in
    `entry_ids` (no live filter)."""
    if not entry_ids:
        return []
    rows = (
        await db.execute(
            select(EntryTag.entry_id, EntryTag.tag_id)
            .where(EntryTag.entry_id.in_(entry_ids))
        )
    ).all()
    return [(e, t) for e, t in rows]


async def delete_all_for_entry(
    db: AsyncSession, entry_id: str,
) -> int:
    """Delete every entry_tags row for the entry. Used by reprocess to
    clear AI-filled tags before re-running ingest. Returns row count.
    Note: does NOT decrement Tag.doc_count — that drift is reconciled
    by tag_quality on its next pass."""
    result = await db.execute(
        delete(EntryTag).where(EntryTag.entry_id == entry_id)
    )
    return int(result.rowcount or 0)
