# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Pixelle-Video Web UI - Main Entry Point

This is the entry point for the Streamlit multi-page application.
Uses st.navigation to define pages and set the default page to Home.
"""

import sys
from pathlib import Path

# Add project root to sys.path for module imports
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import streamlit as st

# Setup page config (must be first Streamlit command)
st.set_page_config(
    page_title="Pixelle-Video - AI Video Generator",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def main():
    """Main entry point with navigation"""
    # Existing Pixelle-Video pages (kept untouched)
    home_page = st.Page(
        "pages/1_🎬_Home.py",
        title="Home",
        icon="🎬",
        default=True
    )

    history_page = st.Page(
        "pages/2_📚_History.py",
        title="History",
        icon="📚"
    )

    # Content Studio pages (orchestration layer on top of Pixelle-Video).
    # These are independent of LazyOffice and live alongside the existing
    # video pages.
    topics_page = st.Page(
        "pages/3_📰_Topics.py",
        title="Topics",
        icon="📰",
    )
    studio_page = st.Page(
        "pages/4_✍️_Content_Studio.py",
        title="Content Studio",
        icon="✍️",
    )
    video_lab_page = st.Page(
        "pages/5_🎞️_Video_Lab.py",
        title="Video Lab",
        icon="🎞️",
    )
    assets_page = st.Page(
        "pages/6_📦_Assets.py",
        title="Assets",
        icon="📦",
    )

    pg = st.navigation(
        {
            "Pixelle-Video": [home_page, history_page],
            "Content Studio": [topics_page, studio_page, video_lab_page, assets_page],
        }
    )
    pg.run()


if __name__ == "__main__":
    main()
