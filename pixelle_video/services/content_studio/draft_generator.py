"""Generate Substack / Facebook / LINE drafts for an approved topic.

Default behaviour: deterministic, dependency-free templates so the
skeleton works offline and stays unit-testable. If the caller injects
an ``llm_caller`` (async callable that takes a prompt and returns a
string) we use it to produce richer drafts and fall back to the
templates on any failure.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Awaitable, Callable, Optional

from loguru import logger

from api.schemas.content_studio import (
    DraftSet,
    Topic,
    TopicStatus,
)
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
    TopicStateMachine,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


LLMCaller = Callable[[str], "str | Awaitable[str]"]


# Topics must have been at least selected before drafts make sense.
_DRAFT_ALLOWED_STATES = {
    TopicStatus.SELECTED,
    TopicStatus.DRAFTED,
    TopicStatus.DRAFT_APPROVED,
}


class DraftGenerator:
    def __init__(
        self,
        storage: ContentStudioStorage,
        llm_caller: Optional[LLMCaller] = None,
    ):
        self.storage = storage
        self.llm_caller = llm_caller

    async def generate(
        self,
        topic_id: str,
        tone: str = "informative",
        regenerate: bool = False,
    ) -> DraftSet:
        topic = self.storage.get_topic(topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")

        if topic.status not in _DRAFT_ALLOWED_STATES:
            raise InvalidStateTransition(
                f"Topic {topic.id} is in '{topic.status.value}' state; select it before generating drafts."
            )

        existing = self.storage.get_drafts(topic_id)
        if existing and not regenerate:
            return existing

        substack = await self._render(topic, tone, "substack")
        facebook = await self._render(topic, tone, "facebook")
        line_draft = await self._render(topic, tone, "line")

        draft_set = DraftSet(
            topic_id=topic.id,
            substack_draft=substack,
            facebook_draft=facebook,
            line_draft=line_draft,
            editor_notes="",
            approved_for_video=existing.approved_for_video if existing else False,
        )
        self.storage.save_drafts(draft_set)

        if topic.status == TopicStatus.SELECTED:
            topic.status = TopicStatus.DRAFTED
            self.storage.save_topic(topic)

        return draft_set

    def update(self, topic_id: str, **changes) -> DraftSet:
        drafts = self.storage.get_drafts(topic_id)
        if drafts is None:
            raise LookupError(f"Drafts for topic {topic_id} not found")
        for key, value in changes.items():
            if value is None:
                continue
            if not hasattr(drafts, key):
                raise AttributeError(f"DraftSet has no field '{key}'")
            setattr(drafts, key, value)
        return self.storage.save_drafts(drafts)

    def approve(self, topic_id: str, approved: bool = True) -> DraftSet:
        drafts = self.storage.get_drafts(topic_id)
        topic = self.storage.get_topic(topic_id)
        if drafts is None or topic is None:
            raise LookupError(f"Drafts for topic {topic_id} not found")

        drafts.approved_for_video = approved
        self.storage.save_drafts(drafts)

        if approved:
            TopicStateMachine.assert_transition(topic.status, TopicStatus.DRAFT_APPROVED)
            topic.status = TopicStatus.DRAFT_APPROVED
        else:
            # Roll the topic back to "drafted" so the operator can edit again.
            if topic.status == TopicStatus.DRAFT_APPROVED:
                topic.status = TopicStatus.DRAFTED
        self.storage.save_topic(topic)
        return drafts

    # ----- rendering --------------------------------------------------------

    async def _render(self, topic: Topic, tone: str, surface: str) -> str:
        prompt = self._build_prompt(topic, tone, surface)
        if self.llm_caller is not None:
            try:
                result = self.llm_caller(prompt)
                if inspect.isawaitable(result):
                    result = await result
                if isinstance(result, str) and result.strip():
                    return result.strip()
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(f"LLM draft generation failed for {surface}: {e}")
        return self._fallback_template(topic, tone, surface)

    @staticmethod
    def _build_prompt(topic: Topic, tone: str, surface: str) -> str:
        return (
            f"You are drafting a {surface} post.\n"
            f"Tone: {tone}.\n"
            f"Topic title: {topic.title}\n"
            f"Summary: {topic.summary}\n"
            f"Why it matters: {topic.why_it_matters}\n"
            f"Constraints: keep it copy-friendly, no markdown headings beyond H2, "
            f"and end with one short call-to-action."
        )

    @staticmethod
    def _fallback_template(topic: Topic, tone: str, surface: str) -> str:
        title = topic.title.strip() or "Today's AI topic"
        summary = topic.summary.strip() or "Why this is on my radar today."
        why = topic.why_it_matters.strip() or "Worth keeping an eye on."

        if surface == "substack":
            return (
                f"# {title}\n\n"
                f"_Tone: {tone}_\n\n"
                f"## What happened\n{summary}\n\n"
                f"## Why it matters\n{why}\n\n"
                f"## My take\n"
                f"This is a draft seed — refine the story, add concrete examples, "
                f"and finish with a single takeaway.\n\n"
                f"_Subscribe if you want the next one._"
            )
        if surface == "facebook":
            return (
                f"📰 {title}\n\n"
                f"{summary}\n\n"
                f"Why it matters: {why}\n\n"
                f"#AI #ContentStudio"
            )
        if surface == "line":
            short_summary = summary if len(summary) <= 120 else summary[:117] + "..."
            return f"【{title}】\n{short_summary}\n→ {why}"
        raise ValueError(f"Unknown surface: {surface}")
