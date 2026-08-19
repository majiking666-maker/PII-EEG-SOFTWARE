"""
Confirm UI contract.

Design rationale (per Grok Note 09, agreed 2026-08-19): every user must be
able to both highlight AND confirm/act, regardless of mode. This module
defines ONE reusable confirm flow that works the same way whether the
user is in EEG_COMMANDS mode (mental Yes/No) or SSVEP_FALLBACK mode
(small Yes/No SSVEP targets) - callers (UI grid selection, keyboard,
scroll, etc.) all use this same contract rather than each building their
own confirm logic.

This module does not render anything - it's the state machine / decision
layer. A real UI would observe a ConfirmSession's state and render
accordingly (what to show, timeout countdown, etc.).
"""

from dataclasses import dataclass, field
from enum import Enum
from time import time
from core.events import BrainEvent, EventType
from core.user_profile import UserProfile, InputMode
from core.command_policy import CommandPolicy, PolicyAction


class ConfirmOutcome(Enum):
    PENDING = "pending"       # still waiting for the user's confirm/cancel input
    ACCEPTED = "accepted"     # user confirmed - caller should commit the action
    CANCELLED = "cancelled"   # user explicitly declined
    TIMED_OUT = "timed_out"   # confirm window expired with no clear input


@dataclass
class ConfirmSession:
    """
    Represents one in-progress confirmation, e.g. "user highlighted the
    SEND button, waiting for them to confirm or cancel."

    subject_label: what's being confirmed (e.g. "SEND button", "letter K",
                    "scroll up"). For UI display purposes.
    mode: which confirm channel to use, taken from the user's profile.
    started_at: when the confirm window opened, for timeout tracking.
    outcome: current state - starts PENDING, resolves to one of the others.
    """
    subject_label: str
    mode: InputMode
    started_at: float = field(default_factory=time)
    outcome: ConfirmOutcome = ConfirmOutcome.PENDING
    timeout_seconds: float = 4.0  # per-confirm timeout; separate from the
                                    # SSVEP ~1-2s detection cycle itself -
                                    # this is how long the whole confirm
                                    # prompt stays alive waiting for a result

    def confirm_target_labels(self) -> tuple[str, str]:
        """
        What the two confirm options should be labeled as, given the mode.
        Both modes use the same YES/NO semantic - only the underlying
        input channel differs (mental action vs SSVEP target).
        """
        return ("YES", "NO")

    def is_expired(self) -> bool:
        return (time() - self.started_at) > self.timeout_seconds


def start_confirm(subject_label: str, profile: UserProfile, timeout_seconds: float = 4.0) -> ConfirmSession:
    """
    Begins a confirm flow for the given subject (whatever was just
    highlighted). Mode is taken directly from the user's profile - the
    caller doesn't need to know or care whether this resolves via mental
    Yes/No or SSVEP targets.
    """
    return ConfirmSession(
        subject_label=subject_label,
        mode=profile.mode,
        timeout_seconds=timeout_seconds,
    )


def resolve_confirm(session: ConfirmSession, event: BrainEvent, policy: CommandPolicy) -> ConfirmOutcome:
    """
    Feeds one incoming BrainEvent into an in-progress confirm session and
    returns the resulting outcome. This is mode-agnostic on purpose: in
    EEG_COMMANDS mode the event.label will be "YES"/"NO" (a decoded mental
    action mapped to that meaning); in SSVEP_FALLBACK mode the
    event.target_id will identify which SSVEP target ("yes_target" /
    "no_target") was fixated on. Both get normalized to the same
    ACCEPTED/CANCELLED outcome here - callers never need mode-specific
    branching after this point.

    Still runs every event through CommandPolicy first - the
    confirm-before-commit safeguard doesn't disappear just because we're
    already inside a confirmation flow. A low-confidence event during
    confirm should not silently resolve anything.
    """
    if session.outcome != ConfirmOutcome.PENDING:
        return session.outcome  # already resolved, don't re-process

    if session.is_expired():
        session.outcome = ConfirmOutcome.TIMED_OUT
        return session.outcome

    decision = policy.decide(event)
    if decision.action == PolicyAction.IGNORE:
        return session.outcome  # stays PENDING - not confident enough to count

    # Normalize both modes to a single YES/NO answer
    answer = None
    if session.mode == InputMode.EEG_COMMANDS and event.event_type == EventType.COMMAND:
        answer = event.label
    elif session.mode == InputMode.SSVEP_FALLBACK and event.event_type == EventType.SSVEP_TARGET:
        if event.target_id == "yes_target":
            answer = "YES"
        elif event.target_id == "no_target":
            answer = "NO"

    if answer == "YES":
        session.outcome = ConfirmOutcome.ACCEPTED
    elif answer == "NO":
        session.outcome = ConfirmOutcome.CANCELLED
    # else: event didn't match this session's expected mode/labels - stays PENDING,
    # caller should keep waiting rather than treat unrelated events as an answer

    return session.outcome
