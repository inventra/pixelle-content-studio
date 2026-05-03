"""News ingest -> topic candidate normalization."""

from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
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


def _identity_parts(*, date: str, title: str, source_type: str, source_ref: str | None, source_url: str | None) -> tuple[str, str, str, str, str]:
    return (
        date.strip(),
        title.strip().casefold(),
        source_type.strip().casefold(),
        (source_ref or "").strip().casefold(),
        (source_url or "").strip(),
    )


def _identity_key_for_candidate(candidate: TopicCandidate, topic_date: str) -> str:
    parts = _identity_parts(
        date=topic_date,
        title=candidate.title,
        source_type=candidate.source.source_type,
        source_ref=candidate.source.source_ref,
        source_url=candidate.source.source_url,
    )
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


def _identity_key_for_topic(topic: Topic) -> str:
    parts = _identity_parts(
        date=topic.date,
        title=topic.title,
        source_type=topic.source.source_type,
        source_ref=topic.source.source_ref,
        source_url=topic.source.source_url,
    )
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()


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

        now = datetime.utcnow()
        existing_by_date: dict[str, dict[str, Topic]] = {}
        candidate_keys_by_date: dict[str, set[str]] = defaultdict(set)
        for c in candidates:
            topic_date = c.date or _today_str()
            existing_by_date.setdefault(
                topic_date,
                {_identity_key_for_topic(t): t for t in self.storage.list_topics(date=topic_date)},
            )
            candidate_keys_by_date[topic_date].add(_identity_key_for_candidate(c, topic_date))

        if replace_for_date:
            for topic_date, existing_topics in existing_by_date.items():
                incoming_keys = candidate_keys_by_date[topic_date]
                for identity_key, topic in list(existing_topics.items()):
                    if identity_key in incoming_keys:
                        continue
                    if topic.status in {TopicStatus.CANDIDATE, TopicStatus.SKIPPED}:
                        self.storage.delete_topic(topic.id)
                        existing_topics.pop(identity_key, None)

        topics: List[Topic] = []
        for c in candidates:
            topic_date = c.date or _today_str()
            identity_key = _identity_key_for_candidate(c, topic_date)
            existing = existing_by_date[topic_date].get(identity_key)
            topic = Topic(
                id=existing.id if existing else str(uuid.uuid4()),
                date=topic_date,
                title=c.title.strip(),
                summary=c.summary.strip(),
                why_it_matters=c.why_it_matters.strip(),
                source=c.source,
                recommended_formats=list(c.recommended_formats),
                priority=c.priority,
                status=existing.status if existing else TopicStatus.CANDIDATE,
                notes=existing.notes if existing else None,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            saved = self.storage.save_topic(topic)
            existing_by_date[topic_date][identity_key] = saved
            topics.append(saved)
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
