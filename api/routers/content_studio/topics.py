"""Topics router for the Content Studio."""

from __future__ import annotations

from datetime import date as _date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.routers.content_studio._deps import (
    NewsIngestDep,
    StorageDep,
    TopicSelectorDep,
)
from api.schemas.content_studio import (
    DailyNoteIngestRequest,
    DailyNoteIngestResponse,
    Topic,
    TopicIngestRequest,
    TopicIngestResponse,
    TopicListResponse,
    TopicResponse,
    TopicSelectRequest,
    TopicStatus,
)
from pixelle_video.services.content_studio.obsidian_news_loader import (
    DailyNoteNotFound,
    daily_note_path,
)
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
)


router = APIRouter(prefix="/topics", tags=["Content Studio - Topics"])


@router.post("/ingest", response_model=TopicIngestResponse)
async def ingest_topics(request: TopicIngestRequest, ingest: NewsIngestDep):
    """Bulk-ingest candidate topics from an upstream news source."""
    try:
        topics = ingest.ingest(request.candidates, replace_for_date=request.replace_for_date)
        return TopicIngestResponse(ingested=len(topics), topics=topics)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Topic ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ingest/daily", response_model=DailyNoteIngestResponse)
async def ingest_from_daily_note(
    ingest: NewsIngestDep,
    request: Optional[DailyNoteIngestRequest] = None,
):
    """Ingest today's (or the given date's) Obsidian AI-news briefing.

    Reads ``meetings/YYYY-MM-DD-daily-project-ai-sync.md`` from the
    user's vault, extracts the morning/evening AI-news items, and
    persists them as ``candidate`` topics. Re-running on the same
    date replaces the previous run by default.
    """
    req = request or DailyNoteIngestRequest()
    target = req.date or _date.today().isoformat()
    path = daily_note_path(target, vault_root=req.vault_root)
    try:
        topics = ingest.ingest_from_daily_note(
            target_date=target,
            vault_root=req.vault_root,
            replace_for_date=req.replace_for_date,
        )
    except DailyNoteNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"Daily-note ingest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    return DailyNoteIngestResponse(
        date=target,
        note_path=str(path),
        ingested=len(topics),
        topics=topics,
    )


@router.get("/today", response_model=TopicListResponse)
async def list_today(
    storage: StorageDep,
    date: Optional[str] = Query(None, description="ISO date (YYYY-MM-DD); defaults to today"),
    include_skipped: bool = Query(False),
):
    """List candidate topics for a given date (default: today)."""
    target = date or _date.today().isoformat()
    statuses: Optional[List[TopicStatus]]
    if include_skipped:
        statuses = None
    else:
        statuses = [
            TopicStatus.CANDIDATE,
            TopicStatus.SELECTED,
            TopicStatus.DRAFTED,
            TopicStatus.DRAFT_APPROVED,
            TopicStatus.SCRIPT_READY,
            TopicStatus.STORYBOARD_READY,
            TopicStatus.RENDER_QUEUED,
            TopicStatus.RENDER_RUNNING,
            TopicStatus.RENDER_COMPLETED,
            TopicStatus.RENDER_FAILED,
        ]
    topics = storage.list_topics(date=target, statuses=statuses)
    return TopicListResponse(date=target, topics=topics)


@router.get("/{topic_id}", response_model=TopicResponse)
async def get_topic(topic_id: str, storage: StorageDep):
    topic = storage.get_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic {topic_id} not found")
    return TopicResponse(topic=topic)


@router.post("/{topic_id}/select", response_model=TopicResponse)
async def select_topic(
    topic_id: str,
    selector: TopicSelectorDep,
    body: Optional[TopicSelectRequest] = None,
):
    try:
        notes = body.notes if body else None
        topic = selector.select(topic_id, notes=notes)
        return TopicResponse(topic=topic)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{topic_id}/skip", response_model=TopicResponse)
async def skip_topic(
    topic_id: str,
    selector: TopicSelectorDep,
    body: Optional[TopicSelectRequest] = None,
):
    try:
        notes = body.notes if body else None
        topic = selector.skip(topic_id, notes=notes)
        return TopicResponse(topic=topic)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{topic_id}/priority", response_model=TopicResponse)
async def set_priority(
    topic_id: str,
    priority: int,
    selector: TopicSelectorDep,
):
    try:
        topic = selector.mark_priority(topic_id, priority)
        return TopicResponse(topic=topic)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
