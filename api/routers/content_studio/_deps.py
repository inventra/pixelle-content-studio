"""Shared dependency-injection helpers for content studio routers."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import Depends

from pixelle_video.services.content_studio import (
    ContentStudioStorage,
    DraftGenerator,
    NewsIngestService,
    StoryboardGenerator,
    TopicSelector,
    VideoBriefBuilder,
    get_storage,
)


# A swappable factory so tests can inject an offline LLM caller.
_llm_caller_factory = None


def set_llm_caller_factory(factory):
    """Register a callable that returns an LLM caller (or None)."""
    global _llm_caller_factory
    _llm_caller_factory = factory


def _get_llm_caller():
    if _llm_caller_factory is None:
        return None
    try:
        return _llm_caller_factory()
    except Exception:
        return None


def get_content_studio_storage() -> ContentStudioStorage:
    return get_storage()


StorageDep = Annotated[ContentStudioStorage, Depends(get_content_studio_storage)]


def get_news_ingest(storage: StorageDep) -> NewsIngestService:
    return NewsIngestService(storage)


def get_topic_selector(storage: StorageDep) -> TopicSelector:
    return TopicSelector(storage)


def get_draft_generator(storage: StorageDep) -> DraftGenerator:
    return DraftGenerator(storage, llm_caller=_get_llm_caller())


def get_storyboard_generator(storage: StorageDep) -> StoryboardGenerator:
    return StoryboardGenerator(storage, llm_caller=_get_llm_caller())


def get_video_brief_builder(storage: StorageDep) -> VideoBriefBuilder:
    return VideoBriefBuilder(storage)


NewsIngestDep = Annotated[NewsIngestService, Depends(get_news_ingest)]
TopicSelectorDep = Annotated[TopicSelector, Depends(get_topic_selector)]
DraftGeneratorDep = Annotated[DraftGenerator, Depends(get_draft_generator)]
StoryboardGeneratorDep = Annotated[StoryboardGenerator, Depends(get_storyboard_generator)]
VideoBriefBuilderDep = Annotated[VideoBriefBuilder, Depends(get_video_brief_builder)]
