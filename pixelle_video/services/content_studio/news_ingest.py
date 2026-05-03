"""News ingest -> topic candidate normalization."""

from __future__ import annotations

import uuid
from datetime import date as _date
from datetime import datetime
from typing import Iterable, List

from api.schemas.content_studio import (
    Topic,
    TopicCandidate,
    TopicStatus,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


def _today_str() -> str:
    return _date.today().isoformat()


class NewsIngestService:
    """Convert raw candidates into stored Topic rows.

    The MVP doesn't crawl news directly; it accepts already-curated
    candidate dicts (e.g. from Hermes/Obsidian) and persists them as
    Topic rows in the ``candidate`` state.
    """

    def __init__(self, storage: ContentStudioStorage):
        self.storage = storage

    def ingest(
        self,
        candidates: Iterable[TopicCandidate],
        replace_for_date: bool = False,
    ) -> List[Topic]:
        candidates = list(candidates)
        if not candidates:
            return []

        if replace_for_date:
            # Drop the existing rows for every distinct date in the batch.
            distinct_dates = {c.date or _today_str() for c in candidates}
            for d in distinct_dates:
                self.storage.delete_topics_for_date(d)

        topics: List[Topic] = []
        now = datetime.utcnow()
        for c in candidates:
            topic_date = c.date or _today_str()
            topic = Topic(
                id=str(uuid.uuid4()),
                date=topic_date,
                title=c.title.strip(),
                summary=c.summary.strip(),
                why_it_matters=c.why_it_matters.strip(),
                source=c.source,
                recommended_formats=list(c.recommended_formats),
                priority=c.priority,
                status=TopicStatus.CANDIDATE,
                created_at=now,
                updated_at=now,
            )
            topics.append(self.storage.save_topic(topic))
        return topics
