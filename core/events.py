"""
Core event types for PII's input pipeline.

Both the real EEG/SSVEP decoder (future) and the simulator (now) produce
these same event types. Everything downstream (calibration, command policy,
UI) only ever talks to these types - it never knows or cares whether the
event came from a real brain or a simulated one. This is the seam that lets
us build and test the whole software stack before real hardware exists.
"""

from dataclasses import dataclass, field
from enum import Enum
from time import time


class EventType(Enum):
    """What kind of input event this is."""
    COMMAND = "command"        # A discrete EEG-decoded command (e.g. UP, DOWN, YES, NO)
    SSVEP_TARGET = "ssvep"     # An SSVEP target was fixated on (e.g. a UI element, a scroll marker)
    IDLE = "idle"               # No clear signal / user not issuing any input right now
    LOW_CONFIDENCE = "low_confidence"  # A signal was detected but confidence was below threshold


@dataclass
class BrainEvent:
    """
    A single output from the input pipeline (real or simulated).

    confidence: 0.0-1.0. Real decoders will rarely be certain; the simulator
    should deliberately produce a realistic spread of confidence values,
    not just 1.0, so the confirm-before-commit UX logic actually gets
    exercised during development.

    target_id: for SSVEP events, which target/frequency was detected
               (e.g. "scroll_up_marker", "ui_grid_3"). None for COMMAND events.

    label: for COMMAND events, which command was decoded (e.g. "UP", "YES").
           None for SSVEP events.
    """
    event_type: EventType
    confidence: float
    label: str | None = None
    target_id: str | None = None
    timestamp: float = field(default_factory=time)

    def is_actionable(self, threshold: float = 0.6) -> bool:
        """
        Whether this event is confident enough to even show the user a
        confirm prompt. Below this, treat it the same as IDLE.
        This threshold is a tunable product decision, not a fixed constant -
        expect to revisit it once real accuracy data exists.
        """
        if self.event_type in (EventType.IDLE, EventType.LOW_CONFIDENCE):
            return False
        return self.confidence >= threshold
