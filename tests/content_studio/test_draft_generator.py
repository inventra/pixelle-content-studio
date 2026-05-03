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


# --- Toulan Office style checks ----------------------------------------------
#
# The Phase-2 brief asks for drafts that feel like 偷懶辦公室 — not a news
# recap but a piece structured around: why-it-matters, real use cases, and a
# concrete prompt/workflow tip. We assert on the structural skeleton (section
# headers / bullet patterns) rather than exact prose so we don't lock the
# templates in too tightly.


def test_substack_draft_carries_toulan_office_skeleton(storage):
    topic_id = _ingest_one(
        storage,
        title="Open Design",
        summary="開源工具，可以把 coding agent 接成設計引擎。能跑出 web、mobile、slides 等原型。",
        why="設計、品牌系統與 agent workflow 正在快速收斂。",
    )
    TopicSelector(storage).select(topic_id)

    result = asyncio.run(DraftGenerator(storage).generate(topic_id))
    sub = result.substack_draft

    # Title still appears as H1 (kept for editor familiarity & external tools).
    assert sub.startswith("# Open Design")
    # The structural sections that define the 偷懶辦公室 voice.
    assert "為什麼值得看一眼" in sub
    assert "實際可以拿來做什麼" in sub
    assert "今天就能用的招式" in sub
    assert "一句話總結" in sub
    # The actionable-prompt section should ship a copy-pasteable code block.
    assert "```" in sub
    # The piece must NOT collapse into a "news list" — it should reference the
    # why-it-matters content, not just restate the summary.
    assert "agent workflow" in sub or "收斂" in sub


def test_facebook_draft_has_hook_use_cases_and_prompt(storage):
    topic_id = _ingest_one(
        storage,
        title="Open Design",
        summary="一個開源的 coding-agent 設計引擎。",
        why="降低設計到原型的迭代成本。",
    )
    TopicSelector(storage).select(topic_id)

    fb = asyncio.run(DraftGenerator(storage).generate(topic_id)).facebook_draft

    assert "Open Design" in fb
    assert "為什麼重要" in fb
    # Use-case bullets — at least one bullet symbol must show up.
    assert "•" in fb
    # Actionable prompt cue.
    assert "prompt" in fb.lower() or "workflow" in fb.lower() or "工作流" in fb
    # Hashtags row.
    assert "#" in fb


def test_line_draft_is_short_and_actionable(storage):
    topic_id = _ingest_one(
        storage,
        title="Open Design",
        summary="開源 coding-agent 設計引擎。",
        why="降低設計迭代成本。",
    )
    TopicSelector(storage).select(topic_id)

    line = asyncio.run(DraftGenerator(storage).generate(topic_id)).line_draft

    assert line.startswith("【Open Design】")
    # LINE drafts must include why-it-matters AND a "how to use" cue, not
    # just the summary.
    assert "為什麼" in line
    assert "怎麼用" in line or "🛠" in line
    # And stay short — the brief specifies LINE messages should be tight.
    assert len(line) <= 260


def test_llm_prompt_carries_toulan_office_style_anchor(storage):
    captured: list[str] = []

    async def capturing_llm(prompt: str) -> str:
        captured.append(prompt)
        return "stub"

    topic_id = _ingest_one(storage)
    TopicSelector(storage).select(topic_id)

    asyncio.run(DraftGenerator(storage, llm_caller=capturing_llm).generate(topic_id))

    # Every surface prompt should carry the explicit style anchor so the LLM
    # produces practical, prompt-aware copy instead of a news recap.
    assert len(captured) == 3
    for prompt in captured:
        assert "偷懶辦公室" in prompt
        assert "use cases" in prompt.lower() or "workflow" in prompt.lower()
