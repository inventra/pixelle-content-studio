"""Storyboards + render-bridge router for the Content Studio.

Render submission is the only place that crosses into the existing
Pixelle-Video task manager. The bridge is intentionally thin: build a
``VideoGenerateRequest`` from the storyboard, then either record a
"queued" pseudo task (sync mode) or hand off to the existing video
async path. The actual rendering still happens via the unmodified
Pixelle-Video pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from loguru import logger

from api.routers.content_studio._deps import (
    StorageDep,
    StoryboardGeneratorDep,
    VideoBriefBuilderDep,
)
from api.schemas.content_studio import (
    RenderResponse,
    RenderSubmitRequest,
    ScriptGenerateRequest,
    ScriptGenerateResponse,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
    StoryboardResponse,
    TopicStatus,
)
from api.tasks import TaskType, task_manager
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition


router = APIRouter(prefix="/storyboards", tags=["Content Studio - Storyboards"])


@router.post("/script", response_model=ScriptGenerateResponse)
async def generate_script(
    request: ScriptGenerateRequest,
    generator: StoryboardGeneratorDep,
):
    try:
        script = await generator.generate_script(
            topic_id=request.topic_id,
            duration_target=request.duration_target,
            angle=request.angle,
            voice_style=request.voice_style,
            regenerate=request.regenerate,
        )
        return ScriptGenerateResponse(script=script)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/generate", response_model=StoryboardGenerateResponse)
async def generate_storyboard(
    request: StoryboardGenerateRequest,
    generator: StoryboardGeneratorDep,
):
    try:
        storyboard = await generator.generate_storyboard(
            topic_id=request.topic_id,
            visual_style=request.visual_style,
            n_scenes=request.n_scenes,
            regenerate=request.regenerate,
        )
        return StoryboardGenerateResponse(storyboard=storyboard)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{topic_id}", response_model=StoryboardResponse)
async def get_storyboard(topic_id: str, storage: StorageDep):
    return StoryboardResponse(
        script=storage.get_script(topic_id),
        storyboard=storage.get_storyboard(topic_id),
    )


@router.post("/render", response_model=RenderResponse)
async def submit_render(
    request: RenderSubmitRequest,
    storage: StorageDep,
    builder: VideoBriefBuilderDep,
):
    """Approval gate + bridge into Pixelle-Video.

    We require ``confirm_cost=True`` so the operator must actively
    acknowledge the cost band before any render task is created.
    """
    if not request.confirm_cost:
        raise HTTPException(
            status_code=409,
            detail="confirm_cost must be true; render is gated behind explicit cost acknowledgement.",
        )

    topic = storage.get_topic(request.topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail=f"Topic {request.topic_id} not found")

    try:
        video_request = builder.build_request(
            topic_id=request.topic_id,
            frame_template=request.frame_template,
            media_workflow=request.media_workflow,
            tts_workflow=request.tts_workflow,
            bgm_path=request.bgm_path,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except InvalidStateTransition as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Bridge: create a Pixelle-Video task. We deliberately do NOT
    # execute it here — execution belongs to the video router. We just
    # register the task so the operator can pick it up from the
    # existing /api/tasks/{id} endpoint or from the History page.
    task = task_manager.create_task(
        task_type=TaskType.VIDEO_GENERATION,
        request_params=video_request.model_dump(),
    )

    record = builder.build_render_record(
        topic_id=request.topic_id,
        request=video_request,
        pixelle_task_id=task.task_id,
        status="queued",
    )

    # Topic state machine: storyboard_ready -> render_queued.
    try:
        topic.status = TopicStatus.RENDER_QUEUED
        storage.save_topic(topic)
    except Exception as e:  # pragma: no cover
        logger.error(f"Failed to update topic state for render: {e}")

    return RenderResponse(render=record)


@router.get("/render/{topic_id}", response_model=RenderResponse)
async def get_render(topic_id: str, storage: StorageDep):
    render = storage.get_render(topic_id)
    if render is None:
        raise HTTPException(status_code=404, detail=f"Render for {topic_id} not found")
    return RenderResponse(render=render)
