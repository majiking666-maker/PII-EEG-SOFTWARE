"""
Tests for core/profile_storage.py. Run with:
    python3 tests/test_profile_storage.py
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.user_profile import UserProfile, InputMode
from core.profile_storage import (
    save_profile,
    load_profile,
    delete_profile,
    get_profile_or_none,
    StoredProfile,
)

TEST_PROFILE_PATH = "/tmp/pii_test_profile.json"


def cleanup():
    if os.path.exists(TEST_PROFILE_PATH):
        os.remove(TEST_PROFILE_PATH)


def test_save_and_load_roundtrip():
    cleanup()
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="UP_vs_RIGHT",
        best_pair_accuracy=0.75,
        reason="Best pair reached 75.0%, above threshold.",
    )
    save_profile(profile, path=TEST_PROFILE_PATH)

    loaded = load_profile(path=TEST_PROFILE_PATH)
    assert loaded is not None
    assert loaded.mode == "eeg_commands"
    assert loaded.best_pair_label == "UP_vs_RIGHT"
    assert loaded.best_pair_accuracy == 0.75

    restored = loaded.to_user_profile()
    assert restored.mode == InputMode.EEG_COMMANDS
    assert restored.best_pair_accuracy == 0.75
    print("PASS: save/load roundtrip preserves all profile data")
    cleanup()


def test_missing_file_returns_none():
    cleanup()  # ensure it really doesn't exist
    result = load_profile(path=TEST_PROFILE_PATH)
    assert result is None
    print("PASS: missing profile file correctly returns None, not an error")


def test_corrupted_file_returns_none_not_crash():
    cleanup()
    os.makedirs(os.path.dirname(TEST_PROFILE_PATH), exist_ok=True)
    with open(TEST_PROFILE_PATH, "w") as f:
        f.write("{not valid json!!!")

    result = load_profile(path=TEST_PROFILE_PATH)
    assert result is None
    print("PASS: corrupted profile file returns None instead of crashing")
    cleanup()


def test_get_profile_or_none_fresh_profile_is_usable():
    cleanup()
    profile = UserProfile(
        mode=InputMode.SSVEP_FALLBACK,
        best_pair_label="UP_vs_LEFT",
        best_pair_accuracy=0.55,
        reason="Below threshold.",
    )
    save_profile(profile, path=TEST_PROFILE_PATH)

    result = get_profile_or_none(path=TEST_PROFILE_PATH, staleness_days=30)
    assert result is not None
    assert result.mode == InputMode.SSVEP_FALLBACK
    print("PASS: fresh saved profile is correctly returned as usable")
    cleanup()


def test_stale_profile_is_treated_as_missing():
    cleanup()
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="UP_vs_DOWN",
        best_pair_accuracy=0.70,
        reason="Above threshold.",
    )
    save_profile(profile, path=TEST_PROFILE_PATH)

    # Manually backdate the saved_at timestamp to simulate an old profile
    stored = load_profile(path=TEST_PROFILE_PATH)
    import json
    from dataclasses import asdict
    stored.saved_at = time.time() - (40 * 86400)  # 40 days ago
    with open(TEST_PROFILE_PATH, "w") as f:
        json.dump(asdict(stored), f)

    result = get_profile_or_none(path=TEST_PROFILE_PATH, staleness_days=30)
    assert result is None, "A profile older than the staleness window should be treated as missing"
    print("PASS: stale profile (40 days old, 30-day limit) correctly triggers re-onboarding")
    cleanup()


def test_delete_profile_removes_file():
    cleanup()
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="X",
        best_pair_accuracy=0.8,
        reason="test",
    )
    save_profile(profile, path=TEST_PROFILE_PATH)
    assert os.path.exists(TEST_PROFILE_PATH)

    delete_profile(path=TEST_PROFILE_PATH)
    assert not os.path.exists(TEST_PROFILE_PATH)
    print("PASS: delete_profile correctly removes the saved file")


if __name__ == "__main__":
    test_save_and_load_roundtrip()
    test_missing_file_returns_none()
    test_corrupted_file_returns_none_not_crash()
    test_get_profile_or_none_fresh_profile_is_usable()
    test_stale_profile_is_treated_as_missing()
    test_delete_profile_removes_file()
    print("\nAll profile storage tests passed.")
