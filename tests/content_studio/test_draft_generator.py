"""Draft generator tests (offline)."""

from __future__ import annotations

import asyncio

import pytest

from api.schemas.content_studio import TopicCandidate, TopicStatus
from pixelle_video.services.content_studio import (
    DraftGenerator,
    NewsIngestService,
    TopicSelector,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition


def _ingest_one(storage, **kwargs) -> str:
    candidate = TopicCandidate(
        title=kwargs.pop("title", "Open Design"),
        summary=kwargs.pop("summary", "A new way to ship UI"),
        why_it_matters=kwargs.pop("why", "Lowers iteration cost"),
        date=kwargs.pop("date", "2026-05-03"),
        **kwargs,
    )
    [topic] = NewsIngestService(storage).ingest([candidate])
    return topic.id


def test_generate_drafts_requires_selected_topic(storage):
    topic_id = _ingest_one(storage)
    drafts = DraftGenerator(storage)
    with pytest.raises(InvalidStateTransition):
        asyncio.run(drafts.generate(topic_id))


def test_generate_drafts_emits_three_surfaces_and_advances_state(storage):
    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)

    drafts = DraftGenerator(storage)
    result = asyncio.run(drafts.generate(topic_id))

    assert result.substack_draft.startswith("# Open Design")
    assert "Open Design" in result.facebook_draft
    assert "Open Design" in result.line_draft
    assert result.approved_for_video is False

    topic = storage.get_topic(topic_id)
    assert topic.status == TopicStatus.DRAFTED


def test_generate_uses_llm_caller_when_provided(storage, stub_llm):
    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)

    drafts = DraftGenerator(storage, llm_caller=stub_llm)
    result = asyncio.run(drafts.generate(topic_id))

    # Each surface should carry the LLM stub marker.
    assert result.substack_draft.startswith("[LLM-STUB]")
    assert result.facebook_draft.startswith("[LLM-STUB]")
    assert result.line_draft.startswith("[LLM-STUB]")


def test_generate_returns_existing_unless_regenerate(storage):
    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)

    drafts = DraftGenerator(storage)
    first = asyncio.run(drafts.generate(topic_id))
    drafts.update(topic_id, editor_notes="hand-edited")

    cached = asyncio.run(drafts.generate(topic_id))
    assert cached.editor_notes == "hand-edited"
    assert cached.substack_draft == first.substack_draft

    refreshed = asyncio.run(drafts.generate(topic_id, regenerate=True))
    # Editor notes preserved? No — regenerate creates a fresh DraftSet.
    assert refreshed.editor_notes == ""


def test_approve_flag_drives_topic_state(storage):
    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)
    drafts = DraftGenerator(storage)
    asyncio.run(drafts.generate(topic_id))

    approved = drafts.approve(topic_id, approved=True)
    assert approved.approved_for_video is True
    assert storage.get_topic(topic_id).status == TopicStatus.DRAFT_APPROVED

    revoked = drafts.approve(topic_id, approved=False)
    assert revoked.approved_for_video is False
    assert storage.get_topic(topic_id).status == TopicStatus.DRAFTED


def test_update_rejects_unknown_field(storage):
    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)
    drafts = DraftGenerator(storage)
    asyncio.run(drafts.generate(topic_id))

    with pytest.raises(AttributeError):
        drafts.update(topic_id, bogus="x")
