"""Storyboard generator tests."""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.content_studio import TopicCandidate, TopicStatus
from pixelle_video.services.content_studio import (
    DraftGenerator,
    NewsIngestService,
    StoryboardGenerator,
    TopicSelector,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition


def _approved_topic(storage) -> str:
    """Helper: ingest -> select -> draft -> approve."""
    [topic] = NewsIngestService(storage).ingest(
        [
            TopicCandidate(
                title="Atomic Agents",
                summary="Composable agent runtimes are taking off.",
                why_it_matters="Lowers integration cost.",
                date="2026-05-03",
            )
        ]
    )
    TopicSelector(storage).select(topic.id)
    drafts = DraftGenerator(storage)
    asyncio.run(drafts.generate(topic.id))
    drafts.approve(topic.id, approved=True)
    return topic.id


def test_script_requires_approved_drafts(storage):
    [topic] = NewsIngestService(storage).ingest(
        [TopicCandidate(title="Unapproved", date="2026-05-03")]
    )
    TopicSelector(storage).select(topic.id)
    DraftGenerator(storage)
    asyncio.run(DraftGenerator(storage).generate(topic.id))
    sb = StoryboardGenerator(storage)
    # Drafts not approved -> reject
    with pytest.raises(InvalidStateTransition):
        asyncio.run(sb.generate_script(topic.id))


def test_script_then_storyboard_advances_state(storage):
    topic_id = _approved_topic(storage)
    sb = StoryboardGenerator(storage)

    script = asyncio.run(sb.generate_script(topic_id, duration_target=45))
    assert script.duration_target == 45
    assert script.hook
    assert script.cta
    assert storage.get_topic(topic_id).status == TopicStatus.SCRIPT_READY

    storyboard = asyncio.run(sb.generate_storyboard(topic_id, n_scenes=4))
    assert len(storyboard.scenes) == 4
    assert all(s.duration_seconds > 0 for s in storyboard.scenes)
    assert storage.get_topic(topic_id).status == TopicStatus.STORYBOARD_READY
    # Cost band is bucketed
    assert storyboard.estimated_cost_band in {"low", "medium", "high"}


def test_storyboard_requires_script_first(storage):
    topic_id = _approved_topic(storage)
    sb = StoryboardGenerator(storage)
    with pytest.raises(LookupError):
        asyncio.run(sb.generate_storyboard(topic_id))


def test_regenerate_replaces_existing(storage):
    topic_id = _approved_topic(storage)
    sb = StoryboardGenerator(storage)

    first = asyncio.run(sb.generate_script(topic_id, duration_target=30))
    cached = asyncio.run(sb.generate_script(topic_id, duration_target=60))
    # Cached path returns the existing script, ignoring the new duration
    assert cached.duration_target == first.duration_target

    fresh = asyncio.run(sb.generate_script(topic_id, duration_target=60, regenerate=True))
    assert fresh.duration_target == 60


def test_cost_band_grows_with_scene_count(storage):
    topic_id = _approved_topic(storage)
    sb = StoryboardGenerator(storage)

    asyncio.run(sb.generate_script(topic_id, duration_target=45))
    low = asyncio.run(sb.generate_storyboard(topic_id, n_scenes=3, regenerate=True))
    assert low.estimated_cost_band == "low"

    medium = asyncio.run(sb.generate_storyboard(topic_id, n_scenes=6, regenerate=True))
    assert medium.estimated_cost_band == "medium"

    high = asyncio.run(sb.generate_storyboard(topic_id, n_scenes=9, regenerate=True))
    assert high.estimated_cost_band == "high"
