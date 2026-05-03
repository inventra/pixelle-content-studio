"""Topic schemas for Content Studio"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ContentFormat(str, Enum):
    """Recommended content surface for a topic"""
    SUBSTACK = "substack"
    FACEBOOK = "facebook"
    LINE = "line"
    VIDEO = "video"


class TopicStatus(str, Enum):
    """Lifecycle states for a topic in the content studio.

    Mirrors the state machine described in the MVP plan. Every state lives
    inside this enum so storage and routers stay in sync.
    """
    CANDIDATE = "candidate"
    SELECTED = "selected"
    SKIPPED = "skipped"
    DRAFTED = "drafted"
    DRAFT_APPROVED = "draft_approved"
    SCRIPT_READY = "script_ready"
    STORYBOARD_READY = "storyboard_ready"
    RENDER_QUEUED = "render_queued"
    RENDER_RUNNING = "render_running"
    RENDER_COMPLETED = "render_completed"
    RENDER_FAILED = "render_failed"
    ARCHIVED = "archived"


class TopicSource(BaseModel):
    """Where the topic came from"""
    source_type: str = Field(..., description="hermes / obsidian / manual / webhook")
    source_url: Optional[str] = None
    source_ref: Optional[str] = Field(None, description="External id or filename")


class TopicCandidate(BaseModel):
    """Raw candidate fed in via the ingest endpoint"""
    title: str
    summary: str = ""
    why_it_matters: str = ""
    source: TopicSource = Field(default_factory=lambda: TopicSource(source_type="manual"))
    recommended_formats: List[ContentFormat] = Field(default_factory=list)
    priority: int = Field(50, ge=0, le=100, description="0..100, higher = more important")
    date: Optional[str] = Field(None, description="ISO date string YYYY-MM-DD; defaults to today")


class Topic(BaseModel):
    """Persisted topic record"""
    id: str
    date: str
    title: str
    summary: str = ""
    why_it_matters: str = ""
    source: TopicSource
    recommended_formats: List[ContentFormat] = Field(default_factory=list)
    priority: int = 50
    status: TopicStatus = TopicStatus.CANDIDATE
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class TopicIngestRequest(BaseModel):
    """Bulk ingest request"""
    candidates: List[TopicCandidate] = Field(..., min_length=1)
    replace_for_date: bool = Field(
        False,
        description="If true, drop existing candidates for the same date before ingesting.",
    )


class TopicIngestResponse(BaseModel):
    success: bool = True
    ingested: int
    topics: List[Topic]


class TopicListResponse(BaseModel):
    success: bool = True
    date: str
    topics: List[Topic]


class TopicResponse(BaseModel):
    success: bool = True
    topic: Topic


class TopicSelectRequest(BaseModel):
    """Optional override fields when selecting a topic"""
    notes: Optional[str] = None


class DailyNoteIngestRequest(BaseModel):
    """Trigger ingestion from the Obsidian daily briefing note."""
    date: Optional[str] = Field(
        None,
        description="ISO date (YYYY-MM-DD); defaults to today.",
    )
    vault_root: Optional[str] = Field(
        None,
        description="Override the Obsidian vault root path (defaults to the configured one).",
    )
    replace_for_date: bool = Field(
        True,
        description="Replace any existing topics for this date so re-runs stay idempotent.",
    )


class DailyNoteIngestResponse(BaseModel):
    success: bool = True
    date: str
    note_path: str
    ingested: int
    topics: List[Topic]
