"""Content Studio routers.

The MVP brief mandates these endpoints sit alongside the existing
Pixelle-Video routers, all under ``/api``. They orchestrate the
content workflow but never replace the existing video routers.
"""

from api.routers.content_studio.topics import router as topics_router
from api.routers.content_studio.drafts import router as drafts_router
from api.routers.content_studio.storyboards import router as storyboards_router

__all__ = ["topics_router", "drafts_router", "storyboards_router"]
