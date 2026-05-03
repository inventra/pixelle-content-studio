"""Bridge: Storyboard -> Pixelle-Video VideoGenerateRequest params.

This is the only piece of code that knows how to translate the new
content-studio storyboard schema into the existing video router input.
Keeping it isolated means the upstream content workflow does not have
to know about Pixelle-Video internals, and the existing video router
stays untouched.
"""

from __future__ import annotations

from typing import Optional

from api.schemas.content_studio import (
    RenderRecord,
    Script,
    Storyboard,
    Topic,
)
from api.schemas.video import VideoGenerateRequest
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
    TopicStateMachine,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


class VideoBriefBuilder:
    def __init__(self, storage: ContentStudioStorage):
        self.storage = storage

    def build_request(
        self,
        topic_id: str,
        frame_template: str = "1080x1920/image_default.html",
        media_workflow: Optional[str] = None,
        tts_workflow: Optional[str] = None,
        bgm_path: Optional[str] = None,
    ) -> VideoGenerateRequest:
        topic, script, storyboard = self._require_ready(topic_id)

        # Compose the prompt text Pixelle-Video will use as source text.
        # We send the storyboard voiceovers concatenated (mode="fixed")
        # so the existing pipeline does not re-narrate from scratch.
        text = self._compose_text(script, storyboard)

        n_scenes = max(1, len(storyboard.scenes))

        return VideoGenerateRequest(
            text=text,
            mode="fixed",
            title=topic.title,
            n_scenes=n_scenes,
            frame_template=frame_template,
            media_workflow=media_workflow,
            tts_workflow=tts_workflow,
            bgm_path=bgm_path,
            prompt_prefix=storyboard.visual_style or None,
        )

    def build_render_record(
        self,
        topic_id: str,
        request: VideoGenerateRequest,
        pixelle_task_id: Optional[str] = None,
        status: str = "queued",
    ) -> RenderRecord:
        storyboard = self.storage.get_storyboard(topic_id)
        cost_band = storyboard.estimated_cost_band if storyboard else "low"
        record = RenderRecord(
            topic_id=topic_id,
            pixelle_task_id=pixelle_task_id,
            status=status,
            estimated_cost_band=cost_band,
            submit_params=request.model_dump(),
        )
        return self.storage.save_render(record)

    def _require_ready(self, topic_id: str) -> tuple[Topic, Script, Storyboard]:
        topic = self.storage.get_topic(topic_id)
        script = self.storage.get_script(topic_id)
        storyboard = self.storage.get_storyboard(topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")
        if script is None:
            raise LookupError(f"No script for topic {topic_id}")
        if storyboard is None:
            raise LookupError(f"No storyboard for topic {topic_id}")
        if not TopicStateMachine.can_submit_render(topic.status):
            raise InvalidStateTransition(
                f"Topic {topic_id} is in '{topic.status.value}'; storyboard must be ready before render submission."
            )
        if not storyboard.scenes:
            raise InvalidStateTransition(f"Storyboard for {topic_id} has no scenes.")
        return topic, script, storyboard

    @staticmethod
    def _compose_text(script: Script, storyboard: Storyboard) -> str:
        # Concatenate hook + scene voiceovers so the fixed pipeline keeps
        # the order and pacing the operator approved.
        chunks = []
        if script.hook:
            chunks.append(script.hook.strip())
        for scene in storyboard.scenes:
            chunks.append(scene.voiceover.strip())
        if script.cta:
            chunks.append(script.cta.strip())
        return "\n".join(c for c in chunks if c)
