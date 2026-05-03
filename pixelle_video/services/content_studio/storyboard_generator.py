"""Generate short-video scripts and storyboards from approved drafts.

Mirrors the pattern of ``draft_generator``: deterministic fallback so
the MVP works offline; optional LLM caller for richer output. The
script must come from drafts that have been explicitly approved for
video — the approval gate is enforced here as well as in the router.
"""

from __future__ import annotations

import inspect
import math
import re
from typing import Awaitable, Callable, List, Optional

from loguru import logger

from api.schemas.content_studio import (
    DraftSet,
    Script,
    Storyboard,
    StoryboardScene,
    Topic,
    TopicStatus,
)
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
    TopicStateMachine,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


LLMCaller = Callable[[str], "str | Awaitable[str]"]


class StoryboardGenerator:
    def __init__(
        self,
        storage: ContentStudioStorage,
        llm_caller: Optional[LLMCaller] = None,
    ):
        self.storage = storage
        self.llm_caller = llm_caller

    # ----- script -----------------------------------------------------------

    async def generate_script(
        self,
        topic_id: str,
        duration_target: int = 45,
        angle: Optional[str] = None,
        voice_style: Optional[str] = None,
        regenerate: bool = False,
    ) -> Script:
        topic, drafts = self._require_approved(topic_id)

        existing = self.storage.get_script(topic_id)
        if existing and not regenerate:
            return existing

        body = await self._compose_body(topic, drafts, duration_target, angle)
        hook = await self._compose_hook(topic, drafts, angle)
        cta = self._compose_cta(topic)

        script = Script(
            topic_id=topic.id,
            angle=(angle or topic.title).strip(),
            duration_target=duration_target,
            hook=hook,
            body=body,
            cta=cta,
            voice_style=voice_style or "calm-narrator",
        )
        self.storage.save_script(script)

        TopicStateMachine.assert_transition(topic.status, TopicStatus.SCRIPT_READY)
        topic.status = TopicStatus.SCRIPT_READY
        self.storage.save_topic(topic)
        return script

    # ----- storyboard -------------------------------------------------------

    async def generate_storyboard(
        self,
        topic_id: str,
        visual_style: Optional[str] = None,
        n_scenes: Optional[int] = None,
        regenerate: bool = False,
    ) -> Storyboard:
        script = self.storage.get_script(topic_id)
        topic = self.storage.get_topic(topic_id)
        if script is None or topic is None:
            raise LookupError(f"No script for topic {topic_id}; generate the script first.")

        existing = self.storage.get_storyboard(topic_id)
        if existing and not regenerate:
            return existing

        scenes = self._split_into_scenes(script, n_scenes=n_scenes)
        storyboard = Storyboard(
            topic_id=topic_id,
            visual_style=visual_style or "clean-editorial",
            scenes=scenes,
            estimated_cost_band=self._estimate_cost_band(scenes),
        )
        self.storage.save_storyboard(storyboard)

        TopicStateMachine.assert_transition(topic.status, TopicStatus.STORYBOARD_READY)
        topic.status = TopicStatus.STORYBOARD_READY
        self.storage.save_topic(topic)
        return storyboard

    # ----- helpers ----------------------------------------------------------

    def _require_approved(self, topic_id: str) -> tuple[Topic, DraftSet]:
        topic = self.storage.get_topic(topic_id)
        drafts = self.storage.get_drafts(topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")
        if drafts is None:
            raise LookupError(f"Drafts for topic {topic_id} not found")
        if not drafts.approved_for_video:
            raise InvalidStateTransition(
                f"Drafts for topic {topic_id} have not been approved for video."
            )
        if not TopicStateMachine.can_generate_script(topic.status):
            raise InvalidStateTransition(
                f"Topic {topic_id} is in '{topic.status.value}'; cannot generate script."
            )
        return topic, drafts

    async def _compose_body(
        self,
        topic: Topic,
        drafts: DraftSet,
        duration_target: int,
        angle: Optional[str],
    ) -> str:
        prompt = (
            f"Write a short-video voiceover (~{duration_target}s) for the topic '{topic.title}'.\n"
            f"Angle: {angle or topic.title}\n"
            f"Source draft (Substack):\n{drafts.substack_draft}\n\n"
            f"Constraints: punchy, conversational, end with a clear takeaway. "
            f"Do not include scene labels."
        )
        llm_text = await self._maybe_llm(prompt)
        if llm_text:
            return llm_text
        # Fallback: stitch the existing summary + why-it-matters.
        chunks = [topic.summary.strip(), topic.why_it_matters.strip()]
        if not any(chunks):
            chunks = [drafts.substack_draft.strip()[:400]]
        return " ".join(c for c in chunks if c)

    async def _compose_hook(
        self,
        topic: Topic,
        drafts: DraftSet,
        angle: Optional[str],
    ) -> str:
        prompt = (
            f"Write a 1-sentence hook for a short video about '{topic.title}'. "
            f"Angle: {angle or topic.title}. Keep it under 18 words."
        )
        llm_text = await self._maybe_llm(prompt)
        if llm_text:
            return llm_text.split("\n")[0].strip()
        return f"Here's why {topic.title} matters today."

    @staticmethod
    def _compose_cta(topic: Topic) -> str:
        return f"Save this — and tell me what you'd build with {topic.title.split(':')[0].strip() or 'it'}."

    async def _maybe_llm(self, prompt: str) -> Optional[str]:
        if self.llm_caller is None:
            return None
        try:
            result = self.llm_caller(prompt)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, str) and result.strip():
                return result.strip()
        except Exception as e:  # pragma: no cover
            logger.warning(f"LLM script generation failed: {e}")
        return None

    @staticmethod
    def _split_into_scenes(script: Script, n_scenes: Optional[int] = None) -> List[StoryboardScene]:
        sentences = _split_sentences(f"{script.hook} {script.body} {script.cta}".strip())
        if not sentences:
            sentences = [script.body or script.hook or "Scene placeholder."]

        target = n_scenes or max(3, min(8, math.ceil(script.duration_target / 8)))
        per_scene_seconds = round(script.duration_target / target, 2)

        # Bucket sentences into exactly `target` chunks. If we don't have
        # enough sentences, pad with a recap of the body so callers still
        # get the requested number of scenes (e.g. operator asks for 6
        # scenes but the script only has 3 sentences).
        chunks = _bucket_sentences(sentences, target)
        if len(chunks) < target:
            filler = script.body.strip() or sentences[-1]
            while len(chunks) < target:
                chunks.append(filler)

        scenes: List[StoryboardScene] = []
        for i, voiceover in enumerate(chunks, start=1):
            voiceover = voiceover.strip()
            visual = _voiceover_to_visual(voiceover)
            onscreen = _short_caption(voiceover)
            scenes.append(
                StoryboardScene(
                    scene_no=i,
                    voiceover=voiceover,
                    visual_prompt=visual,
                    onscreen_text=onscreen,
                    duration_seconds=per_scene_seconds,
                )
            )
        return scenes

    @staticmethod
    def _estimate_cost_band(scenes: List[StoryboardScene]) -> str:
        # Cheap heuristic: scene count drives expected render cost.
        n = len(scenes)
        if n <= 4:
            return "low"
        if n <= 7:
            return "medium"
        return "high"


# ----- text helpers ---------------------------------------------------------


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+")


def _split_sentences(text: str) -> List[str]:
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p.strip()]
    return parts or [text]


def _bucket_sentences(sentences: List[str], buckets: int) -> List[str]:
    """Distribute ``sentences`` across ``buckets`` chunks as evenly as possible.

    Returns at most ``buckets`` non-empty chunks. Caller is responsible
    for padding when the source has fewer sentences than buckets.
    """
    if buckets <= 0:
        return []
    n = len(sentences)
    if n == 0:
        return []
    if n <= buckets:
        return list(sentences)

    # Compute boundaries by integer division so chunks vary by at most 1.
    boundaries = [(i * n) // buckets for i in range(buckets + 1)]
    chunks: List[str] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if start == end:
            continue
        chunks.append(" ".join(sentences[start:end]))
    return chunks


def _voiceover_to_visual(voiceover: str) -> str:
    summary = voiceover[:120]
    return f"Editorial cinematic shot illustrating: {summary}"


def _short_caption(voiceover: str) -> str:
    words = voiceover.split()
    return " ".join(words[:6])
