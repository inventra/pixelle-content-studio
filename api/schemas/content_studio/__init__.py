"""Content Studio API schemas"""

from api.schemas.content_studio.topics import (
    ContentFormat,
    Topic,
    TopicSource,
    TopicStatus,
    TopicCandidate,
    TopicIngestRequest,
    TopicIngestResponse,
    TopicListResponse,
    TopicResponse,
    TopicSelectRequest,
    DailyNoteIngestRequest,
    DailyNoteIngestResponse,
)
from api.schemas.content_studio.drafts import (
    DraftSet,
    DraftGenerateRequest,
    DraftGenerateResponse,
    DraftUpdateRequest,
    DraftApproveRequest,
    DraftResponse,
)
from api.schemas.content_studio.storyboards import (
    StoryboardScene,
    Storyboard,
    Script,
    ScriptGenerateRequest,
    ScriptGenerateResponse,
    StoryboardGenerateRequest,
    StoryboardGenerateResponse,
    StoryboardResponse,
    RenderSubmitRequest,
    RenderRecord,
    RenderResponse,
)

__all__ = [
    # Topics
    "ContentFormat",
    "Topic",
    "TopicSource",
    "TopicStatus",
    "TopicCandidate",
    "TopicIngestRequest",
    "TopicIngestResponse",
    "TopicListResponse",
    "TopicResponse",
    "TopicSelectRequest",
    "DailyNoteIngestRequest",
    "DailyNoteIngestResponse",
    # Drafts
    "DraftSet",
    "DraftGenerateRequest",
    "DraftGenerateResponse",
    "DraftUpdateRequest",
    "DraftApproveRequest",
    "DraftResponse",
    # Storyboards
    "StoryboardScene",
    "Storyboard",
    "Script",
    "ScriptGenerateRequest",
    "ScriptGenerateResponse",
    "StoryboardGenerateRequest",
    "StoryboardGenerateResponse",
    "StoryboardResponse",
    "RenderSubmitRequest",
    "RenderRecord",
    "RenderResponse",
]
