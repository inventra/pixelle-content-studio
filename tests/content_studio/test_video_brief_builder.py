"""Bridge builder tests: storyboard -> VideoGenerateRequest."""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.content_studio import TopicCandidate, TopicStatus
from pixelle_video.services.content_studio import (
    DraftGenerator,
    NewsIngestService,
    StoryboardGenerator,
    TopicSelector,
    VideoBriefBuilder,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition


def _ready_topic(storage) -> str:
    [topic] = NewsIngestService(storage).ingest(
        [
            TopicCandidate(
                title="Pixelle Studio",
                summary="A new content studio on top of Pixelle-Video.",
                why_it_matters="Independent of LazyOffice.",
                date="2026-05-03",
            )
        ]
    )
    TopicSelector(storage).select(topic.id)
    drafts = DraftGenerator(storage)
    asyncio.run(drafts.generate(topic.id))
    drafts.approve(topic.id, approved=True)
    sb = StoryboardGenerator(storage)
    asyncio.run(sb.generate_script(topic.id, duration_target=45))
    asyncio.run(sb.generate_storyboard(topic.id, n_scenes=4))
    return topic.id


def test_build_request_uses_fixed_mode_and_storyboard_text(storage):
    topic_id = _ready_topic(storage)
    builder = VideoBriefBuilder(storage)
    req = builder.build_request(topic_id, frame_template="1080x1920/image_default.html")

    assert req.mode == "fixed"
    assert req.title == "Pixelle Studio"
    assert req.frame_template == "1080x1920/image_default.html"
    storyboard = storage.get_storyboard(topic_id)
    assert req.n_scenes == len(storyboard.scenes)

    # Each storyboard voiceover line should appear in the source text.
    for scene in storyboard.scenes:
        assert scene.voiceover.strip() in req.text


def test_build_request_blocked_until_storyboard_ready(storage):
    [topic] = NewsIngestService(storage).ingest(
        [TopicCandidate(title="Half-baked", date="2026-05-03")]
    )
    TopicSelector(storage).select(topic.id)
    builder = VideoBriefBuilder(storage)
    with pytest.raises(LookupError):
        builder.build_request(topic.id)


def test_build_request_blocked_when_topic_not_at_storyboard_ready(storage):
    topic_id = _ready_topic(storage)
    # Move topic state forward past STORYBOARD_READY into a state that is
    # not in the render-ready set (e.g. RENDER_COMPLETED).
    topic = storage.get_topic(topic_id)
    topic.status = TopicStatus.RENDER_COMPLETED
    storage.save_topic(topic)

    builder = VideoBriefBuilder(storage)
    with pytest.raises(InvalidStateTransition):
        builder.build_request(topic_id)


def test_build_render_record_persists_with_cost_band(storage):
    topic_id = _ready_topic(storage)
    builder = VideoBriefBuilder(storage)
    req = builder.build_request(topic_id)
    record = builder.build_render_record(
        topic_id=topic_id,
        request=req,
        pixelle_task_id="pix-1",
    )
    assert record.pixelle_task_id == "pix-1"
    assert record.estimated_cost_band in {"low", "medium", "high"}
    assert record.submit_params["mode"] == "fixed"

    reloaded = storage.get_render(topic_id)
    assert reloaded is not None
    assert reloaded.pixelle_task_id == "pix-1"
