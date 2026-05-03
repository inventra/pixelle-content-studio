"""Drafts router for the Content Studio."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.routers.content_studio._deps import DraftGeneratorDep, StorageDep
from api.schemas.content_studio import (
    DraftApproveRequest,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftResponse,
    DraftUpdateRequest,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition


router = APIRouter(prefix="/drafts", tags=["Content Studio - Drafts"])


@router.post("/generate", response_model=DraftGenerateResponse)
async def generate_drafts(request: DraftGenerateRequest, drafts: DraftGeneratorDep):
    try:
        draft_set = await drafts.generate(
            topic_id=request.topic_id,
            tone=request.tone,
            regenerate=request.regenerate,
        )
        return DraftGenerateResponse(draft_set=draft_set)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:  # pragma: no cover
        logger.error(f"Draft generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{topic_id}", response_model=DraftResponse)
async def get_drafts(topic_id: str, storage: StorageDep):
    drafts = storage.get_drafts(topic_id)
    if drafts is None:
        raise HTTPException(status_code=404, detail=f"Drafts for {topic_id} not found")
    return DraftResponse(draft_set=drafts)


@router.put("/{topic_id}", response_model=DraftResponse)
async def update_drafts(
    topic_id: str,
    request: DraftUpdateRequest,
    drafts: DraftGeneratorDep,
):
    try:
        updated = drafts.update(
            topic_id,
            substack_draft=request.substack_draft,
            facebook_draft=request.facebook_draft,
            line_draft=request.line_draft,
            editor_notes=request.editor_notes,
        )
        return DraftResponse(draft_set=updated)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{topic_id}/approve", response_model=DraftResponse)
async def approve_drafts(
    topic_id: str,
    request: DraftApproveRequest,
    drafts: DraftGeneratorDep,
):
    try:
        updated = drafts.approve(topic_id, approved=request.approved)
        return DraftResponse(draft_set=updated)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))
