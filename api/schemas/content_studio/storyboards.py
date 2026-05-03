"""Storyboard, script, and render schemas for Content Studio"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Script(BaseModel):
    """Short-video script generated from approved drafts"""
    topic_id: str
    angle: str = Field("", description="Hook angle / framing for the video")
    duration_target: int = Field(45, ge=15, le=120, description="Target seconds")
    hook: str = ""
    body: str = ""
    cta: str = ""
    voice_style: str = "calm-narrator"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class StoryboardScene(BaseModel):
    scene_no: int = Field(..., ge=1)
    voiceover: str
    visual_prompt: str
    onscreen_text: str = ""
    duration_seconds: float = Field(5.0, gt=0)


class Storyboard(BaseModel):
    topic_id: str
    visual_style: str = "clean-editorial"
    scenes: List[StoryboardScene] = Field(default_factory=list)
    estimated_cost_band: str = Field(
        "low",
        description="rough cost band: low / medium / high",
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ScriptGenerateRequest(BaseModel):
    topic_id: str
    duration_target: int = Field(45, ge=15, le=120)
    angle: Optional[str] = None
    voice_style: Optional[str] = None
    regenerate: bool = False


class ScriptGenerateResponse(BaseModel):
    success: bool = True
    script: Script


class StoryboardGenerateRequest(BaseModel):
    topic_id: str
    visual_style: Optional[str] = None
    n_scenes: Optional[int] = Field(
        None,
        ge=1,
        le=12,
        description="Override number of scenes; otherwise inferred from script length",
    )
    regenerate: bool = False


class StoryboardGenerateResponse(BaseModel):
    success: bool = True
    storyboard: Storyboard


class StoryboardResponse(BaseModel):
    success: bool = True
    script: Optional[Script] = None
    storyboard: Optional[Storyboard] = None


class RenderMode(str, Enum):
    SYNC = "sync"
    ASYNC = "async"


class RenderSubmitRequest(BaseModel):
    topic_id: str
    frame_template: str = Field("1080x1920/image_default.html")
    media_workflow: Optional[str] = None
    tts_workflow: Optional[str] = None
    bgm_path: Optional[str] = None
    confirm_cost: bool = Field(
        False,
        description="Operator must explicitly confirm to leave the approval gate.",
    )
    mode: RenderMode = RenderMode.ASYNC


class RenderRecord(BaseModel):
    topic_id: str
    pixelle_task_id: Optional[str] = None
    status: str = "queued"
    estimated_cost_band: str = "low"
    output_url: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    submit_params: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RenderResponse(BaseModel):
    success: bool = True
    render: RenderRecord
