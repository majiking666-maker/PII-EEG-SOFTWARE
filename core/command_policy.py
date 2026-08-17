"""
Command policy: decides what actually happens in response to a BrainEvent.

This is where the "confirm-before-commit" safeguard lives, agreed on
2026-08-17 given our real-data accuracy ceiling (~65-75% for a calibrated
best-pair 2-command system - see docs/design_decisions.md). We do not let
a single decoded event instantly execute an action; we surface intent and
require a brief confirmation window, unless confidence is very high.

This module is intentionally decoupled from both the simulator and any
real decoder - it only consumes BrainEvent objects.
"""

from dataclasses import dataclass
from enum import Enum
from core.events import BrainEvent, EventType


class PolicyAction(Enum):
    IGNORE = "ignore"                    # Not confident enough to act on at all
    SHOW_CONFIRM = "show_confirm"        # Show the user what was detected, wait for confirm/cancel
    AUTO_COMMIT = "auto_commit"          # Confidence high enough to act immediately, no confirm needed


@dataclass
class PolicyDecision:
    action: PolicyAction
    event: BrainEvent


class CommandPolicy:
    """
    Tunable thresholds - these are product decisions, not fixed constants.
    Expect to revisit once real calibration data exists per user.
    """

    def __init__(
        self,
        ignore_below: float = 0.5,
        confirm_below: float = 0.85,
        confirm_window_seconds: float = 2.0,
    ):
        """
        ignore_below: events with confidence under this are treated as noise.
        confirm_below: events between ignore_below and this require a
                       confirm-before-commit step. Above this, auto-commit.
                       Set intentionally high (0.85) because our real accuracy
                       data (mean 65-75%) means we should rarely, if ever,
                       auto-commit in the pre-release version - this is a
                       safety-first default, not a claim that 85%+ confidence
                       events will be common.
        confirm_window_seconds: how long the confirm prompt stays live before
                                 auto-cancelling (prevents stale prompts).
        """
        self.ignore_below = ignore_below
        self.confirm_below = confirm_below
        self.confirm_window_seconds = confirm_window_seconds

    def decide(self, event: BrainEvent) -> PolicyDecision:
        if event.event_type in (EventType.IDLE, EventType.LOW_CONFIDENCE):
            return PolicyDecision(action=PolicyAction.IGNORE, event=event)

        if event.confidence < self.ignore_below:
            return PolicyDecision(action=PolicyAction.IGNORE, event=event)

        if event.confidence < self.confirm_below:
            return PolicyDecision(action=PolicyAction.SHOW_CONFIRM, event=event)

        return PolicyDecision(action=PolicyAction.AUTO_COMMIT, event=event)
