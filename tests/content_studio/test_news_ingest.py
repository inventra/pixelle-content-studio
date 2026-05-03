"""News ingest service tests."""

from __future__ import annotations

from datetime import date as _date

from api.schemas.content_studio import (
    ContentFormat,
    TopicCandidate,
    TopicSource,
    TopicStatus,
)
import asyncio

from pixelle_video.services.content_studio import DraftGenerator, NewsIngestService, TopicSelector


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


def test_reingest_preserves_progressed_topic_identity_and_status(storage):
    service = NewsIngestService(storage)
    [topic] = service.ingest(
        [
            TopicCandidate(
                title="Open Design",
                summary="First summary",
                why_it_matters="First why",
                source=TopicSource(source_type="obsidian", source_ref="2026-05-03-daily-project-ai-sync.md"),
                date="2026-05-03",
            )
        ]
    )
    TopicSelector(storage).select(topic.id)
    asyncio.run(DraftGenerator(storage).generate(topic.id))
    DraftGenerator(storage).approve(topic.id, approved=True)

    [reingested] = service.ingest(
        [
            TopicCandidate(
                title="Open Design",
                summary="Updated summary",
                why_it_matters="Updated why",
                source=TopicSource(source_type="obsidian", source_ref="2026-05-03-daily-project-ai-sync.md"),
                date="2026-05-03",
            )
        ],
        replace_for_date=True,
    )

    assert reingested.id == topic.id
    assert reingested.status == TopicStatus.DRAFT_APPROVED
    assert reingested.summary == "Updated summary"
    assert storage.get_drafts(topic.id).approved_for_video is True


def test_reingest_drops_stale_candidates_but_keeps_active_work(storage):
    service = NewsIngestService(storage)
    [active] = service.ingest(
        [
            TopicCandidate(
                title="Keep Me",
                source=TopicSource(source_type="obsidian", source_ref="note.md"),
                date="2026-05-03",
            )
        ]
    )
    TopicSelector(storage).select(active.id)

    service.ingest(
        [
            TopicCandidate(
                title="Old Candidate",
                source=TopicSource(source_type="obsidian", source_ref="note.md"),
                date="2026-05-03",
            )
        ]
    )

    rows = service.ingest(
        [
            TopicCandidate(
                title="Keep Me",
                source=TopicSource(source_type="obsidian", source_ref="note.md"),
                date="2026-05-03",
            ),
            TopicCandidate(
                title="Fresh Candidate",
                source=TopicSource(source_type="obsidian", source_ref="note.md"),
                date="2026-05-03",
            ),
        ],
        replace_for_date=True,
    )

    assert {t.title for t in rows} == {"Keep Me", "Fresh Candidate"}
    saved = storage.list_topics(date="2026-05-03")
    assert {t.title for t in saved} == {"Keep Me", "Fresh Candidate"}
    keep = next(t for t in saved if t.title == "Keep Me")
    assert keep.id == active.id
    assert keep.status == TopicStatus.SELECTED
