"""News ingest -> topic candidate normalization."""

from __future__ import annotations

import uuid
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from api.schemas.content_studio import (
    Topic,
    TopicCandidate,
    TopicStatus,
)
from pixelle_video.services.content_studio.obsidian_news_loader import (
    DailyNoteNotFound,
    load_candidates_for_date,
)
from pixelle_video.services.content_studio.storage import ContentStudioStorage


def _today_str() -> str:
    return _date.today().isoformat()


class NewsIngestService:
    """Convert raw candidates into stored Topic rows.

    Beyond the manual candidate path, the service can also pull
    candidates straight from the user's Obsidian daily briefing note
    (see ``obsidian_news_loader``) so the Topics page has a one-click
    "ingest today's news" path.
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

    def ingest_from_daily_note(
        self,
        target_date: Optional[str] = None,
        vault_root: Path | str | None = None,
        replace_for_date: bool = True,
    ) -> List[Topic]:
        """Read the Obsidian daily briefing note for ``target_date`` and ingest it.

        Defaults to today's note. ``replace_for_date`` defaults to True
        because re-running the daily ingest should be idempotent — we
        replace the previous run's rows instead of stacking duplicates.

        Raises ``DailyNoteNotFound`` if the file is missing so the
        caller (router / UI button) can surface a clear error.
        """
        candidates = load_candidates_for_date(target_date, vault_root=vault_root)
        if not candidates:
            return []
        return self.ingest(candidates, replace_for_date=replace_for_date)


__all__ = ["NewsIngestService", "DailyNoteNotFound"]
