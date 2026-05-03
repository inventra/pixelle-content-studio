"""Draft schemas for Content Studio"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DraftSet(BaseModel):
    """Bundle of platform-specific drafts for a single topic"""
    topic_id: str
    substack_draft: str = ""
    facebook_draft: str = ""
    line_draft: str = ""
    editor_notes: str = ""
    approved_for_video: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class DraftGenerateRequest(BaseModel):
    topic_id: str
    tone: str = Field("informative", description="Tone hint: informative / casual / hype")
    regenerate: bool = Field(
        False,
        description="If a draft already exists, replace it instead of returning the cached one.",
    )


class DraftGenerateResponse(BaseModel):
    success: bool = True
    draft_set: DraftSet


class DraftUpdateRequest(BaseModel):
    substack_draft: Optional[str] = None
    facebook_draft: Optional[str] = None
    line_draft: Optional[str] = None
    editor_notes: Optional[str] = None


class DraftApproveRequest(BaseModel):
    approved: bool = True
    notes: Optional[str] = None


class DraftResponse(BaseModel):
    success: bool = True
    draft_set: DraftSet
