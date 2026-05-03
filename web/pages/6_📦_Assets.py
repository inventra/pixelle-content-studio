# Copyright (C) 2025 Pixelle Content Studio
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Assets / Render History page - per-topic content assets and render status."""

import sys
from pathlib import Path

# Add project root to sys.path
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

from api.schemas.content_studio import TopicStatus
from api.tasks import task_manager
from pixelle_video.services.content_studio import get_storage

st.set_page_config(
    page_title="Assets - Pixelle Content Studio",
    page_icon="📦",
    layout="wide",
)


_HISTORY_STATES = {
    TopicStatus.DRAFT_APPROVED,
    TopicStatus.SCRIPT_READY,
    TopicStatus.STORYBOARD_READY,
    TopicStatus.RENDER_QUEUED,
    TopicStatus.RENDER_RUNNING,
    TopicStatus.RENDER_COMPLETED,
    TopicStatus.RENDER_FAILED,
    TopicStatus.ARCHIVED,
}


def main():
    st.title("📦 Assets & Render History")
    st.caption("Per-topic view of drafts, scripts, storyboards, and Pixelle-Video render tasks.")

    storage = get_storage()
    topics = [t for t in storage.list_topics() if t.status in _HISTORY_STATES]

    if not topics:
        st.info("No assets yet — approve a draft and generate a storyboard first.")
        return

    options = {f"{t.title}  [{t.status.value}]": t.id for t in topics}
    label = st.selectbox("Topic", list(options.keys()))
    topic_id = options[label]
    topic = storage.get_topic(topic_id)

    drafts = storage.get_drafts(topic_id)
    script = storage.get_script(topic_id)
    storyboard = storage.get_storyboard(topic_id)
    render = storage.get_render(topic_id)

    tab_drafts, tab_script, tab_storyboard, tab_render = st.tabs(
        ["Drafts", "Script", "Storyboard", "Render"]
    )

    with tab_drafts:
        if drafts is None:
            st.info("No drafts.")
        else:
            st.caption(f"approved_for_video = **{drafts.approved_for_video}**")
            with st.expander("Substack draft", expanded=True):
                st.code(drafts.substack_draft or "(empty)", language="markdown")
            with st.expander("Facebook draft"):
                st.code(drafts.facebook_draft or "(empty)", language="markdown")
            with st.expander("LINE draft"):
                st.code(drafts.line_draft or "(empty)", language="markdown")
            if drafts.editor_notes:
                st.caption(f"Notes: {drafts.editor_notes}")

    with tab_script:
        if script is None:
            st.info("No script generated yet.")
        else:
            st.markdown(f"**Angle:** {script.angle}")
            st.markdown(f"**Duration target:** {script.duration_target}s")
            st.markdown(f"**Voice style:** {script.voice_style}")
            st.markdown("---")
            st.markdown(f"**Hook:** {script.hook}")
            st.text_area("Body", value=script.body, height=200, disabled=True, key=f"asset-body-{topic_id}")
            st.markdown(f"**CTA:** {script.cta}")

    with tab_storyboard:
        if storyboard is None:
            st.info("No storyboard generated yet.")
        else:
            st.caption(
                f"Visual style: **{storyboard.visual_style}** · "
                f"Cost band: **{storyboard.estimated_cost_band}** · "
                f"{len(storyboard.scenes)} scenes"
            )
            for scene in storyboard.scenes:
                with st.container(border=True):
                    st.markdown(f"**Scene {scene.scene_no}** — {scene.duration_seconds}s")
                    st.write(f"_Voiceover:_ {scene.voiceover}")
                    st.write(f"_Visual prompt:_ {scene.visual_prompt}")
                    if scene.onscreen_text:
                        st.caption(f"On-screen: {scene.onscreen_text}")

    with tab_render:
        if render is None:
            st.info("No render task submitted yet.")
        else:
            st.markdown(f"**Topic state:** {topic.status.value}")
            st.markdown(f"**Render local status:** {render.status}")
            st.markdown(f"**Estimated cost band:** {render.estimated_cost_band}")
            if render.pixelle_task_id:
                st.markdown(f"**Pixelle task id:** `{render.pixelle_task_id}`")
                live = task_manager.get_task(render.pixelle_task_id)
                if live:
                    st.markdown(f"**Live task status:** {live.status.value}")
                    if live.error:
                        st.error(live.error)
                    if live.result:
                        st.json(live.result)
                else:
                    st.caption("Task no longer in memory (server restart or cleanup).")
            if render.output_url:
                st.video(render.output_url)
            if render.error:
                st.error(render.error)
            with st.expander("Submitted parameters"):
                st.json(render.submit_params)


if __name__ == "__main__":
    main()
