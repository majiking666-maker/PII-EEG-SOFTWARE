"""
Thin end-to-end demo for PII software (priority item 4).

Wires together:
  onboarding -> user profile -> save/load -> live attempts
  through CommandPolicy + Confirm flow, all driven by FakeBrain.

Run from repo root:
  python3 demo_end_to_end.py

No real hardware required. This is the first script that exercises the
modules as one system instead of in isolation.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.events import BrainEvent, EventType
from core.command_policy import CommandPolicy, PolicyAction
from core.calibration import FakeBrainTrialProvider, run_full_onboarding
from core.user_profile import profile_user, InputMode, UserProfile
from core.profile_storage import (
    save_profile,
    load_profile,
    get_profile_or_none,
    delete_profile,
)
from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from simulator.fake_brain import FakeBrain


def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    # Use a temp profile path so the demo never touches the real ~/.pii profile
    demo_profile_path = os.path.join(tempfile.gettempdir(), "pii_demo_user_profile.json")
    if os.path.exists(demo_profile_path):
        os.remove(demo_profile_path)

    section("1. Simulated onboarding (multiple pairs)")
    brain = FakeBrain(accuracy=0.72, idle_rate=0.10, seed=42)
    provider = FakeBrainTrialProvider(brain)

    pairs = {
        "UP_vs_DOWN": ["UP", "DOWN"],
        "UP_vs_LEFT": ["UP", "LEFT"],
        "YES_vs_NO": ["YES", "NO"],
    }
    session = run_full_onboarding(
        provider,
        pairs,
        trials_per_class=12,
        check_trials_per_class=6,
    )
    print(session.summary())

    section("2. Profile decision")
    profile = profile_user(session)
    print(f"Mode:           {profile.mode.value}")
    print(f"Best pair:      {profile.best_pair_label}")
    print(f"Best accuracy:  {profile.best_pair_accuracy:.1%}")
    print(f"Reason:         {profile.reason}")

    section("3. Persist profile (offline)")
    save_profile(profile, path=demo_profile_path)
    print(f"Saved to: {demo_profile_path}")

    stored = load_profile(path=demo_profile_path)
    assert stored is not None, "load_profile returned None after save"
    loaded = stored.to_user_profile()
    print(f"Loaded mode:  {loaded.mode.value}")
    print(f"Loaded pair:  {loaded.best_pair_label}")
    assert loaded.mode == profile.mode
    assert loaded.best_pair_label == profile.best_pair_label

    via_helper = get_profile_or_none(path=demo_profile_path)
    assert via_helper is not None
    assert via_helper.mode == profile.mode
    print("Save/load round-trip OK (including get_profile_or_none)")

    section("4. Live input through policy + confirm")
    policy = CommandPolicy(ignore_below=0.5, confirm_below=0.85)

    # Semantic Yes/No; in EEG mode the user's best pair is the underlying mental actions
    if profile.mode == InputMode.EEG_COMMANDS and profile.best_pair_label:
        raw = profile.best_pair_label.replace("_vs_", " ").replace("_", " ").split()
        if len(raw) >= 2:
            mental_yes, mental_no = raw[0], raw[1]
        else:
            mental_yes, mental_no = "YES", "NO"
        print(f"EEG mode: mental actions {mental_yes}/{mental_no} mapped to Yes/No")
    else:
        mental_yes, mental_no = "YES", "NO"
        print("SSVEP_FALLBACK mode: confirm will use yes_target / no_target")

    print("\nSimulating 8 intended YES attempts (user trying to confirm a selection):")
    accepted = cancelled = ignored = timed_out = 0

    for i in range(8):
        # First event: the system "detected" something worth confirming
        detection = brain.next_command_attempt(mental_yes, [mental_yes, mental_no])
        decision = policy.decide(detection)

        if decision.action == PolicyAction.IGNORE:
            ignored += 1
            print(f"  [{i+1}] IGNORE  (type={detection.event_type.value}, conf={detection.confidence:.2f})")
            continue

        if decision.action == PolicyAction.AUTO_COMMIT:
            accepted += 1
            print(f"  [{i+1}] AUTO_COMMIT  label={detection.label} conf={detection.confidence:.2f}")
            continue

        # SHOW_CONFIRM — shared confirm contract
        subject = detection.label or "selection"
        print(f"  [{i+1}] SHOW_CONFIRM subject={subject} conf={detection.confidence:.2f} -> confirm flow")
        conf_session = start_confirm(
            subject_label=subject,
            profile=profile,
            timeout_seconds=4.0,
        )

        # Simulate user response during the confirm window
        if i == 3:
            # deliberate cancel
            if profile.mode == InputMode.EEG_COMMANDS:
                resp = brain.next_command_attempt(mental_no, [mental_yes, mental_no])
            else:
                resp = brain.next_ssvep_attempt("no_target", ["yes_target", "no_target"])
        else:
            if profile.mode == InputMode.EEG_COMMANDS:
                resp = brain.next_command_attempt(mental_yes, [mental_yes, mental_no])
            else:
                resp = brain.next_ssvep_attempt("yes_target", ["yes_target", "no_target"])

        outcome = resolve_confirm(conf_session, resp, policy)
        if outcome == ConfirmOutcome.ACCEPTED:
            accepted += 1
            print(f"       -> ACCEPTED")
        elif outcome == ConfirmOutcome.CANCELLED:
            cancelled += 1
            print(f"       -> CANCELLED")
        elif outcome == ConfirmOutcome.TIMED_OUT:
            timed_out += 1
            print(f"       -> TIMED_OUT")
        else:
            ignored += 1
            print(f"       -> still PENDING / ignored ({outcome.value})")

    section("5. Summary")
    print(f"Accepted:  {accepted}")
    print(f"Cancelled: {cancelled}")
    print(f"Ignored:   {ignored}")
    print(f"Timed out: {timed_out}")
    print(f"\nUser mode for this session: {profile.mode.value}")
    if profile.mode == InputMode.SSVEP_FALLBACK:
        print("Weak-signal path exercised: confirms used SSVEP yes/no targets.")
    else:
        print("Strong-signal path exercised: confirms used mental Yes/No.")

    # Cleanup demo profile file
    delete_profile(path=demo_profile_path)
    print("\nEnd-to-end demo complete.")


if __name__ == "__main__":
    main()
