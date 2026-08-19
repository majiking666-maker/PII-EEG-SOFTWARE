"""
Tests for core/confirm.py. Run with:
    python3 tests/test_confirm.py
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from core.user_profile import UserProfile, InputMode
from core.command_policy import CommandPolicy
from core.events import BrainEvent, EventType


def make_eeg_profile():
    return UserProfile(mode=InputMode.EEG_COMMANDS, best_pair_label="UP_vs_RIGHT", best_pair_accuracy=0.75, reason="ok")


def make_fallback_profile():
    return UserProfile(mode=InputMode.SSVEP_FALLBACK, best_pair_label="UP_vs_LEFT", best_pair_accuracy=0.55, reason="below threshold")


def test_eeg_commands_mode_accepts_on_yes():
    profile = make_eeg_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile)

    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.9, label="YES")
    outcome = resolve_confirm(session, event, policy)

    assert outcome == ConfirmOutcome.ACCEPTED
    print("PASS: EEG_COMMANDS mode correctly accepts on a high-confidence YES command")


def test_eeg_commands_mode_cancels_on_no():
    profile = make_eeg_profile()
    policy = CommandPolicy()
    session = start_confirm("DELETE button", profile)

    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.9, label="NO")
    outcome = resolve_confirm(session, event, policy)

    assert outcome == ConfirmOutcome.CANCELLED
    print("PASS: EEG_COMMANDS mode correctly cancels on a high-confidence NO command")


def test_ssvep_fallback_mode_accepts_on_yes_target():
    profile = make_fallback_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile)

    event = BrainEvent(event_type=EventType.SSVEP_TARGET, confidence=0.85, target_id="yes_target")
    outcome = resolve_confirm(session, event, policy)

    assert outcome == ConfirmOutcome.ACCEPTED
    print("PASS: SSVEP_FALLBACK mode correctly accepts via the yes_target SSVEP target")


def test_ssvep_fallback_mode_cancels_on_no_target():
    profile = make_fallback_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile)

    event = BrainEvent(event_type=EventType.SSVEP_TARGET, confidence=0.85, target_id="no_target")
    outcome = resolve_confirm(session, event, policy)

    assert outcome == ConfirmOutcome.CANCELLED
    print("PASS: SSVEP_FALLBACK mode correctly cancels via the no_target SSVEP target")


def test_low_confidence_event_does_not_resolve_confirm():
    """The confirm-before-commit safeguard should still apply INSIDE a confirm flow."""
    profile = make_eeg_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile)

    weak_event = BrainEvent(event_type=EventType.COMMAND, confidence=0.3, label="YES")
    outcome = resolve_confirm(session, weak_event, policy)

    assert outcome == ConfirmOutcome.PENDING
    print("PASS: low-confidence event during confirm correctly stays PENDING, doesn't false-accept")


def test_timeout_resolves_to_timed_out():
    profile = make_eeg_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile, timeout_seconds=0.05)

    time.sleep(0.1)  # let it expire

    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.9, label="YES")
    outcome = resolve_confirm(session, event, policy)

    assert outcome == ConfirmOutcome.TIMED_OUT
    print("PASS: expired confirm session correctly times out, even with a strong incoming event")


def test_wrong_mode_event_does_not_resolve():
    """An SSVEP event arriving during an EEG_COMMANDS confirm shouldn't accidentally resolve it."""
    profile = make_eeg_profile()
    policy = CommandPolicy()
    session = start_confirm("SEND button", profile)

    mismatched_event = BrainEvent(event_type=EventType.SSVEP_TARGET, confidence=0.9, target_id="yes_target")
    outcome = resolve_confirm(session, mismatched_event, policy)

    assert outcome == ConfirmOutcome.PENDING
    print("PASS: mismatched event type for the session's mode correctly stays PENDING")


if __name__ == "__main__":
    test_eeg_commands_mode_accepts_on_yes()
    test_eeg_commands_mode_cancels_on_no()
    test_ssvep_fallback_mode_accepts_on_yes_target()
    test_ssvep_fallback_mode_cancels_on_no_target()
    test_low_confidence_event_does_not_resolve_confirm()
    test_timeout_resolves_to_timed_out()
    test_wrong_mode_event_does_not_resolve()
    print("\nAll confirm contract tests passed.")
