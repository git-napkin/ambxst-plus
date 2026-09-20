"""Computer-use session input capture rules (pointer lock / Exclusive grab)."""

from __future__ import annotations

LOCKING_STATE = "agentDriving"
RELEASE_STATES = frozenset({"idle", "ending", "approvalWait", "grantedIdle", "userControl"})
RELEASE_EVENTS = frozenset({
    "esc_confirmed",
    "stop",
    "cancel",
    "error",
    "end",
    "complete_end",
    "lockscreen",
    "module_closed",
    "never_profile",
})


def should_lock_pointers(
    session_state,
    *,
    ending=False,
    user_has_control=False,
    intent="lock",
    epoch=0,
    callback_epoch=0,
):
    """True only while the agent is driving and this lock generation is still current.

    A devices-proc callback that finishes after unlock/exit must not re-disable mice.
    """
    if intent != "lock":
        return False
    if ending:
        return False
    if user_has_control:
        return False
    if epoch != callback_epoch:
        return False
    if session_state in RELEASE_STATES:
        return False
    return session_state == LOCKING_STATE


def should_release_cursor(event, session_state=None, *, ending=False):
    """Every CU exit path must release pointer lock + Exclusive keyboard."""
    if event in RELEASE_EVENTS:
        return True
    if ending:
        return True
    if session_state in RELEASE_STATES:
        return True
    return False


def hud_exclusive_keyboard(session_state, *, ending=False, injecting=False, handoff=False, user_has_control=False):
    """Exclusive layer-shell grab is incompatible with Hyprland client focus."""
    if ending or injecting or handoff or user_has_control:
        return False
    if session_state != LOCKING_STATE:
        return False
    return True
