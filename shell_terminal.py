#!/usr/bin/env python3
"""
Terminal debug shell for PII.

Lets you dogfood the product spine without Android or real EEG:
  - optional quick onboarding (or force a mode)
  - hierarchical keyboard display
  - select targets by number
  - confirm Yes/No (simulates mental or SSVEP confirm)
  - see committed text grow

Run from repo root:
  python3 shell_terminal.py

Commands inside the shell are shown in the help banner.
No dependencies beyond the standard library + this repo's core/.
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
from core.command_policy import CommandPolicy, PolicyAction
from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from core.events import BrainEvent, EventType
from simulator.fake_brain import FakeBrain


PROFILE_PATH = os.path.join(tempfile.gettempdir(), "pii_shell_user_profile.json")


def banner() -> None:
    print(
        """
============================================================
  PII terminal shell  (FakeBrain / keyboard / confirm)
============================================================
  help          show this help
  status        show mode, page, text
  keys          list visible keyboard targets (numbered)
  pick N        select target N (starts confirm)
  y / n         answer confirm Yes / No
  onboard       short simulated onboarding -> save profile
  mode eeg|ssvep  force mode without onboarding
  noise on|off  use imperfect FakeBrain for confirm answers
  clear         clear typed text
  reset         delete shell profile
  quit          exit
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
    pairs = {
        "UP_vs_DOWN": ["UP", "DOWN"],
        "YES_vs_NO": ["YES", "NO"],
    }
    session = run_full_onboarding(
        provider, pairs, trials_per_class=8, check_trials_per_class=4
    )
    print(session.summary())
    profile = profile_user(session)
    save_profile(profile, path=PROFILE_PATH)
    print(f"Saved profile -> {PROFILE_PATH}")
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
    """Return ordered target ids currently visible (may be capped by pool)."""
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
    print("-----------------------")
    return ids


def perfect_confirm_event(profile: UserProfile, yes: bool) -> BrainEvent:
    """Direct high-confidence confirm answer (no noise)."""
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
        print("Run 'onboard' for simulated calibration, or 'mode ssvep'.")
        profile = make_forced_profile(InputMode.EEG_COMMANDS)
    else:
        print(f"Loaded shell profile: {profile.mode.value} "
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
            print("Shell profile deleted; keyboard reset; mode=eeg_commands.")
            continue

        if cmd == "noise":
            if len(parts) < 2 or parts[1] not in ("on", "off"):
                print("Usage: noise on|off")
                continue
            noise = parts[1] == "on"
            print(f"Noisy FakeBrain confirm answers: {noise}")
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
            print(f"Mode forced to {profile.mode.value}")
            continue

        if cmd == "onboard":
            profile = run_quick_onboard()
            pending_subject = None
            confirm_session = None
            continue

        if cmd == "pick":
            if confirm_session is not None:
                print("Finish or cancel the current confirm first (y/n).")
                continue
            if len(parts) < 2 or not parts[1].isdigit():
                print("Usage: pick N   (run 'keys' first)")
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
            confirm_session = start_confirm(subject_label=subject, profile=profile)
            channel = (
                "mental YES/NO"
                if profile.mode == InputMode.EEG_COMMANDS
                else "SSVEP yes_target/no_target"
            )
            print(f"CONFIRM: {subject}")
            print(f"  Answer with y or n  (channel: {channel})")
            continue

        if cmd in ("y", "n", "yes", "no"):
            if confirm_session is None:
                print("Nothing pending to confirm. Use 'pick N' first.")
                continue
            want_yes = cmd in ("y", "yes")
            if noise:
                event = noisy_confirm_event(brain, profile, want_yes)
                print(f"  (noisy event: type={event.event_type.value} "
                      f"label={event.label} target={event.target_id} "
                      f"conf={event.confidence:.2f})")
            else:
                event = perfect_confirm_event(profile, want_yes)

            outcome = resolve_confirm(confirm_session, event, policy)
            print(f"  outcome: {outcome.value}")

            if outcome == ConfirmOutcome.ACCEPTED:
                kb.commit_selection()
                print(f"  committed. text={kb.current_text()!r} page={kb.state.page.value}")
                confirm_session = None
                pending_subject = None
                visible_ids = []  # page may have changed
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
                # PENDING — low confidence noise; keep waiting
                print("  still pending (try y/n again, or 'noise off').")
            continue

        print(f"Unknown command: {cmd!r}  (type help)")

    print("Bye.")


if __name__ == "__main__":
    main()
