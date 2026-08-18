"""
Tests for core/ssvep_targets.py. Run with:
    python3 tests/test_ssvep_targets.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ssvep_targets import (
    UIElement,
    assign_frequencies,
    group_into_regions,
    prepare_screen,
    MAX_SIMULTANEOUS_TARGETS,
    DEFAULT_FREQUENCY_POOL,
)


def make_elements(n: int, screen_width=1000, screen_height=2000) -> list[UIElement]:
    """Spread n fake elements evenly across a fake screen for testing."""
    elements = []
    cols = max(1, int(n ** 0.5))
    for i in range(n):
        row = i // cols
        col = i % cols
        elements.append(UIElement(
            element_id=f"el_{i}",
            label=f"Button {i}",
            x=(col / cols) * screen_width,
            y=(row / cols) * screen_height,
            width=50, height=50,
        ))
    return elements


def test_few_elements_fit_in_single_group():
    elements = make_elements(4)
    groups = prepare_screen(elements, 1000, 2000)

    assert len(groups) == 1
    assert groups[0].group_label == "single_group"
    assert len(groups[0].targets) == 4
    frequencies_used = [t.frequency for t in groups[0].targets]
    assert len(set(frequencies_used)) == 4, "Each element should get a unique frequency"
    print(f"PASS: {len(elements)} elements correctly fit in a single group with unique frequencies")


def test_too_many_elements_split_into_regions():
    n_elements = 15  # more than MAX_SIMULTANEOUS_TARGETS (6)
    elements = make_elements(n_elements)
    groups = prepare_screen(elements, 1000, 2000)

    assert len(groups) > 1, "Should split into multiple regions when exceeding max simultaneous targets"

    total_targets = sum(len(g.targets) for g in groups)
    assert total_targets == n_elements, "No elements should be lost during grouping"

    for group in groups:
        assert len(group.targets) <= MAX_SIMULTANEOUS_TARGETS, \
            f"Group '{group.group_label}' exceeds max simultaneous targets"
        frequencies_in_group = [t.frequency for t in group.targets]
        assert len(set(frequencies_in_group)) == len(frequencies_in_group), \
            f"Group '{group.group_label}' has duplicate frequencies"

    print(f"PASS: {n_elements} elements correctly split into {len(groups)} regions, "
          f"each within the {MAX_SIMULTANEOUS_TARGETS}-target limit, no elements lost")


def test_assign_frequencies_raises_when_pool_too_small():
    elements = make_elements(10)
    try:
        assign_frequencies(elements, frequency_pool=DEFAULT_FREQUENCY_POOL)  # pool has 6
        assert False, "Should have raised ValueError for too many elements"
    except ValueError as e:
        print(f"PASS: correctly raised error for oversized element list: {e}")


def test_exact_boundary_fits_single_group():
    """Exactly MAX_SIMULTANEOUS_TARGETS elements should still be one group, not split."""
    elements = make_elements(MAX_SIMULTANEOUS_TARGETS)
    groups = prepare_screen(elements, 1000, 2000)
    assert len(groups) == 1
    print(f"PASS: exactly {MAX_SIMULTANEOUS_TARGETS} elements (the limit) correctly stays as one group")


if __name__ == "__main__":
    test_few_elements_fit_in_single_group()
    test_too_many_elements_split_into_regions()
    test_assign_frequencies_raises_when_pool_too_small()
    test_exact_boundary_fits_single_group()
    print("\nAll SSVEP target tests passed.")
