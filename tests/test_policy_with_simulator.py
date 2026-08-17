"""
Proves the simulator + command policy behave sensibly together before any
real hardware exists. Run with: python -m pytest tests/ -v
(or just: python tests/test_policy_with_simulator.py)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.fake_brain import FakeBrain
from core.command_policy import CommandPolicy, PolicyAction
from core.events import BrainEvent, EventType


def test_low_confidence_is_ignored():
    policy = CommandPolicy()
    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.3, label="UP")
    decision = policy.decide(event)
    assert decision.action == PolicyAction.IGNORE
    print("PASS: low-confidence event correctly ignored")


def test_idle_is_ignored():
    policy = CommandPolicy()
    event = BrainEvent(event_type=EventType.IDLE, confidence=0.0)
    decision = policy.decide(event)
    assert decision.action == PolicyAction.IGNORE
    print("PASS: idle event correctly ignored")


def test_midrange_confidence_requires_confirm():
    policy = CommandPolicy()
    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.7, label="UP")
    decision = policy.decide(event)
    assert decision.action == PolicyAction.SHOW_CONFIRM
    print("PASS: mid-confidence event correctly requires confirmation")


def test_very_high_confidence_auto_commits():
    policy = CommandPolicy()
    event = BrainEvent(event_type=EventType.COMMAND, confidence=0.9, label="UP")
    decision = policy.decide(event)
    assert decision.action == PolicyAction.AUTO_COMMIT
    print("PASS: very high-confidence event correctly auto-commits")


def test_simulator_produces_realistic_accuracy_over_many_trials():
    """
    Sanity check: over many simulated attempts at a realistic 0.70 accuracy,
    the simulator's actual correct rate should land close to that - proving
    the simulator itself is behaving as designed, not silently always
    returning the correct answer.
    """
    brain = FakeBrain(accuracy=0.70, idle_rate=0.0, seed=42)
    correct_count = 0
    total = 500
    for _ in range(total):
        event = brain.next_command_attempt("UP", ["UP", "DOWN"])
        if event.event_type == EventType.COMMAND and event.label == "UP":
            correct_count += 1

    observed_accuracy = correct_count / total
    print(f"Observed simulator accuracy over {total} trials: {observed_accuracy:.2f} (target 0.70)")
    assert 0.60 <= observed_accuracy <= 0.80, "Simulator accuracy drifted too far from configured target"
    print("PASS: simulator accuracy matches configured target within tolerance")


def test_confirm_safeguard_catches_wrong_decodes_in_practice():
    """
    The real point of the confirm-before-commit design: even when the
    simulator produces a WRONG label, it should still (usually) go through
    SHOW_CONFIRM rather than AUTO_COMMIT, because our confidence thresholds
    are set conservatively given the real accuracy ceiling. This proves the
    safeguard is actually doing its job, not just present in name.
    """
    brain = FakeBrain(accuracy=0.70, idle_rate=0.0, seed=7)
    policy = CommandPolicy()

    auto_committed_wrong = 0
    total_wrong = 0

    for _ in range(500):
        event = brain.next_command_attempt("UP", ["UP", "DOWN"])
        if event.event_type == EventType.COMMAND and event.label != "UP":
            total_wrong += 1
            decision = policy.decide(event)
            if decision.action == PolicyAction.AUTO_COMMIT:
                auto_committed_wrong += 1

    wrong_auto_commit_rate = auto_committed_wrong / total_wrong if total_wrong else 0
    print(f"Wrong decodes that were auto-committed without confirmation: "
          f"{auto_committed_wrong}/{total_wrong} ({wrong_auto_commit_rate:.1%})")
    assert wrong_auto_commit_rate < 0.15, "Too many wrong decodes are slipping through without confirmation"
    print("PASS: confirm safeguard catches the large majority of wrong decodes")


if __name__ == "__main__":
    test_low_confidence_is_ignored()
    test_idle_is_ignored()
    test_midrange_confidence_requires_confirm()
    test_very_high_confidence_auto_commits()
    test_simulator_produces_realistic_accuracy_over_many_trials()
    test_confirm_safeguard_catches_wrong_decodes_in_practice()
    print("\nAll tests passed.")
