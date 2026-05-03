# Copyright (C) 2025 Pixelle Content Studio
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Topics page - daily candidate review and selection."""

import sys
from datetime import date as _date
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from api.schemas.content_studio import (
    ContentFormat,
    TopicCandidate,
    TopicSource,
    TopicStatus,
)
from pixelle_video.services.content_studio import (
    DailyNoteNotFound,
    NewsIngestService,
    TopicSelector,
    daily_note_path,
    get_storage,
)

st.set_page_config(
    page_title="Topics - Pixelle Content Studio",
    page_icon="📰",
    layout="wide",
)


def _format_status(status: TopicStatus) -> str:
    icon = {
        TopicStatus.CANDIDATE: "🟡",
        TopicStatus.SELECTED: "🟢",
        TopicStatus.SKIPPED: "⚪",
        TopicStatus.DRAFTED: "📝",
        TopicStatus.DRAFT_APPROVED: "✅",
        TopicStatus.SCRIPT_READY: "🎬",
        TopicStatus.STORYBOARD_READY: "🎞️",
        TopicStatus.RENDER_QUEUED: "⏳",
        TopicStatus.RENDER_RUNNING: "🔄",
        TopicStatus.RENDER_COMPLETED: "🏁",
        TopicStatus.RENDER_FAILED: "❌",
        TopicStatus.ARCHIVED: "📦",
    }.get(status, "•")
    return f"{icon} {status.value}"


def _ingest_form(storage):
    with st.expander("➕ Ingest a topic candidate", expanded=False):
        with st.form("ingest_topic"):
            title = st.text_input("Title")
            summary = st.text_area("Summary", height=80)
            why = st.text_area("Why it matters", height=80)
            col1, col2 = st.columns(2)
            with col1:
                priority = st.slider("Priority", 0, 100, 60)
                source_type = st.selectbox(
                    "Source", ["manual", "hermes", "obsidian", "webhook"]
                )
            with col2:
                source_url = st.text_input("Source URL (optional)")
                target_date = st.date_input("Date", value=_date.today())
            formats = st.multiselect(
                "Recommended formats",
                options=[f.value for f in ContentFormat],
                default=[ContentFormat.SUBSTACK.value, ContentFormat.FACEBOOK.value],
            )
            submitted = st.form_submit_button("Ingest")
            if submitted:
                if not title.strip():
                    st.error("Title is required")
                else:
                    candidate = TopicCandidate(
                        title=title,
                        summary=summary,
                        why_it_matters=why,
                        source=TopicSource(
                            source_type=source_type,
                            source_url=source_url or None,
                        ),
                        recommended_formats=[ContentFormat(f) for f in formats],
                        priority=priority,
                        date=target_date.isoformat(),
                    )
                    NewsIngestService(storage).ingest([candidate])
                    st.success(f"Ingested: {title}")
                    st.rerun()


def _daily_note_button(storage, target_iso: str):
    """One-click ingest from the user's Obsidian daily briefing."""
    note_path = daily_note_path(target_iso)
    cols = st.columns([1, 3])
    with cols[0]:
        if st.button("📥 Ingest daily note", help=str(note_path)):
            ingest = NewsIngestService(storage)
            try:
                topics = ingest.ingest_from_daily_note(
                    target_date=target_iso,
                    replace_for_date=True,
                )
            except DailyNoteNotFound:
                st.error(f"Daily note not found: {note_path}")
                return
            if not topics:
                st.warning("Daily note found but no AI-news items were detected.")
            else:
                st.success(f"Ingested {len(topics)} topics from {note_path.name}")
                st.rerun()
    with cols[1]:
        exists = note_path.exists()
        marker = "✅" if exists else "⚠️"
        st.caption(f"{marker} `{note_path}`")


def main():
    st.title("📰 Today's Topics")
    st.caption("Daily AI news → topic candidates → selection. Approval gate happens later in Content Studio.")

    storage = get_storage()
    selector = TopicSelector(storage)

    target_date = st.date_input("Date", value=_date.today())
    target_iso = target_date.isoformat()

    _daily_note_button(storage, target_iso)
    _ingest_form(storage)

    topics = storage.list_topics(date=target_iso)
    if not topics:
        st.info("No candidates for this date. Ingest some via the form above or POST to /api/topics/ingest.")
        return

    for topic in topics:
        with st.container(border=True):
            top_col, action_col = st.columns([4, 1])
            with top_col:
                st.markdown(f"### {topic.title}")
                st.markdown(f"_{_format_status(topic.status)} · priority {topic.priority} · {topic.source.source_type}_")
                if topic.summary:
                    st.write(topic.summary)
                if topic.why_it_matters:
                    st.markdown(f"**Why it matters:** {topic.why_it_matters}")
                if topic.recommended_formats:
                    st.caption(
                        "Recommended: "
                        + ", ".join(f.value for f in topic.recommended_formats)
                    )
                st.code(f"topic_id = {topic.id}", language="text")
            with action_col:
                if topic.status == TopicStatus.CANDIDATE:
                    if st.button("Select", key=f"select-{topic.id}"):
                        selector.select(topic.id)
                        st.rerun()
                    if st.button("Skip", key=f"skip-{topic.id}"):
                        selector.skip(topic.id)
                        st.rerun()
                else:
                    st.write(f"Status: **{topic.status.value}**")


if __name__ == "__main__":
    main()
