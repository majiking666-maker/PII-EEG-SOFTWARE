"""
User capability profiling: turns a completed CalibrationSession into a
concrete mode decision for that user.

Design rationale (locked 2026-08-18): our own real EEG experiments showed
some subjects (e.g. "Subject 2" in project notes) never produced a
meaningfully usable pair, even after testing all combinations - flat ~55-60%
across the board, no standout. Shipping EEG-based discrete commands to a
user like that would mean an unreliable, frustrating experience disguised
as a working feature. Instead: measure it during onboarding, and if the
user's best achievable pair doesn't clear a minimum usable bar, fall back
to SSVEP-only operation for their discrete actions (e.g. SSVEP-selecting a
YES/NO target instead of thinking it). Slower, but honest and reliable.

This is a product-safety decision, not a technical limitation we're hiding -
the fallback should be visible/explained to the user, not silent.
"""

from dataclasses import dataclass
from enum import Enum
from core.calibration import CalibrationSession


class InputMode(Enum):
    EEG_COMMANDS = "eeg_commands"    # User's best pair is reliable enough for EEG discrete commands
    SSVEP_FALLBACK = "ssvep_fallback"  # Best pair too unreliable - use SSVEP selection instead


@dataclass
class UserProfile:
    mode: InputMode
    best_pair_label: str | None
    best_pair_accuracy: float
    reason: str


# Minimum accuracy for EEG discrete commands to be considered usable.
# Based on real experimental evidence: pairs that reached ~65%+ felt like a
# real, if imperfect, channel; pairs stuck at ~55-60% never showed a
# meaningful standout even after testing every combination. This threshold
# is a tunable product decision - revisit as real user data accumulates.
MINIMUM_USABLE_ACCURACY = 0.60


def profile_user(session: CalibrationSession) -> UserProfile:
    """
    Given a completed calibration session (all pairs tested), decide which
    input mode this user should be placed in.
    """
    best = session.best_pair()

    if best is None:
        return UserProfile(
            mode=InputMode.SSVEP_FALLBACK,
            best_pair_label=None,
            best_pair_accuracy=0.0,
            reason="No calibration data available.",
        )

    best_accuracy = max(best.zero_shot_accuracy, best.calibrated_accuracy)

    if best_accuracy >= MINIMUM_USABLE_ACCURACY:
        return UserProfile(
            mode=InputMode.EEG_COMMANDS,
            best_pair_label=best.pair_label,
            best_pair_accuracy=best_accuracy,
            reason=(
                f"Best pair '{best.pair_label}' reached {best_accuracy:.1%}, "
                f"at or above the {MINIMUM_USABLE_ACCURACY:.0%} usability threshold."
            ),
        )

    return UserProfile(
        mode=InputMode.SSVEP_FALLBACK,
        best_pair_label=best.pair_label,
        best_pair_accuracy=best_accuracy,
        reason=(
            f"Best pair '{best.pair_label}' only reached {best_accuracy:.1%}, "
            f"below the {MINIMUM_USABLE_ACCURACY:.0%} usability threshold. "
            f"Falling back to SSVEP-only mode for discrete actions."
        ),
    )
