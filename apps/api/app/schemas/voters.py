"""Validation contract for curated voter records.

These rules are the reason the curated table is worth having: OCR output is
accepted with its flaws so nothing is lost, but anything promoted here has
been checked. Validation therefore rejects rather than warns.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Permissive on shape, strict on structure: real EPIC numbers are three
# letters and seven digits, but older and re-issued cards vary, so the stored
# form allows 2-4 letters and 6-9 digits. Anything else is a misread.
EPIC_RE = re.compile(r"^[A-Z]{2,4}\d{6,9}$")
CANONICAL_EPIC_RE = re.compile(r"^[A-Z]{3}\d{7}$")

MIN_AGE = 18
MAX_AGE = 120

Gender = Literal["Male", "Female", "Other"]
RelationType = Literal["Husband", "Father", "Mother", "Other"]

SORTABLE = {
    "epic", "serial", "name", "age", "gender", "house_number",
    "part_number", "created_at", "updated_at",
}


def normalise_epic(value: str) -> str:
    """Uppercase alphanumerics only -- OCR leaves stray spaces and dashes."""
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


class VoterBase(BaseModel):
    epic: str = Field(default="", description="Elector Photo Identity Card number; unique")
    name: str = Field(default="", max_length=255)
    serial: int | None = Field(default=None, ge=1, le=100_000)
    relation_type: RelationType | Literal[""] = ""
    relation_name: str = Field(default="", max_length=255)
    house_number: str = Field(default="", max_length=64)
    age: int | None = Field(default=None)
    gender: Gender | Literal[""] = ""
    part_number: str = Field(default="", max_length=32)
    constituency: str = Field(default="", max_length=255)
    notes: str = Field(default="", max_length=2000)
    verified: bool = False

    @field_validator("epic")
    @classmethod
    def _check_epic(cls, v: str) -> str:
        cleaned = normalise_epic(v)
        if not cleaned or not EPIC_RE.match(cleaned):
            raise ValueError(f"Malformed EPIC number: {v}")
        return cleaned

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        cleaned = (v or "").strip()
        if not cleaned:
            raise ValueError("Name cannot be empty")
        return cleaned

    @field_validator("age")
    @classmethod
    def _check_age(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not MIN_AGE <= v <= MAX_AGE:
            raise ValueError(f"Age {v} is outside the plausible range {MIN_AGE}-{MAX_AGE}")
        return v

    @field_validator("relation_name", "house_number", "part_number",
                     "constituency", "notes")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()

    @model_validator(mode="after")
    def _relation_pair(self):
        if self.relation_name and not self.relation_type:
            raise ValueError("relation_name requires relation_type")
        return self


class VoterCreate(VoterBase):
    pass


class VoterUpdate(BaseModel):
    """Every field optional -- this is a PATCH."""

    epic: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=255)
    serial: int | None = Field(default=None, ge=1, le=100_000)
    relation_type: RelationType | Literal[""] | None = None
    relation_name: str | None = Field(default=None, max_length=255)
    house_number: str | None = Field(default=None, max_length=64)
    age: int | None = None
    gender: Gender | Literal[""] | None = None
    part_number: str | None = Field(default=None, max_length=32)
    constituency: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)
    verified: bool | None = None

    @field_validator("epic")
    @classmethod
    def _check_epic(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return VoterBase._check_epic(v)

    @field_validator("age")
    @classmethod
    def _check_age(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if not MIN_AGE <= v <= MAX_AGE:
            raise ValueError(
                f"Age {v} is outside the plausible range {MIN_AGE}-{MAX_AGE}"
            )
        return v


class Voter(VoterBase):
    id: str
    polling_station_id: str | None = None
    is_supplement: bool = False
    """Added by a supplement rather than carried from the base roll.

    Exposed because the distinction is not cosmetic: a supplement elector
    joined the roll after the base list was published, and a report that
    cannot separate the two misstates the revision.
    """
    is_deleted: bool = False
    """Struck off the roll by the Special Intensive Revision.

    Surfaced so a deleted elector is never silently counted as active; the
    reason code sits alongside it.
    """
    deletion_reason: str = ""
    source_record_id: str | None = None
    source_page_id: str | None = None
    source_file_id: str | None = None
    source_file_name: str = ""
    page_number: int | None = None
    page_id: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str = ""
    updated_by: str = ""

    model_config = {"from_attributes": True}


class VoterPage(BaseModel):
    items: list[Voter]
    total: int
    offset: int
    limit: int


class PromotionConflict(BaseModel):
    """A record that could not be promoted, and why."""

    record_id: str
    epic: str = ""
    reason: str
    existing_voter_id: str | None = None
    existing_name: str = ""
    incoming_name: str = ""


class PromotionResult(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    conflicts: list[PromotionConflict] = Field(default_factory=list)
    voter_ids: list[str] = Field(default_factory=list)


class PromotionRequest(BaseModel):
    record_ids: list[str] = Field(default_factory=list)
    file_id: str | None = None
    page_id: str | None = None
    only_clean: bool = True
    """Promote only records with zero validation errors."""
    on_conflict: Literal["skip", "update"] = "skip"
    """`skip` reports the collision and leaves the existing row untouched;
    `update` overwrites it with the incoming values."""
