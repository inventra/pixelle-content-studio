# Copyright (C) 2025 Pixelle Content Studio
#
# Licensed under the Apache License, Version 2.0 (the "License").

"""Video Lab page - script + storyboard + render approval gate."""

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
from api.tasks import TaskType, task_manager
from pixelle_video.services.content_studio import (
    StoryboardGenerator,
    VideoBriefBuilder,
    get_storage,
)
from pixelle_video.services.content_studio.state_machine import InvalidStateTransition

st.set_page_config(
    page_title="Video Lab - Pixelle",
    page_icon="🎞️",
    layout="wide",
)


_VIDEO_READY_STATES = {
    TopicStatus.DRAFT_APPROVED,
    TopicStatus.SCRIPT_READY,
    TopicStatus.STORYBOARD_READY,
    TopicStatus.RENDER_QUEUED,
    TopicStatus.RENDER_RUNNING,
    TopicStatus.RENDER_COMPLETED,
    TopicStatus.RENDER_FAILED,
}


def _approved_topics(storage):
    return [t for t in storage.list_topics() if t.status in _VIDEO_READY_STATES]


def main():
    st.title("🎞️ Video Lab")
    st.caption("Approval gate — drafts must be approved. Then we generate the script, storyboard, and submit a render task.")

    storage = get_storage()
    sb_service = StoryboardGenerator(storage)
    builder = VideoBriefBuilder(storage)

    topics = _approved_topics(storage)
    if not topics:
        st.info("No drafts approved yet. Approve a draft in Content Studio first.")
        return

    options = {f"{t.title}  [{t.status.value}]": t.id for t in topics}
    label = st.selectbox("Topic", list(options.keys()))
    topic_id = options[label]
    topic = storage.get_topic(topic_id)

    drafts = storage.get_drafts(topic_id)
    if drafts is None or not drafts.approved_for_video:
        st.error("Drafts have not been approved for video. Re-approve in Content Studio.")
        return

    st.markdown("---")
    st.subheader("1. Script")

    col1, col2 = st.columns(2)
    with col1:
        duration = st.slider("Duration target (s)", 15, 90, 45)
        angle = st.text_input("Angle (optional)", value=topic.title)
    with col2:
        voice_style = st.selectbox(
            "Voice style", ["calm-narrator", "energetic", "documentary"]
        )
        regenerate = st.checkbox("Regenerate script", value=False)

    if st.button("Generate script"):
        try:
            asyncio.run(
                sb_service.generate_script(
                    topic_id,
                    duration_target=duration,
                    angle=angle or None,
                    voice_style=voice_style,
                    regenerate=regenerate,
                )
            )
            st.rerun()
        except InvalidStateTransition as e:
            st.error(str(e))

    script = storage.get_script(topic_id)
    if script:
        st.markdown(f"**Hook:** {script.hook}")
        st.text_area("Body", value=script.body, height=200, disabled=True)
        st.markdown(f"**CTA:** {script.cta}")

    st.markdown("---")
    st.subheader("2. Storyboard")

    n_scenes = st.slider("Scenes", 3, 10, 5)
    visual_style = st.text_input("Visual style", value="clean-editorial")
    if st.button("Generate storyboard"):
        try:
            asyncio.run(
                sb_service.generate_storyboard(
                    topic_id,
                    visual_style=visual_style,
                    n_scenes=n_scenes,
                    regenerate=True,
                )
            )
            st.rerun()
        except LookupError as e:
            st.error(str(e))

    storyboard = storage.get_storyboard(topic_id)
    if storyboard:
        st.caption(
            f"Estimated cost band: **{storyboard.estimated_cost_band}** · "
            f"{len(storyboard.scenes)} scenes"
        )
        for scene in storyboard.scenes:
            with st.container(border=True):
                st.markdown(f"**Scene {scene.scene_no}** — {scene.duration_seconds}s")
                st.write(f"_Voiceover_: {scene.voiceover}")
                st.write(f"_Visual prompt_: {scene.visual_prompt}")
                if scene.onscreen_text:
                    st.caption(f"On-screen: {scene.onscreen_text}")

    st.markdown("---")
    st.subheader("3. Render submission (cost gate)")

    if not storyboard:
        st.info("Generate a storyboard before submitting a render task.")
        return

    frame_template = st.text_input("Frame template", value="1080x1920/image_default.html")
    media_workflow = st.text_input("Media workflow (optional)", value="")
    tts_workflow = st.text_input("TTS workflow (optional)", value="")
    bgm_path = st.text_input("BGM path (optional)", value="")
    confirm = st.checkbox(
        f"I acknowledge the **{storyboard.estimated_cost_band}** cost band and want to render."
    )

    if st.button("🚀 Submit render task", type="primary"):
        if not confirm:
            st.error("Tick the cost-acknowledgement box first.")
        else:
            try:
                video_request = builder.build_request(
                    topic_id=topic_id,
                    frame_template=frame_template,
                    media_workflow=media_workflow or None,
                    tts_workflow=tts_workflow or None,
                    bgm_path=bgm_path or None,
                )
                task = task_manager.create_task(
                    task_type=TaskType.VIDEO_GENERATION,
                    request_params=video_request.model_dump(),
                )
                builder.build_render_record(
                    topic_id=topic_id,
                    request=video_request,
                    pixelle_task_id=task.task_id,
                    status="queued",
                )
                topic.status = TopicStatus.RENDER_QUEUED
                storage.save_topic(topic)
                st.success(f"Submitted. Pixelle task id: {task.task_id}")
            except InvalidStateTransition as e:
                st.error(str(e))


if __name__ == "__main__":
    main()
