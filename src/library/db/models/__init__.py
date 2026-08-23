"""SQLAlchemy ORM models for Library.

14 business tables organized by the four-layer architecture (DESIGN.md §7):

User-visible (3):
  - folders, file_entries, files

Audit (3):
  - audit_events, sessions, conversations

AI-internal (7):
  - catalogs, views, tags, tag_aliases, entry_tags
  - entry_relations, journal

Infrastructure (1):
  - tasks

Importing this package registers every table on Base.metadata so Alembic
autogenerate / Base.metadata.create_all picks them all up.
"""

from library.db.models.base import Base
from library.db.models.user_visible import File, FileEntry, Folder
from library.db.models.audit import AgentEvent, AuditEvent, Conversation, Session
from library.db.models.ai_structural import (
    Catalog,
    EntryTag,
    Tag,
    TagAlias,
    View,
)
from library.db.models.ai_recall import EntryRelation, Journal
from library.db.models.task_outcomes import TaskOutcome
from library.db.models.tasks import Task

__all__ = [
    "AuditEvent",
    "AgentEvent",
    "Base",
    "Catalog",
    "Conversation",
    "EntryRelation",
    "EntryTag",
    "File",
    "FileEntry",
    "Folder",
    "Journal",
    "Session",
    "Tag",
    "TagAlias",
    "Task",
    "TaskOutcome",
    "View",
]
