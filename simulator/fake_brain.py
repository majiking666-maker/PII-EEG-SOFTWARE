"""
Simulated input source ("fake brain") for developing PII's software without
real EEG/SSVEP hardware.

Design intent (locked in project discussion, 2026-08-17):
- Must behave like a real, imperfect decoder - not a flawless test harness.
- Supports deliberate wrong answers and "no clear signal" states so that
  downstream safeguards (confirm-before-commit, idle handling) are actually
  exercised during development, not just the happy path.
- Two modes: scripted (for deterministic tests) and interactive (for manual
  dev-panel style testing, e.g. via keyboard).

When real hardware exists, only this module gets replaced. Everything that
consumes BrainEvent objects (calibration, command policy, UI) should not
need to change at all.
"""

import random
from core.events import BrainEvent, EventType


class FakeBrain:
    """
    A stand-in input source. Call `next_event()` to get the next simulated
    BrainEvent, the same way real code will poll a real decoder.
    """

    def __init__(self, accuracy: float = 0.70, idle_rate: float = 0.15, seed: int | None = None):
        """
        accuracy: probability that a COMMAND/SSVEP event, when it does fire,
                  reflects the "correct" intended label rather than a wrong one.
                  0.70 matches our real-data evidence range (65-75%) for a
                  calibrated single best-pair 2-command system - see project notes.
        idle_rate: probability that any given poll produces IDLE instead of
                   a command/target attempt at all (mirrors real gaps where
                   the user isn't issuing input, or signal quality is too poor).
        seed: optional, for reproducible test runs.
        """
        self.accuracy = accuracy
        self.idle_rate = idle_rate
        self._rng = random.Random(seed)
        self._scripted_queue: list[BrainEvent] = []

    def queue_scripted_events(self, events: list[BrainEvent]) -> None:
        """
        For deterministic tests: pre-load exact events to be returned in
        order before falling back to random simulation. Lets tests assert
        exact behavior (e.g. "given event X, does the UI show a confirm
        prompt?") without relying on randomness.
        """
        self._scripted_queue.extend(events)

    def next_command_attempt(self, intended_label: str, possible_labels: list[str]) -> BrainEvent:
        """
        Simulate one decode attempt where the user is *intending* to trigger
        `intended_label` (e.g. "UP"). Returns a BrainEvent that is correct
        with probability `self.accuracy`, otherwise a wrong label from
        `possible_labels`, or IDLE/LOW_CONFIDENCE some of the time.

        This is the primary method dev/test code should call when simulating
        "the user is trying to do X" - it mirrors how a real decoder can
        fail even when the user's intent is clear.
        """
        if self._scripted_queue:
            return self._scripted_queue.pop(0)

        if self._rng.random() < self.idle_rate:
            return BrainEvent(event_type=EventType.IDLE, confidence=0.0)

        correct = self._rng.random() < self.accuracy
        label = intended_label if correct else self._rng.choice(
            [l for l in possible_labels if l != intended_label] or possible_labels
        )

        # Confidence isn't just 1.0/0.0 - simulate a realistic spread.
        # Correct decodes tend to have somewhat higher confidence on average,
        # but not always - this is intentional, real decoders aren't perfectly
        # calibrated either.
        if correct:
            confidence = self._rng.uniform(0.55, 0.95)
        else:
            confidence = self._rng.uniform(0.35, 0.85)

        if confidence < 0.5:
            return BrainEvent(event_type=EventType.LOW_CONFIDENCE, confidence=confidence, label=label)

        return BrainEvent(event_type=EventType.COMMAND, confidence=confidence, label=label)

    def next_ssvep_attempt(self, intended_target: str, possible_targets: list[str]) -> BrainEvent:
        """
        Same idea as next_command_attempt, but for SSVEP target selection.
        Mirrors the ~1-2s detection cycle conceptually (caller is responsible
        for the actual timing/polling interval - this just returns one
        detection result per call).
        """
        if self._scripted_queue:
            return self._scripted_queue.pop(0)

        if self._rng.random() < self.idle_rate:
            return BrainEvent(event_type=EventType.IDLE, confidence=0.0)

        correct = self._rng.random() < self.accuracy
        target = intended_target if correct else self._rng.choice(
            [t for t in possible_targets if t != intended_target] or possible_targets
        )
        confidence = self._rng.uniform(0.55, 0.95) if correct else self._rng.uniform(0.35, 0.85)

        if confidence < 0.5:
            return BrainEvent(event_type=EventType.LOW_CONFIDENCE, confidence=confidence, target_id=target)

        return BrainEvent(event_type=EventType.SSVEP_TARGET, confidence=confidence, target_id=target)
