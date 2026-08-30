"""Shared Pydantic response-model bases."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_serializer


class StrictModel(BaseModel):
    """Stable snapshots: every public key is declared; extras are bugs."""

    model_config = ConfigDict(extra="forbid")


class OmitUnsetModel(BaseModel):
    """Polymorphic 200s: omit keys that were not in the source dict.

    Preserves current wire behavior where absent optional keys are omitted
    rather than serialized as JSON null.
    """

    model_config = ConfigDict(extra="forbid")

    @model_serializer(mode="wrap")
    def _omit_unset(self, serializer):  # noqa: ANN001
        data = serializer(self)
        if not isinstance(data, dict):
            return data
        return {key: value for key, value in data.items() if key in self.model_fields_set}
