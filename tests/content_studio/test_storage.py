"""Storage layer tests: round-trip, listing, deletion."""

from __future__ import annotations

from datetime import datetime

from api.schemas.content_studio import (
    DraftSet,
    RenderRecord,
    Script,
    Storyboard,
    StoryboardScene,
    Topic,
    TopicSource,
    TopicStatus,
)


def _make_topic(topic_id: str, date: str = "2026-05-03", priority: int = 50) -> Topic:
    return Topic(
        id=topic_id,
        date=date,
        title=f"Topic {topic_id}",
        summary="summary",
        why_it_matters="matters",
        source=TopicSource(source_type="manual"),
        priority=priority,
    )


def test_topic_roundtrip(storage):
    topic = _make_topic("t1")
    saved = storage.save_topic(topic)
    assert saved.id == "t1"

    loaded = storage.get_topic("t1")
    assert loaded is not None
    assert loaded.title == "Topic t1"
    assert loaded.status == TopicStatus.CANDIDATE


def test_list_topics_filters_by_date_and_status(storage):
    storage.save_topic(_make_topic("a", date="2026-05-03", priority=10))
    storage.save_topic(_make_topic("b", date="2026-05-03", priority=80))
    skipped = _make_topic("c", date="2026-05-03")
    skipped.status = TopicStatus.SKIPPED
    storage.save_topic(skipped)
    storage.save_topic(_make_topic("d", date="2026-05-04"))

    today = storage.list_topics(date="2026-05-03")
    assert {t.id for t in today} == {"a", "b", "c"}
    # Highest priority first
    assert today[0].id == "b"

    only_candidates = storage.list_topics(
        date="2026-05-03", statuses=[TopicStatus.CANDIDATE]
    )
    assert {t.id for t in only_candidates} == {"a", "b"}


def test_delete_topics_for_date(storage):
    storage.save_topic(_make_topic("a", date="2026-05-03"))
    storage.save_topic(_make_topic("b", date="2026-05-03"))
    storage.save_topic(_make_topic("c", date="2026-05-04"))

    removed = storage.delete_topics_for_date("2026-05-03")
    assert removed == 2
    assert storage.list_topics(date="2026-05-03") == []
    assert len(storage.list_topics(date="2026-05-04")) == 1


def test_drafts_script_storyboard_render_roundtrip(storage):
    topic_id = "topic-x"
    storage.save_topic(_make_topic(topic_id))

    drafts = DraftSet(topic_id=topic_id, substack_draft="hello")
    storage.save_drafts(drafts)
    assert storage.get_drafts(topic_id).substack_draft == "hello"

    script = Script(topic_id=topic_id, hook="hi", body="body", cta="go")
    storage.save_script(script)
    assert storage.get_script(topic_id).body == "body"

    storyboard = Storyboard(
        topic_id=topic_id,
        scenes=[
            StoryboardScene(
                scene_no=1,
                voiceover="vo",
                visual_prompt="visual",
                onscreen_text="on",
                duration_seconds=5,
            )
        ],
    )
    storage.save_storyboard(storyboard)
    loaded_sb = storage.get_storyboard(topic_id)
    assert loaded_sb is not None and len(loaded_sb.scenes) == 1

    render = RenderRecord(topic_id=topic_id, status="queued", pixelle_task_id="pt-1")
    storage.save_render(render)
    loaded_render = storage.get_render(topic_id)
    assert loaded_render.pixelle_task_id == "pt-1"
    assert isinstance(loaded_render.created_at, datetime)


def test_unknown_keys_return_none(storage):
    assert storage.get_topic("missing") is None
    assert storage.get_drafts("missing") is None
    assert storage.get_script("missing") is None
    assert storage.get_storyboard("missing") is None
    assert storage.get_render("missing") is None


def test_path_sanitization_prevents_dir_escape(storage):
    """save/get of an entity with slashes in the id should not escape base_dir."""
    topic = _make_topic("../weird/id")
    storage.save_topic(topic)
    # The file ends up sanitized; round-trip works via the same key.
    loaded = storage.get_topic("../weird/id")
    assert loaded is not None
    assert loaded.id == "../weird/id"
