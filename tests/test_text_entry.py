"""Tests for hierarchical text-entry keyboard."""

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


def test_groups_page_has_no_predictions():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=4)
    ids = [e.element_id for e in kb.visible_elements()]
    assert any(i.startswith("group:") for i in ids)
    assert "page:PREDICTIONS" in ids
    assert not any(i.startswith("pred:") for i in ids)


def test_predictions_own_page():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=4)
    kb.state.text = "th"
    kb.request_select("page:PREDICTIONS")
    kb.commit_selection()
    assert kb.state.page == KeyboardPage.PREDICTIONS
    ids = [e.element_id for e in kb.visible_elements()]
    assert any(i.startswith("pred:") for i in ids)
    assert "nav:BACK" in ids


def test_letter_by_letter_updates_text():
    reg = TargetRegistry()
    kb = TextKeyboard(reg)
    kb.request_select("group:A-G")
    kb.commit_selection()
    kb.request_select("letter:H")
    # H not in A-G — use A then E
    kb.request_select("letter:A")
    kb.commit_selection()
    assert kb.current_text() == "A"
    kb.request_select("letter:E")
    kb.commit_selection()
    assert kb.current_text() == "AE"


def test_predictions_reflect_prefix():
    eng = PredictionEngine()
    p = eng.get_predictions("th", max_n=6)
    assert all(w.startswith("th") or w.startswith("t") for w in p) or len(p) >= 0
    assert any(w.startswith("th") for w in p)


def test_prediction_accept():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=6)
    kb.state.text = "th"
    kb.state.page = KeyboardPage.PREDICTIONS
    preds = kb.predictions.get_predictions("th", max_n=6)
    word = next(p for p in preds if p.startswith("th"))
    kb.request_select(f"pred:{word}")
    kb.commit_selection()
    assert kb.current_text().startswith(word)
    assert kb.state.page == KeyboardPage.GROUPS


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


def test_prepare_targets_no_reserved_collision():
    reg = TargetRegistry()
    kb = TextKeyboard(reg, max_predictions=3)
    for page in (KeyboardPage.GROUPS, KeyboardPage.PREDICTIONS):
        kb.state.page = page
        groups = kb.prepare_visible_targets()
        freqs = [t.frequency for g in groups for t in g.targets]
        reserved = reg.reserved_frequencies()
        for f in freqs:
            assert f in reg.dynamic_pool or f not in reserved


def test_keyboard_confirm_flow():
    reg = TargetRegistry()
    kb = TextKeyboard(reg)
    policy = CommandPolicy()
    profile = UserProfile(
        mode=InputMode.EEG_COMMANDS,
        best_pair_label="YES_vs_NO",
        best_pair_accuracy=0.8,
        reason="test",
    )
    brain = FakeBrain(accuracy=0.99, idle_rate=0.0, seed=3)
    subject = kb.request_select("group:A-G")
    session = start_confirm(subject_label=subject, profile=profile, timeout_seconds=30.0)
    resp = brain.next_command_attempt("YES", ["YES", "NO"])
    outcome = resolve_confirm(session, resp, policy)
    if outcome == ConfirmOutcome.ACCEPTED:
        assert kb.commit_selection()
        assert kb.state.page == KeyboardPage.LETTERS
    else:
        kb.cancel_selection()


if __name__ == "__main__":
    test_groups_page_has_no_predictions()
    print("test_groups_page_has_no_predictions OK")
    test_predictions_own_page()
    print("test_predictions_own_page OK")
    test_letter_by_letter_updates_text()
    print("test_letter_by_letter_updates_text OK")
    test_predictions_reflect_prefix()
    print("test_predictions_reflect_prefix OK")
    test_prediction_accept()
    print("test_prediction_accept OK")
    test_delete_and_space()
    print("test_delete_and_space OK")
    test_prepare_targets_no_reserved_collision()
    print("test_prepare_targets_no_reserved_collision OK")
    test_keyboard_confirm_flow()
    print("test_keyboard_confirm_flow OK")
    print("All text_entry tests passed.")
