"""mine_tag_overlap — structural entry-relation mining via tag Jaccard.

Purpose:
  Two entries that share many tags are likely related, even if no journal
  has explicitly co-cited them yet. This miner gives the discovery layer
  a useful signal even on a fresh library where mine_session_cooccurrence
  has no data — and complements cooccurrence on a mature library by
  surfacing structural neighbours the agent hasn't gotten around to
  thinking about together yet.

Algorithm:
  1. Pull every (entry_id, tag_id) pair where the entry is live.
  2. Group by entry → set of tag_ids; then by tag → set of entries
     wearing it.
  3. For every tag with >= 2 entries (and <= MAX_TAG_FANOUT to skip
     "default" / "untagged" / popular catch-all tags), emit candidate
     pairs from that tag's entry set.
  4. Score each candidate pair by Jaccard: |A ∩ B| / |A ∪ B| over their
     tag sets. Higher Jaccard = more structurally aligned.
  5. Filter pairs with Jaccard >= MIN_JACCARD and >= MIN_SHARED_TAGS to
     drop noise.
  6. Cap at MAX_NEW_RELATIONS_PER_RUN and emit, ordered by Jaccard desc.
  7. Upsert into entry_relations with source_kind='mine_tag_overlap':
     existing pair (any source_kind) → bump observation_count by
     ceil(jaccard * 10); else INSERT.

Writes:
  - entry_relations (INSERT new + UPDATE existing observation_count)
  - audit_events: 'relation_mined' per row
  - task_outcomes: per-pair detail + global summary

Does NOT write to: tags / entry_tags / file_entries / catalogs / journal /
files / views.
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

from library.db.session import session_scope
from library.config import get_settings
from library.repositories import entries as entries_repo
from library.repositories import entry_tags as entry_tags_repo
from library.repositories.task_outcomes import (
    GLOBAL_OBJECT_ID,
    GLOBAL_OBJECT_KIND,
    record_outcome,
)
from library.tasks.handlers._mining_helpers import upsert_relation_pair
log = logging.getLogger(__name__)

MIN_JACCARD = 0.30
MIN_SHARED_TAGS = 2
# Tags worn by more than this many entries are too generic to be a
# useful similarity signal — skip them when seeding candidate pairs.
# (Pairs whose Jaccard is high overall will still surface from other
# shared tags they have.)
MAX_TAG_FANOUT = 40
MAX_NEW_RELATIONS_PER_RUN = 50
SOURCE_KIND = "mine_tag_overlap"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def handle_mine_tag_overlap(payload: Mapping[str, Any]) -> None:
    now = _utcnow()
    settings = get_settings()
    min_jaccard = float(payload.get("min_jaccard") or MIN_JACCARD)
    min_shared = int(payload.get("min_shared_tags") or MIN_SHARED_TAGS)
    max_fanout = int(payload.get("max_tag_fanout") or MAX_TAG_FANOUT)
    cap = int(payload.get("cap") or MAX_NEW_RELATIONS_PER_RUN)
    entry_page_size = max(
        1,
        int(payload.get("entry_page_size") or settings.relation_mining_entry_page_size),
    )
    eligible_tag_limit = max(
        1,
        int(
            payload.get("eligible_tag_limit")
            or settings.relation_mining_eligible_tag_limit
        ),
    )
    candidate_limit = max(
        1,
        int(payload.get("candidate_limit") or settings.relation_mining_candidate_limit),
    )

    new_relations = 0
    incremented = 0
    candidates_considered = 0
    pairs_above_threshold = 0
    skipped_dead_entry = 0
    entries_scanned = 0
    eligible_tags_truncated = False
    candidate_pairs_truncated = False
    next_entry_id: str | None = None
    cycle_complete = True

    async with session_scope() as session:
        # 1. Continue from the cursor stored in the previous outcome. Only a
        # bounded keyset page seeds candidates in this run.
        previous = await entry_tags_repo_outcome_detail(session)
        after_entry_id = str(previous.get("next_entry_id") or "").strip() or None
        page_rows = await entry_tags_repo.list_live_entry_ids_page(
            session,
            after_entry_id=after_entry_id,
            limit=entry_page_size + 1,
        )
        page_entry_ids = page_rows[:entry_page_size]
        entries_scanned = len(page_entry_ids)
        has_more = len(page_rows) > entry_page_size
        cycle_complete = not has_more
        next_entry_id = page_entry_ids[-1] if has_more and page_entry_ids else None

        seed_tag_ids = await entry_tags_repo.list_distinct_tag_ids_for_entries(
            session, page_entry_ids,
        )
        eligible_tag_ids = await entry_tags_repo.list_eligible_live_tag_ids(
            session,
            tag_ids=seed_tag_ids,
            max_fanout=max_fanout,
            limit=eligible_tag_limit + 1,
        )
        eligible_tags_truncated = len(eligible_tag_ids) > eligible_tag_limit
        eligible_tag_ids = eligible_tag_ids[:eligible_tag_limit]

        overlap_rows = await entry_tags_repo.list_live_pairs_for_tags(
            session, eligible_tag_ids,
        )
        involved_entry_ids = sorted({entry_id for entry_id, _ in overlap_rows})
        rows = await entry_tags_repo.list_tag_ids_for_entries(
            session, involved_entry_ids,
        )

        entry_tags: dict[str, set[str]] = defaultdict(set)
        tag_entries: dict[str, set[str]] = defaultdict(set)
        for entry_id, tag_id in rows:
            entry_tags[entry_id].add(tag_id)
            tag_entries[tag_id].add(entry_id)

        # 2. Build candidate pairs from each tag's entry set, skipping
        #    over-popular tags. Use a set so a pair seeded from multiple
        #    tags is only scored once.
        candidate_pairs: set[tuple[str, str]] = set()
        page_entry_id_set = set(page_entry_ids)
        for _tag_id in sorted(eligible_tag_ids):
            entries = tag_entries[_tag_id]
            if len(entries) < 2 or len(entries) > max_fanout:
                continue
            sorted_entries = sorted(entries)
            for i in range(len(sorted_entries)):
                for j in range(i + 1, len(sorted_entries)):
                    if (
                        sorted_entries[i] not in page_entry_id_set
                        and sorted_entries[j] not in page_entry_id_set
                    ):
                        continue
                    candidate_pairs.add(
                        (sorted_entries[i], sorted_entries[j])
                    )
                    if len(candidate_pairs) >= candidate_limit:
                        candidate_pairs_truncated = True
                        break
                if candidate_pairs_truncated:
                    break
            if candidate_pairs_truncated:
                break
        candidates_considered = len(candidate_pairs)

        # 3. Score each pair by Jaccard.
        scored: list[tuple[str, str, float, int]] = []
        for a, b in candidate_pairs:
            ta, tb = entry_tags[a], entry_tags[b]
            shared = ta & tb
            if len(shared) < min_shared:
                continue
            union = ta | tb
            if not union:
                continue
            jaccard = len(shared) / len(union)
            if jaccard < min_jaccard:
                continue
            scored.append((a, b, jaccard, len(shared)))

        scored.sort(key=lambda r: r[2], reverse=True)
        pairs_above_threshold = len(scored)

        # 4. Validate live entries (rare: should already be live since
        #    we filtered EntryTag join; defence-in-depth against races).
        all_ids: set[str] = set()
        for a, b, _, _ in scored:
            all_ids.add(a)
            all_ids.add(b)
        live_ids = (
            set(await entries_repo.filter_live_ids(session, list(all_ids)))
            if all_ids else set()
        )

        for a, b, jaccard, shared_count in scored:
            if new_relations >= cap:
                break
            if a not in live_ids or b not in live_ids:
                skipped_dead_entry += 1
                continue
            # observation_count is integer; map jaccard to a small
            # weight. ceil(jaccard * 10) lands in 1-10 range, comparable
            # to cooccurrence counts so the random-walk graph isn't
            # lopsided by signal source.
            obs_add = max(1, math.ceil(jaccard * 10))
            note = (
                f"Tag overlap: {shared_count} shared tags, "
                f"Jaccard {jaccard:.2f}."
            )
            _, action = await upsert_relation_pair(
                session,
                entry_a_id=a, entry_b_id=b,
                observation_add=obs_add,
                source_kind=SOURCE_KIND,
                note=note,
                now=now,
                audit_extra={
                    "jaccard": round(jaccard, 3),
                    "shared_tags": shared_count,
                },
            )
            if action == "incremented":
                incremented += 1
            else:
                new_relations += 1

        await record_outcome(
            session,
            task_kind="mine_tag_overlap",
            object_kind=GLOBAL_OBJECT_KIND,
            object_id=GLOBAL_OBJECT_ID,
            outcome="applied" if (new_relations or incremented) else "noop",
            detail={
                "min_jaccard": min_jaccard,
                "min_shared_tags": min_shared,
                "max_tag_fanout": max_fanout,
                "cap": cap,
                "entry_page_size": entry_page_size,
                "eligible_tag_limit": eligible_tag_limit,
                "candidate_limit": candidate_limit,
                "entries_scanned": entries_scanned,
                "next_entry_id": next_entry_id,
                "cycle_complete": cycle_complete,
                "eligible_tags": len(eligible_tag_ids),
                "eligible_tags_truncated": eligible_tags_truncated,
                "candidates_considered": candidates_considered,
                "candidate_pairs_truncated": candidate_pairs_truncated,
                "pairs_above_threshold": pairs_above_threshold,
                "new_relations": new_relations,
                "incremented_relations": incremented,
                "skipped_dead_entry": skipped_dead_entry,
            },
        )
        await session.commit()

    log.info(
        "mine_tag_overlap: candidates=%d above_threshold=%d "
        "new=%d incremented=%d",
        candidates_considered, pairs_above_threshold,
        new_relations, incremented,
    )


async def entry_tags_repo_outcome_detail(session) -> dict[str, Any]:
    """Read the durable keyset cursor from the previous completed run."""
    from library.repositories import task_outcomes as outcomes_repo

    return await outcomes_repo.latest_detail_for(
        session,
        task_kind=SOURCE_KIND,
        object_kind=GLOBAL_OBJECT_KIND,
        object_id=GLOBAL_OBJECT_ID,
    )
