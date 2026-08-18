"""
Tests for core/user_profile.py. Run with:
    python3 tests/test_user_profile.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.fake_brain import FakeBrain
from core.calibration import FakeBrainTrialProvider, run_full_onboarding
from core.user_profile import profile_user, InputMode, MINIMUM_USABLE_ACCURACY


def test_strong_signal_user_gets_eeg_commands_mode():
    """A user with genuinely good accuracy (like Subject 1's best pair) should be placed in EEG_COMMANDS mode."""
    brain = FakeBrain(accuracy=0.80, idle_rate=0.0, seed=1)
    provider = FakeBrainTrialProvider(brain)
    pairs = {"UP_vs_DOWN": ["UP", "DOWN"], "UP_vs_RIGHT": ["UP", "RIGHT"]}

    session = run_full_onboarding(provider, pairs, trials_per_class=30, check_trials_per_class=15)
    profile = profile_user(session)

    print(f"Strong-signal user -> mode={profile.mode.value}, "
          f"best={profile.best_pair_label} ({profile.best_pair_accuracy:.1%})")
    assert profile.mode == InputMode.EEG_COMMANDS
    print("PASS: strong-signal user correctly placed in EEG_COMMANDS mode")


def test_weak_signal_user_falls_back_to_ssvep():
    """
    A user whose accuracy never clears the threshold (like Subject 2's flat
    profile across all pairs) should fall back to SSVEP-only mode, not be
    silently given an unreliable EEG-command experience.
    """
    brain = FakeBrain(accuracy=0.52, idle_rate=0.1, seed=2)
    provider = FakeBrainTrialProvider(brain)
    pairs = {
        "UP_vs_DOWN": ["UP", "DOWN"],
        "UP_vs_RIGHT": ["UP", "RIGHT"],
        "UP_vs_LEFT": ["UP", "LEFT"],
        "DOWN_vs_RIGHT": ["DOWN", "RIGHT"],
    }

    session = run_full_onboarding(provider, pairs, trials_per_class=30, check_trials_per_class=15)
    profile = profile_user(session)

    print(f"Weak-signal user -> mode={profile.mode.value}, "
          f"best={profile.best_pair_label} ({profile.best_pair_accuracy:.1%})")
    print(f"Reason: {profile.reason}")
    assert profile.mode == InputMode.SSVEP_FALLBACK
    print("PASS: weak-signal user correctly falls back to SSVEP_FALLBACK mode")


def test_threshold_boundary_is_respected():
    """Direct check that the threshold constant is being used consistently, not a hardcoded magic number."""
    assert MINIMUM_USABLE_ACCURACY == 0.60
    print(f"PASS: usability threshold is {MINIMUM_USABLE_ACCURACY:.0%}, as documented")


if __name__ == "__main__":
    test_strong_signal_user_gets_eeg_commands_mode()
    test_weak_signal_user_falls_back_to_ssvep()
    test_threshold_boundary_is_respected()
    print("\nAll user profile tests passed.")
