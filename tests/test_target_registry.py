"""
Tests for the TargetRegistry addition in core/ssvep_targets.py. Run with:
    python3 tests/test_target_registry.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ssvep_targets import TargetRegistry, UIElement, DEFAULT_FREQUENCY_POOL


def make_elements(n: int, screen_width=1000, screen_height=2000) -> list[UIElement]:
    elements = []
    cols = max(1, int(n ** 0.5))
    for i in range(n):
        row = i // cols
        col = i % cols
        elements.append(UIElement(
            element_id=f"el_{i}", label=f"Button {i}",
            x=(col / cols) * screen_width, y=(row / cols) * screen_height,
            width=50, height=50,
        ))
    return elements


def test_confirm_and_scroll_frequencies_never_overlap_dynamic():
    reg = TargetRegistry()
    reserved = reg.reserved_frequencies()
    dynamic = set(reg.dynamic_pool)
    assert reserved.isdisjoint(dynamic), "Reserved CONFIRM/SCROLL frequencies leaked into the dynamic pool"
    print(f"PASS: reserved frequencies {sorted(reserved)} and dynamic pool "
          f"{sorted(dynamic)} are fully disjoint")


def test_confirm_targets_are_exactly_two_distinct_frequencies():
    reg = TargetRegistry()
    assert len(reg.confirm_targets) == 2
    assert reg.confirm_targets["yes_target"] != reg.confirm_targets["no_target"]
    print("PASS: yes_target and no_target have distinct, stable frequencies")


def test_scroll_targets_get_fast_tier_with_large_pool():
    reg = TargetRegistry()  # default pool has 10 - room for fast tier
    assert "scroll_up_fast" in reg.scroll_targets
    assert "scroll_down_fast" in reg.scroll_targets
    print("PASS: default pool is large enough to include fast-tier scroll markers")


def test_scroll_falls_back_to_single_tier_with_small_pool():
    # Exactly enough for confirm(2) + scroll(2) + dynamic minimum(2) = 6, no room for fast tier
    small_pool = [8.0, 10.0, 12.0, 15.0, 17.0, 20.0]
    reg = TargetRegistry(full_pool=small_pool)
    assert "scroll_up_fast" not in reg.scroll_targets
    assert "scroll_up_slow" in reg.scroll_targets
    assert len(reg.dynamic_pool) >= 2
    print("PASS: small pool correctly falls back to single-tier scroll, preserving dynamic capacity")


def test_too_small_pool_raises_clear_error():
    tiny_pool = [8.0, 10.0, 12.0]  # only 3 - not enough for confirm+scroll+dynamic
    try:
        TargetRegistry(full_pool=tiny_pool)
        assert False, "Should have raised ValueError for undersized pool"
    except ValueError as e:
        print(f"PASS: correctly rejected undersized pool: {e}")


def test_prepare_dynamic_screen_never_uses_reserved_frequencies():
    reg = TargetRegistry()
    elements = make_elements(4)
    groups = reg.prepare_dynamic_screen(elements, 1000, 2000)

    used_frequencies = set()
    for group in groups:
        for target in group.targets:
            used_frequencies.add(target.frequency)

    assert used_frequencies.isdisjoint(reg.reserved_frequencies()), \
        "Dynamic screen preparation used a reserved CONFIRM/SCROLL frequency"
    print("PASS: prepare_dynamic_screen() never assigns a reserved frequency to a UI element")


if __name__ == "__main__":
    test_confirm_and_scroll_frequencies_never_overlap_dynamic()
    test_confirm_targets_are_exactly_two_distinct_frequencies()
    test_scroll_targets_get_fast_tier_with_large_pool()
    test_scroll_falls_back_to_single_tier_with_small_pool()
    test_too_small_pool_raises_clear_error()
    test_prepare_dynamic_screen_never_uses_reserved_frequencies()
    print("\nAll target registry tests passed.")
