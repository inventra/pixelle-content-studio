# Copyright (C) 2025 Pixelle Content Studio
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Content Studio page - generate, edit, approve drafts."""

import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from api.schemas.content_studio import TopicStatus
from pixelle_video.services.content_studio import (
    DraftGenerator,
    get_storage,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition

st.set_page_config(
    page_title="Content Studio - Pixelle",
    page_icon="✍️",
    layout="wide",
)


def _select_topic_widget(storage):
    selectable_states = {
        TopicStatus.SELECTED,
        TopicStatus.DRAFTED,
        TopicStatus.DRAFT_APPROVED,
        TopicStatus.SCRIPT_READY,
        TopicStatus.STORYBOARD_READY,
    }
    topics = [
        t for t in storage.list_topics() if t.status in selectable_states
    ]
    if not topics:
        st.info("No selected topics. Pick one on the Topics page first.")
        return None
    options = {f"{t.title}  [{t.status.value}]": t.id for t in topics}
    label = st.selectbox("Topic", list(options.keys()))
    return options[label]


def main():
    st.title("✍️ Content Studio")
    st.caption("Generate Substack / Facebook / LINE drafts, edit them, then approve for short video.")

    storage = get_storage()
    drafts_service = DraftGenerator(storage)

    topic_id = _select_topic_widget(storage)
    if topic_id is None:
        return
    topic = storage.get_topic(topic_id)

    col1, col2 = st.columns([1, 1])
    with col1:
        tone = st.selectbox(
            "Tone",
            ["informative", "casual", "hype", "analytical"],
        )
    with col2:
        regenerate = st.checkbox("Regenerate (overwrite existing)", value=False)

    if st.button("✨ Generate drafts", type="primary"):
        try:
            asyncio.run(drafts_service.generate(topic_id, tone=tone, regenerate=regenerate))
            st.rerun()
        except InvalidStateTransition as e:
            st.error(str(e))

    drafts = storage.get_drafts(topic_id)
    if drafts is None:
        st.info("No drafts yet — click Generate.")
        return

    st.divider()
    st.markdown(f"### Drafts for: {topic.title}")
    st.caption(f"Status: **{topic.status.value}** · approved_for_video=**{drafts.approved_for_video}**")

    substack_text = st.text_area(
        "Substack draft",
        value=drafts.substack_draft,
        height=240,
        key=f"substack-{topic_id}",
    )
    facebook_text = st.text_area(
        "Facebook draft",
        value=drafts.facebook_draft,
        height=160,
        key=f"facebook-{topic_id}",
    )
    line_text = st.text_area(
        "LINE draft",
        value=drafts.line_draft,
        height=120,
        key=f"line-{topic_id}",
    )
    notes = st.text_area(
        "Editor notes",
        value=drafts.editor_notes,
        height=80,
        key=f"notes-{topic_id}",
    )

    a, b, c = st.columns(3)
    with a:
        if st.button("💾 Save edits"):
            drafts_service.update(
                topic_id,
                substack_draft=substack_text,
                facebook_draft=facebook_text,
                line_draft=line_text,
                editor_notes=notes,
            )
            st.success("Saved")
    with b:
        if st.button("✅ Approve for video"):
            try:
                drafts_service.approve(topic_id, approved=True)
                st.success("Approved — head to the Video Lab page.")
                st.rerun()
            except InvalidStateTransition as e:
                st.error(str(e))
    with c:
        if drafts.approved_for_video and st.button("↩︎ Revoke approval"):
            drafts_service.approve(topic_id, approved=False)
            st.rerun()


if __name__ == "__main__":
    main()
