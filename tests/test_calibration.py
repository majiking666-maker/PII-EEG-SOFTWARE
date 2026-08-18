"""
Tests for core/calibration.py. Run with:
    python3 tests/test_calibration.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.fake_brain import FakeBrain
from core.calibration import (
    FakeBrainTrialProvider,
    run_pair_calibration,
    run_full_onboarding,
    CalibrationChoice,
)


def test_single_pair_calibration_runs_and_produces_valid_result():
    brain = FakeBrain(accuracy=0.70, idle_rate=0.0, seed=1)
    provider = FakeBrainTrialProvider(brain)

    result = run_pair_calibration(provider, "UP_vs_DOWN", ["UP", "DOWN"], trials_per_class=30, check_trials_per_class=10)

    assert 0.0 <= result.zero_shot_accuracy <= 1.0
    assert 0.0 <= result.calibrated_accuracy <= 1.0
    assert result.trials_collected == 60  # 30 per class x 2 classes
    assert result.choice in (CalibrationChoice.ZERO_SHOT, CalibrationChoice.CALIBRATED)
    print(f"PASS: single pair calibration produced valid result "
          f"(zero-shot={result.zero_shot_accuracy:.1%}, calibrated={result.calibrated_accuracy:.1%}, "
          f"chose={result.choice.value})")


def test_full_onboarding_across_multiple_pairs():
    """
    Mirrors the real class_pair_scan finding: different pairs for the same
    simulated user can end up favoring different choices. We don't assert
    which specific choice wins (that's expected to vary run to run, exactly
    like real data did) - we assert the flow correctly handles multiple
    pairs and picks a sensible best overall pair.
    """
    brain = FakeBrain(accuracy=0.65, idle_rate=0.1, seed=99)
    provider = FakeBrainTrialProvider(brain)

    pairs = {
        "UP_vs_DOWN": ["UP", "DOWN"],
        "UP_vs_RIGHT": ["UP", "RIGHT"],
        "UP_vs_LEFT": ["UP", "LEFT"],
    }

    session = run_full_onboarding(provider, pairs, trials_per_class=20, check_trials_per_class=8)

    assert len(session.results) == 3
    best = session.best_pair()
    assert best is not None
    assert best.pair_label in pairs

    print(session.summary())
    print(f"PASS: full onboarding across {len(pairs)} pairs completed, "
          f"best pair correctly identified as {best.pair_label}")


def test_best_pair_is_actually_the_highest_accuracy_one():
    """Sanity check that best_pair() picks correctly, not just any result."""
    brain = FakeBrain(accuracy=0.70, idle_rate=0.0, seed=5)
    provider = FakeBrainTrialProvider(brain)

    pairs = {
        "PAIR_A": ["UP", "DOWN"],
        "PAIR_B": ["UP", "RIGHT"],
    }
    session = run_full_onboarding(provider, pairs, trials_per_class=25, check_trials_per_class=10)

    best = session.best_pair()
    best_score = max(best.zero_shot_accuracy, best.calibrated_accuracy)
    for r in session.results:
        other_score = max(r.zero_shot_accuracy, r.calibrated_accuracy)
        assert best_score >= other_score, "best_pair() did not return the actual highest-accuracy pair"

    print(f"PASS: best_pair() correctly identifies the highest-accuracy pair ({best.pair_label}, {best_score:.1%})")


if __name__ == "__main__":
    test_single_pair_calibration_runs_and_produces_valid_result()
    test_full_onboarding_across_multiple_pairs()
    test_best_pair_is_actually_the_highest_accuracy_one()
    print("\nAll calibration tests passed.")
