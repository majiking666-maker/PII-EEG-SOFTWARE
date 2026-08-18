"""
Calibration / onboarding flow.

Implements the guided enrollment session design locked in project discussion:
- Short session (target: 20-40 trials/class per pair, matching our
  experimental budget range - see docs/design_decisions.md).
- Per-pair "test both, keep winner" policy: after collecting calibration
  data, compare zero-shot vs calibrated performance on a held-back check
  set, and use whichever actually performs better for that specific pair.
  This was a real finding from our own experiments (Note 05) - calibration
  helps some pairs and hurts others for the same person, so it must be
  verified per pair, never assumed.

This module is hardware-agnostic: it consumes a "trial provider" (either
the FakeBrain simulator now, or a real decoder later) via a small interface,
so the actual enrollment logic doesn't change when hardware arrives.
"""

from dataclasses import dataclass, field
from enum import Enum
from core.events import BrainEvent, EventType


class CalibrationChoice(Enum):
    ZERO_SHOT = "zero_shot"    # Base model performed as well or better - no calibration needed
    CALIBRATED = "calibrated"  # Calibration measurably improved this pair for this user


@dataclass
class PairCalibrationResult:
    pair_label: str  # e.g. "UP_vs_DOWN"
    zero_shot_accuracy: float
    calibrated_accuracy: float
    choice: CalibrationChoice
    trials_collected: int


@dataclass
class CalibrationSession:
    """Accumulates results across all command pairs tested during onboarding."""
    results: list[PairCalibrationResult] = field(default_factory=list)

    def best_pair(self) -> PairCalibrationResult | None:
        """
        Returns the pair with the highest achieved accuracy (whichever of
        zero-shot/calibrated won for that pair) - this becomes the
        recommended default command pair for this user's pre-release
        2-command vocabulary.
        """
        if not self.results:
            return None
        return max(self.results, key=lambda r: max(r.zero_shot_accuracy, r.calibrated_accuracy))

    def summary(self) -> str:
        lines = ["Calibration session summary:"]
        for r in self.results:
            final_acc = max(r.zero_shot_accuracy, r.calibrated_accuracy)
            lines.append(
                f"  {r.pair_label}: zero-shot={r.zero_shot_accuracy:.1%}, "
                f"calibrated={r.calibrated_accuracy:.1%} -> "
                f"using {r.choice.value} ({final_acc:.1%})"
            )
        best = self.best_pair()
        if best:
            lines.append(f"\nRecommended pair for this user: {best.pair_label}")
        return "\n".join(lines)


class TrialProvider:
    """
    Minimal interface any input source (simulator or real decoder) must
    satisfy to be used during calibration. Real hardware integration means
    writing one class satisfying this interface - nothing else in this
    module needs to change.
    """

    def attempt(self, intended_label: str, possible_labels: list[str]) -> BrainEvent:
        raise NotImplementedError


class FakeBrainTrialProvider(TrialProvider):
    """Adapts simulator.fake_brain.FakeBrain to the TrialProvider interface."""

    def __init__(self, fake_brain):
        self.fake_brain = fake_brain

    def attempt(self, intended_label: str, possible_labels: list[str]) -> BrainEvent:
        return self.fake_brain.next_command_attempt(intended_label, possible_labels)


def run_pair_calibration(
    provider: TrialProvider,
    pair_label: str,
    labels: list[str],
    trials_per_class: int = 30,
    check_trials_per_class: int = 10,
) -> PairCalibrationResult:
    """
    Simulates one full calibration round for a single command pair:
    1. Collect `trials_per_class` enrollment attempts per label (the user
       is prompted to think each command repeatedly).
    2. Evaluate "zero-shot" style accuracy using a held-back check set
       BEFORE calibration is applied.
    3. Evaluate "calibrated" accuracy on the same check set AFTER
       calibration (in this simulated version, calibration effect is
       modeled by the provider itself - a real implementation would
       actually fine-tune a model between steps 2 and 3).
    4. Pick whichever performed better, per our locked "test both, keep
       winner" policy.

    Note: this simulates the *outcome* of calibration for software-flow
    testing purposes. It does not perform real model fine-tuning - that
    logic belongs in the eventual ML pipeline, not the UX/flow layer.
    """
    enrollment_correct = 0
    enrollment_total = trials_per_class * len(labels)

    for label in labels:
        for _ in range(trials_per_class):
            event = provider.attempt(label, labels)
            if event.event_type == EventType.COMMAND and event.label == label:
                enrollment_correct += 1

    # Zero-shot check: measure accuracy fresh, independent of enrollment data
    zero_shot_correct = 0
    zero_shot_total = check_trials_per_class * len(labels)
    for label in labels:
        for _ in range(check_trials_per_class):
            event = provider.attempt(label, labels)
            if event.event_type == EventType.COMMAND and event.label == label:
                zero_shot_correct += 1
    zero_shot_accuracy = zero_shot_correct / zero_shot_total if zero_shot_total else 0.0

    # "Calibrated" check: in this simulated flow, we use the enrollment-phase
    # accuracy as a proxy for post-calibration performance on this pair.
    # This is intentionally simple for now - it exercises the FLOW LOGIC
    # (compare two numbers, pick the winner) which is what this module is
    # responsible for. Real accuracy modeling belongs in the ML layer.
    calibrated_accuracy = enrollment_correct / enrollment_total if enrollment_total else 0.0

    choice = CalibrationChoice.CALIBRATED if calibrated_accuracy > zero_shot_accuracy else CalibrationChoice.ZERO_SHOT

    return PairCalibrationResult(
        pair_label=pair_label,
        zero_shot_accuracy=zero_shot_accuracy,
        calibrated_accuracy=calibrated_accuracy,
        choice=choice,
        trials_collected=enrollment_total,
    )


def run_full_onboarding(
    provider: TrialProvider,
    pairs: dict[str, list[str]],
    trials_per_class: int = 30,
    check_trials_per_class: int = 10,
) -> CalibrationSession:
    """
    Runs calibration across multiple command pairs (e.g. UP_vs_DOWN,
    UP_vs_RIGHT) and returns a full session summary, including which pair
    is recommended as the user's default 2-command vocabulary.

    `pairs` example: {"UP_vs_DOWN": ["UP", "DOWN"], "UP_vs_RIGHT": ["UP", "RIGHT"]}
    """
    session = CalibrationSession()
    for pair_label, labels in pairs.items():
        result = run_pair_calibration(
            provider, pair_label, labels, trials_per_class, check_trials_per_class
        )
        session.results.append(result)
    return session
