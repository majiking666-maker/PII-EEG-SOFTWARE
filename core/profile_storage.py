"""
UserProfile persistence.

Design rationale (per Grok Note 09/10/11, agreed with Maji 2026-08-19):
onboarding should not repeat every launch. This module saves the result of
a completed calibration session (mode, best pair, accuracy, when it
happened) to a local file, and loads it back on the next app start.

Offline-first, per the hard requirement in docs/design_decisions.md: this
is plain local file I/O, no network calls, no cloud dependency. JSON is
used for the on-disk format because it's human-readable (useful for
debugging during this dev phase) and trivial to swap for a different
storage backend later without changing the interface other modules use.
"""

import json
import os
import time
from dataclasses import dataclass, asdict
from core.user_profile import UserProfile, InputMode


DEFAULT_PROFILE_PATH = os.path.join(os.path.expanduser("~"), ".pii", "user_profile.json")

# If a saved profile is older than this, treat it as stale and prompt
# re-calibration rather than silently trusting old data. Tunable - EEG
# signal characteristics could plausibly drift over weeks (electrode wear,
# skin conditions, etc.) though this is not yet backed by real data at
# this stage - conservative default until we have evidence either way.
DEFAULT_STALENESS_DAYS = 30


@dataclass
class StoredProfile:
    """
    On-disk representation of a UserProfile, plus metadata not present in
    the in-memory UserProfile itself (when it was saved).
    """
    mode: str
    best_pair_label: str | None
    best_pair_accuracy: float
    reason: str
    saved_at: float  # unix timestamp

    def to_user_profile(self) -> UserProfile:
        return UserProfile(
            mode=InputMode(self.mode),
            best_pair_label=self.best_pair_label,
            best_pair_accuracy=self.best_pair_accuracy,
            reason=self.reason,
        )

    def is_stale(self, staleness_days: float = DEFAULT_STALENESS_DAYS) -> bool:
        age_days = (time.time() - self.saved_at) / 86400
        return age_days > staleness_days


def save_profile(profile: UserProfile, path: str = DEFAULT_PROFILE_PATH) -> None:
    """
    Writes the given profile to disk as JSON. Creates the parent directory
    if it doesn't exist yet (first-run case).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    stored = StoredProfile(
        mode=profile.mode.value,
        best_pair_label=profile.best_pair_label,
        best_pair_accuracy=profile.best_pair_accuracy,
        reason=profile.reason,
        saved_at=time.time(),
    )

    with open(path, "w") as f:
        json.dump(asdict(stored), f, indent=2)


def load_profile(path: str = DEFAULT_PROFILE_PATH) -> StoredProfile | None:
    """
    Loads a previously saved profile. Returns None if no profile exists yet
    (first launch) or if the file is corrupted/unreadable - callers should
    treat None the same as "user needs onboarding", not raise an error, since
    a corrupted profile file should never block the user from using the app.
    """
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r") as f:
            data = json.load(f)
        return StoredProfile(**data)
    except (json.JSONDecodeError, TypeError, KeyError):
        # Corrupted or unexpected-format file. Treat as "no profile" rather
        # than crashing - this is a recoverable situation (re-run onboarding),
        # not a fatal error.
        return None


def delete_profile(path: str = DEFAULT_PROFILE_PATH) -> None:
    """Removes a saved profile, e.g. for a 'reset my calibration' feature."""
    if os.path.exists(path):
        os.remove(path)


def get_profile_or_none(
    path: str = DEFAULT_PROFILE_PATH,
    staleness_days: float = DEFAULT_STALENESS_DAYS,
) -> UserProfile | None:
    """
    Convenience function for app startup: returns a usable UserProfile if
    one exists and isn't stale, otherwise None (meaning: run onboarding).
    This is the function most calling code should actually use.
    """
    stored = load_profile(path)
    if stored is None:
        return None
    if stored.is_stale(staleness_days):
        return None
    return stored.to_user_profile()
