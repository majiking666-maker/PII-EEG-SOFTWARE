#!/usr/bin/env python3
"""
Terminal debug shell for PII.

Dogfood the product spine without Android or real EEG:
  - hierarchical keyboard (groups / letters / predictions / numbers)
  - letter-by-letter text + predictions page reflecting current prefix
  - select by number, confirm Yes/No

Run:
  python3 shell_terminal.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssvep_targets import TargetRegistry
from core.text_entry import TextKeyboard
from core.user_profile import UserProfile, InputMode, profile_user
from core.profile_storage import save_profile, get_profile_or_none, delete_profile
from core.calibration import FakeBrainTrialProvider, run_full_onboarding
from core.command_policy import CommandPolicy
from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from core.events import BrainEvent, EventType
from simulator.fake_brain import FakeBrain


PROFILE_PATH = os.path.join(tempfile.gettempdir(), "pii_shell_user_profile.json")
# Product UI uses a short confirm window; the shell is slower human typing.
SHELL_CONFIRM_TIMEOUT = 60.0


def banner() -> None:
    print(
        """
============================================================
  PII terminal shell  (keyboard / confirm / FakeBrain)
============================================================
  help            show this help
  status          mode, page, text
  keys            list visible targets (numbered)
  pick N          select target N (starts confirm)
  y / n           answer confirm Yes / No
  onboard         short simulated onboarding
  mode eeg|ssvep  force mode
  noise on|off    imperfect FakeBrain for confirm answers
  clear           clear typed text
  reset           delete shell profile + reset keyboard
  quit            exit

  Typing path: keys -> pick group -> y -> keys -> pick letter -> y
  Predictions: on groups page pick PREDICT -> y -> pick a word -> y
============================================================
""".strip()
    )


def make_forced_profile(mode: InputMode) -> UserProfile:
    if mode == InputMode.EEG_COMMANDS:
        return UserProfile(
            mode=mode,
            best_pair_label="YES_vs_NO",
            best_pair_accuracy=0.75,
            reason="Forced EEG_COMMANDS mode from terminal shell.",
        )
    return UserProfile(
        mode=mode,
        best_pair_label="YES_vs_NO",
        best_pair_accuracy=0.55,
        reason="Forced SSVEP_FALLBACK mode from terminal shell.",
    )


def run_quick_onboard() -> UserProfile:
    print("Running short simulated onboarding...")
    brain = FakeBrain(accuracy=0.75, idle_rate=0.05, seed=11)
    provider = FakeBrainTrialProvider(brain)
    pairs = {"UP_vs_DOWN": ["UP", "DOWN"], "YES_vs_NO": ["YES", "NO"]}
    session = run_full_onboarding(
        provider, pairs, trials_per_class=8, check_trials_per_class=4
    )
    print(session.summary())
    profile = profile_user(session)
    save_profile(profile, path=PROFILE_PATH)
    print(f"Mode: {profile.mode.value} | best: {profile.best_pair_label} "
          f"({profile.best_pair_accuracy:.1%})")
    return profile


def show_status(profile: UserProfile, kb: TextKeyboard, pending: str | None) -> None:
    print(f"Mode:   {profile.mode.value}")
    print(f"Page:   {kb.state.page.value}"
          + (f" ({kb.state.active_group})" if kb.state.active_group else ""))
    print(f"Text:   {kb.current_text()!r}")
    if pending:
        print(f"Pending confirm: {pending}")


def list_keys(kb: TextKeyboard) -> list[str]:
    groups = kb.prepare_visible_targets()
    ids: list[str] = []
    print("--- visible targets ---")
    n = 1
    for g in groups:
        for t in g.targets:
            eid = t.element.element_id
            ids.append(eid)
            print(f"  {n:2d}.  {t.element.label:12s}  [{eid}]  @ {t.frequency:.1f} Hz")
            n += 1
    if not ids:
        print("  (none)")
    # Note if dynamic pool truncated the page
    full = len(kb.visible_elements())
    if full > len(ids):
        print(f"  (showing {len(ids)}/{full} — dynamic frequency pool cap)")
    print("-----------------------")
    return ids


def perfect_confirm_event(profile: UserProfile, yes: bool) -> BrainEvent:
    if profile.mode == InputMode.EEG_COMMANDS:
        return BrainEvent(
            event_type=EventType.COMMAND,
            confidence=0.95,
            label="YES" if yes else "NO",
        )
    return BrainEvent(
        event_type=EventType.SSVEP_TARGET,
        confidence=0.95,
        target_id="yes_target" if yes else "no_target",
    )


def noisy_confirm_event(brain: FakeBrain, profile: UserProfile, yes: bool) -> BrainEvent:
    if profile.mode == InputMode.EEG_COMMANDS:
        intended = "YES" if yes else "NO"
        return brain.next_command_attempt(intended, ["YES", "NO"])
    intended = "yes_target" if yes else "no_target"
    return brain.next_ssvep_attempt(intended, ["yes_target", "no_target"])


def main() -> None:
    banner()
    registry = TargetRegistry()
    kb = TextKeyboard(registry, max_predictions=4)
    policy = CommandPolicy()
    noise = False
    brain = FakeBrain(accuracy=0.70, idle_rate=0.10, seed=21)

    profile = get_profile_or_none(path=PROFILE_PATH)
    if profile is None:
        print("No saved shell profile. Using forced EEG mode.")
        print("Run 'onboard' or 'mode ssvep'.")
        profile = make_forced_profile(InputMode.EEG_COMMANDS)
    else:
        print(f"Loaded profile: {profile.mode.value} "
              f"({profile.best_pair_label}, {profile.best_pair_accuracy:.1%})")

    pending_subject: str | None = None
    confirm_session = None
    visible_ids: list[str] = []

    while True:
        try:
            line = input("pii> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()

        if cmd in ("quit", "exit", "q"):
            break
        if cmd == "help":
            banner()
            continue
        if cmd == "status":
            show_status(profile, kb, pending_subject)
            continue
        if cmd == "keys":
            visible_ids = list_keys(kb)
            continue
        if cmd == "clear":
            kb.state.text = ""
            print("Text cleared.")
            continue
        if cmd == "reset":
            delete_profile(path=PROFILE_PATH)
            profile = make_forced_profile(InputMode.EEG_COMMANDS)
            kb = TextKeyboard(registry, max_predictions=4)
            pending_subject = None
            confirm_session = None
            print("Reset. mode=eeg_commands")
            continue
        if cmd == "noise":
            if len(parts) < 2 or parts[1] not in ("on", "off"):
                print("Usage: noise on|off")
                continue
            noise = parts[1] == "on"
            print(f"Noisy confirm: {noise}")
            continue
        if cmd == "mode":
            if len(parts) < 2 or parts[1] not in ("eeg", "ssvep"):
                print("Usage: mode eeg|ssvep")
                continue
            mode = InputMode.EEG_COMMANDS if parts[1] == "eeg" else InputMode.SSVEP_FALLBACK
            profile = make_forced_profile(mode)
            save_profile(profile, path=PROFILE_PATH)
            pending_subject = None
            confirm_session = None
            print(f"Mode: {profile.mode.value}")
            continue
        if cmd == "onboard":
            profile = run_quick_onboard()
            pending_subject = None
            confirm_session = None
            continue

        if cmd == "pick":
            if confirm_session is not None:
                print("Finish current confirm first (y/n).")
                continue
            if len(parts) < 2 or not parts[1].isdigit():
                print("Usage: pick N")
                continue
            if not visible_ids:
                visible_ids = list_keys(kb)
            idx = int(parts[1]) - 1
            if idx < 0 or idx >= len(visible_ids):
                print(f"N must be 1..{len(visible_ids)}")
                continue
            tid = visible_ids[idx]
            subject = kb.request_select(tid)
            pending_subject = subject
            confirm_session = start_confirm(
                subject_label=subject,
                profile=profile,
                timeout_seconds=SHELL_CONFIRM_TIMEOUT,
            )
            channel = (
                "mental YES/NO"
                if profile.mode == InputMode.EEG_COMMANDS
                else "SSVEP yes_target/no_target"
            )
            print(f"CONFIRM: {subject}")
            print(f"  Answer y or n  (channel: {channel}, timeout {SHELL_CONFIRM_TIMEOUT:.0f}s)")
            continue

        if cmd in ("y", "n", "yes", "no"):
            if confirm_session is None:
                print("Nothing to confirm. pick N first.")
                continue
            want_yes = cmd in ("y", "yes")
            if noise:
                event = noisy_confirm_event(brain, profile, want_yes)
                print(f"  (noisy: {event.event_type.value} conf={event.confidence:.2f})")
            else:
                event = perfect_confirm_event(profile, want_yes)

            outcome = resolve_confirm(confirm_session, event, policy)
            print(f"  outcome: {outcome.value}")

            if outcome == ConfirmOutcome.ACCEPTED:
                kb.commit_selection()
                print(f"  text={kb.current_text()!r}  page={kb.state.page.value}")
                confirm_session = None
                pending_subject = None
                visible_ids = []
            elif outcome == ConfirmOutcome.CANCELLED:
                kb.cancel_selection()
                print("  cancelled.")
                confirm_session = None
                pending_subject = None
            elif outcome == ConfirmOutcome.TIMED_OUT:
                kb.cancel_selection()
                print("  timed out.")
                confirm_session = None
                pending_subject = None
            else:
                print("  still pending (try y/n again, or noise off).")
            continue

        print(f"Unknown: {cmd!r}  (help)")

    print("Bye.")


if __name__ == "__main__":
    main()
