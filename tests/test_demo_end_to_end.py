"""
Smoke test for the thin end-to-end demo (priority item 4).

Checks that:
- onboarding produces a profile
- save/load round-trips via profile_storage
- policy + confirm path does not crash in both modes

Run from repo root:
  python3 tests/test_demo_end_to_end.py
  # or
  python3 -m pytest tests/test_demo_end_to_end.py -q
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.calibration import FakeBrainTrialProvider, run_full_onboarding
from core.user_profile import profile_user, InputMode, UserProfile
from core.profile_storage import save_profile, load_profile, get_profile_or_none, delete_profile
from core.command_policy import CommandPolicy, PolicyAction
from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from core.events import EventType
from simulator.fake_brain import FakeBrain


def _temp_profile_path() -> str:
    return os.path.join(tempfile.gettempdir(), "pii_test_user_profile.json")


def test_onboarding_to_profile_to_storage():
    path = _temp_profile_path()
    if os.path.exists(path):
        os.remove(path)

    brain = FakeBrain(accuracy=0.80, idle_rate=0.05, seed=7)
    provider = FakeBrainTrialProvider(brain)
    pairs = {"YES_vs_NO": ["YES", "NO"]}
    session = run_full_onboarding(provider, pairs, trials_per_class=8, check_trials_per_class=4)
    profile = profile_user(session)
    assert profile is not None
    assert profile.mode in (InputMode.EEG_COMMANDS, InputMode.SSVEP_FALLBACK)

    save_profile(profile, path=path)
    stored = load_profile(path=path)
    assert stored is not None
    loaded = stored.to_user_profile()
    assert loaded.mode == profile.mode
    assert loaded.best_pair_label == profile.best_pair_label

    via_helper = get_profile_or_none(path=path)
    assert via_helper is not None
    assert via_helper.mode == profile.mode

    delete_profile(path=path)
    assert load_profile(path=path) is None


def test_policy_and_confirm_eeg_mode():
    brain = FakeBrain(accuracy=0.95, idle_rate=0.0, seed=1)
    policy = CommandPolicy(ignore_below=0.5, confirm_below=0.85)
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="YES_vs_NO",
        best_pair_accuracy=0.75,
        reason="test",
    )

    event = brain.next_command_attempt("YES", ["YES", "NO"])
    decision = policy.decide(event)
    assert decision.action in (
        PolicyAction.IGNORE,
        PolicyAction.SHOW_CONFIRM,
        PolicyAction.AUTO_COMMIT,
    )

    if decision.action == PolicyAction.SHOW_CONFIRM:
        session = start_confirm(subject_label=event.label or "YES", profile=profile)
        resp = brain.next_command_attempt("YES", ["YES", "NO"])
        outcome = resolve_confirm(session, resp, policy)
        assert outcome in (
            ConfirmOutcome.ACCEPTED,
            ConfirmOutcome.CANCELLED,
            ConfirmOutcome.PENDING,
            ConfirmOutcome.TIMED_OUT,
        )


def test_policy_and_confirm_ssvep_fallback_mode():
    brain = FakeBrain(accuracy=0.95, idle_rate=0.0, seed=2)
    policy = CommandPolicy(ignore_below=0.5, confirm_below=0.85)
    profile = UserProfile(
        mode=InputMode.SSVEP_FALLBACK,
        best_pair_label="YES_vs_NO",
        best_pair_accuracy=0.55,
        reason="test weak signal",
    )

    detection = brain.next_ssvep_attempt("ui_grid_1", ["ui_grid_1", "ui_grid_2"])
    decision = policy.decide(detection)
    assert decision.action in (
        PolicyAction.IGNORE,
        PolicyAction.SHOW_CONFIRM,
        PolicyAction.AUTO_COMMIT,
    )

    session = start_confirm(subject_label="ui_grid_1", profile=profile)
    resp = brain.next_ssvep_attempt("yes_target", ["yes_target", "no_target"])
    outcome = resolve_confirm(session, resp, policy)
    assert outcome in (
        ConfirmOutcome.ACCEPTED,
        ConfirmOutcome.CANCELLED,
        ConfirmOutcome.PENDING,
        ConfirmOutcome.TIMED_OUT,
    )


if __name__ == "__main__":
    test_onboarding_to_profile_to_storage()
    print("test_onboarding_to_profile_to_storage OK")
    test_policy_and_confirm_eeg_mode()
    print("test_policy_and_confirm_eeg_mode OK")
    test_policy_and_confirm_ssvep_fallback_mode()
    print("test_policy_and_confirm_ssvep_fallback_mode OK")
    print("All smoke tests passed.")
