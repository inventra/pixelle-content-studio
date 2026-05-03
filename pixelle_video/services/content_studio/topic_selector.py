"""Topic selection / skipping helpers.

These are the user-driven state transitions out of ``candidate``.
"""

from __future__ import annotations

from typing import Optional

from api.schemas.content_studio import Topic, TopicStatus
from pixelle_video.services.content_studio.state_machine import TopicStateMachine
from pixelle_video.services.content_studio.storage import ContentStudioStorage


class TopicSelector:
    def __init__(self, storage: ContentStudioStorage):
        self.storage = storage

    def _get_or_404(self, topic_id: str) -> Topic:
        topic = self.storage.get_topic(topic_id)
        if topic is None:
            raise LookupError(f"Topic {topic_id} not found")
        return topic

    def select(self, topic_id: str, notes: Optional[str] = None) -> Topic:
        topic = self._get_or_404(topic_id)
        TopicStateMachine.assert_transition(topic.status, TopicStatus.SELECTED)
        topic.status = TopicStatus.SELECTED
        if notes is not None:
            topic.notes = notes
        return self.storage.save_topic(topic)

    def skip(self, topic_id: str, notes: Optional[str] = None) -> Topic:
        topic = self._get_or_404(topic_id)
        TopicStateMachine.assert_transition(topic.status, TopicStatus.SKIPPED)
        topic.status = TopicStatus.SKIPPED
        if notes is not None:
            topic.notes = notes
        return self.storage.save_topic(topic)

    def mark_priority(self, topic_id: str, priority: int) -> Topic:
        topic = self._get_or_404(topic_id)
        topic.priority = max(0, min(100, priority))
        return self.storage.save_topic(topic)
