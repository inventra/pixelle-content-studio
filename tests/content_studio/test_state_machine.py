"""Topic state machine tests."""

import pytest

from api.schemas.content_studio import TopicStatus
from pixelle_video.services.content_studio.state_machine import (
    InvalidStateTransition,
    TopicStateMachine,
)


def test_legal_forward_path():
    sm = TopicStateMachine
    chain = [
        TopicStatus.CANDIDATE,
        TopicStatus.SELECTED,
        TopicStatus.DRAFTED,
        TopicStatus.DRAFT_APPROVED,
        TopicStatus.SCRIPT_READY,
        TopicStatus.STORYBOARD_READY,
        TopicStatus.RENDER_QUEUED,
        TopicStatus.RENDER_RUNNING,
        TopicStatus.RENDER_COMPLETED,
        TopicStatus.ARCHIVED,
    ]
    for src, dst in zip(chain, chain[1:]):
        sm.assert_transition(src, dst)


def test_cannot_skip_draft_approval():
    with pytest.raises(InvalidStateTransition):
        TopicStateMachine.assert_transition(
            TopicStatus.DRAFTED, TopicStatus.SCRIPT_READY
        )


def test_cannot_render_without_storyboard():
    assert not TopicStateMachine.can_submit_render(TopicStatus.DRAFT_APPROVED)
    assert not TopicStateMachine.can_submit_render(TopicStatus.SCRIPT_READY)
    assert TopicStateMachine.can_submit_render(TopicStatus.STORYBOARD_READY)
    assert TopicStateMachine.can_submit_render(TopicStatus.RENDER_FAILED)


def test_cannot_generate_script_before_approval():
    assert not TopicStateMachine.can_generate_script(TopicStatus.DRAFTED)
    assert TopicStateMachine.can_generate_script(TopicStatus.DRAFT_APPROVED)


def test_archived_is_terminal():
    for status in TopicStatus:
        if status == TopicStatus.ARCHIVED:
            continue
        # Can transition to ARCHIVED from many states; that's fine.
        TopicStateMachine.can_transition(status, TopicStatus.ARCHIVED)
    # Nothing leaves ARCHIVED
    for status in TopicStatus:
        if status == TopicStatus.ARCHIVED:
            continue
        assert not TopicStateMachine.can_transition(TopicStatus.ARCHIVED, status)
