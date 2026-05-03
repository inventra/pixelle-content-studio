"""News ingest service tests."""

from __future__ import annotations

from datetime import date as _date

from api.schemas.content_studio import (
    ContentFormat,
    TopicCandidate,
    TopicSource,
    TopicStatus,
)
from pixelle_video.services.content_studio import NewsIngestService


def test_ingest_creates_candidate_topics(storage):
    service = NewsIngestService(storage)
    topics = service.ingest(
        [
            TopicCandidate(
                title="Open Design",
                summary="A new way to ship UI",
                why_it_matters="Lowers iteration cost",
                source=TopicSource(source_type="hermes"),
                recommended_formats=[ContentFormat.SUBSTACK, ContentFormat.VIDEO],
                priority=80,
                date="2026-05-03",
            )
        ]
    )

    assert len(topics) == 1
    saved = storage.get_topic(topics[0].id)
    assert saved is not None
    assert saved.status == TopicStatus.CANDIDATE
    assert saved.priority == 80
    assert ContentFormat.SUBSTACK in saved.recommended_formats


def test_ingest_replace_for_date_drops_old_rows(storage):
    service = NewsIngestService(storage)
    service.ingest([
        TopicCandidate(title="Old A", date="2026-05-03"),
        TopicCandidate(title="Old B", date="2026-05-03"),
    ])
    assert len(storage.list_topics(date="2026-05-03")) == 2

    service.ingest(
        [TopicCandidate(title="Fresh", date="2026-05-03")],
        replace_for_date=True,
    )
    rows = storage.list_topics(date="2026-05-03")
    assert {t.title for t in rows} == {"Fresh"}


def test_ingest_defaults_date_to_today(storage):
    service = NewsIngestService(storage)
    topics = service.ingest([TopicCandidate(title="Today's pick")])
    assert topics[0].date == _date.today().isoformat()


def test_empty_ingest_is_a_noop(storage):
    service = NewsIngestService(storage)
    assert service.ingest([]) == []
