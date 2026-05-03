"""Topic state machine for the Content Studio MVP.

The MVP brief explicitly enumerates every state a topic can be in, and
several transitions act as approval gates (most importantly:
``draft_approved`` is required before any video work). Centralizing the
allowed transitions here keeps every router/service consistent.
"""

from __future__ import annotations

from typing import Dict, Set

from api.schemas.content_studio import TopicStatus


class InvalidStateTransition(ValueError):
    """Raised when a caller tries to push a topic into an illegal state."""


# Forward + retry edges. We keep things permissive enough for re-runs:
# regenerating drafts from `draft_approved` should still work.
_TRANSITIONS: Dict[TopicStatus, Set[TopicStatus]] = {
    TopicStatus.CANDIDATE: {
        TopicStatus.SELECTED,
        TopicStatus.SKIPPED,
    },
    TopicStatus.SELECTED: {
        # Once a topic is selected the operator has committed to drafting
        # it. Backing out at this point should go via ARCHIVED, not SKIP
        # (skip is reserved for the initial triage decision).
        TopicStatus.DRAFTED,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.DRAFTED: {
        TopicStatus.DRAFTED,
        TopicStatus.DRAFT_APPROVED,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.DRAFT_APPROVED: {
        TopicStatus.DRAFTED,
        TopicStatus.SCRIPT_READY,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.SCRIPT_READY: {
        TopicStatus.SCRIPT_READY,
        TopicStatus.STORYBOARD_READY,
        TopicStatus.DRAFT_APPROVED,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.STORYBOARD_READY: {
        TopicStatus.STORYBOARD_READY,
        TopicStatus.RENDER_QUEUED,
        TopicStatus.SCRIPT_READY,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.RENDER_QUEUED: {
        TopicStatus.RENDER_RUNNING,
        TopicStatus.RENDER_COMPLETED,
        TopicStatus.RENDER_FAILED,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.RENDER_RUNNING: {
        TopicStatus.RENDER_COMPLETED,
        TopicStatus.RENDER_FAILED,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.RENDER_COMPLETED: {
        TopicStatus.ARCHIVED,
    },
    TopicStatus.RENDER_FAILED: {
        TopicStatus.RENDER_QUEUED,
        TopicStatus.STORYBOARD_READY,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.SKIPPED: {
        TopicStatus.CANDIDATE,
        TopicStatus.ARCHIVED,
    },
    TopicStatus.ARCHIVED: set(),
}


# States that have effectively "passed" the draft-approval gate. Render
# submission is allowed only from one of these.
_RENDER_READY_STATES = {
    TopicStatus.STORYBOARD_READY,
    TopicStatus.RENDER_FAILED,
}


# States that allow short-video script generation. Drafts must have been
# approved before any script work happens.
_SCRIPT_ALLOWED_STATES = {
    TopicStatus.DRAFT_APPROVED,
    TopicStatus.SCRIPT_READY,
    TopicStatus.STORYBOARD_READY,
}


class TopicStateMachine:
    """Tiny state-machine helper.

    Kept stateless on purpose so it can be shared between routers, services
    and tests without lifecycle concerns.
    """

    @staticmethod
    def can_transition(source: TopicStatus, target: TopicStatus) -> bool:
        if source == target:
            return True
        return target in _TRANSITIONS.get(source, set())

    @staticmethod
    def assert_transition(source: TopicStatus, target: TopicStatus) -> None:
        if not TopicStateMachine.can_transition(source, target):
            raise InvalidStateTransition(
                f"Illegal topic transition: {source.value} -> {target.value}"
            )

    @staticmethod
    def can_generate_script(status: TopicStatus) -> bool:
        return status in _SCRIPT_ALLOWED_STATES

    @staticmethod
    def can_submit_render(status: TopicStatus) -> bool:
        return status in _RENDER_READY_STATES
