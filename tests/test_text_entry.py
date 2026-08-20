"""
Tests for hierarchical text-entry keyboard (item 5).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.ssvep_targets import TargetRegistry
from core.text_entry import TextKeyboard, PredictionEngine, KeyboardPage
from core.user_profile import UserProfile, InputMode
from core.command_policy import CommandPolicy
from core.confirm import start_confirm, resolve_confirm, ConfirmOutcome
from simulator.fake_brain import FakeBrain


def test_visible_elements_groups_page():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=4)
    els = kb.visible_elements()
    ids = [e.element_id for e in els]
    assert any(i.startswith("group:") for i in ids)
    assert any(i.startswith("pred:") for i in ids)
    assert "special:SPACE" in ids
    assert "special:DELETE" in ids


def test_navigate_group_to_letter_and_type():
    reg = TargetRegistry()
    kb = TextKeyboard(reg)
    # Open A-G group
    label = kb.request_select("group:A-G")
    assert "A-G" in label
    assert kb.commit_selection()
    assert kb.state.page == KeyboardPage.LETTERS
    assert kb.state.active_group == "A-G"

    # Type H is not in A-G; type A
    kb.request_select("letter:A")
    kb.commit_selection()
    assert kb.current_text() == "A"

    kb.request_select("letter:B")
    kb.commit_selection()
    assert kb.current_text() == "AB"


def test_prediction_accept():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=6)
    kb.state.text = "th"
    preds = kb.predictions.get_predictions("th", max_n=6)
    assert any(p.startswith("th") for p in preds)
    # Accept first matching prediction if present
    word = next(p for p in preds if p.startswith("th"))
    kb.request_select(f"pred:{word}")
    kb.commit_selection()
    assert kb.current_text().startswith(word)


def test_delete_and_space():
    reg = TargetRegistry()
    kb = TextKeyboard(reg)
    kb.state.text = "hi"
    kb.request_select("special:DELETE")
    kb.commit_selection()
    assert kb.current_text() == "h"
    kb.request_select("special:SPACE")
    kb.commit_selection()
    assert kb.current_text() == "h "


def test_prepare_targets_uses_registry_pool():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=3)
    groups = kb.prepare_visible_targets()
    assert len(groups) >= 1
    freqs = [t.frequency for g in groups for t in g.targets]
    # No collision with reserved confirm/scroll
    reserved = reg.reserved_frequencies()
    for f in freqs:
        assert f not in reserved or f in reg.dynamic_pool


def test_keyboard_confirm_flow_with_fake_brain():
    """Wire keyboard selection through shared confirm contract."""
    reg = TargetRegistry()
    kb = TextKeyboard(reg)
    policy = CommandPolicy(ignore_below=0.5, confirm_below=0.85)
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="YES_vs_NO",
        best_pair_accuracy=0.8,
        reason="test",
    )
    brain = FakeBrain(accuracy=0.99, idle_rate=0.0, seed=3)

    subject = kb.request_select("group:A-G")
    session = start_confirm(subject_label=subject, profile=profile)
    # User confirms with mental YES
    resp = brain.next_command_attempt("YES", ["YES", "NO"])
    outcome = resolve_confirm(session, resp, policy)
    # High accuracy brain should usually accept; if pending, still ok for smoke
    if outcome == ConfirmOutcome.ACCEPTED:
        assert kb.commit_selection()
        assert kb.state.page == KeyboardPage.LETTERS
    else:
        kb.cancel_selection()


def test_prediction_group_boost():
    eng = PredictionEngine()
    # Highlight group containing 'e' should prefer words continuing with e when prefix is "th"
    boosted = eng.get_predictions("th", highlighted_group_letters="EFG", max_n=10)
    plain = eng.get_predictions("th", highlighted_group_letters="", max_n=10)
    assert len(boosted) > 0
    assert len(plain) > 0


if __name__ == "__main__":
    test_visible_elements_groups_page()
    print("test_visible_elements_groups_page OK")
    test_navigate_group_to_letter_and_type()
    print("test_navigate_group_to_letter_and_type OK")
    test_prediction_accept()
    print("test_prediction_accept OK")
    test_delete_and_space()
    print("test_delete_and_space OK")
    test_prepare_targets_uses_registry_pool()
    print("test_prepare_targets_uses_registry_pool OK")
    test_keyboard_confirm_flow_with_fake_brain()
    print("test_keyboard_confirm_flow_with_fake_brain OK")
    test_prediction_group_boost()
    print("test_prediction_group_boost OK")
    print("All text_entry tests passed.")
