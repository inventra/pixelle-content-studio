"""Content Studio orchestration services.

These services sit on top of Pixelle-Video and implement the content
workflow described in docs/2026-05-03_content-studio-mvp-brief.md.
They are intentionally independent of LazyOffice and reuse Pixelle-Video
capabilities only via the existing PixelleVideoCore + video router.
"""

from pixelle_video.services.content_studio.storage import (
    ContentStudioStorage,
    get_storage,
    set_storage,
    reset_storage,
)
from pixelle_video.services.content_studio.news_ingest import NewsIngestService
from pixelle_video.services.content_studio.topic_selector import TopicSelector
from pixelle_video.services.content_studio.draft_generator import DraftGenerator
from pixelle_video.services.content_studio.storyboard_generator import StoryboardGenerator
from pixelle_video.services.content_studio.video_brief_builder import VideoBriefBuilder
from pixelle_video.services.content_studio.state_machine import (
    TopicStateMachine,
    InvalidStateTransition,
)

__all__ = [
    "ContentStudioStorage",
    "get_storage",
    "set_storage",
    "reset_storage",
    "NewsIngestService",
    "TopicSelector",
    "DraftGenerator",
    "StoryboardGenerator",
    "VideoBriefBuilder",
    "TopicStateMachine",
    "InvalidStateTransition",
]
